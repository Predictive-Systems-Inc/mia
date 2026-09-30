"""FastAPI app: health, the chat page, chat endpoints and approval decisions."""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import col, select

import mia
from mia.chat.router import ActorHeader, resolve_actor
from mia.chat.router import router as chat_router
from mia.core import approvals
from mia.core.db import session_scope
from mia.core.events import verify_chain
from mia.core.models import Actor, Person
from mia.settings import get_settings

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Mia Node", version=mia.__version__)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, object]:
    with session_scope() as session:
        chain_ok = verify_chain(session)
    return {
        "status": "ok",
        "version": mia.__version__,
        "model": get_settings().MIA_MODEL,
        "events_chain": chain_ok,
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
def persons() -> list[PersonOut]:
    """Demo only: lists people for the chat page's actor picker (no auth in this build)."""
    with session_scope() as session:
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
    approval_id: str, body: DecideRequest, x_mia_actor: ActorHeader = None
) -> DecideResponse:
    """Stand-in for the approvals inbox. Decisions come from the authenticated app channel."""
    with session_scope() as session:
        person = resolve_actor(session, x_mia_actor)
        try:
            row = approvals.decide(
                session, approval_id, Actor.person(person), body.outcome, body.reason, channel="app"
            )
        except approvals.ApprovalError as exc:
            raise HTTPException(403, str(exc)) from exc
        return DecideResponse(approval_id=row.id, status=row.status, decided_by=row.decided_by)
