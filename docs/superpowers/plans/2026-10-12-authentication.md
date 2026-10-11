# Authentication and Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every request to a Mia Node carries an actor the node verified: office users log in with password and TOTP, staff with a WhatsApp code and a bound device, outside services with client credentials, and risky approvals need a fresh PIN.

**Architecture:** Crypto primitives with no database live in `core/keys.py` (master key file, HKDF subkeys, scrypt, TOTP, tokens). Database services that write through `store` and emit events live in `core/auth.py` (attempts and lockout, one-time codes, credentials, sessions, devices, clients). One FastAPI dependency in `api/deps.py` (`current_auth`) turns a bearer token, a cookie or, in dev mode only, the X-Mia-Actor header into an `AuthContext`; every route takes it. Routes under `/auth/*` live in `api/auth.py`.

**Tech Stack:** Python 3.12 standard library only (`hashlib.scrypt`, `hmac`, `secrets`), FastAPI, SQLModel, Alembic. No new dependency; passkeys (`webauthn`) and SMS are out of scope until approved (D17).

**Spec:** docs/superpowers/specs/2026-10-05-authentication-design.md (accepted by D17), docs/adr/011-authentication.md. Spec section 16 steps 1 to 10 and 12 are built; 11 (passkeys) and 13 (SMS) wait for approval.

## Global Constraints

- CLAUDE.md rules: writes only through `store.insert` and `store.update` with an event (rule 1); `rbac.require` before every tool call (rule 4); nothing leaves the node except through egress or `channels/transport.py` (rule 6); ULIDs, ISO times with zone (rule 10); short write transactions (rule 11); Alembic migration for every schema change (rule 14).
- Rule 1 wins over the spec's "refreshes are not events": a refresh rotation is a `store.update` and emits `auth.session_refreshed`. Access token checks are reads and emit nothing.
- Tokens: 32 random bytes, base64url, stored as SHA-256 hex; access 15 minutes; office refresh 12 h idle and 7 days absolute; staff on a bound mobile device 30 days idle and 90 days absolute; client tokens 1 hour, no refresh.
- Codes: 6 digits for `invite` (7 days), `self` (10 min), `otp_login` (5 min); random tokens for `link_login` (10 min), `mfa` (5 min), `enrol` (24 h). Single use, at most 5 tries, stored only as an HMAC.
- Limits (spec section 10): password per (login, IP) 5 failures in 15 min, 15 min block; per login 20 in 1 h, 15 min block and `auth.locked`; any auth per IP 50 in 15 min, 15 min block; client secret 10 in 15 min; link code 5 per hour per address (unchanged); OTP sends 3 per number per hour, silently not sent; PIN 5 failures locks the PIN until the next MFA or phone-code login.
- MFA required for roles owner, admin and accountant; a password-only login for them yields an `enrol` session that can only reach `/auth/*`.
- Failures answer 401 `invalid credentials` whatever was wrong; unknown logins take the same time as known ones (a dummy scrypt verify runs).
- No password, code, PIN, token or token hash in an event, a log line or an error body. Models declare `__redact__`; `events.snapshot` applies it.
- `MIA_AUTH_MODE=required` is the default. `dev` accepts X-Mia-Actor only from a loopback peer (or Starlette's `testclient`) without `CF-Connecting-IP` or `CF-Ray` headers, never on `/auth/*`; the node refuses to start in dev mode when `MIA_PUBLIC_URL` is not on localhost.
- Cookies: `mia_at` (Path=/) and `mia_rt` (Path=/auth/refresh), HttpOnly, SameSite=Strict, Secure when `MIA_PUBLIC_URL` is https. Unsafe methods with cookie auth need an `Origin` equal to the origin of `MIA_PUBLIC_URL`.
- Style: Ruff line length 100, mypy strict on mia/core and mia/chat, docstrings on public functions, no em-dashes, i18n keys for user-facing strings.
- Check after every task: `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && uv run pytest`.

## Review Focus

1. A login typed as `Owner@Example.fi ` (capitals, trailing space) must log in as `owner@example.fi`. Pinned in Task 5 (`test_login_normalises_email`).
2. On `http://localhost:8000` in dev the cookies must not carry `Secure` (a browser would drop them), on `https://` they must. Pinned in Task 5 (`test_cookie_flags_follow_public_url`).
3. A refresh token presented after the absolute lifetime must revoke the session and answer 401, not silently extend it. Pinned in Task 4 (`test_refresh_after_absolute_expiry_revokes`).
4. A login link fetched with GET (link preview, scanner) must not be consumed; only the POST logs in. Pinned in Task 7 (`test_link_get_does_not_consume`).
5. A client token on a person route (`/chat`) must get 403, and a person cookie on a client route 401. Pinned in Task 9 (`test_client_token_is_refused_on_person_routes`).

## File Structure

- Create `node/mia/core/keys.py`: master key file, HKDF, scrypt, tokens, TOTP, numeric codes. No database.
- Create `node/mia/core/auth.py`: attempts and lockout, one-time codes, credentials (password, TOTP, recovery, PIN), sessions, devices, clients, enrolment. Every write through `store`.
- Create `node/mia/api/deps.py`: `get_session`, `DbSession` (moved from `chat/router.py`), `AuthContext`, `current_auth`, `CurrentAuth`, `PersonAuth`, `ClientAuth`, `client_ip`, `check_mode`, cookie helpers.
- Create `node/mia/api/auth.py`: the `/auth/*` routes.
- Modify `node/mia/core/models.py`: data standard 1.3 tables; `__redact__`.
- Modify `node/mia/core/events.py` and `node/mia/core/store.py`: redaction.
- Create `node/migrations/versions/0004_data_standard_1_3_auth.py`.
- Modify `node/mia/channels/linking.py`: codes and attempts through `core/auth.py`.
- Modify `node/mia/chat/router.py`, `node/mia/api/main.py`: routes take `PersonAuth`; `/health` shows `auth_mode` and is reduced behind Cloudflare.
- Modify `node/mia/core/approvals.py`: `decide` takes `aal` and `stepped_up_at`.
- Modify `node/mia/core/people.py`: deactivate revokes devices and sessions.
- Modify `node/mia/channels/whatsapp/templates.py`: `mia_login_code`.
- Modify `node/mia/channels/service.py`: `deliver(..., redact=True)`.
- Modify `node/mia/cli.py`: `mia keys init`, `mia auth bootstrap | reset | unlock | link | client add | client revoke`; `serve` runs `check_mode`; `decide` passes a step-up.
- Modify `node/mia/settings.py`, `.env.example`, `node/tests/conftest.py`, `node/config/policies/policy.csv`, `node/mia/static/index.html`, `node/mia/i18n/strings.py`.
- Tests in `node/tests/auth/` (new folder, one file per task) plus edits to `node/tests/channels/test_linking.py`, `node/tests/test_migrations.py`, `node/tests/test_approvals.py`, `node/tests/test_tools.py`, `node/tests/test_chat.py`, `node/tests/test_architecture.py`.
- Docs: `docs/layout.md`, `docs/adr/011-authentication.md`, `docs/decisions.md` (D33), `README.md`, `deploy/install.md`, `deploy/docker-compose.yml`.

---

### Task 1: Data standard 1.3 (models, redaction, migration 0004, linking on the renamed tables)

**Files:**
- Modify: `node/mia/core/models.py` (STANDARD_VERSION, new tables, rename ChannelLinkCode and ChannelLinkAttempt)
- Modify: `node/mia/core/events.py:65-68` (snapshot redaction)
- Modify: `node/mia/core/store.py` (redact keyword)
- Create: `node/migrations/versions/0004_data_standard_1_3_auth.py`
- Modify: `node/mia/channels/linking.py` (AuthCode, AuthAttempt)
- Modify: `node/tests/channels/test_linking.py` (names), `node/tests/test_migrations.py`, `node/tests/test_events.py`
- Modify: `docs/layout.md`

**Interfaces:**
- Produces: `AuthCredential`, `AuthDevice`, `AuthSession`, `AuthClient`, `AuthCode` (fields of `ChannelLinkCode` plus `address: str | None`, `tries: int`), `AuthAttempt(kind: str, key: str, ok: bool)`; `events.snapshot(row, redact=())`; `store.insert(..., redact=())`, `store.update(..., redact=())`; `STANDARD_VERSION == "1.3"`.

- [ ] **Step 1: Write the failing tests**

Append to `node/tests/test_events.py`:

```python
def test_snapshot_redacts_declared_and_requested_fields(branch: Branch) -> None:
    from mia.core.events import snapshot
    from mia.core.models import AuthCredential, ChannelOutbox

    cred = AuthCredential(
        branch_id=branch.id, person_id="P", kind="password", login="a@b.fi", secret_hash="scrypt$x"
    )
    snap = snapshot(cred)
    assert snap is not None and snap["secret_hash"] == "<redacted>" and snap["login"] == "a@b.fi"
    row = ChannelOutbox(
        branch_id=branch.id, person_id="P", channel="sim", address="1", payload={"text": "123456"},
        idempotency_key="k",
    )
    assert snapshot(row, redact={"payload"})["payload"] == "<redacted>"  # type: ignore[index]
```

Append to `node/tests/test_migrations.py`:

```python
def test_upgrade_from_1_2_keeps_link_codes_and_attempts() -> None:
    """Link codes and attempts move to auth_codes and auth_attempts with their rows."""
    cfg = _alembic_config()
    command.upgrade(cfg, "0003")
    with get_engine().begin() as conn:
        conn.execute(text("INSERT INTO organisation VALUES ('O', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'Org', 'FI', 'fi')"))
        conn.execute(text("INSERT INTO branch VALUES ('B', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'O', 'Hki', 'Europe/Helsinki')"))
        conn.execute(text(
            "INSERT INTO person VALUES ('P', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', "
            "'B', 'Pia', 'active', '[\"staff\"]', '[]', 'employee', 'fi', '', NULL, NULL, 1)"
        ))
        conn.execute(text(
            "INSERT INTO channel_link_codes VALUES ('C', '2026-01-01T00:00:00+00:00', "
            "'2026-01-01T00:00:00+00:00', 'B', 'P', 'abc', 'invite', '2026-01-08T00:00:00+00:00', NULL, 'P')"
        ))
        conn.execute(text(
            "INSERT INTO channel_link_attempts VALUES ('A', '2026-01-01T00:00:00+00:00', "
            "'2026-01-01T00:00:00+00:00', 'whatsapp', '358401', 0)"
        ))
    command.upgrade(cfg, "head")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT purpose, address, tries FROM auth_codes")).one() == ("invite", None, 0)
        assert conn.execute(text("SELECT kind, key, ok FROM auth_attempts")).one() == ("link_code", "whatsapp:358401@-", 0)
        tables = set(inspect(conn).get_table_names())
        assert {"auth_credentials", "auth_devices", "auth_sessions", "auth_clients"} <= tables
        assert not {"channel_link_codes", "channel_link_attempts"} & tables
    command.downgrade(cfg, "0003")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT channel, address FROM channel_link_attempts")).one() == ("whatsapp", "358401")
```

In `node/tests/channels/test_linking.py` replace `ChannelLinkCode` with `AuthCode` everywhere (import and uses), and where the test reads attempt rows, `ChannelLinkAttempt` with `AuthAttempt` (its `key` is `f"{channel}:{address}@-"`, its `kind` is `"link_code"`).

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/test_events.py node/tests/test_migrations.py node/tests/channels/test_linking.py --no-cov -q`
Expected: ImportError on `AuthCredential` / `AuthCode`.

- [ ] **Step 3: Models**

In `node/mia/core/models.py` set `STANDARD_VERSION = "1.3"`, add `from typing import ClassVar` if missing, and replace the `ChannelLinkCode` and `ChannelLinkAttempt` classes with:

```python
class AuthCode(BranchScoped, table=True):
    """A one-time code: channel link (invite, self), staff OTP, login link, MFA token or
    enrolment link. Stored only as an HMAC (core/keys.py), single use, expiring, at most 5 tries."""

    __tablename__: ClassVar[str] = "auth_codes"
    __redact__: ClassVar[frozenset[str]] = frozenset({"code_hmac"})

    person_id: str = Field(foreign_key="person.id", index=True)
    code_hmac: str = Field(unique=True)
    purpose: str  # invite, self, otp_login, link_login, mfa, enrol
    address: str | None = None  # where it was sent, if anywhere
    tries: int = 0
    expires_at: datetime = Field(sa_type=TZDateTime)
    used_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    created_by: str


class AuthAttempt(Stamped, table=True):
    """One credential check, for rate limits and lockouts. `key` is `<subject>@<ip>` where the
    subject is a login HMAC, an address, a person or client id; `@-` when there is no IP."""

    __tablename__: ClassVar[str] = "auth_attempts"

    kind: str  # link_code, password, otp, pin, client_secret, mfa, device
    key: str = Field(index=True)
    ok: bool


class AuthCredential(BranchScoped, table=True):
    """One login factor of a person: password, totp, recovery_code, pin (passkey later)."""

    __tablename__: ClassVar[str] = "auth_credentials"
    __redact__: ClassVar[frozenset[str]] = frozenset({"secret_hash", "data"})

    person_id: str = Field(foreign_key="person.id", index=True)
    kind: str
    login: str | None = Field(default=None, unique=True)  # lowercased email, password rows only
    secret_hash: str | None = None  # scrypt string; null for totp
    data: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)  # totp: nonce, last_step
    status: str = "active"  # pending, active, revoked, used, locked
    last_used_at: datetime | None = Field(default=None, sa_type=TZDateTime)


class AuthDevice(BranchScoped, table=True):
    """A browser or phone a person signed in on. Mobile devices hold a device secret."""

    __tablename__: ClassVar[str] = "auth_devices"
    __redact__: ClassVar[frozenset[str]] = frozenset({"secret_hash"})

    person_id: str = Field(foreign_key="person.id", index=True)
    kind: str  # browser, mobile
    name: str
    secret_hash: str | None = None
    status: str = "active"  # active, revoked
    last_seen_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    revoked_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    revoked_by: str | None = None


class AuthSession(BranchScoped, table=True):
    """One signed-in session of a person or a client. Tokens are stored as SHA-256 hashes."""

    __tablename__: ClassVar[str] = "auth_sessions"
    __redact__: ClassVar[frozenset[str]] = frozenset(
        {"access_hash", "refresh_hash", "prev_refresh_hash"}
    )

    subject_type: str  # person, client
    subject_id: str = Field(index=True)
    device_id: str | None = Field(default=None, foreign_key="auth_devices.id")
    method: str  # password_totp, password, phone_otp, device, wa_link, client, enrol
    aal: str  # aal1, aal2, client, enrol
    access_hash: str = Field(unique=True)
    access_expires_at: datetime = Field(sa_type=TZDateTime)
    refresh_hash: str | None = Field(default=None, unique=True)
    prev_refresh_hash: str | None = None
    refresh_expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    absolute_expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    stepped_up_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    status: str = "active"  # active, revoked
    ip: str = ""


class AuthClient(BranchScoped, table=True):
    """An outside agent or service with OAuth2 client credentials issued by this node."""

    __tablename__: ClassVar[str] = "auth_clients"
    __redact__: ClassVar[frozenset[str]] = frozenset({"secret_hash"})

    name: str
    client_id: str = Field(unique=True)
    secret_hash: str
    roles: list[str] = Field(default_factory=list, sa_type=JSON)
    status: str = "active"  # active, revoked
    expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    created_by: str
    last_used_at: datetime | None = Field(default=None, sa_type=TZDateTime)
```

- [ ] **Step 4: Redaction in events and store**

In `node/mia/core/events.py` replace `snapshot`:

```python
REDACTED = "<redacted>"


def snapshot(row: SQLModel | None, redact: Iterable[str] = ()) -> dict[str, Any] | None:
    """JSON-safe copy of a row for before/after values. Fields named in the model's
    `__redact__` and in `redact` are replaced by "<redacted>" so secrets never enter events."""
    if row is None:
        return None
    data = row.model_dump(mode="json")
    hidden = set(getattr(row, "__redact__", ())) | set(redact)
    return {k: (REDACTED if k in hidden and v is not None else v) for k, v in data.items()}
```

Add `from collections.abc import Iterable` to its imports. In `node/mia/core/store.py` add a keyword `redact: Iterable[str] = ()` to `insert` and `update` (after `approval_id`), pass `events.snapshot(row, redact)` for the `after` of insert and for both `before` and `after` of update, and import `Iterable` from `collections.abc`.

- [ ] **Step 5: Migration 0004**

Create `node/migrations/versions/0004_data_standard_1_3_auth.py`:

```python
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
```

If `test_upgrade_matches_models_and_adds_triggers` reports a diff, fix the migration until `diff == []` (the models are the source of truth; the usual culprits are index names and nullability).

- [ ] **Step 6: Linking on the renamed tables**

In `node/mia/channels/linking.py`: import `AuthAttempt, AuthCode` instead of `ChannelLinkAttempt, ChannelLinkCode`; `create_code` inserts `AuthCode(...)` with the same fields; `redeem` selects `AuthCode`; `_blocked` counts `AuthAttempt` rows `.where(AuthAttempt.kind == "link_code").where(AuthAttempt.key == f"{channel}:{address}@-")`; `_record` inserts `AuthAttempt(kind="link_code", key=f"{channel}:{address}@-", ok=ok, created_at=now)`. (Task 3 moves this logic into `core/auth.py`; here only the names change.)

- [ ] **Step 7: Run the tests, then the full suite**

Run: `uv run pytest node/tests/test_events.py node/tests/test_migrations.py node/tests/channels --no-cov -q`, then `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && uv run pytest`
Expected: all pass.

- [ ] **Step 8: Layout and commit**

In `docs/layout.md` add `auth, keys` to the `core/` line and `deps.py, auth.py` to `api/` ("main.py, deps.py (session and auth dependencies), auth.py (login routes)"). Commit:

```bash
git add -A
git commit -m "auth: data standard 1.3 (auth tables, redacted event snapshots, migration 0004)"
```

---

### Task 2: Key material and crypto primitives (`core/keys.py`, `mia keys init`)

**Files:**
- Create: `node/mia/core/keys.py`
- Modify: `node/mia/settings.py` (MIA_MASTER_KEY_FILE, MIA_AUTH_MODE, MIA_TRUSTED_PROXIES), `.env.example`, `node/mia/cli.py` (`keys init`), `node/tests/conftest.py`
- Test: `node/tests/auth/__init__.py` (empty), `node/tests/auth/test_keys.py`

**Interfaces:**
- Produces: `MasterKeyError`; `generate(path)`; `master_key() -> bytes`; `reset_cache()`; `hkdf(ikm, info, length=32, salt=b"") -> bytes`; `subkey(label) -> bytes`; `code_hmac(code: str) -> str`; `hash_secret(secret) -> str`; `verify_secret(secret, stored) -> bool`; `dummy_hash() -> str`; `new_token() -> str`; `token_hash(token) -> str`; `numeric_code(digits=6) -> str`; `hotp(key, counter, digits=6) -> str`; `totp_step(now) -> int`; `totp_seed(credential_id, nonce) -> bytes`; `totp_uri(seed, label) -> str`; `SCRYPT_N`.
- Settings: `MIA_MASTER_KEY_FILE: Path | None = None`, `MIA_AUTH_MODE: Literal["required", "dev"] = "required"`, `MIA_TRUSTED_PROXIES: str = ""`.

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_keys.py`:

```python
"""Master key file, HKDF (RFC 5869), scrypt strings, tokens and TOTP (RFC 4226 and 6238)."""

import datetime as dt
import os
from pathlib import Path

import pytest

from mia.core import keys
from mia.settings import get_settings


def test_generate_refuses_overwrite_and_sets_mode(tmp_path: Path) -> None:
    path = tmp_path / "k" / "master.key"
    keys.generate(path)
    assert len(path.read_bytes()) == 32 and oct(path.stat().st_mode & 0o777) == "0o400"
    with pytest.raises(keys.MasterKeyError, match="exists"):
        keys.generate(path)


def test_master_key_refuses_missing_or_open_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "master.key"
    monkeypatch.setenv("MIA_MASTER_KEY_FILE", str(path))
    get_settings.cache_clear()
    keys.reset_cache()
    with pytest.raises(keys.MasterKeyError, match="not found"):
        keys.master_key()
    keys.generate(path)
    os.chmod(path, 0o644)
    with pytest.raises(keys.MasterKeyError, match="chmod 400"):
        keys.master_key()
    os.chmod(path, 0o400)
    assert keys.master_key() == path.read_bytes()


def test_without_key_file_node_secret_is_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIA_MASTER_KEY_FILE")
    monkeypatch.setenv("MIA_NODE_SECRET", "old-secret")
    get_settings.cache_clear()
    keys.reset_cache()
    import hashlib
    import hmac

    assert keys.master_key() == hashlib.sha256(b"old-secret").digest()
    # Link codes created before the key file existed keep working: same HMAC as before.
    assert keys.code_hmac("123456") == hmac.new(b"old-secret", b"123456", hashlib.sha256).hexdigest()
    monkeypatch.setenv("MIA_NODE_SECRET", "")
    get_settings.cache_clear()
    keys.reset_cache()
    with pytest.raises(keys.MasterKeyError, match="mia keys init"):
        keys.master_key()


def test_hkdf_rfc_5869_case_1() -> None:
    okm = keys.hkdf(bytes([0x0B] * 22), bytes(range(0xF0, 0xFA)), 42, bytes(range(13)))
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"
    )


def test_subkeys_differ_by_label() -> None:
    assert keys.subkey("mia/totp") != keys.subkey("mia/auth-codes")
    assert len(keys.subkey("mia/totp")) == 32


def test_scrypt_string_round_trip_and_params() -> None:
    stored = keys.hash_secret("correct horse")
    assert stored.startswith(f"scrypt${keys.SCRYPT_N}$8$1$")
    assert keys.verify_secret("correct horse", stored)
    assert not keys.verify_secret("wrong", stored)
    assert not keys.verify_secret("x", "garbage")
    assert keys.verify_secret("x", keys.dummy_hash()) is False


def test_tokens_and_codes() -> None:
    tok = keys.new_token()
    assert len(tok) == 43 and "=" not in tok and len(keys.token_hash(tok)) == 64
    assert keys.numeric_code().isdigit() and len(keys.numeric_code()) == 6


def test_hotp_rfc_4226_vectors() -> None:
    key = b"12345678901234567890"
    assert [keys.hotp(key, c) for c in (0, 1, 2)] == ["755224", "287082", "359152"]


def test_totp_step_and_seed() -> None:
    assert keys.totp_step(dt.datetime(1970, 1, 1, 0, 0, 59, tzinfo=dt.UTC)) == 1
    seed = keys.totp_seed("CRED", "nonce")
    assert len(seed) == 20 and seed != keys.totp_seed("CRED", "other")
    uri = keys.totp_uri(seed, "owner@example.fi")
    assert uri.startswith("otpauth://totp/Mia:owner%40example.fi?secret=") and "issuer=Mia" in uri
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_keys.py --no-cov -q`
Expected: ModuleNotFoundError `mia.core.keys`.

