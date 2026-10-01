"""Write services. The only place rows are added or changed, and every write emits an event.

Agents, tools and API routes never touch tables directly: they call these functions (or the
domain services built on them in mia/core and mia/templates).
"""

from typing import Any

from sqlmodel import Session, SQLModel

from mia.core import events
from mia.core.db import utcnow
from mia.core.models import Actor


def _table(row: SQLModel) -> str:
    return str(getattr(row, "__tablename__", type(row).__name__.lower()))


def insert[T: SQLModel](
    session: Session,
    row: T,
    actor: Actor,
    *,
    action: str | None = None,
    tool_call_id: str | None = None,
    approval_id: str | None = None,
) -> T:
    """Insert a row and emit `<table>.created` (or `action`) with the new values."""
    session.add(row)
    session.flush()
    events.emit(
        session,
        action or f"{_table(row)}.created",
        row,
        None,
        events.snapshot(row),
        actor,
        tool_call_id=tool_call_id,
        approval_id=approval_id,
    )
    return row


def update[T: SQLModel](
    session: Session,
    row: T,
    changes: dict[str, Any],
    actor: Actor,
    *,
    action: str | None = None,
    tool_call_id: str | None = None,
    approval_id: str | None = None,
) -> T:
    """Apply changes to a row and emit `<table>.updated` (or `action`) with before and after."""
    before = events.snapshot(row)
    for key, value in changes.items():
        if not hasattr(row, key):
            raise AttributeError(f"{type(row).__name__} has no field {key!r}")
        setattr(row, key, value)
    if hasattr(row, "updated_at"):
        row.updated_at = utcnow()
    session.add(row)
    session.flush()
    events.emit(
        session,
        action or f"{_table(row)}.updated",
        row,
        before,
        events.snapshot(row),
        actor,
        tool_call_id=tool_call_id,
        approval_id=approval_id,
    )
    return row
