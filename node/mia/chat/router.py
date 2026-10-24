"""Chat endpoints: POST /chat (JSON), POST /chat/stream (SSE), and the AG-UI protocol:
POST /ag-ui (start a run), POST /ag-ui/connect (catch up), POST /ag-ui/stop (cancel a run).

The actor is the signed-in person from `PersonAuth` (ADR 011).
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_ai.ui.ag_ui import AGUIAdapter
from sqlmodel import Session
from ulid import ULID

from mia.agents.shift_supervisor.agent import get_agent
from mia.api.deps import AuthContext, DbSession, PersonAuth
from mia.chat import features, runs
from mia.chat.blocks import ChatReply
from mia.chat.service import ChatError, run_turn
from mia.core.ids import new_id
from mia.core.models import Message, Person, Thread
from mia.core.rbac import PermissionDenied, get_rbac

router = APIRouter()
FEATURE_REQUESTS = features.RESOURCE
MAX_TEXT = 4000


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    thread_id: str | None = None


def _person(auth: AuthContext) -> Person:
    assert auth.person is not None  # PersonAuth guarantees it
    return auth.person


async def _turn(session: Session, body: ChatRequest, auth: AuthContext) -> ChatReply:
    person = _person(auth)
    try:
        return await run_turn(session, get_agent(), person, body.text, body.thread_id)
    except ChatError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/chat", response_model=ChatReply)
async def chat(session: DbSession, body: ChatRequest, auth: PersonAuth) -> ChatReply:
    """One chat turn as JSON for the acting person."""
    return await _turn(session, body, auth)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(session: DbSession, body: ChatRequest, auth: PersonAuth) -> StreamingResponse:
    """Server-Sent Events: thread, text deltas, then the final blocks, then done."""
    reply = await _turn(session, body, auth)

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
async def ag_ui(request: Request, session: DbSession, auth: PersonAuth) -> Response:
    """Start an AG-UI run on the person's thread (threadId: an existing thread or a new ULID).

    The run belongs to the server, not the connection: a dropped stream keeps it going and
    POST /ag-ui/connect rejoins it. 409 when the thread already has a live run.
    """
    person = _person(auth)
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
async def ag_ui_connect(session: DbSession, body: ThreadRef, auth: PersonAuth) -> StreamingResponse:
    """Catch up on a thread after a dropped connection: rejoin its live run, or get the stored
    messages and blocks as one snapshot run. 404 for unknown threads and other people's."""
    person = _person(auth)
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
async def ag_ui_stop(session: DbSession, body: ThreadRef, auth: PersonAuth) -> dict[str, bool]:
    """Cancel the person's live run on the thread; it ends with RUN_FINISHED. 404 when there is
    no live run of this person on the thread."""
    person = _person(auth)
    if not runs.stop(body.thread_id, person.id):
        raise HTTPException(404, "no live run")
    return {"stopped": True}


class FeatureRequestIn(BaseModel):
    text: str = Field(min_length=1, max_length=features.MAX_TEXT)
    failed_message_id: str | None = None


@router.post("/feature-requests")
def feature_request(session: DbSession, body: FeatureRequestIn, auth: PersonAuth) -> dict[str, str]:
    """A feature request from the signed-in person (spec teach-mia 4b): rbac write on
    data:feature_requests (every staff role), then feature.requested. A failed message is
    kept only when it is the person's own."""
    person = _person(auth)
    try:
        get_rbac().require(auth.actor, FEATURE_REQUESTS, "write", session=session)
    except PermissionDenied as exc:
        session.commit()  # keep the rbac.deny event
        raise HTTPException(403, "not allowed") from exc
    failed = session.get(Message, body.failed_message_id) if body.failed_message_id else None
    if failed is not None and failed.sender_id != person.id:
        failed = None
    ev = features.request(session, person, body.text, auth.actor, failed=failed)
    session.commit()
    return {"id": ev.id}
