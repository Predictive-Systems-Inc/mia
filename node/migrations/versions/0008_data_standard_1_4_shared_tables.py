"""data standard 1.4: the dispatcher's tables become shared tables

absences, cover_requests, timesheets and incidents move to core; checklist ticks move to the
cleaning template. A rename in place: rows, columns and constraints are kept, indexes are
renamed to match the new table names.

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


def upgrade() -> None:
    for old, new in TABLES.items():
        _rename(old, new)


def downgrade() -> None:
    for old, new in TABLES.items():
        _rename(new, old)