- [ ] **Step 3: Settings, conftest and the module**

In `node/mia/settings.py` add after `MIA_PUBLIC_URL`:

```python
    # Authentication (ADR 011). The master key file (mia keys init) derives every subkey;
    # without it MIA_NODE_SECRET is the key, so invites made before it keep working.
    MIA_MASTER_KEY_FILE: Path | None = None
    MIA_AUTH_MODE: Literal["required", "dev"] = "required"
    # Peers allowed to set CF-Connecting-IP (the cloudflared container), comma separated.
    MIA_TRUSTED_PROXIES: str = ""
```

In `.env.example` add the three with the same comments (`MIA_AUTH_MODE=dev` in the example, since it is the development file; say so in the comment).

In `node/tests/conftest.py`, inside `isolated_settings` after the `MIA_WA_NUMBER` line:

```python
    key_file = tmp_path / "master.key"
    from mia.core import keys

    keys.generate(key_file)
    monkeypatch.setenv("MIA_MASTER_KEY_FILE", str(key_file))
    monkeypatch.setenv("MIA_AUTH_MODE", "dev")
    monkeypatch.setattr(keys, "SCRYPT_N", 2**8)  # the real 2**17 makes every login slow
    keys.reset_cache()
```

and `keys.reset_cache()` after the yield too.

Create `node/mia/core/keys.py`:

```python
"""Key material and the crypto primitives of authentication (ADR 011). No database here.

Guarantees: the master key is read from a root-only file (mode 0400) or, without one, derived
from MIA_NODE_SECRET; subkeys come from HKDF-SHA256 with fixed labels, so no TOTP seed is ever
stored; passwords, PINs and client secrets are scrypt strings that carry their parameters;
tokens are 32 random bytes; TOTP follows RFC 6238 on HOTP (RFC 4226).
"""

import base64
import hashlib
import hmac
import os
import secrets
import struct
import urllib.parse
from datetime import datetime
from pathlib import Path

from mia.settings import get_settings

KEY_BYTES = 32
SCRYPT_N = 2**17  # OWASP; tests lower it through monkeypatch
SCRYPT_R = 8
SCRYPT_P = 1
TOTP_STEP = 30
TOTP_DIGITS = 6
_cache: dict[Path, bytes] = {}
_dummy: str | None = None


class MasterKeyError(RuntimeError):
    """The master key file is missing, unreadable or too open, and there is no fallback."""


def generate(path: Path) -> None:
    """Write a new 32-byte key with mode 0400. Refuses to overwrite an existing file."""
    if path.exists():
        raise MasterKeyError(f"{path} exists; refusing to overwrite a master key")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as f:
        f.write(secrets.token_bytes(KEY_BYTES))


def master_key() -> bytes:
    """The node's master key. Without MIA_MASTER_KEY_FILE, SHA-256 of MIA_NODE_SECRET."""
    settings = get_settings()
    path = settings.MIA_MASTER_KEY_FILE
    if path is None:
        if not settings.MIA_NODE_SECRET:
            raise MasterKeyError("set MIA_MASTER_KEY_FILE (run `mia keys init`) or MIA_NODE_SECRET")
        return hashlib.sha256(settings.MIA_NODE_SECRET.encode()).digest()
    if path not in _cache:
        try:
            mode = path.stat().st_mode
        except FileNotFoundError as exc:
            raise MasterKeyError(f"master key file not found: {path}") from exc
        if mode & 0o077:
            raise MasterKeyError(f"{path} is readable by group or others; chmod 400 it")
        data = path.read_bytes()
        if len(data) < KEY_BYTES:
            raise MasterKeyError(f"{path} holds fewer than {KEY_BYTES} bytes")
        _cache[path] = data
    return _cache[path]


def reset_cache() -> None:
    """Forget the cached key file (tests, key rotation)."""
    global _dummy
    _cache.clear()
    _dummy = None


def hkdf(ikm: bytes, info: bytes, length: int = 32, salt: bytes = b"") -> bytes:
    """HKDF-SHA256 (RFC 5869): extract, then expand to `length` bytes."""
    prk = hmac.new(salt or bytes(32), ikm, hashlib.sha256).digest()
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def subkey(label: str) -> bytes:
    """A 32-byte key for one purpose: mia/link-codes, mia/auth-codes, mia/totp."""
    return hkdf(master_key(), label.encode())


def code_hmac(code: str) -> str:
    """HMAC of a one-time code. Keyed by MIA_NODE_SECRET itself when there is no key file, so
    link codes created before the key file keep working; by the auth-codes subkey otherwise."""
    settings = get_settings()
    key = (
        subkey("mia/auth-codes")
        if settings.MIA_MASTER_KEY_FILE is not None
        else settings.MIA_NODE_SECRET.encode()
    )
    if not key:
        raise MasterKeyError("set MIA_MASTER_KEY_FILE (run `mia keys init`) or MIA_NODE_SECRET")
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_secret(secret: str) -> str:
    """scrypt string `scrypt$N$r$p$salt$hash` (parameters travel with the hash)."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        secret.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=256 * 1024 * 1024
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_secret(secret: str, stored: str) -> bool:
    """Constant-time check of a secret against a scrypt string. False for a malformed string."""
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = hashlib.scrypt(
            secret.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), maxmem=256 * 1024 * 1024
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, _unb64(digest))


def dummy_hash() -> str:
    """A hash to verify against when the login is unknown, so timing does not reveal it."""
    global _dummy
    if _dummy is None:
        _dummy = hash_secret(secrets.token_hex(8))
    return _dummy


def new_token() -> str:
    """32 random bytes, base64url without padding (43 characters)."""
    return _b64(secrets.token_bytes(32))


def token_hash(token: str) -> str:
    """SHA-256 hex of a token, the only form stored."""
    return hashlib.sha256(token.encode()).hexdigest()


def numeric_code(digits: int = 6) -> str:
    """A zero-padded random numeric code."""
    return f"{secrets.randbelow(10**digits):0{digits}d}"


def hotp(key: bytes, counter: int, digits: int = TOTP_DIGITS) -> str:
    """HOTP (RFC 4226) with HMAC-SHA1 and dynamic truncation."""
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 10**digits:0{digits}d}"


def totp_step(now: datetime) -> int:
    """The 30-second step a time falls in (RFC 6238)."""
    return int(now.timestamp()) // TOTP_STEP


def totp_seed(credential_id: str, nonce: str) -> bytes:
    """The 20-byte TOTP seed of a credential, derived, never stored."""
    return hkdf(subkey("mia/totp"), f"{credential_id}:{nonce}".encode(), 20)


def totp_uri(seed: bytes, label: str) -> str:
    """otpauth URI for authenticator apps."""
    secret = base64.b32encode(seed).decode().rstrip("=")
    return (
        f"otpauth://totp/Mia:{urllib.parse.quote(label, safe='')}?secret={secret}"
        f"&issuer=Mia&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_STEP}"
    )
```

In `node/mia/cli.py` add:

```python
def keys_init(args: argparse.Namespace) -> int:
    from mia.core import keys

    path = args.path or get_settings().MIA_MASTER_KEY_FILE
    if path is None:
        raise SystemExit("give a path or set MIA_MASTER_KEY_FILE")
    try:
        keys.generate(Path(path))
    except keys.MasterKeyError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"master key written to {path} (mode 400). Back it up outside the data folder.")
    return 0
```

