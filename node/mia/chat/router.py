"""Chat endpoints: POST /chat (JSON), POST /chat/stream (SSE), and the AG-UI protocol:
POST /ag-ui (start a run), POST /ag-ui/connect (catch up), POST /ag-ui/stop (cancel a run).

The actor comes from the X-Mia-Actor header (a person id). This is a temporary stand-in for
real authentication (Sprint 1); see docs/adr/001-stack.md.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_ai.ui.ag_ui import AGUIAdapter
from sqlmodel import Session
from ulid import ULID

from mia.agents.dispatcher.agent import get_agent
from mia.chat import runs
from mia.chat.blocks import ChatReply
from mia.chat.service import ChatError, run_turn
from mia.core.db import session_scope
from mia.core.ids import new_id
from mia.core.models import Person, Thread

router = APIRouter()
MAX_TEXT = 4000


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    thread_id: str | None = None
    actor_id: str | None = Field(None, description="Person id; the X-Mia-Actor header wins")


def resolve_actor(session: Session, header: str | None, body: str | None = None) -> Person:
    """The acting person. 401 when missing, 403 when unknown or inactive, 400 on mismatch."""
    if header and body and header != body:
        raise HTTPException(400, "X-Mia-Actor and actor_id differ")
    actor_id = header or body
    if not actor_id:
        raise HTTPException(401, "X-Mia-Actor header required")
    person = session.get(Person, actor_id)
    if person is None or person.status != "active":
        raise HTTPException(403, "unknown actor")
    return person


ActorHeader = Annotated[str | None, Header(alias="X-Mia-Actor")]


def get_session() -> Iterator[Session]:
    """One session per request: commits on success, rolls back on error, always closes."""
    with session_scope() as session:
        yield session


# "function": commit before the response is sent, so a failed commit is a 500, not a lost write.
DbSession = Annotated[Session, Depends(get_session, scope="function")]
# "request": the AG-UI stream runs after the route returns; close only when the response ends.
StreamSession = Annotated[Session, Depends(get_session, scope="request")]


async def _turn(session: Session, body: ChatRequest, x_mia_actor: str | None) -> ChatReply:
    person = resolve_actor(session, x_mia_actor, body.actor_id)
    try:
        return await run_turn(session, get_agent(), person, body.text, body.thread_id)
    except ChatError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/chat", response_model=ChatReply)
async def chat(session: DbSession, body: ChatRequest, x_mia_actor: ActorHeader = None) -> ChatReply:
    """One chat turn as JSON for the acting person."""
    return await _turn(session, body, x_mia_actor)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    session: DbSession, body: ChatRequest, x_mia_actor: ActorHeader = None
) -> StreamingResponse:
    """Server-Sent Events: thread, text deltas, then the final blocks, then done."""
    reply = await _turn(session, body, x_mia_actor)

    async def events() -> AsyncIterator[str]:
        yield _sse("thread", {"thread_id": reply.thread_id})
        for block in reply.blocks:
            if block.type == "text":
                for word in block.text.split(" "):
                    yield _sse("delta", {"text": word + " "})
                yield _sse("delta", {"text": "\n"})
        yield _sse("blocks", reply.model_dump(mode="json"))
        yield _sse("done", {})

    return StreamingResponse(events(), media_type="text/event-stream")


class ThreadRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId", min_length=1, max_length=64)


def _own_thread(session: Session, person: Person, thread_id: str) -> Thread | None:
    """The person's thread, or None when no thread has this id. 404 for anyone else's thread."""
    thread = session.get(Thread, thread_id)
    if thread is not None and thread.person_id != person.id:
        raise HTTPException(404, "thread not found")
    return thread


def _stream(chunks: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(chunks, media_type="text/event-stream")


@router.post("/ag-ui")
async def ag_ui(request: Request, session: DbSession, x_mia_actor: ActorHeader = None) -> Response:
    """Start an AG-UI run on the person's thread (threadId: an existing thread or a new ULID).

    The run belongs to the server, not the connection: a dropped stream keeps it going and
    POST /ag-ui/connect rejoins it. 409 when the thread already has a live run.
    """
    person = resolve_actor(session, x_mia_actor)
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(415, "application/json required")
    try:
        run_input = AGUIAdapter.build_run_input(await request.body())
    except ValidationError as exc:
        raise HTTPException(422, "invalid AG-UI run input") from exc
    text = runs.user_text(run_input)
    if not text or len(text) > MAX_TEXT:
        raise HTTPException(422, f"a user message of 1 to {MAX_TEXT} characters is required")
    thread = await asyncio.to_thread(_own_thread, session, person, run_input.thread_id)
    if thread is None:
        try:
            ULID.from_str(run_input.thread_id)
        except ValueError as exc:
            raise HTTPException(422, "threadId of a new thread must be a ULID") from exc
    try:
        run = runs.start(person.id, run_input, text)
    except runs.RunBusy as exc:
        raise HTTPException(409, "thread has a live run") from exc
    return _stream(runs.follow(run))


@router.post("/ag-ui/connect")
async def ag_ui_connect(
    session: DbSession, body: ThreadRef, x_mia_actor: ActorHeader = None
) -> StreamingResponse:
    """Catch up on a thread after a dropped connection: rejoin its live run, or get the stored
    messages and blocks as one snapshot run. 404 for unknown threads and other people's."""
    person = resolve_actor(session, x_mia_actor)
    run = runs.live(body.thread_id)
    if run is not None and run.person_id != person.id:
        raise HTTPException(404, "thread not found")
    thread = await asyncio.to_thread(_own_thread, session, person, body.thread_id)
    if run is not None:
        rows = await asyncio.to_thread(runs.stored_messages, session, body.thread_id)
        return _stream(runs.rejoin(run, runs.messages_snapshot(runs.rejoin_rows(run, rows))))
    if thread is None:
        raise HTTPException(404, "thread not found")
    events = await asyncio.to_thread(runs.snapshot, session, thread, new_id())
    frames = [runs.frame(e.model_dump_json(by_alias=True)) for e in events]

    async def replay() -> AsyncIterator[str]:
        for chunk in frames:
            yield chunk

    return _stream(replay())


@router.post("/ag-ui/stop")
async def ag_ui_stop(
    session: DbSession, body: ThreadRef, x_mia_actor: ActorHeader = None
) -> dict[str, bool]:
    """Cancel the person's live run on the thread; it ends with RUN_FINISHED. 404 when there is
    no live run of this person on the thread."""
    person = resolve_actor(session, x_mia_actor)
    if not runs.stop(body.thread_id, person.id):
        raise HTTPException(404, "no live run")
    return {"stopped": True}
