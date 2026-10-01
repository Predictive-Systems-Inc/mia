"""Append-only events log with a SHA-256 hash chain.

Guarantees: rows are only ever inserted; the ORM refuses to flush updates or deletes of Event
rows and SQLite triggers abort UPDATE and DELETE statements on the table. Each hash covers the
previous hash plus the canonical JSON of the row, so any edit breaks verify_chain().
"""

import hashlib
import json
from typing import Any

from sqlalchemy import DDL, event
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Session, SQLModel, col, select

from mia.core.models import Actor, Event

GENESIS_HASH = "0" * 64

TRIGGER_SQL = (
    (
        "CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events "
        "BEGIN SELECT RAISE(ABORT, 'events are append-only'); END"
    ),
    (
        "CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events "
        "BEGIN SELECT RAISE(ABORT, 'events are append-only'); END"
    ),
)

for _sql in TRIGGER_SQL:
    event.listen(Event.metadata.tables["events"], "after_create", DDL(_sql))  # type: ignore[no-untyped-call]


class AppendOnlyViolation(RuntimeError):
    """Raised when code tries to update or delete an event row."""


@event.listens_for(OrmSession, "before_flush")
def _refuse_event_changes(session: OrmSession, _ctx: Any, _instances: Any) -> None:
    for obj in list(session.dirty) + list(session.deleted):
        if isinstance(obj, Event):
            raise AppendOnlyViolation("events are append-only; never update or delete them")


def _payload(ev: Event) -> str:
    data = ev.model_dump(mode="json", exclude={"hash", "prev_hash"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, ev: Event) -> str:
    """sha256(prev_hash + canonical payload)."""
    return hashlib.sha256((prev_hash + _payload(ev)).encode()).hexdigest()


def _last_hash(session: Session) -> str:
    last = session.exec(select(Event.hash).order_by(col(Event.id).desc()).limit(1)).first()
    return last or GENESIS_HASH


def snapshot(row: SQLModel | None) -> dict[str, Any] | None:
    """JSON-safe copy of a row for before/after values."""
    return None if row is None else row.model_dump(mode="json")


def emit(
    session: Session,
    action: str,
    entity: SQLModel | tuple[str, str],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: Actor,
    *,
    tool_call_id: str | None = None,
    approval_id: str | None = None,
) -> Event:
    """Append one event, chained to the previous one, in the caller's transaction."""
    if isinstance(entity, tuple):
        entity_type, entity_id = entity
    else:
        entity_type = str(getattr(entity, "__tablename__", type(entity).__name__.lower()))
        entity_id = str(getattr(entity, "id", ""))
    ev = Event(
        branch_id=actor.branch_id,
        actor_type=actor.principal.type,
        actor_id=actor.principal.id,
        on_behalf_of=actor.on_behalf_of.id if actor.on_behalf_of else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        tool_call_id=tool_call_id,
        approval_id=approval_id,
        prev_hash="",
        hash="",
    )
    ev.prev_hash = _last_hash(session)
    ev.hash = compute_hash(ev.prev_hash, ev)
    session.add(ev)
    session.flush()
    return ev


def verify_chain(session: Session) -> bool:
    """True when every event links to its predecessor and its hash matches its content."""
    prev = GENESIS_HASH
    for ev in session.exec(select(Event).order_by(col(Event.id))):
        if ev.prev_hash != prev or compute_hash(prev, ev) != ev.hash:
            return False
        prev = ev.hash
    return True