and in `build_parser`: `keys_p = sub.add_parser("keys", help="key material").add_subparsers(dest="keys_command", required=True)`; `p = keys_p.add_parser("init", help="create the master key file"); p.add_argument("path", nargs="?"); p.set_defaults(func=keys_init)`. Import `Path` from `pathlib` at the top of cli.py.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest node/tests/auth/test_keys.py --no-cov -q` then the full check line.
Expected: PASS. Add to `node/tests/test_cli.py`:

```python
def test_keys_init(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "k.key"
    assert main(["keys", "init", str(path)]) == 0
    assert "master key written" in capsys.readouterr().out and len(path.read_bytes()) == 32
    with pytest.raises(SystemExit, match="exists"):
        main(["keys", "init", str(path)])
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "auth: master key file, HKDF subkeys, scrypt, tokens and TOTP primitives; mia keys init"
```

---

### Task 3: Attempts, lockout, one-time codes and credentials (`core/auth.py` part 1)

**Files:**
- Create: `node/mia/core/auth.py`
- Modify: `node/mia/channels/linking.py` (codes and attempts through `core/auth.py`)
- Test: `node/tests/auth/test_credentials.py`; `node/tests/channels/test_linking.py` keeps passing

**Interfaces:**
- Consumes: `keys.*` (Task 2), models (Task 1).
- Produces (all in `mia.core.auth`):
  - `class AuthError(RuntimeError)`, `class Locked(AuthError)`, `class StepUpRequired(RuntimeError)`
  - `MFA_ROLES`, `CODE_TTL: dict[str, timedelta]`, `CODE_TRIES = 5`, `LIMITS: dict[str, Limit]`, `STEP_UP_TTL`
  - `auth_actor(branch_id: str = "") -> Actor` (system principal `auth`)
  - `login_key(login: str) -> str`, `attempt_key(subject: str, ip: str | None) -> str`
  - `throttled(session, kind, key, now) -> bool`, `record_attempt(session, kind, key, ok, now, *, actor=None, action=None) -> AuthAttempt`
  - `create_code(session, actor, person, purpose, now, *, address=None, token=False) -> str`
  - `CodeResult(status: Literal["ok","invalid","expired","used","exhausted"], row: AuthCode | None)`, `check_code(session, purpose, code, now, *, person_id=None) -> CodeResult`, `use_code(session, actor, row, now) -> AuthCode`, `fail_code(session, purpose, now, *, address=None, person_id=None) -> None`, `sends_in_last_hour(session, purpose, address, now) -> int`
  - `normalise_login(login) -> str`, `set_password(session, actor, person, login, password, now) -> AuthCredential`, `person_by_login(session, login) -> tuple[Person, AuthCredential] | None`, `check_password(session, login, password, ip, now) -> Person`
  - `needs_mfa(session, person) -> bool`, `has_mfa(session, person) -> bool`, `enrol_totp(session, actor, person, now) -> tuple[AuthCredential, str]`, `confirm_totp(session, actor, cred, code, now) -> list[str]`, `check_totp(session, person, code, now) -> bool`, `check_recovery(session, actor, person, code, now) -> bool`
  - `trivial_pin(pin) -> bool`, `set_pin(session, actor, person, pin, now) -> AuthCredential`, `check_pin(session, person, pin, ip, now) -> bool`, `unlock_pin(session, actor, person, now) -> None`, `has_pin(session, person) -> bool`

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_credentials.py`:

```python
"""Lockouts, one-time codes, passwords, TOTP, recovery codes and PINs."""

import datetime as dt

import pytest
from sqlmodel import Session, select

from mia.core import auth, keys
from mia.core.db import utcnow
from mia.core.models import Actor, AuthCode, AuthCredential, Event, Person

IP = "203.0.113.5"


def _owner(people: dict[str, Person]) -> tuple[Person, Actor]:
    helena = people["Helena"]
    return helena, Actor.person(helena)


def test_password_round_trip_and_generic_failure(
    session: Session, people: dict[str, Person]
) -> None:
    helena, actor = _owner(people)
    now = utcnow()
    cred = auth.set_password(session, actor, helena, " Helena@Example.FI ", "correct horse 1", now)
    assert cred.login == "helena@example.fi" and cred.secret_hash and cred.secret_hash != "correct horse 1"
    assert auth.check_password(session, "HELENA@example.fi", "correct horse 1", IP, now).id == helena.id
    for login, pw in (("helena@example.fi", "nope"), ("nobody@example.fi", "nope")):
        with pytest.raises(auth.AuthError, match="invalid credentials"):
            auth.check_password(session, login, pw, IP, now)
    actions = [e.action for e in session.exec(select(Event).where(Event.action.startswith("auth.")))]  # type: ignore[attr-defined]
    assert actions.count("auth.login_failed") == 2 and "auth.login_succeeded" in actions
    assert "auth.password_set" in actions
    for e in session.exec(select(Event)):
        assert "correct horse" not in str(e.after) and "scrypt$" not in str(e.after)


def test_password_rules(session: Session, people: dict[str, Person]) -> None:
    helena, actor = _owner(people)
    with pytest.raises(ValueError, match="12 characters"):
        auth.set_password(session, actor, helena, "h@e.fi", "short", utcnow())
    with pytest.raises(ValueError, match="email"):
        auth.set_password(session, actor, helena, "not-an-email", "long enough password", utcnow())
    auth.set_password(session, actor, helena, "h@e.fi", "long enough password", utcnow())
    with pytest.raises(ValueError, match="in use"):
        auth.set_password(session, actor, people["Sanna"], "h@e.fi", "another long password", utcnow())


def test_lockout_per_pair_login_and_ip(session: Session, people: dict[str, Person]) -> None:
    helena, actor = _owner(people)
    now = utcnow()
    auth.set_password(session, actor, helena, "h@e.fi", "long enough password", now)
    for _ in range(5):
        with pytest.raises(auth.AuthError):
            auth.check_password(session, "h@e.fi", "wrong", IP, now)
    with pytest.raises(auth.Locked):  # the (login, IP) pair is blocked, even with the right password
        auth.check_password(session, "h@e.fi", "long enough password", IP, now)
    assert auth.check_password(session, "h@e.fi", "long enough password", "198.51.100.1", now)
    later = now + dt.timedelta(minutes=16)
    assert auth.check_password(session, "h@e.fi", "long enough password", IP, later)
    # 20 failures on the login from many IPs lock the login and write auth.locked.
    for i in range(20):
        with pytest.raises(auth.AuthError):
            auth.check_password(session, "h@e.fi", "wrong", f"10.0.0.{i}", later)
    with pytest.raises(auth.Locked):
        auth.check_password(session, "h@e.fi", "long enough password", "10.0.1.1", later)
    assert session.exec(select(Event).where(Event.action == "auth.locked")).first() is not None
    # 50 failures of any kind from one IP block that IP for everyone.
    ip_now = later + dt.timedelta(hours=2)
    for i in range(50):
        auth.record_attempt(session, "otp", auth.attempt_key(f"3584{i}", "9.9.9.9"), False, ip_now)
    assert auth.throttled(session, "password", auth.attempt_key("x", "9.9.9.9"), ip_now)
    assert not auth.throttled(session, "password", auth.attempt_key("x", "9.9.9.8"), ip_now)


def test_codes_single_use_expiry_tries_and_sends(session: Session, people: dict[str, Person]) -> None:
    juha, actor = people["Juha"], Actor.person(people["Juha"])
    now = utcnow()
    code = auth.create_code(session, actor, juha, "otp_login", now, address="358401")
    assert code.isdigit() and len(code) == 6
    row = session.exec(select(AuthCode)).one()
    assert row.code_hmac == keys.code_hmac(code) and row.address == "358401" and row.tries == 0
    assert auth.check_code(session, "otp_login", "000000", now).status == "invalid"
    assert auth.check_code(session, "mfa", code, now).status == "invalid"  # wrong purpose
    assert auth.check_code(session, "otp_login", code, now + dt.timedelta(minutes=6)).status == "expired"
    for _ in range(5):
        auth.fail_code(session, "otp_login", now, address="358401")
    assert auth.check_code(session, "otp_login", code, now).status == "exhausted"
    token = auth.create_code(session, actor, juha, "enrol", now, token=True)
    assert len(token) == 43
    res = auth.check_code(session, "enrol", token, now)
    assert res.status == "ok" and res.row is not None and res.row.person_id == juha.id
    auth.use_code(session, actor, res.row, now)
    assert auth.check_code(session, "enrol", token, now).status == "used"
    auth.create_code(session, actor, juha, "otp_login", now, address="358401")
    assert auth.sends_in_last_hour(session, "otp_login", "358401", now) == 2
    for e in session.exec(select(Event).where(Event.action == "auth.code_created")):
        assert e.after is not None and e.after["code_hmac"] == "<redacted>"


def test_totp_enrol_confirm_window_and_reuse(session: Session, people: dict[str, Person]) -> None:
    helena, actor = _owner(people)
    now = dt.datetime(2026, 10, 12, 9, 0, 0, tzinfo=dt.UTC)
    assert auth.needs_mfa(session, helena) and not auth.has_mfa(session, helena)
    cred, uri = auth.enrol_totp(session, actor, helena, now)
    assert cred.status == "pending" and uri.startswith("otpauth://totp/Mia:")
    seed = keys.totp_seed(cred.id, cred.data["nonce"])
    assert not auth.check_totp(session, helena, keys.hotp(seed, keys.totp_step(now)), now)  # pending
    with pytest.raises(auth.AuthError):
        auth.confirm_totp(session, actor, cred, "000000", now)
    recovery = auth.confirm_totp(session, actor, cred, keys.hotp(seed, keys.totp_step(now)), now)
    assert len(recovery) == 10 and cred.status == "active" and auth.has_mfa(session, helena)
    step = keys.totp_step(now)
    assert not auth.check_totp(session, helena, keys.hotp(seed, step), now)  # used at confirm
    assert auth.check_totp(session, helena, keys.hotp(seed, step + 1), now)  # window of one step
    assert not auth.check_totp(session, helena, keys.hotp(seed, step + 1), now)  # each step once
    assert not auth.check_totp(session, helena, keys.hotp(seed, step + 3), now)
    assert auth.check_recovery(session, actor, helena, recovery[0], now)
    assert not auth.check_recovery(session, actor, helena, recovery[0], now)  # single use
    assert not auth.check_recovery(session, actor, helena, "nope", now)
    assert session.exec(select(Event).where(Event.action == "auth.recovery_code_used")).first()


def test_pin_rules_and_lock(session: Session, people: dict[str, Person]) -> None:
    sanna, actor = people["Sanna"], Actor.person(people["Sanna"])
    now = utcnow()
    for bad in ("111111", "123456", "654321", "12345", "abcdef"):
        assert auth.trivial_pin(bad) or not bad.isdigit() or len(bad) != 6
        with pytest.raises(ValueError):
            auth.set_pin(session, actor, sanna, bad, now)
    auth.set_pin(session, actor, sanna, "273916", now)
    assert auth.has_pin(session, sanna)
    assert auth.check_pin(session, sanna, "273916", IP, now)
    for _ in range(5):
        assert not auth.check_pin(session, sanna, "000000", IP, now)
    with pytest.raises(auth.Locked):
        auth.check_pin(session, sanna, "273916", IP, now)
    cred = session.exec(select(AuthCredential).where(AuthCredential.kind == "pin")).one()
    assert cred.status == "locked"
    auth.unlock_pin(session, actor, sanna, now)
    assert auth.check_pin(session, sanna, "273916", IP, now)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_credentials.py --no-cov -q`
Expected: ModuleNotFoundError `mia.core.auth`.

- [ ] **Step 3: Write `core/auth.py` (part 1)**

```python
"""Authentication services (ADR 011): rate limits, one-time codes, credentials, sessions,
devices and clients. Every write goes through store and emits an event; secrets never do.

Failures raise AuthError with one message, `invalid credentials`, whatever was wrong; Locked
when a limit holds. Times come in as arguments so tests can move the clock.
"""

import datetime as dt
import secrets
from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session, col, select

from mia.core import keys, store
from mia.core.models import (
    Actor,
    AuthAttempt,
    AuthClient,
    AuthCode,
    AuthCredential,
    AuthDevice,
    AuthSession,
    Person,
    Principal,
)

INVALID = "invalid credentials"
MFA_ROLES = frozenset({"owner", "admin", "accountant"})
CODE_TRIES = 5
CODE_TTL: dict[str, dt.timedelta] = {
    "invite": dt.timedelta(days=7),
    "self": dt.timedelta(minutes=10),
    "otp_login": dt.timedelta(minutes=5),
    "link_login": dt.timedelta(minutes=10),
    "mfa": dt.timedelta(minutes=5),
    "enrol": dt.timedelta(hours=24),
}
OTP_SENDS_PER_HOUR = 3
MIN_PASSWORD = 12
PIN_FAILURES = 5
STEP_UP_TTL = dt.timedelta(minutes=5)


class AuthError(RuntimeError):
    """A failed credential check. Routes answer 401 with the same body for every cause."""


class Locked(AuthError):
    """A limit from spec section 10 holds (or a PIN is locked)."""


class StepUpRequired(RuntimeError):
    """An app_only approval needs aal2 and a PIN entered in the last five minutes."""


@dataclass(frozen=True)
class Limit:
    count: int
    window: dt.timedelta
    block: dt.timedelta


M15, H1 = dt.timedelta(minutes=15), dt.timedelta(hours=1)
LIMITS: dict[str, Limit] = {
    "password": Limit(5, M15, M15),  # per (login, IP)
    "password_login": Limit(20, H1, M15),  # per login, any IP
    "ip": Limit(50, M15, M15),  # any kind, per IP
    "client_secret": Limit(10, M15, M15),
    "device": Limit(10, M15, M15),
    "link_code": Limit(5, H1, H1),
    "otp": Limit(5, dt.timedelta(minutes=5), dt.timedelta(minutes=5)),
    "mfa": Limit(5, dt.timedelta(minutes=5), dt.timedelta(minutes=5)),
}
EVENT_NAME = {"password": "login", "client_secret": "client", "link_code": "link"}


def auth_actor(branch_id: str = "") -> Actor:
    """The system principal that records failures before anyone is known."""
    return Actor(principal=Principal(type="system", id="auth"), branch_id=branch_id)


def login_key(login: str) -> str:
    """HMAC of a login, so a password typed into the login field never lands in a row."""
    return keys.code_hmac(normalise_login(login))[:32]


def attempt_key(subject: str, ip: str | None) -> str:
    """`<subject>@<ip>`; `@-` when the attempt has no IP (channel messages)."""
    return f"{subject}@{ip or '-'}"


# ---- attempts and limits ----------------------------------------------------------------


def _recent(
    session: Session,
    since: dt.datetime,
    *,
    kind: str | None = None,
    key: str | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
) -> list[AuthAttempt]:
    stmt = select(AuthAttempt).where(AuthAttempt.ok == False).where(col(AuthAttempt.created_at) > since)  # noqa: E712
    if kind is not None:
        stmt = stmt.where(AuthAttempt.kind == kind)
    if key is not None:
        stmt = stmt.where(AuthAttempt.key == key)
    if prefix is not None:
        stmt = stmt.where(col(AuthAttempt.key).startswith(prefix))
    if suffix is not None:
        stmt = stmt.where(col(AuthAttempt.key).endswith(suffix))
    return list(session.exec(stmt).all())


def _over(session: Session, now: dt.datetime, limit: Limit, **where: str | None) -> bool:
    rows = _recent(session, now - limit.window, **where)
    return len(rows) >= limit.count and max(r.created_at for r in rows) > now - limit.block


def throttled(session: Session, kind: str, key: str, now: dt.datetime) -> bool:
    """True when the IP, the login (passwords) or the exact (kind, key) is over its limit."""
    subject, ip = key.rsplit("@", 1)
    if ip != "-" and _over(session, now, LIMITS["ip"], suffix=f"@{ip}"):
        return True
    if kind == "password" and _over(
        session, now, LIMITS["password_login"], kind=kind, prefix=f"{subject}@"
    ):
        return True
    limit = LIMITS.get(kind)
    return limit is not None and _over(session, now, LIMITS[kind], kind=kind, key=key)


def record_attempt(
    session: Session,
    kind: str,
    key: str,
    ok: bool,
    now: dt.datetime,
    *,
    actor: Actor | None = None,
    action: str | None = None,
) -> AuthAttempt:
    """One attempt row and one event (`auth.<kind>_succeeded` or `_failed`)."""
    name = EVENT_NAME.get(kind, kind)
    row = AuthAttempt(kind=kind, key=key, ok=ok, created_at=now, updated_at=now)
    return store.insert(
        session,
        row,
        actor or auth_actor(),
        action=action or f"auth.{name}_{'succeeded' if ok else 'failed'}",
    )


def _locked_event(session: Session, kind: str, subject: str, now: dt.datetime) -> None:
    from mia.core import events

    events.emit(session, "auth.locked", ("login", subject), None, {"kind": kind}, auth_actor())


# ---- one-time codes ---------------------------------------------------------------------

CodeStatus = Literal["ok", "invalid", "expired", "used", "exhausted"]


@dataclass(frozen=True)
class CodeResult:
    status: CodeStatus
    row: AuthCode | None = None


def create_code(
    session: Session,
    actor: Actor,
    person: Person,
    purpose: str,
    now: dt.datetime,
    *,
    address: str | None = None,
    token: bool = False,
) -> str:
    """A new code for the person (6 digits, or a 43-character token). Returned once, stored
    only as an HMAC. Events never carry it."""
    while True:
        code = keys.new_token() if token else keys.numeric_code()
        digest = keys.code_hmac(code)
        if session.exec(select(AuthCode).where(AuthCode.code_hmac == digest)).first() is None:
            break
    store.insert(
        session,
        AuthCode(
            branch_id=person.branch_id,
            person_id=person.id,
            code_hmac=digest,
            purpose=purpose,
            address=address,
            expires_at=now + CODE_TTL[purpose],
            created_by=actor.principal.id,
        ),
        actor,
        action="auth.code_created",
    )
    return code


def check_code(
    session: Session, purpose: str, code: str, now: dt.datetime, *, person_id: str | None = None
) -> CodeResult:
    """Look a code up without consuming it. `ok` only when unused, in time and under 5 tries."""
    row = session.exec(
        select(AuthCode)
        .where(AuthCode.code_hmac == keys.code_hmac(code))
        .where(AuthCode.purpose == purpose)
    ).first()
    if row is None or (person_id is not None and row.person_id != person_id):
        return CodeResult("invalid")
    if row.used_at is not None:
        return CodeResult("used", row)
    if row.expires_at <= now:
        return CodeResult("expired", row)
    if row.tries >= CODE_TRIES:
        return CodeResult("exhausted", row)
    return CodeResult("ok", row)


def use_code(session: Session, actor: Actor, row: AuthCode, now: dt.datetime) -> AuthCode:
    """Consume a code (single use)."""
    return store.update(session, row, {"used_at": now}, actor, action="auth.code_used")


def _live_codes(
    session: Session, purpose: str, now: dt.datetime, *, address: str | None, person_id: str | None
) -> list[AuthCode]:
    stmt = (
        select(AuthCode)
        .where(AuthCode.purpose == purpose)
        .where(col(AuthCode.used_at).is_(None))
        .where(AuthCode.expires_at > now)
    )
    if address is not None:
        stmt = stmt.where(AuthCode.address == address)
    if person_id is not None:
        stmt = stmt.where(AuthCode.person_id == person_id)
    return list(session.exec(stmt.order_by(col(AuthCode.id).desc())).all())


def fail_code(
    session: Session,
    purpose: str,
    now: dt.datetime,
    *,
    address: str | None = None,
    person_id: str | None = None,
) -> None:
    """A wrong guess against the live code of an address or person: one more try used."""
    for row in _live_codes(session, purpose, now, address=address, person_id=person_id)[:1]:
        store.update(session, row, {"tries": row.tries + 1}, auth_actor(row.branch_id), action="auth.code_try")


def sends_in_last_hour(session: Session, purpose: str, address: str, now: dt.datetime) -> int:
    """How many codes went to an address in the last hour (the send limit)."""
    rows = session.exec(
        select(AuthCode)
        .where(AuthCode.purpose == purpose)
        .where(AuthCode.address == address)
        .where(col(AuthCode.created_at) > now - H1)
    ).all()
    return len(rows)


# ---- credentials -------------------------------------------------------------------------


def _credential(
    session: Session, person_id: str, kind: str, statuses: tuple[str, ...] = ("active",)
) -> AuthCredential | None:
    return session.exec(
        select(AuthCredential)
        .where(AuthCredential.person_id == person_id)
        .where(AuthCredential.kind == kind)
        .where(col(AuthCredential.status).in_(statuses))
        .order_by(col(AuthCredential.id).desc())
    ).first()


def normalise_login(login: str) -> str:
    """Lowercased, trimmed email."""
    return login.strip().lower()


def set_password(
    session: Session, actor: Actor, person: Person, login: str, password: str, now: dt.datetime
) -> AuthCredential:
    """Set or replace the person's password and login. Other sessions of the person are
    revoked by the caller (api) through revoke_sessions. Raises ValueError on a bad login,
    a short password or a login another person holds."""
    login = normalise_login(login)
    if "@" not in login or " " in login:
        raise ValueError("login must be an email address")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must have at least {MIN_PASSWORD} characters")
    other = session.exec(select(AuthCredential).where(AuthCredential.login == login)).first()
    if other is not None and other.person_id != person.id:
        raise ValueError("that email is already in use")
    changes = {"login": login, "secret_hash": keys.hash_secret(password), "status": "active"}
    row = _credential(session, person.id, "password", ("active", "revoked"))
    if row is None:
        return store.insert(
            session,
            AuthCredential(branch_id=person.branch_id, person_id=person.id, kind="password", **changes),
            actor,
            action="auth.password_set",
        )
    return store.update(session, row, changes, actor, action="auth.password_set")


def person_by_login(session: Session, login: str) -> tuple[Person, AuthCredential] | None:
    """The active person behind a login, with the password credential."""
    cred = session.exec(
        select(AuthCredential)
        .where(AuthCredential.login == normalise_login(login))
        .where(AuthCredential.kind == "password")
        .where(AuthCredential.status == "active")
    ).first()
    if cred is None:
        return None
    person = session.get(Person, cred.person_id)
    return (person, cred) if person is not None and person.status == "active" else None


def check_password(
    session: Session, login: str, password: str, ip: str, now: dt.datetime
) -> Person:
    """The person when login and password match. Limits are checked first; unknown logins
    verify against a dummy hash so they take as long as known ones."""
    subject = login_key(login)
    key = attempt_key(subject, ip)
    if throttled(session, "password", key, now):
        raise Locked(INVALID)
    found = person_by_login(session, login)
    stored = found[1].secret_hash if found and found[1].secret_hash else keys.dummy_hash()
    ok = keys.verify_secret(password, stored) and found is not None
    actor = Actor.person(found[0]) if found else None
    record_attempt(session, "password", key, ok, now, actor=actor if ok else None)
    if not ok:
        if _over(session, now, LIMITS["password_login"], kind="password", prefix=f"{subject}@"):
            _locked_event(session, "password", subject, now)
        raise AuthError(INVALID)
    assert found is not None
    store.update(session, found[1], {"last_used_at": now}, Actor.person(found[0]), action="auth.credential_used")
    return found[0]


def needs_mfa(session: Session, person: Person) -> bool:
    """Owner, admin and accountant always; anyone who enrolled TOTP."""
    return bool(MFA_ROLES & set(person.roles)) or has_mfa(session, person)


def has_mfa(session: Session, person: Person) -> bool:
    """True when an active TOTP credential exists."""
    return _credential(session, person.id, "totp") is not None


def enrol_totp(
    session: Session, actor: Actor, person: Person, now: dt.datetime
) -> tuple[AuthCredential, str]:
    """A pending TOTP credential and its otpauth URI. Earlier pending ones are revoked."""
    for old in session.exec(
        select(AuthCredential)
        .where(AuthCredential.person_id == person.id)
        .where(AuthCredential.kind == "totp")
        .where(AuthCredential.status == "pending")
    ):
        store.update(session, old, {"status": "revoked"}, actor, action="auth.mfa_enrolment_dropped")
    cred = store.insert(
        session,
        AuthCredential(
            branch_id=person.branch_id,
            person_id=person.id,
            kind="totp",
            status="pending",
            data={"nonce": secrets.token_hex(16), "last_step": 0},
        ),
        actor,
        action="auth.mfa_enrolment_started",
    )
    pw = _credential(session, person.id, "password")
    label = pw.login if pw and pw.login else person.name
    return cred, keys.totp_uri(keys.totp_seed(cred.id, cred.data["nonce"]), label)


def _totp_match(cred: AuthCredential, code: str, now: dt.datetime) -> int | None:
    seed = keys.totp_seed(cred.id, cred.data["nonce"])
    step = keys.totp_step(now)
    for candidate in (step - 1, step, step + 1):
        if candidate > int(cred.data.get("last_step", 0)) and secrets.compare_digest(
            keys.hotp(seed, candidate), code
        ):
            return candidate
    return None


def confirm_totp(
    session: Session, actor: Actor, cred: AuthCredential, code: str, now: dt.datetime
) -> list[str]:
    """Activate a pending TOTP credential with a first code; returns ten recovery codes,
    shown once. Raises AuthError on a wrong code."""
    step = _totp_match(cred, code, now)
    if cred.status != "pending" or step is None:
        raise AuthError(INVALID)
    store.update(
        session,
        cred,
        {"status": "active", "data": {**cred.data, "last_step": step}, "last_used_at": now},
        actor,
        action="auth.mfa_enrolled",
    )
    person_id, branch_id = cred.person_id, cred.branch_id
    for old in session.exec(
        select(AuthCredential)
        .where(AuthCredential.person_id == person_id)
        .where(AuthCredential.kind == "recovery_code")
        .where(AuthCredential.status == "active")
    ):
        store.update(session, old, {"status": "revoked"}, actor, action="auth.recovery_code_revoked")
    codes = [f"{secrets.randbelow(10**4):04d}-{secrets.randbelow(10**4):04d}" for _ in range(10)]
    for plain in codes:
        store.insert(
            session,
            AuthCredential(
                branch_id=branch_id,
                person_id=person_id,
                kind="recovery_code",
                secret_hash=keys.hash_secret(plain),
            ),
            actor,
            action="auth.recovery_code_created",
        )
    return codes


def check_totp(session: Session, person: Person, code: str, now: dt.datetime) -> bool:
    """True for a fresh code in the current step or one step either side. Each step once."""
    cred = _credential(session, person.id, "totp")
    if cred is None:
        return False
    step = _totp_match(cred, code, now)
    if step is None:
        return False
    store.update(
        session,
        cred,
        {"data": {**cred.data, "last_step": step}, "last_used_at": now},
        Actor.person(person),
        action="auth.mfa_succeeded",
    )
    return True


def check_recovery(
    session: Session, actor: Actor, person: Person, code: str, now: dt.datetime
) -> bool:
    """Consume one recovery code. False when none matches."""
    rows = session.exec(
        select(AuthCredential)
        .where(AuthCredential.person_id == person.id)
        .where(AuthCredential.kind == "recovery_code")
        .where(AuthCredential.status == "active")
    ).all()
    for row in rows:
        if row.secret_hash and keys.verify_secret(code, row.secret_hash):
            store.update(
                session, row, {"status": "used", "last_used_at": now}, actor, action="auth.recovery_code_used"
            )
            return True
    return False


def trivial_pin(pin: str) -> bool:
    """All one digit, or a straight run up or down (123456, 654321, 012345)."""
    digits = [int(c) for c in pin]
    steps = {b - a for a, b in zip(digits, digits[1:], strict=True)}
    return len(set(digits)) == 1 or steps == {1} or steps == {-1}


def set_pin(session: Session, actor: Actor, person: Person, pin: str, now: dt.datetime) -> AuthCredential:
    """Set or replace the 6-digit PIN. Raises ValueError for a non-numeric or trivial PIN."""
    if len(pin) != 6 or not pin.isdigit():
        raise ValueError("the PIN is 6 digits")
    if trivial_pin(pin):
        raise ValueError("choose a less obvious PIN")
    changes = {"secret_hash": keys.hash_secret(pin), "status": "active"}
    row = _credential(session, person.id, "pin", ("active", "locked"))
    if row is None:
        return store.insert(
            session,
            AuthCredential(branch_id=person.branch_id, person_id=person.id, kind="pin", **changes),
            actor,
            action="auth.pin_set",
        )
    return store.update(session, row, changes, actor, action="auth.pin_set")


def has_pin(session: Session, person: Person) -> bool:
    """True when the person has a PIN (active or locked)."""
    return _credential(session, person.id, "pin", ("active", "locked")) is not None


def check_pin(session: Session, person: Person, pin: str, ip: str, now: dt.datetime) -> bool:
    """True for the right PIN. Five failures since the last success lock it (Locked)."""
    cred = _credential(session, person.id, "pin", ("active", "locked"))
    if cred is None:
        return False
    if cred.status == "locked":
        raise Locked("pin locked")
    key = attempt_key(person.id, ip)
    ok = bool(cred.secret_hash) and keys.verify_secret(pin, cred.secret_hash or "")
    record_attempt(session, "pin", key, ok, now, actor=Actor.person(person))
    if ok:
        store.update(session, cred, {"last_used_at": now}, Actor.person(person), action="auth.credential_used")
        return True
    since = cred.last_used_at or cred.created_at
    failures = [
        r for r in _recent(session, since, kind="pin", prefix=f"{person.id}@")
    ]
    if len(failures) >= PIN_FAILURES:
        store.update(session, cred, {"status": "locked"}, Actor.person(person), action="auth.pin_locked")
    return False


def unlock_pin(session: Session, actor: Actor, person: Person, now: dt.datetime) -> None:
    """After a login with MFA or a phone code: a locked PIN is active again."""
    cred = _credential(session, person.id, "pin", ("locked",))
    if cred is not None:
        store.update(session, cred, {"status": "active", "last_used_at": now}, actor, action="auth.pin_unlocked")
```

`_recent` and `_over` take `since`/`now` as timezone-aware datetimes; `AuthAttempt.created_at` comes back aware through `TZDateTime`.

- [ ] **Step 4: Linking through core/auth**

Rewrite the code and attempt parts of `node/mia/channels/linking.py` so it keeps its public API (`create_code(session, actor, person, purpose) -> str`, `redeem(...) -> RedeemResult`, `revoke_all`, `identity_for`, `parse_link_text`, `invite_link`) but delegates:

```python
def create_code(session: Session, actor: Actor, person: Person, purpose: Purpose) -> str:
    """A new code for the person. The plain code is returned once and never stored."""
    try:
        return auth.create_code(session, actor, person, purpose, utcnow())
    except keys.MasterKeyError as exc:
        raise LinkingError(str(exc)) from exc


def _key(channel: str, address: str) -> str:
    return auth.attempt_key(f"{channel}:{address}", None)


def _record(session: Session, channel: str, address: str, ok: bool, now: dt.datetime) -> None:
    auth.record_attempt(
        session, "link_code", _key(channel, address), ok, now,
        actor=_channel_actor(channel), action="channel.link_attempt",
    )


def redeem(session, channel, address, code, now) -> RedeemResult:
    if auth.throttled(session, "link_code", _key(channel, address), now):
        _record(session, channel, address, False, now)
        return RedeemResult(status="blocked")
    result = auth.check_code(session, "invite", code, now)
    if result.status == "invalid":
        result = auth.check_code(session, "self", code, now)
    status: Status = {"ok": "linked", "invalid": "invalid", "expired": "expired", "used": "used", "exhausted": "invalid"}[result.status]
    row = result.row
    ... (the rest unchanged: person lookup, taken check, auth.use_code(session, actor, row, now) in place of store.update(... used_at ...), identity insert, _record)
```

Delete `_hmac`, `_blocked`, `VALID_FOR`, `MAX_FAILURES`, `LOCKOUT` and the `hashlib`/`hmac`/`secrets` imports from linking.py; import `from mia.core import auth, keys`. The `channel.code_created` action becomes `auth.code_created` and `channel.code_used` becomes `auth.code_used`: update the two assertions in `node/tests/channels/test_linking.py` accordingly.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest node/tests/auth node/tests/channels --no-cov -q` then the full check line.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "auth: attempts and lockouts, one-time codes, passwords, TOTP, recovery codes and PINs; linking uses them"
```

---

### Task 4: Sessions, devices and `current_auth` on every route

**Files:**
- Modify: `node/mia/core/auth.py` (sessions, devices, enrolment, revoke_everything)
- Create: `node/mia/api/deps.py`
- Modify: `node/mia/chat/router.py` (routes take `PersonAuth`; `DbSession` moves to deps; `resolve_actor` and `ActorHeader` deleted)
- Modify: `node/mia/api/main.py` (routes take `PersonAuth`; `/health` adds `auth_mode`; lifespan runs `check_mode`; `/persons` dev only)
- Modify: `node/mia/core/approvals.py:119-160` (`aal`, `stepped_up_at`)
- Modify: `node/mia/core/people.py` (`deactivate` revokes devices and sessions)
- Modify: `node/mia/cli.py` (`serve` runs `check_mode`; `decide` passes `stepped_up_at=utcnow()`)
- Modify: `node/tests/conftest.py` (`login` fixture), `node/tests/test_approvals.py`, `node/tests/test_tools.py`, `node/tests/test_architecture.py`, `node/tests/test_chat.py::test_actor_is_required_and_must_exist`
- Test: `node/tests/auth/test_sessions.py`

**Interfaces:**
- Consumes: Task 3 services.
- Produces in `mia.core.auth`: `ACCESS_TTL`, `OFFICE_IDLE`, `OFFICE_MAX`, `STAFF_IDLE`, `STAFF_MAX`, `CLIENT_TTL`; `Tokens(access: str, refresh: str | None, row: AuthSession)`; `issue_session(session, subject: Person | AuthClient, *, method, aal, ip, now, device=None) -> Tokens`; `verify_access(session, token, now) -> AuthSession | None`; `refresh_session(session, token, now) -> Tokens`; `revoke_session(session, actor, row, now) -> AuthSession`; `revoke_sessions(session, actor, subject_id, now, *, keep=None, device_id=None) -> int`; `bind_device(session, actor, person, kind, name, now) -> tuple[AuthDevice, str | None]`; `check_device(session, device_id, secret, ip, now) -> AuthDevice`; `revoke_device(session, actor, device, now) -> AuthDevice`; `revoke_everything(session, actor, person, now) -> int`; `start_enrolment(session, actor, person, now, *, reason="enrol") -> str`; `step_up(session, row, now) -> AuthSession`; `client_actor(client) -> Actor`.
- Produces in `mia.api.deps`: `get_session`, `DbSession`, `AuthContext(actor, person, client, method, aal, session_id, channel, via)`, `current_auth`, `CurrentAuth`, `current_person`, `PersonAuth`, `current_client`, `ClientAuth`, `client_ip(request) -> str`, `check_mode(settings) -> None`, `set_cookies(response, tokens)`, `clear_cookies(response)`, `public_origin() -> str`.
- `approvals.decide(session, approval_id, decider, outcome, reason=None, *, channel="app", aal="aal2", stepped_up_at: datetime | None = None)`: an `app_only` approval needs `channel == "app"`, `aal == "aal2"` and `stepped_up_at` within `STEP_UP_TTL` of now, else raises `StepUpRequired` (it subclasses `ApprovalError` here: `class StepUpRequired(ApprovalError)` is defined in approvals.py and re-exported by auth as the same object).
- conftest: `login(client, person, *, aal="aal2", method="password_totp", stepped_up=False, device=None) -> Tokens` sets `Authorization: Bearer` on the TestClient.

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_sessions.py`:

```python
"""Sessions: issue, verify, rotate, reuse detection, lifetimes, devices, the auth dependency,
the dev header rules and the approval step-up."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.core import auth
from mia.core.db import utcnow
from mia.core.models import Actor, AuthSession, Event, Person
from mia.settings import get_settings

IP = "203.0.113.5"


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


def test_issue_verify_rotate_and_reuse(session: Session, people: dict[str, Person]) -> None:
    helena = people["Helena"]
    now = utcnow()
    t = auth.issue_session(session, helena, method="password_totp", aal="aal2", ip=IP, now=now)
    assert t.refresh and auth.verify_access(session, t.access, now) is t.row
    assert auth.verify_access(session, t.access, now + auth.ACCESS_TTL) is None
    assert auth.verify_access(session, "nope", now) is None
    assert t.row.refresh_expires_at == now + auth.OFFICE_IDLE
    assert t.row.absolute_expires_at == now + auth.OFFICE_MAX
    t2 = auth.refresh_session(session, t.refresh, now + dt.timedelta(minutes=10))
    assert t2.row is t.row and t2.access != t.access and t2.refresh != t.refresh
    assert auth.verify_access(session, t.access, now + dt.timedelta(minutes=10)) is None
    with pytest.raises(auth.AuthError):  # the old refresh token again: reuse, session revoked
        auth.refresh_session(session, t.refresh, now + dt.timedelta(minutes=11))
    assert t.row.status == "revoked"
    assert session.exec(select(Event).where(Event.action == "auth.refresh_reused")).first()
    with pytest.raises(auth.AuthError):
        auth.refresh_session(session, t2.refresh, now + dt.timedelta(minutes=12))
    for e in session.exec(select(Event).where(Event.entity_type == "auth_sessions")):
        assert e.after is not None and e.after["access_hash"] == "<redacted>"


def test_refresh_after_absolute_expiry_revokes(session: Session, people: dict[str, Person]) -> None:
    now = utcnow()
    t = auth.issue_session(session, people["Helena"], method="password_totp", aal="aal2", ip=IP, now=now)
    assert t.refresh
    at = now + auth.OFFICE_MAX + dt.timedelta(seconds=1)
    with pytest.raises(auth.AuthError):
        auth.refresh_session(session, t.refresh, at)
    assert t.row.status == "revoked"
    idle = auth.issue_session(session, people["Helena"], method="password_totp", aal="aal2", ip=IP, now=now)
    assert idle.refresh
    with pytest.raises(auth.AuthError):
        auth.refresh_session(session, idle.refresh, now + auth.OFFICE_IDLE + dt.timedelta(seconds=1))


def test_staff_device_lifetimes_and_revoke(session: Session, people: dict[str, Person]) -> None:
    juha, actor = people["Juha"], Actor.person(people["Juha"])
    now = utcnow()
    device, secret = auth.bind_device(session, actor, juha, "mobile", "iPhone", now)
    assert secret and len(secret) == 43 and device.secret_hash != secret
    t = auth.issue_session(session, juha, method="phone_otp", aal="aal1", ip=IP, now=now, device=device)
    assert t.row.refresh_expires_at == now + auth.STAFF_IDLE
    assert t.row.absolute_expires_at == now + auth.STAFF_MAX
    assert auth.check_device(session, device.id, secret, IP, now) is device
    with pytest.raises(auth.AuthError):
        auth.check_device(session, device.id, "wrong", IP, now)
    auth.revoke_device(session, actor, device, now)
    assert auth.verify_access(session, t.access, now) is None and t.row.status == "revoked"
    with pytest.raises(auth.AuthError):
        auth.check_device(session, device.id, secret, IP, now)
    browser, none = auth.bind_device(session, actor, juha, "browser", "Safari", now)
    assert none is None
    auth.issue_session(session, juha, method="wa_link", aal="aal1", ip=IP, now=now, device=browser)
    assert auth.revoke_everything(session, actor, juha, now) == 1  # one live session
    assert browser.status == "revoked"


def test_client_sessions_have_no_refresh(session: Session, people: dict[str, Person]) -> None:
    from mia.core.models import AuthClient

    helena = people["Helena"]
    client = AuthClient(
        branch_id=helena.branch_id, name="n", client_id="mia_x", secret_hash="s", roles=["dispatcher"], created_by=helena.id
    )
    session.add(client)  # a bare row for this unit test; Task 9 adds the service
    session.flush()
    now = utcnow()
    t = auth.issue_session(session, client, method="client", aal="client", ip=IP, now=now)
    assert t.refresh is None and t.row.access_expires_at == now + auth.CLIENT_TTL
    assert auth.client_actor(client).principal.id == "client:mia_x"


# ---- the dependency ----------------------------------------------------------------------


def test_bearer_session_is_the_actor(client: TestClient, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Juha"])
    res = client.post("/chat", json={"text": "hi"})
    assert res.status_code == 200
    res = client.get("/notifications")
    assert res.status_code == 200


def test_header_is_refused_in_required_mode(
    client: TestClient, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    res = client.post("/chat", json={"text": "hi"}, headers={"X-Mia-Actor": people["Juha"].id})
    assert res.status_code == 401 and res.json()["detail"] == "invalid credentials"


def test_dev_header_needs_a_loopback_peer_without_cloudflare(
    client: TestClient, people: dict[str, Person]
) -> None:
    juha = people["Juha"].id
    assert client.post("/chat", json={"text": "hi"}, headers={"X-Mia-Actor": juha}).status_code == 200
    via_cf = {"X-Mia-Actor": juha, "CF-Connecting-IP": "198.51.100.7"}
    assert client.post("/chat", json={"text": "hi"}, headers=via_cf).status_code == 401
    assert client.post("/auth/logout", headers={"X-Mia-Actor": juha}).status_code == 401
    assert session_events_count_dev_header(client, juha) == 1


def session_events_count_dev_header(client: TestClient, person_id: str) -> int:
    """auth.dev_header_used is written once per process and person."""
    from mia.core.db import session_scope

    client.post("/chat", json={"text": "again"}, headers={"X-Mia-Actor": person_id})
    with session_scope() as s:
        rows = s.exec(select(Event).where(Event.action == "auth.dev_header_used")).all()
        return len([r for r in rows if r.actor_id == person_id])


def test_inactive_person_gets_403_and_roles_are_read_fresh(
    client: TestClient, people: dict[str, Person], session: Session, login
) -> None:  # type: ignore[no-untyped-def]
    from mia.core import people as people_service, store

    sanna = people["Sanna"]
    login(client, sanna)
    assert client.get("/notifications").status_code == 200
    store.update(session, sanna, {"roles": ["staff"]}, Actor.person(people["Helena"]))
    session.commit()
    assert client.get("/notifications").status_code == 200  # still signed in, roles now staff
    people_service.deactivate(session, Actor.person(people["Helena"]), sanna)
    session.commit()
    assert client.get("/notifications").status_code == 403


def test_enrol_session_reaches_only_auth_routes(client: TestClient, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Helena"], aal="enrol", method="enrol")
    assert client.post("/chat", json={"text": "hi"}).status_code == 403
    assert client.get("/auth/me").status_code == 200


def test_dev_mode_refuses_a_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from mia.api.deps import check_mode

    monkeypatch.setenv("MIA_PUBLIC_URL", "https://mia.example.fi")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="MIA_AUTH_MODE=dev"):
        check_mode(get_settings())
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    check_mode(get_settings())


def test_client_ip_trusts_cf_header_only_from_a_trusted_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from mia.api.deps import client_ip

    req = SimpleNamespace(client=SimpleNamespace(host="172.18.0.9"), headers={"cf-connecting-ip": "198.51.100.7"})
    assert client_ip(req) == "172.18.0.9"  # type: ignore[arg-type]
    monkeypatch.setenv("MIA_TRUSTED_PROXIES", "172.18.0.9, 10.0.0.1")
    get_settings.cache_clear()
    assert client_ip(req) == "198.51.100.7"  # type: ignore[arg-type]


# ---- approvals need a step-up ------------------------------------------------------------


def test_app_only_approval_needs_aal2_and_a_fresh_step_up(
    session: Session, people: dict[str, Person]
) -> None:
    from mia.core import approvals

    helena = Actor.person(people["Helena"])
    row = approvals.request(
        session, Actor.person(people["Sanna"]), "dispatcher.cover_override", "visit", "V",
        "x", {}, ["admin"], channel="app_only",
    )
    now = utcnow()
    for kw in (
        {"aal": "aal1", "stepped_up_at": now},
        {"aal": "aal2", "stepped_up_at": None},
        {"aal": "aal2", "stepped_up_at": now - auth.STEP_UP_TTL - dt.timedelta(seconds=1)},
        {"aal": "aal2", "stepped_up_at": now, "channel": "whatsapp"},
    ):
        with pytest.raises(approvals.ApprovalError):
            approvals.decide(session, row.id, helena, "approved", **kw)  # type: ignore[arg-type]
    denied = session.exec(select(Event).where(Event.action == "approval.refused")).all()
    assert len(denied) == 4
    approvals.decide(session, row.id, helena, "approved", aal="aal2", stepped_up_at=now)
    assert row.status == "approved"
```

Check the exact signature of `approvals.request` in `node/mia/core/approvals.py` before writing the test call and adapt the positional arguments to it (keep `channel="app_only"`).

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_sessions.py --no-cov -q`
Expected: AttributeError `issue_session`, then ImportError `mia.api.deps`.

- [ ] **Step 3: Sessions, devices, enrolment in `core/auth.py`**

Append to `node/mia/core/auth.py`:

```python
# ---- sessions ----------------------------------------------------------------------------

ACCESS_TTL = dt.timedelta(minutes=15)
OFFICE_IDLE, OFFICE_MAX = dt.timedelta(hours=12), dt.timedelta(days=7)
STAFF_IDLE, STAFF_MAX = dt.timedelta(days=30), dt.timedelta(days=90)
CLIENT_TTL = dt.timedelta(hours=1)


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str | None
    row: AuthSession


def client_actor(client: AuthClient) -> Actor:
    """An outside client acts as agent `client:<client_id>` with its registered roles."""
    return Actor(
        principal=Principal(type="agent", id=f"client:{client.client_id}", roles=list(client.roles)),
        branch_id=client.branch_id,
    )


def _subject_actor(subject: Person | AuthClient) -> Actor:
    return Actor.person(subject) if isinstance(subject, Person) else client_actor(subject)


def issue_session(
    session: Session,
    subject: Person | AuthClient,
    *,
    method: str,
    aal: str,
    ip: str,
    now: dt.datetime,
    device: AuthDevice | None = None,
) -> Tokens:
    """A new session. People get a rotating refresh token (office lifetimes, or staff
    lifetimes on a bound mobile device); clients get one hour and no refresh. The event is
    `auth.login_succeeded` (`auth.client_token_issued` for clients)."""
    person = isinstance(subject, Person)
    access, refresh = keys.new_token(), keys.new_token() if person else None
    mobile = device is not None and device.kind == "mobile"
    idle, longest = (STAFF_IDLE, STAFF_MAX) if mobile else (OFFICE_IDLE, OFFICE_MAX)
    row = AuthSession(
        branch_id=subject.branch_id,
        subject_type="person" if person else "client",
        subject_id=subject.id,
        device_id=device.id if device else None,
        method=method,
        aal=aal,
        access_hash=keys.token_hash(access),
        access_expires_at=now + (ACCESS_TTL if person else CLIENT_TTL),
        refresh_hash=keys.token_hash(refresh) if refresh else None,
        refresh_expires_at=now + idle if person else None,
        absolute_expires_at=now + longest if person else None,
        ip=ip,
    )
    store.insert(
        session,
        row,
        _subject_actor(subject),
        action="auth.login_succeeded" if person else "auth.client_token_issued",
    )
    return Tokens(access, refresh, row)


def verify_access(session: Session, token: str, now: dt.datetime) -> AuthSession | None:
    """The active, unexpired session behind an access token. A read, never a write."""
    row = session.exec(
        select(AuthSession).where(AuthSession.access_hash == keys.token_hash(token))
    ).first()
    if row is None or row.status != "active" or row.access_expires_at <= now:
        return None
    return row


def _session_actor(session: Session, row: AuthSession) -> Actor:
    if row.subject_type == "client":
        client = session.get(AuthClient, row.subject_id)
        return client_actor(client) if client else auth_actor(row.branch_id)
    person = session.get(Person, row.subject_id)
    return Actor.person(person) if person else auth_actor(row.branch_id)


def refresh_session(session: Session, token: str, now: dt.datetime) -> Tokens:
    """Rotate the tokens of a session. A refresh token presented twice revokes the session
    (`auth.refresh_reused`); an idle or absolute expiry revokes it too."""
    digest = keys.token_hash(token)
    row = session.exec(select(AuthSession).where(AuthSession.refresh_hash == digest)).first()
    if row is None:
        reused = session.exec(
            select(AuthSession).where(AuthSession.prev_refresh_hash == digest)
        ).first()
        if reused is not None and reused.status == "active":
            store.update(
                session, reused, {"status": "revoked"}, _session_actor(session, reused), action="auth.refresh_reused"
            )
        raise AuthError(INVALID)
    actor = _session_actor(session, row)
    expired = (row.refresh_expires_at or now) <= now or (row.absolute_expires_at or now) <= now
    if row.status != "active" or expired:
        if row.status == "active":
            store.update(session, row, {"status": "revoked"}, actor, action="auth.session_expired")
        raise AuthError(INVALID)
    access, refresh = keys.new_token(), keys.new_token()
    device = session.get(AuthDevice, row.device_id) if row.device_id else None
    idle = STAFF_IDLE if device is not None and device.kind == "mobile" else OFFICE_IDLE
    assert row.absolute_expires_at is not None
    store.update(
        session,
        row,
        {
            "access_hash": keys.token_hash(access),
            "access_expires_at": now + ACCESS_TTL,
            "prev_refresh_hash": row.refresh_hash,
            "refresh_hash": keys.token_hash(refresh),
            "refresh_expires_at": min(now + idle, row.absolute_expires_at),
        },
        actor,
        action="auth.session_refreshed",
    )
    if device is not None:
        store.update(session, device, {"last_seen_at": now}, actor, action="auth.device_seen")
    return Tokens(access, refresh, row)


def revoke_session(session: Session, actor: Actor, row: AuthSession, now: dt.datetime) -> AuthSession:
    """End one session."""
    return store.update(session, row, {"status": "revoked"}, actor, action="auth.session_revoked")


def revoke_sessions(
    session: Session,
    actor: Actor,
    subject_id: str,
    now: dt.datetime,
    *,
    keep: str | None = None,
    device_id: str | None = None,
) -> int:
    """End every active session of a person or client (optionally only on one device,
    optionally keeping one). Returns how many ended."""
    stmt = (
        select(AuthSession)
        .where(AuthSession.subject_id == subject_id)
        .where(AuthSession.status == "active")
    )
    if device_id is not None:
        stmt = stmt.where(AuthSession.device_id == device_id)
    rows = [r for r in session.exec(stmt).all() if r.id != keep]
    for row in rows:
        revoke_session(session, actor, row, now)
    return len(rows)


def step_up(session: Session, row: AuthSession, now: dt.datetime) -> AuthSession:
    """Mark a session stepped up (PIN entered) at `now`."""
    return store.update(session, row, {"stepped_up_at": now}, _session_actor(session, row), action="auth.step_up")


# ---- devices -----------------------------------------------------------------------------


def bind_device(
    session: Session, actor: Actor, person: Person, kind: str, name: str, now: dt.datetime
) -> tuple[AuthDevice, str | None]:
    """A new device row. Mobile devices get a device secret, returned once."""
    secret = keys.new_token() if kind == "mobile" else None
    row = store.insert(
        session,
        AuthDevice(
            branch_id=person.branch_id,
            person_id=person.id,
            kind=kind,
            name=name[:80],
            secret_hash=keys.token_hash(secret) if secret else None,
            last_seen_at=now,
        ),
        actor,
        action="auth.device_bound",
    )
    return row, secret


def check_device(
    session: Session, device_id: str, secret: str, ip: str, now: dt.datetime
) -> AuthDevice:
    """The active device when the secret matches. Limits per device and IP apply."""
    key = attempt_key(device_id, ip)
    if throttled(session, "device", key, now):
        raise Locked(INVALID)
    row = session.get(AuthDevice, device_id)
    ok = (
        row is not None
        and row.status == "active"
        and row.secret_hash is not None
        and secrets.compare_digest(row.secret_hash, keys.token_hash(secret))
    )
    record_attempt(session, "device", key, ok, now)
    if not ok or row is None:
        raise AuthError(INVALID)
    return row


def revoke_device(session: Session, actor: Actor, device: AuthDevice, now: dt.datetime) -> AuthDevice:
    """Revoke a device and end its sessions at once."""
    revoke_sessions(session, actor, device.person_id, now, device_id=device.id)
    return store.update(
        session,
        device,
        {"status": "revoked", "revoked_at": now, "revoked_by": actor.principal.id},
        actor,
        action="auth.device_revoked",
    )


def revoke_everything(session: Session, actor: Actor, person: Person, now: dt.datetime) -> int:
    """Every device and session of the person ends. Returns the number of sessions ended."""
    for device in session.exec(
        select(AuthDevice).where(AuthDevice.person_id == person.id).where(AuthDevice.status == "active")
    ).all():
        revoke_device(session, actor, device, now)
    return revoke_sessions(session, actor, person.id, now)


def start_enrolment(
    session: Session, actor: Actor, person: Person, now: dt.datetime, *, reason: str = "enrol"
) -> str:
    """A 24-hour enrolment token (set password, enrol TOTP). Every session of the person
    ends. `reason="reset"` also writes `auth.reset` with both actors."""
    revoke_everything(session, actor, person, now)
    if reason == "reset":
        from mia.core import events

        events.emit(session, "auth.reset", person, None, {"by": actor.principal.id}, actor)
    return create_code(session, actor, person, "enrol", now, token=True)
```

- [ ] **Step 4: `api/deps.py`**

```python
"""FastAPI dependencies: the database session and the authenticated actor (ADR 011).

`current_auth` resolves, in order, a bearer token, the `mia_at` cookie and, in dev mode only,
the X-Mia-Actor header from a loopback peer without Cloudflare headers. No credential is 401,
an inactive person 403. Roles come from the person row on every request, never from a token.
"""

import ipaddress
import logging
from collections.abc import Iterator
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from mia.core import auth
from mia.core.db import session_scope, utcnow
from mia.core.models import Actor, AuthClient, Person
from mia.settings import Settings, get_settings

log = logging.getLogger(__name__)
ACCESS_COOKIE, REFRESH_COOKIE = "mia_at", "mia_rt"
_dev_header_seen: set[str] = set()


def get_session() -> Iterator[Session]:
    """One session per request: commits on success, rolls back on error, always closes."""
    with session_scope() as session:
        yield session


# "function": commit before the response is sent, so a failed commit is a 500, not a lost write.
DbSession = Annotated[Session, Depends(get_session, scope="function")]


class AuthContext(BaseModel):
    """Who is acting on this request and how they were verified."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    actor: Actor
    person: Person | None = None
    client: AuthClient | None = None
    method: str  # password_totp, password, phone_otp, device, wa_link, client, enrol, dev
    aal: str  # aal1, aal2, client, enrol, dev
    session_id: str | None = None
    channel: str = "app"
    via: Literal["bearer", "cookie", "header"]
    stepped_up_at: object | None = None  # datetime | None; object keeps pydantic out of it


def public_origin() -> str:
    """scheme://host[:port] of MIA_PUBLIC_URL (the cookie and CSRF origin)."""
    parts = urlsplit(get_settings().MIA_PUBLIC_URL)
    return f"{parts.scheme}://{parts.netloc}"


def client_ip(request: Request) -> str:
    """The TCP peer, or CF-Connecting-IP when the peer is a trusted proxy."""
    peer = request.client.host if request.client else ""
    trusted = {p.strip() for p in get_settings().MIA_TRUSTED_PROXIES.split(",") if p.strip()}
    if peer in trusted:
        return request.headers.get("cf-connecting-ip", peer)
    return peer


def _loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    if host == "testclient":  # Starlette's TestClient
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_mode(settings: Settings) -> None:
    """Refuse dev mode on anything but localhost (called at startup)."""
    host = urlsplit(settings.MIA_PUBLIC_URL).hostname or ""
    if settings.MIA_AUTH_MODE == "dev" and host not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError(
            f"MIA_AUTH_MODE=dev accepts the X-Mia-Actor header; refuse to serve {settings.MIA_PUBLIC_URL}"
        )


def _credential(request: Request) -> tuple[str, Literal["bearer", "cookie"]] | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip(), "bearer"
    cookie = request.cookies.get(ACCESS_COOKIE)
    return (cookie, "cookie") if cookie else None


def _dev_header(request: Request, session: Session) -> AuthContext | None:
    settings = get_settings()
    actor_id = request.headers.get("x-mia-actor")
    if settings.MIA_AUTH_MODE != "dev" or not actor_id or request.url.path.startswith("/auth/"):
        return None
    if not _loopback(request) or "cf-connecting-ip" in request.headers or "cf-ray" in request.headers:
        return None
    person = session.get(Person, actor_id)
    if person is None or person.status != "active":
        raise HTTPException(403, "unknown actor")
    if person.id not in _dev_header_seen:
        from mia.core import events

        _dev_header_seen.add(person.id)
        events.emit(session, "auth.dev_header_used", person, None, None, Actor.person(person))
    return AuthContext(actor=Actor.person(person), person=person, method="dev", aal="dev", via="header")


def current_auth(request: Request, session: DbSession) -> AuthContext:
    """The verified actor of the request (see the module docstring)."""
    found = _credential(request)
    if found is None:
        ctx = _dev_header(request, session)
        if ctx is None:
            raise HTTPException(401, auth.INVALID)
        return ctx
    token, via = found
    if via == "cookie" and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("origin") != public_origin():
            raise HTTPException(403, "origin not allowed")
    row = auth.verify_access(session, token, utcnow())
    if row is None:
        raise HTTPException(401, auth.INVALID)
    if row.subject_type == "client":
        client = session.get(AuthClient, row.subject_id)
        if client is None or client.status != "active":
            raise HTTPException(401, auth.INVALID)
        return AuthContext(
            actor=auth.client_actor(client), client=client, method=row.method, aal=row.aal,
            session_id=row.id, via=via,
        )
    person = session.get(Person, row.subject_id)
    if person is None or person.status != "active":
        raise HTTPException(403, "person is not active")
    return AuthContext(
        actor=Actor.person(person), person=person, method=row.method, aal=row.aal,
        session_id=row.id, via=via, stepped_up_at=row.stepped_up_at,
    )


CurrentAuth = Annotated[AuthContext, Depends(current_auth)]


def current_person(auth_ctx: CurrentAuth) -> AuthContext:
    """A signed-in person with a full session: clients and enrolment sessions get 403."""
    if auth_ctx.person is None:
        raise HTTPException(403, "a person must be signed in")
    if auth_ctx.aal == "enrol":
        raise HTTPException(403, "finish enrolment first")
    return auth_ctx


PersonAuth = Annotated[AuthContext, Depends(current_person)]


def current_client(auth_ctx: CurrentAuth) -> AuthContext:
    """An outside client with a client token; anything else is 401 (ADR 008)."""
    if auth_ctx.client is None:
        raise HTTPException(401, auth.INVALID)
    return auth_ctx


ClientAuth = Annotated[AuthContext, Depends(current_client)]


def set_cookies(response: Response, tokens: auth.Tokens) -> None:
    """Access and refresh cookies: HttpOnly, SameSite=Strict, Secure when the node is https."""
    secure = public_origin().startswith("https://")
    response.set_cookie(
        ACCESS_COOKIE, tokens.access, max_age=int(auth.ACCESS_TTL.total_seconds()), path="/",
        httponly=True, secure=secure, samesite="strict",
    )
    if tokens.refresh:
        response.set_cookie(
            REFRESH_COOKIE, tokens.refresh, max_age=int(auth.OFFICE_MAX.total_seconds()),
            path="/auth/refresh", httponly=True, secure=secure, samesite="strict",
        )


def clear_cookies(response: Response) -> None:
    """Drop both cookies."""
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/auth/refresh")
```

`stepped_up_at` typed as `object | None` is awkward; use `datetime | None` with `from datetime import datetime` instead (pydantic handles it). Do that.

- [ ] **Step 5: Switch the routes**

`node/mia/chat/router.py`: delete `ChatRequest.actor_id`, `resolve_actor`, `ActorHeader`, `get_session`, `DbSession` and the module docstring's header paragraph; `from mia.api.deps import DbSession, PersonAuth`; each route takes `auth: PersonAuth` instead of `x_mia_actor: ActorHeader = None` and uses `person = auth.person` (assert it is not None for mypy: `person = _person(auth)` where `def _person(auth: AuthContext) -> Person: assert auth.person is not None; return auth.person`). `/chat` tests that posted `actor_id` in the body now send the header (dev mode) or log in.

`node/mia/api/main.py`: import `DbSession, PersonAuth, check_mode` from `mia.api.deps`; `decide` and `notifications` take `auth: PersonAuth`; `decide` calls `approvals.decide(session, approval_id, auth.actor, body.outcome, body.reason, channel=auth.channel, aal=auth.aal, stepped_up_at=auth.stepped_up_at)` and maps `approvals.StepUpRequired` to `HTTPException(403, "step_up_required")` before the generic `ApprovalError` 403; `/persons` raises 404 unless `get_settings().MIA_AUTH_MODE == "dev"`; `/health` adds `"auth_mode": get_settings().MIA_AUTH_MODE`; `lifespan` calls `check_mode(get_settings())` first. `app.include_router(auth_router)` is added in Task 5.

`node/mia/core/approvals.py`: add `class StepUpRequired(ApprovalError): """An app_only approval needs aal2 and a PIN entered in the last five minutes."""`, extend `decide` with `aal: str = "aal2", stepped_up_at: datetime | None = None`, and replace the `app_only` check with:

```python
    if approval.channel == "app_only":
        fresh = stepped_up_at is not None and utcnow() - stepped_up_at <= STEP_UP_TTL
        if channel != "app":
            _refused(session, approval, decider, "this approval can only be decided in the Mia app")
        if aal != "aal2" or not fresh:
            _refused(session, approval, decider, "step_up_required", StepUpRequired)
```

with `STEP_UP_TTL = timedelta(minutes=5)` in approvals.py (auth imports it from there: in `core/auth.py` replace its own `STEP_UP_TTL` with `from mia.core.approvals import STEP_UP_TTL, StepUpRequired` if that import is cycle-free; approvals does not import auth, so it is) and

```python
def _refused(session: Session, approval: Approval, decider: Actor, why: str, exc: type[ApprovalError] = ApprovalError) -> None:
    events.emit(session, "approval.refused", approval, None, {"reason": why}, decider, approval_id=approval.id)
    raise exc(why)
```

Keep the other `ApprovalError` raises as they are (they already have tests).

`node/mia/core/people.py` `deactivate`: also `from mia.core.auth import revoke_everything` and call `revoke_everything(session, actor, person, utcnow())` before `revoke_all`.

`node/mia/cli.py`: `serve` calls `check_mode(get_settings())` (import from `mia.api.deps`) before `uvicorn.run`; `decide` passes `stepped_up_at=utcnow()` (shell access is full access; the event carries the CLI person as decider).

`node/tests/conftest.py`: add

```python
@pytest.fixture
def login(session: Session):  # type: ignore[no-untyped-def]
    """Sign a person in on a TestClient through the service (bearer token on every request)."""
    from mia.core import auth as auth_service
    from mia.core.db import utcnow

    def _login(client, person, *, aal: str = "aal2", method: str = "password_totp", stepped_up: bool = False, device=None):  # type: ignore[no-untyped-def]
        now = utcnow()
        tokens = auth_service.issue_session(session, person, method=method, aal=aal, ip="127.0.0.1", now=now, device=device)
        if stepped_up:
            auth_service.step_up(session, tokens.row, now)
        session.commit()
        client.headers["Authorization"] = f"Bearer {tokens.access}"
        return tokens

    return _login
```

`node/tests/test_approvals.py` and `node/tests/test_tools.py`: every `decide(...)` of an `app_only` approval (cover overrides) passes `stepped_up_at=utcnow()`; other approvals need nothing. `node/tests/test_chat.py::test_actor_is_required_and_must_exist`: drop the `actor_id` cases (the body field is gone), keep 401 without a header, 403 for an unknown header, 404 for another person's thread.

`node/tests/test_architecture.py` add:

```python
def test_x_mia_actor_is_read_only_by_the_dev_dependency() -> None:
    """ADR 011: the header is accepted in one place, in dev mode."""
    offenders = [
        str(p) for p in _py_files() if "x-mia-actor" in p.read_text().lower() and p != MIA / "api" / "deps.py"
    ]
    assert offenders == []


def test_every_route_depends_on_auth_or_is_public() -> None:
    """Every route except /health, /, /auth/*, webhooks and /.well-known takes CurrentAuth."""
    from mia.api.main import app

    public = {"/health", "/", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    for route in app.routes:
        path = getattr(route, "path", "")
        if path in public or path.startswith(("/auth/", "/channels/", "/.well-known/")):
            continue
        names = {d.call.__name__ for d in route.dependant.dependencies}  # type: ignore[attr-defined]
        assert names & {"current_auth", "current_person", "current_client"}, path
```

- [ ] **Step 6: Run the tests, then the full suite**

Run: `uv run pytest node/tests/auth --no-cov -q`, then the full check line.
Expected: PASS. The chat tests still use the header in dev mode, which conftest sets.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "auth: sessions, devices, current_auth on every route, dev header rules, approvals need a step-up"
```

---

### Task 5: Office login (password, TOTP, recovery codes, refresh, logout, cookies, login page)

**Files:**
- Create: `node/mia/api/auth.py`
- Modify: `node/mia/api/main.py` (include the router), `node/mia/static/index.html` (login form in required mode), `node/mia/i18n/strings.py` (auth strings for the page are English only, inline; no new i18n keys needed because the dev page is English)
- Test: `node/tests/auth/test_office_login.py`

**Interfaces:**
- Consumes: Tasks 3 and 4.
- Produces routes (JSON in, JSON out, cookies set when `?cookie=1` or `X-Mia-Client: web` header is present, bearer tokens in the body otherwise):
  - `POST /auth/login {email, password}` -> `{mfa_required: true, mfa_token}` or `{access, refresh, aal, enrol: bool}` (+cookies). Enrol is true when MFA is required but not enrolled (session aal `enrol`).
  - `POST /auth/mfa {mfa_token, code}` -> tokens (code is TOTP or a recovery code `1234-5678`).
  - `POST /auth/mfa/enrol` (person or enrol session) -> `{uri}`; `POST /auth/mfa/confirm {code}` -> `{recovery_codes: [...]}` and, from an enrol session, fresh aal2 tokens.
  - `POST /auth/password {password, email?}` (person session or enrol session): sets the password; other sessions end.
  - `POST /auth/refresh {refresh?}` (body or `mia_rt` cookie) -> tokens.
  - `POST /auth/logout` -> `{ok: true}`, revokes the session (and its device, if mobile) and clears cookies.
  - `GET /auth/me` -> `{person_id, name, roles, aal, method, stepped_up: bool, mfa: bool, pin: bool}`.
- Pydantic bodies: `LoginIn(email: str, password: str)`, `MfaIn(mfa_token: str, code: str)`, `CodeIn(code: str)`, `PasswordIn(password: str, email: str | None = None)`, `RefreshIn(refresh: str | None = None)`; `TokensOut(access: str, refresh: str | None, aal: str, enrol: bool = False)`.

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_office_login.py`:

```python
"""Office login over HTTP: password then TOTP, enrolment, recovery codes, refresh, logout,
cookies and the CSRF origin check."""

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.core import auth, keys
from mia.core.db import utcnow
from mia.core.models import Actor, AuthCredential, Event, Person
from mia.settings import get_settings

PW = "correct horse battery"


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


@pytest.fixture
def owner(session: Session, people: dict[str, Person]) -> Person:
    helena = people["Helena"]
    auth.set_password(session, Actor.person(helena), helena, "helena@example.fi", PW, utcnow())
    session.commit()
    return helena


def _totp_now(session: Session, person: Person) -> str:
    cred = session.exec(
        select(AuthCredential).where(AuthCredential.person_id == person.id).where(AuthCredential.kind == "totp")
    ).one()
    session.refresh(cred)
    return keys.hotp(keys.totp_seed(cred.id, cred.data["nonce"]), keys.totp_step(utcnow()) + 1)


def _enrol(client: TestClient, session: Session, person: Person) -> list[str]:
    assert client.post("/auth/mfa/enrol").status_code == 200
    res = client.post("/auth/mfa/confirm", json={"code": _totp_now(session, person)})
    assert res.status_code == 200, res.text
    return res.json()["recovery_codes"]  # type: ignore[no-any-return]


def test_owner_without_mfa_gets_an_enrol_session_then_full_access(
    client: TestClient, session: Session, owner: Person
) -> None:
    res = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW})
    assert res.status_code == 200 and res.json()["enrol"] is True and res.json()["aal"] == "enrol"
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.post("/chat", json={"text": "hi"}).status_code == 403
    res = client.post("/auth/mfa/enrol")
    assert res.json()["uri"].startswith("otpauth://")
    res = client.post("/auth/mfa/confirm", json={"code": "000000"})
    assert res.status_code == 401
    res = client.post("/auth/mfa/confirm", json={"code": _totp_now(session, owner)})
    body = res.json()
    assert len(body["recovery_codes"]) == 10 and body["aal"] == "aal2"
    client.headers["Authorization"] = f"Bearer {body['access']}"
    assert client.get("/auth/me").json()["mfa"] is True
    assert client.post("/chat", json={"text": "hi"}).status_code == 200


