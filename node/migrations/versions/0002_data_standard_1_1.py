"""data standard 1.1: employee data in core, geocoding cache, cover requests

Decisions D6 to D10 (docs/decisions.md), ADR 005. Availability and working-hour limits move
from the cleaning template to core (renamed, data kept); people get a home base; locations get
coordinates; geocode_cache and dispatcher_cover_requests are new.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

import mia.core.db

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOVED = {"cleaning_availability": "availability", "cleaning_work_limits": "work_limits"}


def _rename(old: str, new: str, unique_person: bool) -> None:
    with op.batch_alter_table(old) as batch_op:
        batch_op.drop_index(f"ix_{old}_branch_id")
        batch_op.drop_index(f"ix_{old}_person_id")
    op.rename_table(old, new)
    with op.batch_alter_table(new) as batch_op:
        batch_op.create_index(f"ix_{new}_branch_id", ["branch_id"], unique=False)
        batch_op.create_index(f"ix_{new}_person_id", ["person_id"], unique=unique_person)


def upgrade() -> None:
    _rename("cleaning_availability", "availability", unique_person=False)
    _rename("cleaning_work_limits", "work_limits", unique_person=True)

    with op.batch_alter_table("person") as batch_op:
        batch_op.add_column(
            sa.Column(
                "home_address",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(sa.Column("home_lat", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("home_lon", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("accepts_calls", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    with op.batch_alter_table("location") as batch_op:
        batch_op.add_column(sa.Column("lat", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("lon", sa.Float(), nullable=True))

    op.create_table(
        "geocode_cache",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("created_at", mia.core.db.TZDateTime(), nullable=False),
        sa.Column("updated_at", mia.core.db.TZDateTime(), nullable=False),
        sa.Column("branch_id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("address", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("geocode_cache") as batch_op:
        batch_op.create_index("ix_geocode_cache_address", ["address"], unique=False)
        batch_op.create_index("ix_geocode_cache_branch_id", ["branch_id"], unique=False)

    op.create_table(
        "dispatcher_cover_requests",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("created_at", mia.core.db.TZDateTime(), nullable=False),
        sa.Column("updated_at", mia.core.db.TZDateTime(), nullable=False),
        sa.Column("branch_id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("visit_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("candidate_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("replace_person_ids", sa.JSON(), nullable=False),
        sa.Column("queue", sa.JSON(), nullable=False),
        sa.Column("instructed_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("approval_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("stage", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("next_action_at", mia.core.db.TZDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["visit_id"], ["visit.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("dispatcher_cover_requests") as batch_op:
        for column in ("branch_id", "candidate_id", "next_action_at", "visit_id"):
            batch_op.create_index(f"ix_dispatcher_cover_requests_{column}", [column], unique=False)


def downgrade() -> None:
    op.drop_table("dispatcher_cover_requests")
    op.drop_table("geocode_cache")
    with op.batch_alter_table("location") as batch_op:
        batch_op.drop_column("lon")
        batch_op.drop_column("lat")
    with op.batch_alter_table("person") as batch_op:
        batch_op.drop_column("accepts_calls")
        batch_op.drop_column("home_lon")
        batch_op.drop_column("home_lat")
        batch_op.drop_column("home_address")
    for old, new in MOVED.items():
        with op.batch_alter_table(new) as batch_op:
            batch_op.drop_index(f"ix_{new}_branch_id")
            batch_op.drop_index(f"ix_{new}_person_id")
        op.rename_table(new, old)
        with op.batch_alter_table(old) as batch_op:
            batch_op.create_index(f"ix_{old}_branch_id", ["branch_id"], unique=False)
            batch_op.create_index(f"ix_{old}_person_id", ["person_id"], unique=new == "work_limits")
