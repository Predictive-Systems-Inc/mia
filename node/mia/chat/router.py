"""Chat endpoints: POST /chat (JSON), POST /chat/stream (SSE), POST /ag-ui (AG-UI protocol).

The actor comes from the X-Mia-Actor header (a person id). This is a temporary stand-in for
real authentication (Sprint 1); see docs/adr/001-stack.md.
"""

import datetime as dt
import json
from collections.abc import AsyncIterator, Iterator
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai.ui.ag_ui import AGUIAdapter
from sqlmodel import Session

from mia.agents.base import AgentDeps
from mia.agents.dispatcher.agent import MANIFEST, get_agent
from mia.chat.blocks import ChatReply
from mia.chat.service import ChatError, run_turn
from mia.core.db import session_scope
from mia.core.egress import EgressContext, bind_context
from mia.core.models import Actor, Branch, Person
from mia.settings import get_settings

router = APIRouter()


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
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


@router.post("/ag-ui")
async def ag_ui(
    request: Request, session: StreamSession, x_mia_actor: ActorHeader = None
) -> Response:
    """AG-UI endpoint for AG-UI clients. The session closes when the stream ends, even when the
    client disconnects; tool calls and egress commit as they go."""
    person = resolve_actor(session, x_mia_actor)
    branch = session.get(Branch, person.branch_id)
    if branch is None:
        raise HTTPException(500, "person has no branch")
    human = Actor.person(person)
    deps = AgentDeps(
        session=session,
        actor=human.as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=dt.datetime.now(ZoneInfo(branch.timezone)).date(),
        lang=person.language,
        manifest=MANIFEST,
    )
    # Set for the rest of this request task (the stream runs after this function returns).
    bind_context(
        EgressContext(
            session=session,
            actor=deps.actor,
            organisation_id=branch.organisation_id,
            agent_id=MANIFEST.id,
            purpose="chat",
            level=get_settings().MIA_EGRESS_LEVEL,
        )
    )

    return await AGUIAdapter.dispatch_request(request, agent=get_agent(), deps=deps)