def test_login_normalises_email(client: TestClient, session: Session, owner: Person, login) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    _enrol(client, session, owner)
    client.headers.pop("Authorization")
    res = client.post("/auth/login", json={"email": " Helena@Example.FI ", "password": PW})
    assert res.status_code == 200 and res.json()["mfa_required"] is True


def test_password_then_totp_then_refresh_then_logout(
    client: TestClient, session: Session, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    recovery = _enrol(client, session, owner)
    client.headers.pop("Authorization")
    res = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW})
    mfa_token = res.json()["mfa_token"]
    assert client.post("/auth/mfa", json={"mfa_token": mfa_token, "code": "000000"}).status_code == 401
    res = client.post("/auth/mfa", json={"mfa_token": mfa_token, "code": _totp_now(session, owner)})
    assert res.status_code == 200 and res.json()["aal"] == "aal2"
    tokens = res.json()
    assert client.post("/auth/mfa", json={"mfa_token": mfa_token, "code": "1"}).status_code == 401  # used
    client.headers["Authorization"] = f"Bearer {tokens['access']}"
    me = client.get("/auth/me").json()
    assert me["person_id"] == owner.id and me["method"] == "password_totp"
    res = client.post("/auth/refresh", json={"refresh": tokens["refresh"]})
    assert res.status_code == 200 and res.json()["access"] != tokens["access"]
    assert client.post("/auth/refresh", json={"refresh": tokens["refresh"]}).status_code == 401
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.post("/auth/logout").json() == {"ok": True}
    assert client.get("/auth/me").status_code == 401
    # Recovery code in place of TOTP, once.
    res = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW})
    res = client.post("/auth/mfa", json={"mfa_token": res.json()["mfa_token"], "code": recovery[0]})
    assert res.status_code == 200
    res = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW})
    assert client.post("/auth/mfa", json={"mfa_token": res.json()["mfa_token"], "code": recovery[0]}).status_code == 401


