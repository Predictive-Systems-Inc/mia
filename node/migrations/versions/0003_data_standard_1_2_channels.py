"""data standard 1.2: channel identities, link codes, outbox and inbound

Decision D13, ADR 007. Channel tables for the pluggable channel layer (WhatsApp first):
identities linked by one-time code, link codes stored as HMACs, link attempts for the lockout,
the outbound queue and the de-duplicated inbound log.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

import mia.core.db

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_link_attempts",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("created_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("updated_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("channel", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("address", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("channel_link_attempts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_channel_link_attempts_address"), ["address"], unique=False
        )

    op.create_table(
        "channel_inbound",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("created_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("updated_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("channel", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("channel_message_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("address", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("branch_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("person_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branch.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel", "channel_message_id"),
    )
    with op.batch_alter_table("channel_inbound", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_channel_inbound_status"), ["status"], unique=False)

    op.create_table(
        "channel_identities",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("created_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("updated_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("branch_id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("person_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("channel", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("address", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("verified_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("consent_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("last_inbound_at", mia.core.db.TZDateTime(length=40), nullable=True),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branch.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("channel_identities", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_channel_identities_address"), ["address"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_channel_identities_branch_id"), ["branch_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_channel_identities_channel"), ["channel"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_channel_identities_person_id"), ["person_id"], unique=False
        )

    op.create_table(
        "channel_link_codes",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("created_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("updated_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("branch_id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("person_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("code_hmac", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("purpose", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expires_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("used_at", mia.core.db.TZDateTime(length=40), nullable=True),
        sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branch.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hmac"),
    )
    with op.batch_alter_table("channel_link_codes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_channel_link_codes_branch_id"), ["branch_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_channel_link_codes_person_id"), ["person_id"], unique=False
        )

    op.create_table(
        "channel_outbox",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("created_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("updated_at", mia.core.db.TZDateTime(length=40), nullable=False),
        sa.Column("branch_id", sqlmodel.sql.sqltypes.AutoString(length=26), nullable=False),
        sa.Column("person_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("channel", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("address", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("send_after", mia.core.db.TZDateTime(length=40), nullable=True),
        sa.Column("channel_message_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_code", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branch.id"],
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    with op.batch_alter_table("channel_outbox", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_channel_outbox_branch_id"), ["branch_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_channel_outbox_channel_message_id"), ["channel_message_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_channel_outbox_person_id"), ["person_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_channel_outbox_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("channel_outbox", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_channel_outbox_status"))
        batch_op.drop_index(batch_op.f("ix_channel_outbox_person_id"))
        batch_op.drop_index(batch_op.f("ix_channel_outbox_channel_message_id"))
        batch_op.drop_index(batch_op.f("ix_channel_outbox_branch_id"))

    op.drop_table("channel_outbox")
    with op.batch_alter_table("channel_link_codes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_channel_link_codes_person_id"))
        batch_op.drop_index(batch_op.f("ix_channel_link_codes_branch_id"))

    op.drop_table("channel_link_codes")
    with op.batch_alter_table("channel_identities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_channel_identities_person_id"))
        batch_op.drop_index(batch_op.f("ix_channel_identities_channel"))
        batch_op.drop_index(batch_op.f("ix_channel_identities_branch_id"))
        batch_op.drop_index(batch_op.f("ix_channel_identities_address"))

    op.drop_table("channel_identities")
    with op.batch_alter_table("channel_inbound", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_channel_inbound_status"))

    op.drop_table("channel_inbound")
    with op.batch_alter_table("channel_link_attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_channel_link_attempts_address"))

    op.drop_table("channel_link_attempts")
