"""dispatcher_checklist_ticks: ticked checklist items per visit

Agent-owned table (rule 9) for the checklist intent over chat.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

import mia.core.db

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = sqlmodel.sql.sqltypes.AutoString
T = mia.core.db.TZDateTime


def upgrade() -> None:
    op.create_table(
        "dispatcher_checklist_ticks",
        sa.Column("id", S(length=26), nullable=False),
        sa.Column("created_at", T(length=40), nullable=False),
        sa.Column("updated_at", T(length=40), nullable=False),
        sa.Column("branch_id", S(length=26), nullable=False),
        sa.Column("visit_id", S(), nullable=False),
        sa.Column("item", S(), nullable=False),
        sa.Column("ticked_by", S(), nullable=False),
        sa.Column("ticked_at", T(length=40), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.ForeignKeyConstraint(["visit_id"], ["visit.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("visit_id", "item"),
    )
    with op.batch_alter_table("dispatcher_checklist_ticks", schema=None) as b:
        b.create_index(b.f("ix_dispatcher_checklist_ticks_branch_id"), ["branch_id"], unique=False)
        b.create_index(b.f("ix_dispatcher_checklist_ticks_visit_id"), ["visit_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("dispatcher_checklist_ticks", schema=None) as b:
        b.drop_index(b.f("ix_dispatcher_checklist_ticks_visit_id"))
        b.drop_index(b.f("ix_dispatcher_checklist_ticks_branch_id"))
    op.drop_table("dispatcher_checklist_ticks")
