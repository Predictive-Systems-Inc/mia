"""data standard 1.3: authentication

Decision D17, ADR 011. channel_link_codes becomes auth_codes (plus address, tries) and
channel_link_attempts becomes auth_attempts (kind, key). New: auth_credentials, auth_devices,
auth_sessions, auth_clients.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

import mia.core.db

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = sqlmodel.sql.sqltypes.AutoString
T = mia.core.db.TZDateTime


def _stamped() -> list[sa.Column[object]]:
    return [
        sa.Column("id", S(length=26), nullable=False),
        sa.Column("created_at", T(length=40), nullable=False),
        sa.Column("updated_at", T(length=40), nullable=False),
        sa.Column("branch_id", S(length=26), nullable=False),
    ]


def upgrade() -> None:
    op.rename_table("channel_link_codes", "auth_codes")
    with op.batch_alter_table("auth_codes", schema=None) as b:
        b.drop_index(b.f("ix_channel_link_codes_branch_id"))
        b.drop_index(b.f("ix_channel_link_codes_person_id"))
        b.add_column(sa.Column("address", S(), nullable=True))
        b.add_column(sa.Column("tries", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("auth_codes", schema=None) as b:
        b.alter_column("tries", server_default=None)
        b.create_index(b.f("ix_auth_codes_branch_id"), ["branch_id"], unique=False)
        b.create_index(b.f("ix_auth_codes_person_id"), ["person_id"], unique=False)

    op.rename_table("channel_link_attempts", "auth_attempts")
    with op.batch_alter_table("auth_attempts", schema=None) as b:
        b.drop_index(b.f("ix_channel_link_attempts_address"))
        b.add_column(sa.Column("kind", S(), nullable=False, server_default="link_code"))
        b.add_column(sa.Column("key", S(), nullable=False, server_default=""))
    op.execute("UPDATE auth_attempts SET key = channel || ':' || address || '@-'")
    with op.batch_alter_table("auth_attempts", schema=None) as b:
        b.drop_column("channel")
        b.drop_column("address")
        b.alter_column("kind", server_default=None)
        b.alter_column("key", server_default=None)
        b.create_index(b.f("ix_auth_attempts_key"), ["key"], unique=False)

    op.create_table(
        "auth_credentials",
        *_stamped(),
        sa.Column("person_id", S(), nullable=False),
        sa.Column("kind", S(), nullable=False),
        sa.Column("login", S(), nullable=True),
        sa.Column("secret_hash", S(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("status", S(), nullable=False),
        sa.Column("last_used_at", T(length=40), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login"),
    )
    with op.batch_alter_table("auth_credentials", schema=None) as b:
        b.create_index(b.f("ix_auth_credentials_branch_id"), ["branch_id"], unique=False)
        b.create_index(b.f("ix_auth_credentials_person_id"), ["person_id"], unique=False)

    op.create_table(
        "auth_devices",
        *_stamped(),
        sa.Column("person_id", S(), nullable=False),
        sa.Column("kind", S(), nullable=False),
        sa.Column("name", S(), nullable=False),
        sa.Column("secret_hash", S(), nullable=True),
        sa.Column("status", S(), nullable=False),
        sa.Column("last_seen_at", T(length=40), nullable=True),
        sa.Column("revoked_at", T(length=40), nullable=True),
        sa.Column("revoked_by", S(), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("auth_devices", schema=None) as b:
        b.create_index(b.f("ix_auth_devices_branch_id"), ["branch_id"], unique=False)
        b.create_index(b.f("ix_auth_devices_person_id"), ["person_id"], unique=False)

    op.create_table(
        "auth_sessions",
        *_stamped(),
        sa.Column("subject_type", S(), nullable=False),
        sa.Column("subject_id", S(), nullable=False),
        sa.Column("device_id", S(), nullable=True),
        sa.Column("method", S(), nullable=False),
        sa.Column("aal", S(), nullable=False),
        sa.Column("access_hash", S(), nullable=False),
        sa.Column("access_expires_at", T(length=40), nullable=False),
        sa.Column("refresh_hash", S(), nullable=True),
        sa.Column("prev_refresh_hash", S(), nullable=True),
        sa.Column("refresh_expires_at", T(length=40), nullable=True),
        sa.Column("absolute_expires_at", T(length=40), nullable=True),
        sa.Column("stepped_up_at", T(length=40), nullable=True),
        sa.Column("status", S(), nullable=False),
        sa.Column("ip", S(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["auth_devices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("access_hash"),
        sa.UniqueConstraint("refresh_hash"),
    )
    with op.batch_alter_table("auth_sessions", schema=None) as b:
        b.create_index(b.f("ix_auth_sessions_branch_id"), ["branch_id"], unique=False)
        b.create_index(b.f("ix_auth_sessions_subject_id"), ["subject_id"], unique=False)

    op.create_table(
        "auth_clients",
        *_stamped(),
        sa.Column("name", S(), nullable=False),
        sa.Column("client_id", S(), nullable=False),
        sa.Column("secret_hash", S(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("status", S(), nullable=False),
        sa.Column("expires_at", T(length=40), nullable=True),
        sa.Column("created_by", S(), nullable=False),
        sa.Column("last_used_at", T(length=40), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    with op.batch_alter_table("auth_clients", schema=None) as b:
        b.create_index(b.f("ix_auth_clients_branch_id"), ["branch_id"], unique=False)


def downgrade() -> None:
    for table in ("auth_clients", "auth_sessions", "auth_devices", "auth_credentials"):
        op.drop_table(table)

    with op.batch_alter_table("auth_attempts", schema=None) as b:
        b.drop_index(b.f("ix_auth_attempts_key"))
        b.add_column(sa.Column("channel", S(), nullable=False, server_default=""))
        b.add_column(sa.Column("address", S(), nullable=False, server_default=""))
    op.execute(
        "UPDATE auth_attempts SET channel = substr(key, 1, instr(key, ':') - 1), "
        "address = substr(key, instr(key, ':') + 1, instr(key, '@') - instr(key, ':') - 1)"
    )
    with op.batch_alter_table("auth_attempts", schema=None) as b:
        b.drop_column("kind")
        b.drop_column("key")
        b.alter_column("channel", server_default=None)
        b.alter_column("address", server_default=None)
    op.rename_table("auth_attempts", "channel_link_attempts")
    with op.batch_alter_table("channel_link_attempts", schema=None) as b:
        b.create_index(b.f("ix_channel_link_attempts_address"), ["address"], unique=False)

    with op.batch_alter_table("auth_codes", schema=None) as b:
        b.drop_index(b.f("ix_auth_codes_branch_id"))
        b.drop_index(b.f("ix_auth_codes_person_id"))
        b.drop_column("address")
        b.drop_column("tries")
    op.rename_table("auth_codes", "channel_link_codes")
    with op.batch_alter_table("channel_link_codes", schema=None) as b:
        b.create_index(b.f("ix_channel_link_codes_branch_id"), ["branch_id"], unique=False)
        b.create_index(b.f("ix_channel_link_codes_person_id"), ["person_id"], unique=False)
