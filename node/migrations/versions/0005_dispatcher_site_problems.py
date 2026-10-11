"""dispatcher_site_problems: problems cleaners report from a site

Agent-owned table (rule 9), for the supervisor view and the cannot_access_site and site_problem
intents.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

import mia.core.db

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = sqlmodel.sql.sqltypes.AutoString
T = mia.core.db.TZDateTime


def upgrade() -> None:
    op.create_table(
        "dispatcher_site_problems",
        sa.Column("id", S(length=26), nullable=False),
        sa.Column("created_at", T(length=40), nullable=False),
        sa.Column("updated_at", T(length=40), nullable=False),
        sa.Column("branch_id", S(length=26), nullable=False),
        sa.Column("visit_id", S(), nullable=False),
        sa.Column("person_id", S(), nullable=False),
        sa.Column("kind", S(), nullable=False),
        sa.Column("text", S(), nullable=False),
        sa.Column("status", S(), nullable=False),
        sa.Column("resolved_by", S(), nullable=True),
        sa.Column("resolved_at", T(length=40), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["visit_id"], ["visit.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("dispatcher_site_problems", schema=None) as b:
        b.create_index(b.f("ix_dispatcher_site_problems_branch_id"), ["branch_id"], unique=False)
        b.create_index(b.f("ix_dispatcher_site_problems_person_id"), ["person_id"], unique=False)
        b.create_index(b.f("ix_dispatcher_site_problems_status"), ["status"], unique=False)
        b.create_index(b.f("ix_dispatcher_site_problems_visit_id"), ["visit_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("dispatcher_site_problems", schema=None) as b:
        b.drop_index(b.f("ix_dispatcher_site_problems_visit_id"))
        b.drop_index(b.f("ix_dispatcher_site_problems_status"))
        b.drop_index(b.f("ix_dispatcher_site_problems_person_id"))
        b.drop_index(b.f("ix_dispatcher_site_problems_branch_id"))
    op.drop_table("dispatcher_site_problems")
