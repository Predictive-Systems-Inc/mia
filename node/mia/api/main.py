"""FastAPI app: health, the chat page, chat endpoints and approval decisions."""

import asyncio
import contextlib
import datetime as dt
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, col, select

import mia
from mia.agents.customer_service import public
from mia.agents.registry import AGENTS, load_roles
from mia.api.auth import router as auth_router
from mia.api.deps import DbSession, PersonAuth, check_mode
from mia.api.schedule import router as schedule_router
from mia.api.sim import router as sim_router
from mia.api.supervisor import router as supervisor_router
from mia.api.timesheets import router as timesheets_router
from mia.channels import inbound as channel_service
from mia.channels import outbox, registry
from mia.channels.router import router as channels_router
from mia.channels.setup import register_configured
from mia.chat import deferred, proposals
from mia.chat.channels import NOTIFICATION
from mia.chat.router import router as chat_router
from mia.core import approvals, scheduling
from mia.core.db import session_scope, utcnow
from mia.core.events import verify_chain
from mia.core.models import ChannelOutbox, Message, Person, Thread
from mia.core.rbac import PermissionDenied
from mia.settings import get_settings
from mia.skills import runtime

STATIC = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger(__name__)


def tick() -> int:
    """Run every registered agent's due work once, each in its own session so one agent's
    failure or rollback never touches another's (a failure is logged and the next agent
    runs). Returns how many items advanced."""
    total = 0
    for spec in AGENTS.values():
        if spec.run_due is None:
            continue
        try:
            with session_scope() as session:
                total += spec.run_due(session, utcnow())
        except Exception:
            log.exception("due work of %s failed; the other agents still run", spec.id)
    return total


def _generate_visits() -> int:
    with session_scope() as session:
        return scheduling.generate_due(session, utcnow())


async def run_due_work() -> tuple[int, int]:
    """One round of due work: visit generation (once a day), cover escalation, the channel
    outbox and customer replies, then turns deferred while Jev was unreachable. Returns the
    cover and outbox counts."""
    generated = await asyncio.to_thread(_generate_visits)
    if generated:
        log.info("generated %d visit(s)", generated)
    advanced = await asyncio.to_thread(tick)  # sync DB work off the event loop
    stale = utcnow() - dt.timedelta(minutes=1)
    for inbound_id in await asyncio.to_thread(channel_service.pending_inbound, stale):
        await channel_service.handle_inbound(inbound_id)  # lost to a restart before handling
    sent = await outbox.send_due(utcnow())  # on-demand channels (the simulator) are left alone
    await public.send_pending(utcnow())  # customer replies (customer_service)
    resumed = await deferred.retry_due(utcnow())  # turns that waited for Jev
    if resumed:
        log.info("closed %d deferred turn(s)", resumed)
    proposed = await proposals.run_due(utcnow())  # the nightly phrase proposals (teach-Mia)
    if proposed:
        log.info("proposed %d phrase(s)", proposed)
    return advanced, sent


async def _ticker(seconds: int) -> None:
    while True:
        await asyncio.sleep(seconds)
        try:
            await run_due_work()
        except Exception:
            log.exception("due work failed; retrying next tick")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Load the agents' roles, register configured channels, then run due work (cover,
    outbox) every MIA_TICK_SECONDS (a stand-in for the Huey worker)."""
    check_mode(get_settings())
    load_roles()  # agent roles for approvals decided outside any turn
    register_configured(get_settings())
    seconds = get_settings().MIA_TICK_SECONDS
    task = asyncio.create_task(_ticker(seconds)) if seconds > 0 else None
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title="Mia Node", version=mia.__version__, lifespan=lifespan)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(schedule_router)
app.include_router(supervisor_router)
app.include_router(timesheets_router)
app.include_router(channels_router)
app.include_router(sim_router)  # dev and loopback only


@app.get("/health")
def health(request: Request, session: DbSession) -> dict[str, object]:
    """Full status on the local network; status only when reached through the tunnel."""
    if "cf-ray" in request.headers:
        return {"status": "ok"}
    return {
        "status": "ok",
        "version": mia.__version__,
        "model": get_settings().MIA_MODEL,
        "auth_mode": get_settings().MIA_AUTH_MODE,
        "events_chain": verify_chain(session),
        "channels": channel_health(session),
        "skills": runtime.health(),
    }


def channel_health(session: Session) -> dict[str, dict[str, object]]:
    """Each enabled channel with its failed messages in the last 24 hours."""
    since = utcnow() - dt.timedelta(hours=24)
    out: dict[str, dict[str, object]] = {}
    for adapter in registry.enabled():
        failed = session.exec(
            select(ChannelOutbox)
            .where(ChannelOutbox.channel == adapter.channel_id)
            .where(ChannelOutbox.status == "failed")
            .where(col(ChannelOutbox.updated_at) >= since)
        ).all()
        out[adapter.channel_id] = {"enabled": True, "failed_24h": len(failed)}
    return out


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
    """Dev mode only: lists people for the chat page's actor picker."""
    if get_settings().MIA_AUTH_MODE != "dev":
        raise HTTPException(404, "not found")
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
    session: DbSession, approval_id: str, body: DecideRequest, auth: PersonAuth
) -> DecideResponse:
    """Stand-in for the approvals inbox. The channel, assurance level and step-up come from
    the session; 403 `step_up_required` asks the app for the PIN."""
    try:
        row = approvals.decide(
            session,
            approval_id,
            auth.actor,
            body.outcome,
            body.reason,
            channel=auth.channel,
            aal="aal2" if auth.via == "header" else auth.aal,
            # Dev mode has no session to step up; the loopback header counts as fresh.
            stepped_up_at=utcnow() if auth.via == "header" else auth.stepped_up_at,
        )
    except approvals.StepUpRequired as exc:
        raise HTTPException(403, "step_up_required") from exc
    except approvals.ApprovalError as exc:
        raise HTTPException(403, str(exc)) from exc
    except PermissionDenied as exc:  # a handler re-ran a tool the requester may not run
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:  # the handler refused: its row changed since the request
        reason = str(getattr(exc, "reason", None) or exc)
        session.rollback()  # the decision and any handler write
        with contextlib.suppress(approvals.ApprovalError):  # no open request to close
            approvals.close_refused(session, approval_id, auth.actor, reason)
            session.commit()  # before the 409, so the request is closed with its reason
        raise HTTPException(409, reason) from exc
    return DecideResponse(approval_id=row.id, status=row.status, decided_by=row.decided_by)


class NotificationOut(BaseModel):
    id: str
    thread_id: str
    blocks: list[dict[str, Any]]


@app.get("/notifications", response_model=list[NotificationOut])
def notifications(session: DbSession, auth: PersonAuth, after: str = "") -> list[NotificationOut]:
    """Proactive messages for the acting person, oldest first, after a message id."""
    assert auth.person is not None
    person = auth.person
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
