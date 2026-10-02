"""FastAPI app: health, the chat page, chat endpoints and approval decisions."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import col, select

import mia
from mia.agents.dispatcher import cover
from mia.channels import outbox
from mia.chat.channels import NOTIFICATION
from mia.chat.router import ActorHeader, DbSession, resolve_actor
from mia.chat.router import router as chat_router
from mia.core import approvals
from mia.core.db import session_scope, utcnow
from mia.core.events import verify_chain
from mia.core.models import Actor, Message, Person, Thread
from mia.settings import get_settings

STATIC = Path(__file__).resolve().parent.parent / "static"


def tick() -> int:
    """Run due work once (cover confirmation escalation). Returns how many items advanced."""
    with session_scope() as session:
        return cover.process_due(session, utcnow())


async def run_due_work() -> tuple[int, int]:
    """One round of due work: cover escalation, then the channel outbox. Returns both counts."""
    advanced = await asyncio.to_thread(tick)  # sync DB work off the event loop
    sent = await outbox.send_due(utcnow())
    return advanced, sent


async def _ticker(seconds: int) -> None:
    while True:
        await asyncio.sleep(seconds)
        await run_due_work()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Stand-in for the Huey worker: run due work (cover, outbox) every MIA_TICK_SECONDS."""
    seconds = get_settings().MIA_TICK_SECONDS
    task = asyncio.create_task(_ticker(seconds)) if seconds > 0 else None
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title="Mia Node", version=mia.__version__, lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
def health(session: DbSession) -> dict[str, object]:
    return {
        "status": "ok",
        "version": mia.__version__,
        "model": get_settings().MIA_MODEL,
        "events_chain": verify_chain(session),
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


class PersonOut(BaseModel):
    id: str
    name: str
    roles: list[str]
    language: str


@app.get("/persons", response_model=list[PersonOut])
def persons(session: DbSession) -> list[PersonOut]:
    """Demo only: lists people for the chat page's actor picker (no auth in this build)."""
    rows = session.exec(select(Person).order_by(col(Person.id))).all()
    return [PersonOut(id=p.id, name=p.name, roles=p.roles, language=p.language) for p in rows]


class DecideRequest(BaseModel):
    outcome: Literal["approved", "rejected"]
    reason: str | None = None


class DecideResponse(BaseModel):
    approval_id: str
    status: str
    decided_by: str | None


@app.post("/approvals/{approval_id}/decide", response_model=DecideResponse)
def decide(
    session: DbSession, approval_id: str, body: DecideRequest, x_mia_actor: ActorHeader = None
) -> DecideResponse:
    """Stand-in for the approvals inbox. Decisions come from the authenticated app channel."""
    person = resolve_actor(session, x_mia_actor)
    try:
        row = approvals.decide(
            session, approval_id, Actor.person(person), body.outcome, body.reason, channel="app"
        )
    except approvals.ApprovalError as exc:
        raise HTTPException(403, str(exc)) from exc
    return DecideResponse(approval_id=row.id, status=row.status, decided_by=row.decided_by)


class NotificationOut(BaseModel):
    id: str
    thread_id: str
    blocks: list[dict[str, Any]]


@app.get("/notifications", response_model=list[NotificationOut])
def notifications(
    session: DbSession, after: str = "", x_mia_actor: ActorHeader = None
) -> list[NotificationOut]:
    """Proactive messages for the acting person, oldest first, after a message id."""
    person = resolve_actor(session, x_mia_actor)
    stmt = (
        select(Message)
        .join(Thread, col(Thread.id) == col(Message.thread_id))
        .where(Thread.person_id == person.id)
        .where(Message.role == NOTIFICATION)
        .where(col(Message.id) > after)
        .order_by(col(Message.id))
    )
    return [
        NotificationOut(id=m.id, thread_id=m.thread_id, blocks=m.blocks) for m in session.exec(stmt)
    ]
