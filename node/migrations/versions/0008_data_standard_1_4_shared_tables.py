"""data standard 1.4: the dispatcher's tables become shared tables

absences, cover_requests, timesheets and incidents move to core; checklist ticks move to the
cleaning template. A rename in place: rows, columns and constraints are kept, indexes are
renamed to match the new table names. The agent id in chat threads, chat messages and approvals
follows (code looks those up by the new id); events are append-only and stay as written.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = {
    "dispatcher_absences": "absences",
    "dispatcher_cover_requests": "cover_requests",
    "dispatcher_timesheets": "timesheets",
    "dispatcher_site_problems": "incidents",
    "dispatcher_checklist_ticks": "cleaning_checklist_ticks",
}


def _rename(old: str, new: str) -> None:
    """Drop the old ix_<old>_* indexes, rename the table, create ix_<new>_* on the same columns."""
    indexes = sa.inspect(op.get_bind()).get_indexes(old)
    with op.batch_alter_table(old) as b:
        for ix in indexes:
            b.drop_index(ix["name"])
    op.rename_table(old, new)
    with op.batch_alter_table(new) as b:
        for ix in indexes:
            name = str(ix["name"]).replace(f"ix_{old}_", f"ix_{new}_", 1)
            b.create_index(name, list(ix["column_names"]), unique=bool(ix["unique"]))


def _agent_id(old: str, new: str) -> None:
    """Rewrite the agent id (and the '<id>.' prefix of approval types) in non-event rows."""
    conn = op.get_bind()
    params = {
        "old": old,
        "new": new,
        "old_role": f"agent.{old}",
        "new_role": f"agent.{new}",
        "like": f"{old}.%",
        "cut": len(old) + 2,
    }
    for table in ("chat_threads", "chat_messages"):
        conn.execute(sa.text(f"UPDATE {table} SET agent_id = :new WHERE agent_id = :old"), params)
    conn.execute(
        sa.text(
            "UPDATE chat_messages SET sender_id = :new_role WHERE role = 'assistant' AND sender_id = :old_role"
        ),
        params,
    )
    conn.execute(
        sa.text(
            "UPDATE approval SET type = :new || '.' || substr(type, :cut) WHERE type LIKE :like"
        ),
        params,
    )
    conn.execute(
        sa.text(
            "UPDATE approval SET requester_id = :new_role "
            "WHERE requester_type = 'agent' AND requester_id = :old_role"
        ),
        params,
    )


def upgrade() -> None:
    for old, new in TABLES.items():
        _rename(old, new)
    _agent_id("dispatcher", "shift_supervisor")


def downgrade() -> None:
    _agent_id("shift_supervisor", "dispatcher")
    for old, new in TABLES.items():
        _rename(new, old)