def test_wrong_password_unknown_login_and_lockout_look_the_same(client: TestClient, owner: Person) -> None:
    bad = client.post("/auth/login", json={"email": "helena@example.fi", "password": "nope"})
    unknown = client.post("/auth/login", json={"email": "x@example.fi", "password": "nope"})
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()
    for _ in range(5):
        client.post("/auth/login", json={"email": "helena@example.fi", "password": "nope"})
    locked = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW})
    assert locked.status_code == 401 and locked.json() == bad.json()


def test_mfa_token_void_after_five_tries(client: TestClient, session: Session, owner: Person, login) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    _enrol(client, session, owner)
    client.headers.pop("Authorization")
    token = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW}).json()["mfa_token"]
    for _ in range(5):
        client.post("/auth/mfa", json={"mfa_token": token, "code": "000000"})
    assert client.post("/auth/mfa", json={"mfa_token": token, "code": _totp_now(session, owner)}).status_code == 401


def test_cookie_flags_follow_public_url_and_csrf_origin(
    client: TestClient, session: Session, owner: Person, login, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    _enrol(client, session, owner)
    client.headers.pop("Authorization")
    res = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW}, headers={"X-Mia-Client": "web"})
    res = client.post(
        "/auth/mfa", json={"mfa_token": res.json()["mfa_token"], "code": _totp_now(session, owner)},
        headers={"X-Mia-Client": "web"},
    )
    cookies = res.headers.get_list("set-cookie")
    at = next(c for c in cookies if c.startswith("mia_at="))
    rt = next(c for c in cookies if c.startswith("mia_rt="))
    assert "HttpOnly" in at and "SameSite=strict" in at.lower().replace("samesite=strict", "SameSite=strict") and "Secure" not in at
    assert "Path=/auth/refresh" in rt
    assert "access" not in res.json()  # web clients get cookies, not tokens in the body
    # Cookie auth on an unsafe method needs the right Origin.
    assert client.get("/auth/me").status_code == 200
    assert client.post("/chat", json={"text": "hi"}).status_code == 403
    assert client.post("/chat", json={"text": "hi"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/chat", json={"text": "hi"}, headers={"Origin": "http://localhost:8000"}).status_code == 200
    assert client.post("/auth/refresh", headers={"Origin": "http://localhost:8000"}).status_code == 200
    monkeypatch.setenv("MIA_PUBLIC_URL", "https://mia.example.fi")
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    res = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW}, headers={"X-Mia-Client": "web"})
    res = client.post(
        "/auth/mfa", json={"mfa_token": res.json()["mfa_token"], "code": _totp_now(session, owner)},
        headers={"X-Mia-Client": "web"},
    )
    assert "Secure" in next(c for c in res.headers.get_list("set-cookie") if c.startswith("mia_at="))


def test_password_change_ends_other_sessions(client: TestClient, session: Session, owner: Person, login) -> None:  # type: ignore[no-untyped-def]
    first = login(client, owner)
    other = TestClient(app)
    login(other, owner)
    res = client.post("/auth/password", json={"password": "a brand new long password"})
    assert res.status_code == 200
    assert client.get("/auth/me").status_code == 200  # the session that changed it stays
    assert other.get("/auth/me").status_code == 401
    assert session.exec(select(Event).where(Event.action == "auth.password_set")).all()
    assert first.row.status == "active"


def test_no_secret_in_events_or_responses(client: TestClient, session: Session, owner: Person, login) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    recovery = _enrol(client, session, owner)
    client.headers.pop("Authorization")
    res = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW})
    body = res.json()
    res = client.post("/auth/mfa", json={"mfa_token": body["mfa_token"], "code": _totp_now(session, owner)})
    tokens = res.json()
    text = " ".join(str(e.after) + str(e.before) for e in session.exec(select(Event)))
    for secret in (PW, body["mfa_token"], tokens["access"], tokens["refresh"], *recovery):
        assert secret not in text
        assert keys.token_hash(secret) not in text
    assert not re.search(r"scrypt\$", text)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_office_login.py --no-cov -q`
Expected: 404 on `/auth/login`.

- [ ] **Step 3: `api/auth.py` (office part)**

```python
"""Authentication routes (ADR 011): office login with password and TOTP, enrolment, refresh,
logout, and (later tasks) staff codes, devices, PIN step-up, clients and administration.

Web clients (header `X-Mia-Client: web`) get HttpOnly cookies and no tokens in the body;
everything else gets bearer tokens. Every failure is 401 `invalid credentials`.
"""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from mia.api.deps import (
    REFRESH_COOKIE,
    AuthContext,
    CurrentAuth,
    DbSession,
    PersonAuth,
    clear_cookies,
    client_ip,
    set_cookies,
)
from mia.core import auth
from mia.core.db import utcnow
from mia.core.models import Actor, Person

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class MfaIn(BaseModel):
    mfa_token: str = Field(max_length=100)
    code: str = Field(max_length=20)


class CodeIn(BaseModel):
    code: str = Field(max_length=20)


class PasswordIn(BaseModel):
    password: str = Field(max_length=200)
    email: str | None = Field(default=None, max_length=200)


class RefreshIn(BaseModel):
    refresh: str | None = Field(default=None, max_length=100)


class TokensOut(BaseModel):
    access: str | None = None
    refresh: str | None = None
    aal: str
    enrol: bool = False


def _web(request: Request) -> bool:
    return request.headers.get("x-mia-client", "").lower() == "web"


def _tokens_response(request: Request, response: Response, tokens: auth.Tokens) -> TokensOut:
    """Cookies for the web, tokens in the body for everyone else."""
    enrol = tokens.row.aal == "enrol"
    if _web(request):
        set_cookies(response, tokens)
        return TokensOut(aal=tokens.row.aal, enrol=enrol)
    return TokensOut(access=tokens.access, refresh=tokens.refresh, aal=tokens.row.aal, enrol=enrol)


