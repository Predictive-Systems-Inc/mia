"""dispatcher_timesheets: one person's time on one visit

Agent-owned table (rule 9) until Q20 decides where timesheets live.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

import mia.core.db

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = sqlmodel.sql.sqltypes.AutoString
T = mia.core.db.TZDateTime


def upgrade() -> None:
    op.create_table(
        "dispatcher_timesheets",
        sa.Column("id", S(length=26), nullable=False),
        sa.Column("created_at", T(length=40), nullable=False),
        sa.Column("updated_at", T(length=40), nullable=False),
        sa.Column("branch_id", S(length=26), nullable=False),
        sa.Column("visit_id", S(), nullable=False),
        sa.Column("person_id", S(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start", T(length=40), nullable=False),
        sa.Column("end", T(length=40), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("source", S(), nullable=False),
        sa.Column("status", S(), nullable=False),
        sa.Column("entered_by", S(), nullable=False),
        sa.Column("note", S(), nullable=False),
        sa.Column("approved_by", S(), nullable=True),
        sa.Column("approved_at", T(length=40), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.ForeignKeyConstraint(["visit_id"], ["visit.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("visit_id", "person_id"),
    )
    with op.batch_alter_table("dispatcher_timesheets", schema=None) as b:
        b.create_index(b.f("ix_dispatcher_timesheets_branch_id"), ["branch_id"], unique=False)
        b.create_index(b.f("ix_dispatcher_timesheets_visit_id"), ["visit_id"], unique=False)
        b.create_index(b.f("ix_dispatcher_timesheets_person_id"), ["person_id"], unique=False)
        b.create_index(b.f("ix_dispatcher_timesheets_date"), ["date"], unique=False)
        b.create_index(b.f("ix_dispatcher_timesheets_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("dispatcher_timesheets", schema=None) as b:
        b.drop_index(b.f("ix_dispatcher_timesheets_status"))
        b.drop_index(b.f("ix_dispatcher_timesheets_date"))
        b.drop_index(b.f("ix_dispatcher_timesheets_person_id"))
        b.drop_index(b.f("ix_dispatcher_timesheets_visit_id"))
        b.drop_index(b.f("ix_dispatcher_timesheets_branch_id"))
    op.drop_table("dispatcher_timesheets")