def _person(ctx: AuthContext) -> Person:
    assert ctx.person is not None
    return ctx.person


def _invalid() -> HTTPException:
    return HTTPException(401, auth.INVALID)


@router.post("/login")
def login(request: Request, response: Response, session: DbSession, body: LoginIn) -> dict[str, object]:
    """Password first. People who need MFA get an mfa_token for POST /auth/mfa; a person who
    must have MFA but has none gets an enrolment session; everyone else is signed in."""
    now, ip = utcnow(), client_ip(request)
    try:
        person = auth.check_password(session, body.email, body.password, ip, now)
    except auth.AuthError:
        raise _invalid() from None
    actor = Actor.person(person)
    if auth.has_mfa(session, person):
        token = auth.create_code(session, actor, person, "mfa", now, address=ip, token=True)
        return {"mfa_required": True, "mfa_token": token}
    if auth.needs_mfa(session, person):
        tokens = auth.issue_session(session, person, method="enrol", aal="enrol", ip=ip, now=now)
    else:
        tokens = auth.issue_session(session, person, method="password", aal="aal1", ip=ip, now=now)
    return _tokens_response(request, response, tokens).model_dump()


@router.post("/mfa", response_model=TokensOut)
def mfa(request: Request, response: Response, session: DbSession, body: MfaIn) -> TokensOut:
    """Second step: a TOTP code or a recovery code against the mfa_token."""
    now, ip = utcnow(), client_ip(request)
    found = auth.check_code(session, "mfa", body.mfa_token, now)
    if found.status != "ok" or found.row is None:
        raise _invalid()
    person = session.get(Person, found.row.person_id)
    if person is None or person.status != "active":
        raise _invalid()
    actor = Actor.person(person)
    ok = auth.check_totp(session, person, body.code, now) or auth.check_recovery(
        session, actor, person, body.code, now
    )
    auth.record_attempt(session, "mfa", auth.attempt_key(found.row.id, ip), ok, now, actor=actor)
    if not ok:
        auth.fail_code(session, "mfa", now, person_id=person.id)
        raise _invalid()
    auth.use_code(session, actor, found.row, now)
    auth.unlock_pin(session, actor, person, now)
    tokens = auth.issue_session(session, person, method="password_totp", aal="aal2", ip=ip, now=now)
    return _tokens_response(request, response, tokens)


@router.post("/mfa/enrol")
def mfa_enrol(session: DbSession, ctx: CurrentAuth) -> dict[str, str]:
    """Start TOTP enrolment (from a full session or an enrolment session)."""
    person = _person_or_403(ctx)
    _, uri = auth.enrol_totp(session, ctx.actor, person, utcnow())
    return {"uri": uri}


@router.post("/mfa/confirm")
def mfa_confirm(
    request: Request, response: Response, session: DbSession, ctx: CurrentAuth, body: CodeIn
) -> dict[str, object]:
    """Confirm TOTP with a first code: recovery codes come back once, and an enrolment session
    becomes a full aal2 session."""
    person = _person_or_403(ctx)
    now = utcnow()
    cred = auth._credential(session, person.id, "totp", ("pending",))
    if cred is None:
        raise HTTPException(400, "start enrolment first")
    try:
        codes = auth.confirm_totp(session, ctx.actor, cred, body.code, now)
    except auth.AuthError:
        raise _invalid() from None
    out: dict[str, object] = {"recovery_codes": codes}
    if ctx.aal == "enrol" and ctx.session_id is not None:
        auth.revoke_sessions(session, ctx.actor, person.id, now)
        tokens = auth.issue_session(
            session, person, method="password_totp", aal="aal2", ip=client_ip(request), now=now
        )
        out.update(_tokens_response(request, response, tokens).model_dump())
    return out


@router.post("/password")
def set_password(session: DbSession, ctx: CurrentAuth, body: PasswordIn) -> dict[str, bool]:
    """Set the password (and email on first set). Every other session of the person ends."""
    person = _person_or_403(ctx)
    now = utcnow()
    current = auth._credential(session, person.id, "password")
    email = body.email or (current.login if current else None)
    if not email:
        raise HTTPException(400, "email required")
    try:
        auth.set_password(session, ctx.actor, person, email, body.password, now)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    auth.revoke_sessions(session, ctx.actor, person.id, now, keep=ctx.session_id)
    return {"ok": True}


@router.post("/refresh", response_model=TokensOut)
def refresh(request: Request, response: Response, session: DbSession, body: RefreshIn | None = None) -> TokensOut:
    """Rotate tokens with the refresh token (body, or the mia_rt cookie for the web)."""
    token = (body.refresh if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise _invalid()
    if request.cookies.get(REFRESH_COOKIE) and not (body and body.refresh):
        from mia.api.deps import public_origin

        if request.headers.get("origin") != public_origin():
            raise HTTPException(403, "origin not allowed")
    try:
        tokens = auth.refresh_session(session, token, utcnow())
    except auth.AuthError:
        clear_cookies(response)
        raise _invalid() from None
    return _tokens_response(request, response, tokens)


@router.post("/logout")
def logout(response: Response, session: DbSession, ctx: CurrentAuth) -> dict[str, bool]:
    """End this session; a mobile device signing out is revoked with it."""
    now = utcnow()
    if ctx.session_id is not None:
        from mia.core.models import AuthDevice, AuthSession

        row = session.get(AuthSession, ctx.session_id)
        if row is not None:
            device = session.get(AuthDevice, row.device_id) if row.device_id else None
            if device is not None and device.kind == "mobile":
                auth.revoke_device(session, ctx.actor, device, now)
            else:
                auth.revoke_session(session, ctx.actor, row, now)
    clear_cookies(response)
    return {"ok": True}


@router.get("/me")
def me(session: DbSession, ctx: CurrentAuth) -> dict[str, object]:
    """Who is signed in and how."""
    if ctx.person is None:
        return {"client_id": ctx.client.client_id if ctx.client else None, "aal": ctx.aal, "method": ctx.method}
    person = ctx.person
    fresh = ctx.stepped_up_at is not None and utcnow() - ctx.stepped_up_at <= auth.STEP_UP_TTL
    return {
        "person_id": person.id,
        "name": person.name,
        "roles": person.roles,
        "aal": ctx.aal,
        "method": ctx.method,
        "stepped_up": fresh,
        "mfa": auth.has_mfa(session, person),
        "pin": auth.has_pin(session, person),
    }


def _person_or_403(ctx: AuthContext) -> Person:
    if ctx.person is None:
        raise HTTPException(403, "a person must be signed in")
    return ctx.person
```

Make `_credential` public as `credential(session, person_id, kind, statuses=("active",))` in `core/auth.py` (rename, keep one name everywhere) rather than calling a private name from the routes. In `main.py`: `from mia.api.auth import router as auth_router` and `app.include_router(auth_router)`.

- [ ] **Step 4: The dev page in required mode**

In `node/mia/static/index.html`: on load, fetch `/health`; if `auth_mode` is `required`, hide the actor select and show a login form (email, password, then a code field when the reply says `mfa_required`), posting with header `X-Mia-Client: web` so cookies are set, and with `credentials: "same-origin"` on every later fetch; drop the `X-Mia-Actor` header when not in dev mode; show the person's name from `/auth/me` and a "Sign out" link that posts `/auth/logout`. In dev mode the page behaves as today. Keep it to the existing style, no framework. Test (in `node/tests/test_chat.py::test_health_and_page`): the page text contains `id="login"` and `auth/me`.

- [ ] **Step 5: Run the tests, then the full suite**

Run: `uv run pytest node/tests/auth --no-cov -q`, then the full check line.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "auth: office login with password and TOTP, enrolment, recovery codes, refresh, logout, cookies; login form on the dev page"
```

---

### Task 6: Bootstrap and recovery (`mia auth bootstrap | reset | unlock`, enrolment links)

**Files:**
- Modify: `node/mia/api/auth.py` (`GET/POST /auth/enrol/{code}`), `node/mia/cli.py`
- Test: `node/tests/auth/test_bootstrap.py`

**Interfaces:**
- Consumes: `auth.start_enrolment`, `auth.check_code`, `auth.use_code`, `auth.issue_session`.
- Produces: `GET /auth/enrol/{code}` -> a small HTML page with one "Continue" form (does not consume the code); `POST /auth/enrol/{code}` -> enrol-session tokens (cookies for web) after consuming the code. CLI: `mia auth bootstrap --email EMAIL [--name NAME] [--branch ID]` creates the first owner if no owner exists (or reuses the one person with that login) and prints the enrolment link; `mia auth reset PERSON` prints a new enrolment link and ends every session (event `auth.reset`, `via: cli`); `mia auth unlock LOGIN` clears the login lockout by writing a synthetic successful attempt (so counts restart) and an `auth.unlocked` event.

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_bootstrap.py`:

```python
"""Enrolment links from the CLI: bootstrap the first owner, reset a person, unlock a login."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.cli import main
from mia.core import auth
from mia.core.db import utcnow
from mia.core.models import Actor, Event, Person

PW = "a long enough password"


def _link(out: str) -> str:
    m = re.search(r"http://localhost:8000/auth/enrol/(\S+)", out)
    assert m, out
    return m[1]


def test_bootstrap_then_enrol_over_http(
    capsys: pytest.CaptureFixture[str], engine: object, branch: object, session: Session
) -> None:
    assert main(["auth", "bootstrap", "--email", "owner@example.fi"]) == 0
    code = _link(capsys.readouterr().out)
    client = TestClient(app)
    page = client.get(f"/auth/enrol/{code}")
    assert page.status_code == 200 and "Continue" in page.text
    assert client.get(f"/auth/enrol/{code}").status_code == 200  # GET never consumes
    res = client.post(f"/auth/enrol/{code}")
    assert res.status_code == 200 and res.json()["aal"] == "enrol"
    assert client.post(f"/auth/enrol/{code}").status_code == 401  # single use
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.post("/auth/password", json={"password": PW}).status_code == 200
    assert client.get("/auth/me").json()["roles"] == ["owner"]
    with Session(engine) as s:  # type: ignore[arg-type]
        found = auth.person_by_login(s, "owner@example.fi")
        assert found is not None and "owner" in found[0].roles
    assert main(["auth", "bootstrap", "--email", "second@example.fi"]) == 1  # an owner exists
    assert "already" in capsys.readouterr().out


def test_reset_ends_sessions_and_unlock_clears_the_lockout(
    capsys: pytest.CaptureFixture[str], engine: object, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    helena = people["Helena"]
    auth.set_password(session, Actor.person(helena), helena, "helena@example.fi", PW, utcnow())
    session.commit()
    client = TestClient(app)
    login(client, helena)
    assert client.get("/auth/me").status_code == 200
    assert main(["auth", "reset", "Helena"]) == 0
    code = _link(capsys.readouterr().out)
    assert client.get("/auth/me").status_code == 401
    with Session(engine) as s:  # type: ignore[arg-type]
        ev = s.exec(select(Event).where(Event.action == "auth.reset")).one()
        assert ev.actor_id == "system" and ev.after == {"by": "system", "via": "cli"}
    assert TestClient(app).post(f"/auth/enrol/{code}").status_code == 200
    for _ in range(20):
        client.post("/auth/login", json={"email": "helena@example.fi", "password": "nope"})
    assert client.post("/auth/login", json={"email": "helena@example.fi", "password": PW}).status_code == 401
    assert main(["auth", "unlock", "helena@example.fi"]) == 0
    assert "unlocked" in capsys.readouterr().out
    assert client.post("/auth/login", json={"email": "helena@example.fi", "password": PW}).status_code == 200
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_bootstrap.py --no-cov -q`
Expected: argparse error on `auth`.

- [ ] **Step 3: Routes and CLI**

Append to `node/mia/api/auth.py`:

```python
ENROL_PAGE = """<!doctype html><meta charset="utf-8"><title>Mia</title>
<body style="font-family:system-ui;max-width:28rem;margin:4rem auto">
<h1>Mia</h1><p>Continue to set up your sign-in.</p>
<form method="post"><button style="padding:.6rem 1.2rem">Continue</button></form>
<script>document.forms[0].onsubmit = async (e) => { e.preventDefault();
 const r = await fetch(location.pathname, {method: "POST", headers: {"X-Mia-Client": "web"}});
 location.href = r.ok ? "/" : location.pathname + "?failed=1"; };</script>"""


@router.get("/enrol/{code}", response_class=HTMLResponse)
def enrol_page(code: str) -> str:
    """One button, so previews and scanners that fetch the link do not consume it."""
    return ENROL_PAGE


@router.post("/enrol/{code}", response_model=TokensOut)
def enrol(request: Request, response: Response, session: DbSession, code: str) -> TokensOut:
    """Consume an enrolment link: an enrolment session that can set a password and TOTP."""
    now = utcnow()
    found = auth.check_code(session, "enrol", code, now)
    if found.status != "ok" or found.row is None:
        raise _invalid()
    person = session.get(Person, found.row.person_id)
    if person is None or person.status != "active":
        raise _invalid()
    auth.use_code(session, Actor.person(person), found.row, now)
    tokens = auth.issue_session(session, person, method="enrol", aal="enrol", ip=client_ip(request), now=now)
    return _tokens_response(request, response, tokens)
```

(import `HTMLResponse` from `fastapi.responses`). In `core/auth.py` `start_enrolment`, the `auth.reset` event's data is `{"by": actor.principal.id, "via": via}` with a new keyword `via: str = "app"`.

In `node/mia/cli.py`:

```python
def _enrol_link(code: str) -> str:
    return f"{get_settings().MIA_PUBLIC_URL.rstrip('/')}/auth/enrol/{code}"


def auth_bootstrap(args: argparse.Namespace) -> int:
    from mia.core import auth, people
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor, Person

    with session_scope() as session:
        branch_id = _only_branch_id(session, args.branch)
        owners = [p for p in session.exec(select(Person).where(Person.branch_id == branch_id)) if "owner" in p.roles and p.status == "active"]
        if owners:
            print(f"an owner already exists ({owners[0].name}); use `mia auth reset` instead")
            return 1
        person = people.add_person(session, Actor.system(branch_id), branch_id=branch_id, name=args.name or args.email.split("@")[0], roles=["owner"], language=args.lang)
        code = auth.start_enrolment(session, Actor.system(branch_id), person, utcnow(), via="cli")
    print(f"owner {person.name} created. Set the password and TOTP through this link (24 hours, single use):\n  {_enrol_link(code)}")
    return 0
```

Bootstrap sets no password: the person sets it through the link with `POST /auth/password {password, email}` (`email` is required there when no password credential exists yet). `--email` is only used for the default name and printed in the instructions. For `mia auth reset`:

```python
def auth_reset(args: argparse.Namespace) -> int:
    from mia.core import auth
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor

    with session_scope() as session:
        person = _match_one(session, args.name)
        code = auth.start_enrolment(session, Actor.system(person.branch_id), person, utcnow(), reason="reset", via="cli")
    print(f"sessions of {person.name} ended. Enrolment link (24 hours, single use):\n  {_enrol_link(code)}")
    return 0


def auth_unlock(args: argparse.Namespace) -> int:
    from mia.core import auth
    from mia.core.db import session_scope, utcnow

    with session_scope() as session:
        auth.unlock_login(session, args.login, utcnow())
    print(f"{auth.normalise_login(args.login)} unlocked")
    return 0
```

and in `core/auth.py`:

```python
def unlock_login(session: Session, login: str, now: dt.datetime) -> None:
    """Owner's unlock from the CLI: failures of the login no longer count (an `auth.unlocked`
    event and one successful marker attempt for every blocked key)."""
    from mia.core import events

    subject = login_key(login)
    for row in _recent(session, now - LIMITS["password_login"].window, kind="password", prefix=f"{subject}@"):
        store.update(session, row, {"ok": True}, auth_actor(), action="auth.attempt_cleared")
    events.emit(session, "auth.unlocked", ("login", subject), None, {"via": "cli"}, auth_actor())
```

Parser: `auth_p = sub.add_parser("auth", help="authentication").add_subparsers(dest="auth_command", required=True)`; `bootstrap` (`--email` required, `--name`, `--lang` default fi, `--branch`), `reset` (`name`), `unlock` (`login`). `_only_branch_id` already exists in cli.py (used by `person add`).

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run pytest node/tests/auth/test_bootstrap.py --no-cov -q`, then the full check line. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "auth: enrolment links; mia auth bootstrap, reset and unlock"
```

---

### Task 7: Staff login (WhatsApp code, device binding, device login, login link, revocation)

**Files:**
- Modify: `node/mia/api/auth.py` (`/auth/otp/start`, `/auth/otp/verify`, `/auth/device`, `GET/POST /auth/link/{code}`), `node/mia/core/auth.py` (`send_otp`, `send_login_link`), `node/mia/channels/service.py` (`deliver(..., redact=False)`), `node/mia/channels/whatsapp/templates.py` (`mia_login_code`), `node/mia/i18n/strings.py` (`auth.otp_text`, `auth.link_text`), `node/mia/cli.py` (`mia auth link PERSON`)
- Test: `node/tests/auth/test_staff_login.py`

**Interfaces:**
- Consumes: Tasks 3 and 4, `channels.service.deliver`, `channels.linking.identity_for`.
- Produces in `core/auth.py`: `send_otp(session, address, now) -> None` (same behaviour for unknown numbers: nothing sent, no error), `send_login_link(session, actor, person, now) -> str | None` (the link, or None when the person has no active identity), `OTP_TEMPLATE = "mia_login_code"`.
- Routes: `POST /auth/otp/start {phone}` -> `{ok: true}` always; `POST /auth/otp/verify {phone, code, device: {name, platform}}` -> `{access, refresh, aal: "aal1", device_id, device_secret}`; `POST /auth/device {device_id, device_secret}` -> tokens aal1; `GET /auth/link/{code}` -> HTML with "Continue as <first name>"; `POST /auth/link/{code}` -> tokens (browser device, aal1, cookies for web).
- `deliver(..., redact: bool = False)`: when true the outbox rows' `payload` is redacted in events (`store.insert(..., redact={"payload"})`).

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_staff_login.py`:

```python
"""Staff: a code over the simulated channel, device binding, device login, the login link,
sign-out and revocation. The sim adapter stands in for WhatsApp."""

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.channels import linking, registry
from mia.channels.simulator import SimAdapter
from mia.core import auth
from mia.core.db import utcnow
from mia.core.models import Actor, AuthCode, ChannelOutbox, Event, Person

ADDR = "358401234567"


@pytest.fixture
def sim(branch: object) -> SimAdapter:
    adapter = SimAdapter()
    registry.register(adapter)
    return adapter


@pytest.fixture
def linked(session: Session, people: dict[str, Person], sim: SimAdapter) -> Person:
    juha = people["Juha"]
    code = linking.create_code(session, Actor.person(people["Sanna"]), juha, "invite")
    assert linking.redeem(session, "sim", ADDR, code, utcnow()).status == "linked"
    session.commit()
    return juha


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


def _sent_code(session: Session) -> str:
    row = session.exec(select(ChannelOutbox).order_by(ChannelOutbox.id.desc())).first()  # type: ignore[attr-defined]
    assert row is not None
    m = re.search(r"\b(\d{6})\b", str(row.payload))
    assert m, row.payload
    return m[1]


def test_otp_flow_binds_a_device_and_device_login_works(
    client: TestClient, session: Session, linked: Person
) -> None:
    assert client.post("/auth/otp/start", json={"phone": "+358 40 1234567"}).json() == {"ok": True}
    code = _sent_code(session)
    for e in session.exec(select(Event)):
        assert code not in str(e.after) and code not in str(e.before)
    bad = client.post("/auth/otp/verify", json={"phone": ADDR, "code": "000000", "device": {"name": "iPhone", "platform": "ios"}})
    assert bad.status_code == 401
    res = client.post("/auth/otp/verify", json={"phone": ADDR, "code": code, "device": {"name": "iPhone", "platform": "ios"}})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["aal"] == "aal1" and len(body["device_secret"]) == 43
    assert client.post("/auth/otp/verify", json={"phone": ADDR, "code": code, "device": {"name": "x", "platform": "ios"}}).status_code == 401
    client.headers["Authorization"] = f"Bearer {body['access']}"
    assert client.get("/auth/me").json()["method"] == "phone_otp"
    assert client.post("/chat", json={"text": "hi"}).status_code == 200
    client.headers.pop("Authorization")
    res = client.post("/auth/device", json={"device_id": body["device_id"], "device_secret": body["device_secret"]})
    assert res.status_code == 200 and res.json()["aal"] == "aal1"
    assert client.post("/auth/device", json={"device_id": body["device_id"], "device_secret": "x"}).status_code == 401
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.post("/auth/logout").json() == {"ok": True}
    assert client.post("/auth/device", json={"device_id": body["device_id"], "device_secret": body["device_secret"]}).status_code == 401


def test_unknown_number_same_response_nothing_sent_and_send_limit(
    client: TestClient, session: Session, linked: Person
) -> None:
    before = len(session.exec(select(ChannelOutbox)).all())
    assert client.post("/auth/otp/start", json={"phone": "358400000000"}).json() == {"ok": True}
    assert len(session.exec(select(ChannelOutbox)).all()) == before
    for _ in range(3):
        client.post("/auth/otp/start", json={"phone": ADDR})
    sent = len(session.exec(select(ChannelOutbox)).all())
    assert client.post("/auth/otp/start", json={"phone": ADDR}).json() == {"ok": True}
    assert len(session.exec(select(ChannelOutbox)).all()) == sent  # fourth in the hour: silently not sent
    assert len(session.exec(select(AuthCode).where(AuthCode.purpose == "otp_login")).all()) == 3


def test_code_tries_expiry_and_wrong_number(client: TestClient, session: Session, linked: Person) -> None:
    client.post("/auth/otp/start", json={"phone": ADDR})
    code = _sent_code(session)
    dev = {"name": "p", "platform": "android"}
    assert client.post("/auth/otp/verify", json={"phone": "358409999999", "code": code, "device": dev}).status_code == 401
    for _ in range(5):
        client.post("/auth/otp/verify", json={"phone": ADDR, "code": "111111", "device": dev})
    assert client.post("/auth/otp/verify", json={"phone": ADDR, "code": code, "device": dev}).status_code == 401


def test_login_link_get_does_not_consume_and_post_logs_in(
    client: TestClient, session: Session, linked: Person, capsys: pytest.CaptureFixture[str]
) -> None:
    from mia.cli import main

    assert main(["auth", "link", "Juha"]) == 0
    out = capsys.readouterr().out
    m = re.search(r"/auth/link/(\S+)", out)
    assert m
    code = m[1]
    page = client.get(f"/auth/link/{code}")
    assert page.status_code == 200 and "Continue as Juha" in page.text
    assert client.get(f"/auth/link/{code}").status_code == 200
    res = client.post(f"/auth/link/{code}")
    assert res.status_code == 200 and res.json()["aal"] == "aal1"
    assert client.post(f"/auth/link/{code}").status_code == 401
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.get("/auth/me").json()["method"] == "wa_link"
    assert session.exec(select(Event).where(Event.action == "auth.link_sent")).first()


def test_deactivation_revokes_devices_sessions_and_identity(
    client: TestClient, session: Session, linked: Person, people: dict[str, Person]
) -> None:
    from mia.core import people as people_service

    client.post("/auth/otp/start", json={"phone": ADDR})
    code = _sent_code(session)
    res = client.post("/auth/otp/verify", json={"phone": ADDR, "code": code, "device": {"name": "p", "platform": "ios"}})
    body = res.json()
    people_service.deactivate(session, Actor.person(people["Helena"]), linked)
    session.commit()
    client.headers["Authorization"] = f"Bearer {body['access']}"
    assert client.get("/auth/me").status_code == 403
    client.headers.pop("Authorization")
    assert client.post("/auth/device", json={"device_id": body["device_id"], "device_secret": body["device_secret"]}).status_code == 401
    assert linking.identity_for(session, "sim", ADDR) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_staff_login.py --no-cov -q`
Expected: 404 on `/auth/otp/start`.

- [ ] **Step 3: Services, template, strings, deliver redaction**

`node/mia/channels/whatsapp/templates.py`: add `"mia_login_code": Template(params=1, langs=("fi", "en"))` with the comment `# Authentication template (copy-code button): "Kirjautumiskoodisi on {{1}}. Älä jaa sitä."`.

`node/mia/i18n/strings.py`: add to `en`: `"auth.otp_text": "Your Mia sign-in code is {code}. It is valid for 5 minutes. Never share it."`, `"auth.link_text": "Open Mia: {url} (valid for 10 minutes, only for you)."`; to `fi`: `"auth.otp_text": "Mia-kirjautumiskoodisi on {code}. Se on voimassa 5 minuuttia. Älä jaa sitä."`, `"auth.link_text": "Avaa Mia: {url} (voimassa 10 minuuttia, vain sinulle)."`.

`node/mia/channels/service.py` `deliver`: add keyword `redact: bool = False` and pass `redact={"payload"} if redact else ()` to the `store.insert` call.

Append to `node/mia/core/auth.py`:

```python
# ---- staff codes and links (delivery through the channel layer, rule 6) ----------------

OTP_TEMPLATE = "mia_login_code"


def normalise_phone(phone: str) -> str:
    """Digits only, no leading zeros or plus (E.164 without the plus, like channel addresses)."""
    digits = "".join(c for c in phone if c.isdigit())
    return digits.lstrip("0")


def _person_for_address(session: Session, address: str) -> tuple[Person, str] | None:
    from mia.core.models import ChannelIdentity

    row = session.exec(
        select(ChannelIdentity)
        .where(ChannelIdentity.address == address)
        .where(ChannelIdentity.status == "active")
        .order_by(col(ChannelIdentity.id).desc())
    ).first()
    if row is None:
        return None
    person = session.get(Person, row.person_id)
    return (person, row.channel) if person is not None and person.status == "active" else None


def send_otp(session: Session, phone: str, now: dt.datetime) -> None:
    """Send a 6-digit code to the active identity behind the number, through the channel
    layer. Unknown numbers and numbers past 3 sends an hour get nothing, silently."""
    from mia.channels.base import TemplateCall
    from mia.channels.service import deliver
    from mia.chat.blocks import TextBlock
    from mia.i18n import t

    address = normalise_phone(phone)
    found = _person_for_address(session, address)
    if found is None or sends_in_last_hour(session, "otp_login", address, now) >= OTP_SENDS_PER_HOUR:
        return
    person, _channel = found
    actor = Actor.person(person)
    code = create_code(session, actor, person, "otp_login", now, address=address)
    deliver(
        session,
        person,
        [TextBlock(text=t("auth.otp_text", person.language, code=code))],
        actor,
        kind="otp",
        template=TemplateCall(name=OTP_TEMPLATE, lang=person.language, params=[code]),
        urgent=True,
        now=now,
        redact=True,
    )
    from mia.core import events

    events.emit(session, "auth.otp_sent", person, None, {"address": address}, actor)


def check_otp(session: Session, phone: str, code: str, ip: str, now: dt.datetime) -> Person:
    """The person behind the number when the code is live and right. Wrong codes use a try."""
    address = normalise_phone(phone)
    key = attempt_key(address, ip)
    if throttled(session, "otp", key, now):
        raise Locked(INVALID)
    found = _person_for_address(session, address)
    result = check_code(session, "otp_login", code, now, person_id=found[0].id if found else None)
    ok = result.status == "ok" and result.row is not None and result.row.address == address
    record_attempt(session, "otp", key, ok, now, actor=Actor.person(found[0]) if found else None)
    if not ok or result.row is None or found is None:
        fail_code(session, "otp_login", now, address=address)
        raise AuthError(INVALID)
    use_code(session, Actor.person(found[0]), result.row, now)
    unlock_pin(session, Actor.person(found[0]), found[0], now)
    return found[0]


def send_login_link(
    session: Session, actor: Actor, person: Person, now: dt.datetime
) -> str | None:
    """A one-time login link to the person's active identity. None without one."""
    from mia.channels.service import deliver
    from mia.chat.blocks import TextBlock
    from mia.i18n import t
    from mia.settings import get_settings

    if _identity_count(session, person) == 0:
        return None
    code = create_code(session, actor, person, "link_login", now, token=True)
    url = f"{get_settings().MIA_PUBLIC_URL.rstrip('/')}/auth/link/{code}"
    deliver(
        session,
        person,
        [TextBlock(text=t("auth.link_text", person.language, url=url))],
        actor,
        kind="otp",
        urgent=True,
        now=now,
        redact=True,
    )
    from mia.core import events

    events.emit(session, "auth.link_sent", person, None, None, actor)
    return url


def _identity_count(session: Session, person: Person) -> int:
    from mia.core.models import ChannelIdentity

    return len(
        session.exec(
            select(ChannelIdentity)
            .where(ChannelIdentity.person_id == person.id)
            .where(ChannelIdentity.status == "active")
        ).all()
    )
```

The `TemplateCall` fields are `name`, `lang`, `params` (check `node/mia/channels/base.py:49`).

- [ ] **Step 4: Routes and CLI**

Append to `node/mia/api/auth.py`:

```python
class PhoneIn(BaseModel):
    phone: str = Field(max_length=30)


class DeviceIn(BaseModel):
    name: str = Field(max_length=80)
    platform: str = Field(max_length=20)


class OtpVerifyIn(BaseModel):
    phone: str = Field(max_length=30)
    code: str = Field(max_length=6)
    device: DeviceIn


class DeviceLoginIn(BaseModel):
    device_id: str = Field(max_length=26)
    device_secret: str = Field(max_length=100)


@router.post("/otp/start")
def otp_start(request: Request, session: DbSession, body: PhoneIn) -> dict[str, bool]:
    """Send a sign-in code to the number's WhatsApp. The answer never says whether the
    number is known."""
    auth.send_otp(session, body.phone, utcnow())
    return {"ok": True}


@router.post("/otp/verify")
def otp_verify(request: Request, response: Response, session: DbSession, body: OtpVerifyIn) -> dict[str, object]:
    """Check the code, bind the device and sign in (aal1). The device secret is shown once."""
    now, ip = utcnow(), client_ip(request)
    try:
        person = auth.check_otp(session, body.phone, body.code, ip, now)
    except auth.AuthError:
        raise _invalid() from None
    actor = Actor.person(person)
    device, secret = auth.bind_device(session, actor, person, "mobile", f"{body.device.name} ({body.device.platform})", now)
    tokens = auth.issue_session(session, person, method="phone_otp", aal="aal1", ip=ip, now=now, device=device)
    out = _tokens_response(request, response, tokens).model_dump()
    out.update({"device_id": device.id, "device_secret": secret})
    return out


@router.post("/device", response_model=TokensOut)
def device_login(request: Request, response: Response, session: DbSession, body: DeviceLoginIn) -> TokensOut:
    """Sign in on a bound device with its secret (aal1; the PIN steps it up)."""
    now, ip = utcnow(), client_ip(request)
    try:
        device = auth.check_device(session, body.device_id, body.device_secret, ip, now)
    except auth.AuthError:
        raise _invalid() from None
    person = session.get(Person, device.person_id)
    if person is None or person.status != "active":
        raise _invalid()
    tokens = auth.issue_session(session, person, method="device", aal="aal1", ip=ip, now=now, device=device)
    return _tokens_response(request, response, tokens)


LINK_PAGE = """<!doctype html><meta charset="utf-8"><title>Mia</title>
<body style="font-family:system-ui;max-width:28rem;margin:4rem auto"><h1>Mia</h1>
<form method="post"><button style="padding:.6rem 1.2rem">Continue as {name}</button></form>
<script>document.forms[0].onsubmit = async (e) => { e.preventDefault();
 const r = await fetch(location.pathname, {method: "POST", headers: {"X-Mia-Client": "web"}});
 location.href = r.ok ? "/" : location.pathname + "?failed=1"; };</script>"""


@router.get("/link/{code}", response_class=HTMLResponse)
def link_page(session: DbSession, code: str) -> str:
    """The login link's page: one button, so fetching the URL never consumes the link."""
    found = auth.check_code(session, "link_login", code, utcnow())
    person = session.get(Person, found.row.person_id) if found.status == "ok" and found.row else None
    if person is None:
        raise HTTPException(404, "link expired or already used")
    return LINK_PAGE.replace("{name}", person.name.split()[0])


@router.post("/link/{code}", response_model=TokensOut)
def link_login(request: Request, response: Response, session: DbSession, code: str) -> TokensOut:
    """Consume the login link: a browser device and an aal1 session."""
    now, ip = utcnow(), client_ip(request)
    found = auth.check_code(session, "link_login", code, now)
    person = session.get(Person, found.row.person_id) if found.status == "ok" and found.row else None
    if found.row is None or person is None or person.status != "active":
        raise _invalid()
    actor = Actor.person(person)
    auth.use_code(session, actor, found.row, now)
    device, _ = auth.bind_device(session, actor, person, "browser", request.headers.get("user-agent", "browser")[:80], now)
    tokens = auth.issue_session(session, person, method="wa_link", aal="aal1", ip=ip, now=now, device=device)
    return _tokens_response(request, response, tokens)
```

CLI `mia auth link PERSON`: `auth.send_login_link(session, Actor.system(person.branch_id), person, utcnow())`, print the URL or "no active channel identity" (exit 1). Register it under the `auth` subparser from Task 6.

- [ ] **Step 5: Run the tests, then the full suite**

Run: `uv run pytest node/tests/auth node/tests/channels --no-cov -q`, then the full check line. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "auth: staff sign-in with a WhatsApp code, device binding and login, login links; deactivation revokes everything"
```

---

### Task 8: PIN and step-up for app-only approvals

**Files:**
- Modify: `node/mia/api/auth.py` (`POST /auth/pin`, `POST /auth/stepup`), `node/mia/static/index.html` (ask for the PIN on 403 `step_up_required`)
- Test: `node/tests/auth/test_stepup.py`

**Interfaces:**
- Consumes: `auth.set_pin`, `auth.check_pin`, `auth.step_up`, `approvals.decide(..., aal, stepped_up_at)`.
- Produces: `POST /auth/pin {pin}` (aal2 session, or a bound mobile device after a phone code: method `phone_otp`) -> `{ok: true}`; `POST /auth/stepup {pin}` -> `{stepped_up: true}`; a session on a bound device becomes `aal2` for the step-up window (the context reports `aal == "aal2"` when `stepped_up_at` is fresh and the session is on a mobile device).

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_stepup.py`:

```python
"""PIN set and step-up; deciding an app_only approval over HTTP."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.core import approvals, auth
from mia.core.db import utcnow
from mia.core.models import Actor, Event, Person


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


@pytest.fixture
def override(session: Session, people: dict[str, Person]) -> str:
    row = approvals.request(
        session, Actor.person(people["Sanna"]), "dispatcher.cover_override", "visit", "V",
        "x", {}, ["admin"], channel="app_only",
    )
    session.commit()
    return row.id


def test_pin_rules_over_http(client: TestClient, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Helena"])
    assert client.post("/auth/pin", json={"pin": "123456"}).status_code == 400
    assert client.post("/auth/pin", json={"pin": "12ab"}).status_code == 422
    assert client.post("/auth/pin", json={"pin": "273916"}).json() == {"ok": True}
    assert client.get("/auth/me").json()["pin"] is True


def test_aal1_session_cannot_set_a_pin(client: TestClient, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Helena"], aal="aal1", method="password")
    assert client.post("/auth/pin", json={"pin": "273916"}).status_code == 403


def test_decide_needs_step_up(
    client: TestClient, session: Session, people: dict[str, Person], login, override: str
) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Helena"])
    client.post("/auth/pin", json={"pin": "273916"})
    res = client.post(f"/approvals/{override}/decide", json={"outcome": "approved"})
    assert res.status_code == 403 and res.json()["detail"] == "step_up_required"
    assert client.post("/auth/stepup", json={"pin": "000000"}).status_code == 401
    assert client.post("/auth/stepup", json={"pin": "273916"}).json() == {"stepped_up": True}
    assert client.get("/auth/me").json()["stepped_up"] is True
    res = client.post(f"/approvals/{override}/decide", json={"outcome": "approved"})
    assert res.status_code == 200 and res.json()["status"] == "approved"
    assert session.exec(select(Event).where(Event.action == "auth.step_up")).first()


def test_five_wrong_pins_lock_until_next_mfa_login(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Helena"])
    client.post("/auth/pin", json={"pin": "273916"})
    for _ in range(5):
        assert client.post("/auth/stepup", json={"pin": "000000"}).status_code == 401
    res = client.post("/auth/stepup", json={"pin": "273916"})
    assert res.status_code == 401 and res.json()["detail"] == "pin locked"
    auth.unlock_pin(session, Actor.person(people["Helena"]), people["Helena"], utcnow())
    session.commit()
    assert client.post("/auth/stepup", json={"pin": "273916"}).status_code == 200


def test_staff_device_steps_up_to_aal2(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    juha = people["Juha"]
    device, _ = auth.bind_device(session, Actor.person(juha), juha, "mobile", "p", utcnow())
    session.commit()
    login(client, juha, aal="aal1", method="phone_otp", device=device)
    assert client.post("/auth/pin", json={"pin": "273916"}).status_code == 200  # after a phone code
    assert client.get("/auth/me").json()["aal"] == "aal1"
    client.post("/auth/stepup", json={"pin": "273916"})
    assert client.get("/auth/me").json()["aal"] == "aal2"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_stepup.py --no-cov -q`
Expected: 404 on `/auth/pin`.

- [ ] **Step 3: Routes and the aal2-on-device rule**

Append to `node/mia/api/auth.py`:

```python
class PinIn(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


def _may_set_pin(ctx: AuthContext) -> bool:
    return ctx.aal == "aal2" or ctx.method == "phone_otp"


@router.post("/pin")
def set_pin(session: DbSession, ctx: PersonAuth, body: PinIn) -> dict[str, bool]:
    """Set the 6-digit PIN from an aal2 session, or on a bound device right after a phone
    code. Trivial PINs are refused (400)."""
    if not _may_set_pin(ctx):
        raise HTTPException(403, "an MFA login or a fresh phone code is needed to set the PIN")
    try:
        auth.set_pin(session, ctx.actor, _person(ctx), body.pin, utcnow())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@router.post("/stepup")
def stepup(request: Request, session: DbSession, ctx: PersonAuth, body: PinIn) -> dict[str, bool]:
    """Enter the PIN: the session counts as stepped up for five minutes."""
    from mia.core.models import AuthSession

    now = utcnow()
    try:
        ok = auth.check_pin(session, _person(ctx), body.pin, client_ip(request), now)
    except auth.Locked:
        raise HTTPException(401, "pin locked") from None
    if not ok:
        raise _invalid()
    row = session.get(AuthSession, ctx.session_id) if ctx.session_id else None
    if row is None:
        raise HTTPException(403, "no session to step up")
    auth.step_up(session, row, now)
    return {"stepped_up": True}
```

In `api/deps.py` `current_auth`, after loading the person session: a session on a mobile device whose `stepped_up_at` is within `STEP_UP_TTL` reports `aal="aal2"`:

```python
    aal = row.aal
    if row.device_id and row.stepped_up_at is not None and utcnow() - row.stepped_up_at <= auth.STEP_UP_TTL:
        device = session.get(AuthDevice, row.device_id)
        if device is not None and device.kind == "mobile":
            aal = "aal2"
```

(import `AuthDevice`). The dev page: when `/approvals/{id}/decide` answers 403 `step_up_required`, prompt for the PIN (`window.prompt` is fine on the dev page), post `/auth/stepup` and retry once.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run pytest node/tests/auth --no-cov -q`, then the full check line. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "auth: PIN and step-up; app-only approvals need aal2 and a fresh PIN"
```

---

### Task 9: Clients (OAuth2 client credentials for outside agents and services)

**Files:**
- Modify: `node/mia/core/auth.py` (`create_client`, `check_client`, `revoke_client`), `node/mia/api/auth.py` (`POST /auth/token`), `node/mia/cli.py` (`mia auth client add | revoke`)
- Test: `node/tests/auth/test_clients.py`

**Interfaces:**
- Consumes: `rbac.get_rbac()` (to refuse roles that can approve), `issue_session(client, ...)`, `ClientAuth`.
- Produces: `create_client(session, actor, name, roles, now, *, expires_at=None) -> tuple[AuthClient, str]` (ValueError for a human role or a role holding any `approve` policy); `check_client(session, client_id, secret, ip, now) -> AuthClient`; `revoke_client(session, actor, client, now) -> AuthClient`; `POST /auth/token` (form `grant_type=client_credentials` with HTTP Basic or `client_id`/`client_secret` form fields) -> `{access_token, token_type: "Bearer", expires_in: 3600}` (RFC 6749 section 5.1), errors as `{error: "invalid_client"}` 401.

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_clients.py`:

```python
"""Client credentials: registration, token endpoint, roles, revocation, and the rule that
clients never hold approve and never act on person routes."""

import base64

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.deps import ClientAuth
from mia.api.main import app
from mia.cli import main
from mia.core import auth
from mia.core.db import utcnow
from mia.core.models import Actor, AuthClient, Event, Person

probe = APIRouter()


@probe.get("/a2a-probe")
def a2a_probe(ctx: ClientAuth) -> dict[str, object]:
    return {"id": ctx.actor.principal.id, "roles": ctx.actor.principal.roles}


@pytest.fixture
def client(branch: object) -> TestClient:
    if not any(getattr(r, "path", "") == "/a2a-probe" for r in app.routes):
        app.include_router(probe)
    return TestClient(app)


def _basic(client_id: str, secret: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"{client_id}:{secret}".encode()).decode()}


def test_register_and_get_a_token(client: TestClient, session: Session, people: dict[str, Person], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["auth", "client", "add", "Partner", "--role", "dispatcher"]) == 0
    out = capsys.readouterr().out
    client_id = out.split("client_id: ")[1].split()[0]
    secret = out.split("client_secret: ")[1].split()[0]
    res = client.post("/auth/token", data={"grant_type": "client_credentials"}, headers=_basic(client_id, secret))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token_type"] == "Bearer" and body["expires_in"] == 3600
    res = client.get("/a2a-probe", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert res.json() == {"id": f"client:{client_id}", "roles": ["dispatcher"]}
    res = client.post("/auth/token", data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret})
    assert res.status_code == 200
    assert client.post("/auth/token", data={"grant_type": "password"}, headers=_basic(client_id, secret)).status_code == 400
    assert client.post("/auth/token", data={"grant_type": "client_credentials"}, headers=_basic(client_id, "x")).json() == {"error": "invalid_client"}
    assert main(["auth", "client", "revoke", client_id]) == 0
    assert client.post("/auth/token", data={"grant_type": "client_credentials"}, headers=_basic(client_id, secret)).status_code == 401
    assert client.get("/a2a-probe", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 401


def test_client_never_holds_approve_or_a_human_role(session: Session, people: dict[str, Person]) -> None:
    helena = Actor.person(people["Helena"])
    with pytest.raises(ValueError, match="approve"):
        auth.create_client(session, helena, "x", ["admin"], utcnow())
    with pytest.raises(ValueError, match="human"):
        auth.create_client(session, helena, "x", ["staff"], utcnow())
    row, secret = auth.create_client(session, helena, "x", ["dispatcher"], utcnow())
    assert row.client_id.startswith("mia_") and row.secret_hash != secret
    for e in session.exec(select(Event).where(Event.action == "auth.client_created")):
        assert e.after is not None and e.after["secret_hash"] == "<redacted>"


def test_client_token_is_refused_on_person_routes_and_cookies_on_client_routes(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    row, secret = auth.create_client(session, Actor.person(people["Helena"]), "x", ["dispatcher"], utcnow())
    session.commit()
    token = client.post("/auth/token", data={"grant_type": "client_credentials"}, headers=_basic(row.client_id, secret)).json()["access_token"]
    assert client.post("/chat", json={"text": "hi"}, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    login(client, people["Helena"])
    assert client.get("/a2a-probe").status_code == 401
    assert client.get("/a2a-probe", headers={"X-Mia-Actor": people["Helena"].id, "Authorization": ""}).status_code == 401


def test_client_lockout(client: TestClient, session: Session, people: dict[str, Person]) -> None:
    row, secret = auth.create_client(session, Actor.person(people["Helena"]), "x", ["dispatcher"], utcnow())
    session.commit()
    for _ in range(10):
        client.post("/auth/token", data={"grant_type": "client_credentials"}, headers=_basic(row.client_id, "bad"))
    assert client.post("/auth/token", data={"grant_type": "client_credentials"}, headers=_basic(row.client_id, secret)).status_code == 401
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_clients.py --no-cov -q`
Expected: AttributeError `create_client`.

- [ ] **Step 3: Services, route, CLI**

Append to `node/mia/core/auth.py`:

```python
# ---- clients (OAuth2 client credentials, ADR 008) ----------------------------------------


def _role_can_approve(role: str) -> bool:
    from mia.core.rbac import get_rbac

    enforcer = get_rbac().enforcer
    return any(p[3] == "approve" for p in enforcer.get_filtered_policy(0, role))


def create_client(
    session: Session,
    actor: Actor,
    name: str,
    roles: list[str],
    now: dt.datetime,
    *,
    expires_at: dt.datetime | None = None,
) -> tuple[AuthClient, str]:
    """Register an outside client. The secret is returned once. Human roles and roles that can
    approve anything are refused (ValueError)."""
    from mia.core.people import HUMAN_ROLES

    if not roles:
        raise ValueError("at least one role")
    for role in roles:
        if role in HUMAN_ROLES:
            raise ValueError(f"{role} is a human role; clients get agent roles")
        if _role_can_approve(role):
            raise ValueError(f"{role} can approve; clients never hold approve")
    secret = keys.new_token()
    row = store.insert(
        session,
        AuthClient(
            branch_id=actor.branch_id,
            name=name,
            client_id="mia_" + keys.new_token()[:20],
            secret_hash=keys.hash_secret(secret),
            roles=list(roles),
            expires_at=expires_at,
            created_by=actor.principal.id,
        ),
        actor,
        action="auth.client_created",
    )
    return row, secret


def check_client(
    session: Session, client_id: str, secret: str, ip: str, now: dt.datetime
) -> AuthClient:
    """The active client when the secret matches (10 failures in 15 minutes block it)."""
    key = attempt_key(client_id, ip)
    if throttled(session, "client_secret", key, now):
        raise Locked(INVALID)
    row = session.exec(select(AuthClient).where(AuthClient.client_id == client_id)).first()
    stored = row.secret_hash if row else keys.dummy_hash()
    ok = (
        keys.verify_secret(secret, stored)
        and row is not None
        and row.status == "active"
        and (row.expires_at is None or row.expires_at > now)
    )
    record_attempt(session, "client_secret", key, ok, now, actor=client_actor(row) if row and ok else None)
    if not ok or row is None:
        raise AuthError(INVALID)
    store.update(session, row, {"last_used_at": now}, client_actor(row), action="auth.credential_used")
    return row


def revoke_client(session: Session, actor: Actor, client: AuthClient, now: dt.datetime) -> AuthClient:
    """Revoke a client and end its tokens."""
    revoke_sessions(session, actor, client.id, now)
    return store.update(session, client, {"status": "revoked"}, actor, action="auth.client_revoked")
```

Route in `api/auth.py`:

```python
@router.post("/token")
def token(
    request: Request,
    session: DbSession,
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    """OAuth2 client credentials (RFC 6749 section 4.4): HTTP Basic or form credentials,
    one-hour opaque bearer token, no refresh."""
    if grant_type != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    basic = request.headers.get("authorization", "")
    if basic.lower().startswith("basic "):
        try:
            client_id, client_secret = base64.b64decode(basic[6:]).decode().split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
    if not client_id or not client_secret:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    now = utcnow()
    try:
        client = auth.check_client(session, client_id, client_secret, client_ip(request), now)
    except auth.AuthError:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    tokens = auth.issue_session(session, client, method="client", aal="client", ip=client_ip(request), now=now)
    return JSONResponse(
        {"access_token": tokens.access, "token_type": "Bearer", "expires_in": int(auth.CLIENT_TTL.total_seconds())},
        headers={"Cache-Control": "no-store"},
    )
```

(imports: `base64`, `Annotated` from typing, `Form` from fastapi, `JSONResponse` from fastapi.responses). FastAPI needs `python-multipart` for `Form`; check `uv run python -c "import multipart"`. If it is missing, add `python-multipart` to pyproject with the reason "form bodies for the OAuth2 token endpoint (RFC 6749 requires `application/x-www-form-urlencoded`)". It is one small pure-Python package; mention it in the PR.

CLI: `mia auth client add NAME --role ROLE [--role ...]` prints `client_id: ... client_secret: ...` (once) and `mia auth client revoke CLIENT_ID`. The acting actor is `Actor.system(branch_id)` with `_only_branch_id`.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run pytest node/tests/auth --no-cov -q`, then the full check line. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "auth: client credentials for outside agents and services; clients never hold approve"
```

---

### Task 10: Administration (sessions and devices lists, revocation, reset) and policy

**Files:**
- Modify: `node/mia/api/auth.py`, `node/config/policies/policy.csv`
- Test: `node/tests/auth/test_admin.py`

**Interfaces:**
- Routes (all `PersonAuth`):
  - `GET /auth/sessions` -> own sessions `[{id, method, aal, ip, created_at, device_id, current: bool}]`
  - `DELETE /auth/sessions/{id}` -> revokes an own session (404 for others')
  - `GET /auth/devices?person_id=` -> own devices, or a person's for someone with `data:core.auth_devices` `read` (supervisors and up)
  - `DELETE /auth/devices/{id}` -> own device, or a person's device with `write` on `data:core.auth_devices` (supervisors and up)
  - `POST /auth/people/{person_id}/reset` -> `{enrol_url}` for admins (`write` on `data:core.auth_credentials`), event `auth.reset` with both actors.
- Policy: `p, staff, *, data:core.auth_devices, read_own, allow`, `p, staff, *, data:core.auth_devices, write_own, allow`, `p, staff, *, data:core.auth_sessions, write_own, allow`; supervisors already read `data:core.*`; add `p, supervisor, *, data:core.auth_devices, write, allow`; admins already write `data:core.*`.

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_admin.py`:

```python
"""Own sessions and devices; supervisors revoke staff devices; admins reset people."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.core import auth
from mia.core.db import utcnow
from mia.core.models import Actor, Event, Person


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


def test_own_sessions_and_devices(client: TestClient, session: Session, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    juha = people["Juha"]
    device, _ = auth.bind_device(session, Actor.person(juha), juha, "mobile", "p", utcnow())
    session.commit()
    login(client, juha, aal="aal1", method="device", device=device)
    other = TestClient(app)
    login(other, juha)
    rows = client.get("/auth/sessions").json()
    assert len(rows) == 2 and sum(r["current"] for r in rows) == 1
    away = next(r for r in rows if not r["current"])
    assert client.delete(f"/auth/sessions/{away['id']}").status_code == 200
    assert other.get("/auth/me").status_code == 401
    assert client.delete("/auth/sessions/nope").status_code == 404
    devices = client.get("/auth/devices").json()
    assert [d["id"] for d in devices] == [device.id]
    assert client.delete(f"/auth/devices/{device.id}").status_code == 200
    assert client.get("/auth/me").status_code == 401  # revoking the current device ends this session


def test_supervisor_revokes_staff_device_staff_cannot_see_others(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    juha, aino = people["Juha"], people["Aino"]
    device, _ = auth.bind_device(session, Actor.person(juha), juha, "mobile", "p", utcnow())
    session.commit()
    login(client, aino)
    assert client.get(f"/auth/devices?person_id={juha.id}").status_code == 403
    assert client.delete(f"/auth/devices/{device.id}").status_code == 403
    sup = TestClient(app)
    login(sup, people["Sanna"])
    assert [d["id"] for d in sup.get(f"/auth/devices?person_id={juha.id}").json()] == [device.id]
    assert sup.delete(f"/auth/devices/{device.id}").status_code == 200
    ev = session.exec(select(Event).where(Event.action == "auth.device_revoked")).one()
    assert ev.actor_id == people["Sanna"].id


def test_admin_reset_writes_both_actors(client: TestClient, session: Session, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Sanna"])
    assert client.post(f"/auth/people/{people['Juha'].id}/reset").status_code == 403
    admin = TestClient(app)
    login(admin, people["Helena"])
    res = admin.post(f"/auth/people/{people['Juha'].id}/reset")
    assert res.status_code == 200 and "/auth/enrol/" in res.json()["enrol_url"]
    ev = session.exec(select(Event).where(Event.action == "auth.reset")).one()
    assert ev.actor_id == people["Helena"].id and ev.entity_id == people["Juha"].id
```

Check the seeded names in `node/mia/templates/cleaning/seed.py`: `Aino` must be a cleaner (staff) and `Sanna` a supervisor; adjust the names if the seed differs.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_admin.py --no-cov -q`
Expected: 404/405 on `/auth/sessions`.

- [ ] **Step 3: Routes and policy**

Append to `node/mia/api/auth.py`:

```python
def _require(session: Session, ctx: AuthContext, obj: str, action: str, owner_id: str | None) -> None:
    from mia.core.rbac import PermissionDenied, Resource, get_rbac

    try:
        get_rbac().require(ctx.actor, Resource(obj=obj, owner_id=owner_id), action, session=session)
    except PermissionDenied as exc:
        raise HTTPException(403, "not allowed") from exc


@router.get("/sessions")
def sessions(session: DbSession, ctx: PersonAuth) -> list[dict[str, object]]:
    """The person's active sessions, oldest first."""
    from mia.core.models import AuthSession

    rows = session.exec(
        select(AuthSession)
        .where(AuthSession.subject_id == _person(ctx).id)
        .where(AuthSession.status == "active")
        .order_by(col(AuthSession.id))
    ).all()
    return [
        {"id": r.id, "method": r.method, "aal": r.aal, "ip": r.ip, "created_at": r.created_at.isoformat(),
         "device_id": r.device_id, "current": r.id == ctx.session_id}
        for r in rows
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(session: DbSession, ctx: PersonAuth, session_id: str) -> dict[str, bool]:
    """End one of the person's own sessions."""
    from mia.core.models import AuthSession

    row = session.get(AuthSession, session_id)
    if row is None or row.subject_id != _person(ctx).id or row.status != "active":
        raise HTTPException(404, "session not found")
    auth.revoke_session(session, ctx.actor, row, utcnow())
    return {"ok": True}


@router.get("/devices")
def devices(session: DbSession, ctx: PersonAuth, person_id: str | None = None) -> list[dict[str, object]]:
    """Active devices of the person, or of another person for those who may read them."""
    from mia.core.models import AuthDevice

    owner = person_id or _person(ctx).id
    _require(session, ctx, "data:core.auth_devices", "read", owner)
    rows = session.exec(
        select(AuthDevice).where(AuthDevice.person_id == owner).where(AuthDevice.status == "active").order_by(col(AuthDevice.id))
    ).all()
    return [
        {"id": d.id, "kind": d.kind, "name": d.name, "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None}
        for d in rows
    ]


@router.delete("/devices/{device_id}")
def revoke_device(session: DbSession, ctx: PersonAuth, device_id: str) -> dict[str, bool]:
    """Revoke a device (own, or a person's for supervisors and up); its sessions end at once."""
    from mia.core.models import AuthDevice

    row = session.get(AuthDevice, device_id)
    if row is None or row.status != "active" or row.branch_id != ctx.actor.branch_id:
        raise HTTPException(404, "device not found")
    _require(session, ctx, "data:core.auth_devices", "write", row.person_id)
    auth.revoke_device(session, ctx.actor, row, utcnow())
    return {"ok": True}


@router.post("/people/{person_id}/reset")
def reset_person(session: DbSession, ctx: PersonAuth, person_id: str) -> dict[str, str]:
    """Admin reset: every session and device of the person ends; a new enrolment link."""
    from mia.settings import get_settings

    target = session.get(Person, person_id)
    if target is None or target.branch_id != ctx.actor.branch_id:
        raise HTTPException(404, "person not found")
    _require(session, ctx, "data:core.auth_credentials", "write", None)
    code = auth.start_enrolment(session, ctx.actor, target, utcnow(), reason="reset")
    return {"enrol_url": f"{get_settings().MIA_PUBLIC_URL.rstrip('/')}/auth/enrol/{code}"}
```

(import `col`, `select` from sqlmodel and `Session`). The 403 for a staff member listing another person's devices comes from `_require`: `read_own` only matches when `owner_id == principal.id`. The 404 vs 403 order in `revoke_device` is deliberate: the row must exist in the branch first, then the permission is checked, so a staff member learns nothing about other branches.

`policy.csv` additions (under `# staff`):

```
p, staff, *, data:core.auth_devices, read_own, allow
p, staff, *, data:core.auth_devices, write_own, allow
```

and under `# supervisor`: `p, supervisor, *, data:core.auth_devices, write, allow`.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run pytest node/tests/auth --no-cov -q`, then the full check line. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "auth: session and device lists, revocation by the person and supervisors, admin reset; policy rows"
```

---

### Task 11: Edge, docs and the secret scan

**Files:**
- Modify: `node/mia/api/main.py` (`/health` reduced behind Cloudflare), `README.md`, `.env.example`, `deploy/install.md`, `deploy/docker-compose.yml` (master key as a secret), `docs/adr/011-authentication.md`, `docs/decisions.md` (D33), `docs/layout.md`, `docs/plan.md` (status), `docs/superpowers/specs/2026-10-05-authentication-design.md` (status line)
- Test: `node/tests/auth/test_edge.py`

- [ ] **Step 1: Write the failing tests**

`node/tests/auth/test_edge.py`:

```python
"""The public /health, and a scan of events and logs after a full run for secrets."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.core import auth, keys
from mia.core.db import utcnow
from mia.core.models import Actor, Event, Person


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


def test_health_behind_cloudflare_is_status_only(client: TestClient) -> None:
    full = client.get("/health").json()
    assert full["auth_mode"] == "dev" and "version" in full
    public = client.get("/health", headers={"CF-Ray": "abc"}).json()
    assert public == {"status": "ok"}


def test_full_run_leaves_no_secret_in_events_or_logs(
    client: TestClient, session: Session, people: dict[str, Person], login, caplog: pytest.LogCaptureFixture
) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    helena = people["Helena"]
    pw = "a long enough password"
    auth.set_password(session, Actor.person(helena), helena, "helena@example.fi", pw, utcnow())
    session.commit()
    login(client, helena)
    client.post("/auth/mfa/enrol")
    client.post("/auth/pin", json={"pin": "273916"})
    client.post("/auth/stepup", json={"pin": "273916"})
    tokens = client.post("/auth/login", json={"email": "helena@example.fi", "password": pw}).json()
    row, secret = auth.create_client(session, Actor.person(helena), "x", ["dispatcher"], utcnow())
    session.commit()
    haystack = " ".join(f"{e.before} {e.after}" for e in session.exec(select(Event))) + caplog.text
    for needle in (pw, "273916", secret, tokens.get("access", ""), tokens.get("refresh", "")):
        if needle:
            assert needle not in haystack and keys.token_hash(needle) not in haystack
    assert "scrypt$" not in haystack
    from mia.core.events import verify_chain

    assert verify_chain(session)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest node/tests/auth/test_edge.py --no-cov -q`
Expected: the public `/health` still returns everything.

- [ ] **Step 3: Reduced /health, compose secret, docs**

`main.py` `/health`: take `request: Request`; when `cf-ray` is in the headers (the tunnel) return `{"status": "ok"}` only.

`deploy/docker-compose.yml`: mount the master key as a secret:

```yaml
  node:
    environment:
      MIA_MASTER_KEY_FILE: /run/secrets/mia_master_key
      MIA_TRUSTED_PROXIES: ""   # tunnel traffic reaches the node on the compose network; set the tunnel container's IP to trust CF-Connecting-IP
    secrets:
      - mia_master_key
secrets:
  mia_master_key:
    file: ./master.key
```

and `deploy/install.md` gains a step: `python3 -c "import secrets,sys; sys.stdout.buffer.write(secrets.token_bytes(32))" > master.key && chmod 400 master.key` (or `uv run mia keys init deploy/master.key` on a machine with the repo), keep a copy outside the data folder, and never put it in a backup target. Docker secrets are mounted mode 0400 for the container user when `secrets:` names the file. Also document: `MIA_AUTH_MODE` stays `required` on a server; `mia auth bootstrap --email ...` run inside the container (`docker compose exec node mia auth bootstrap --email owner@example.fi`) prints the first enrolment link; the Cloudflare ingress allowlist (`/auth/*`, `/chat*`, `/ag-ui*`, `/approvals/*`, `/notifications`, `/channels/*/webhook`, `/health`, `/`, `/static/*`) and the WhatsApp two-step verification advice for staff; the `mia_login_code` authentication template must be approved in WhatsApp Manager before staff can sign in by phone.

`README.md`: an "Authentication" section (dev mode and the header; `mia keys init`, `mia auth bootstrap`, `mia auth reset`, `mia auth unlock`, `mia auth link`, `mia auth client add`; the login flows in two sentences each; the PIN). `.env.example`: the new variables (Task 2) plus a line on `MIA_AUTH_MODE=dev` being for development only.

`docs/adr/011-authentication.md`: status "Accepted (D17), built 2026-10 (this plan)"; consequences add: rule 1 keeps refreshes as events; `api/deps.py` holds the dependencies; `python-multipart` if it was added in Task 9; the render.py "View in the Mia app" link stays a plain URL to the login page until a per-person link is wired into rendering (follow-up).

`docs/decisions.md` D33: "Authentication built as designed (ADR 011): data standard 1.3 in effect; refresh rotations are events (rule 1 over the spec); `python-multipart` added for the OAuth2 token endpoint if needed; passkeys and SMS still wait for approval." `docs/plan.md` status: item 1 built. `docs/layout.md`: `tests/auth/`.

- [ ] **Step 4: Run the full suite and the smoke commands**

Run: the full check line, then `cp .env.example .env.ci && MIA_DB_PATH=/tmp/ci.db uv run mia migrate && MIA_DB_PATH=/tmp/ci.db uv run mia seed && MIA_DB_PATH=/tmp/ci.db uv run mia chat "Olen kipeä huomenna." --as Juha` (what CI runs) and `uv run mia auth bootstrap --email owner@example.fi` against that database.
Expected: all pass, the bootstrap link prints.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "auth: public health is status only; master key as a Docker secret; docs, ADR 011 consequences, D33"
```

---

## Self-review notes

- Spec coverage: section 3 identities (Tasks 4, 7, 9); 4.1 (Task 5), 4.2 passkeys (out, approval), 4.3 (Task 6), 4.4 (Task 7), 4.5 (Task 7: link via `mia auth link` and `send_login_link`; the chat intent "open the app" and the sensitive-block link are follow-ups noted in ADR 011); 5 (Task 4); 6 (Task 4: `AuthContext`, `approvals.decide` from the context, `ChatRequest.actor_id` removed); 7 (Task 9; A2A routes do not exist yet, `ClientAuth` is ready for them); 8 (Task 8); 9 (Task 6 and Task 10); 10 (Task 3, limits table); 11 (Task 2 keys and settings, Task 11 ingress); 12 (Task 1); 12.3 events: every name in the list is emitted by some task except `auth.passkey_added` (passkeys out); 13 (no dependency, except `python-multipart` if FastAPI lacks form support in this environment); 14 (Tasks 4 and 11); 15 (every bullet has a test above; equal timing is by construction: a dummy scrypt verify runs for unknown logins, pinned by `test_wrong_password_unknown_login_and_lockout_look_the_same` on the response, not on time).
- Deviation from the spec, recorded in Task 11: refreshes are events (rule 1).
- Type consistency: `Tokens`, `AuthContext`, `CodeResult`, `Limit` are defined once (Tasks 3 and 4) and used with the same field names; `credential()` is the public name of the credential lookup (Task 5 renames the private `_credential` once, every later task uses `credential`). `start_enrolment(..., reason=, via=)` gains `via` in Task 6.
- Review Focus: each line names its test and task above.
