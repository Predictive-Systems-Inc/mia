"""Authentication services (ADR 011): rate limits, one-time codes, credentials, sessions,
devices and clients. Every write goes through store and emits an event; secrets never do.

Failures raise AuthError with one message, `invalid credentials`, whatever was wrong; Locked
when a limit holds. Times come in as arguments so tests can move the clock.
"""

import datetime as dt
import secrets
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from sqlmodel import Session, col, select

from mia.core import events, keys, store
from mia.core.approvals import STEP_UP_TTL, StepUpRequired
from mia.core.models import (
    Actor,
    AuthAttempt,
    AuthCode,
    AuthCredential,
    Person,
    Principal,
)

__all__ = ["STEP_UP_TTL", "StepUpRequired"]

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


class AuthError(RuntimeError):
    """A failed credential check. Routes answer 401 with the same body for every cause."""


class Locked(AuthError):
    """A limit from spec section 10 holds (or a PIN is locked)."""


@dataclass(frozen=True)
class Limit:
    count: int
    window: dt.timedelta
    block: dt.timedelta


M15, H1 = dt.timedelta(minutes=15), dt.timedelta(hours=1)
M5 = dt.timedelta(minutes=5)
LIMITS: dict[str, Limit] = {
    "password": Limit(5, M15, M15),  # per (login, IP)
    "password_login": Limit(20, H1, M15),  # per login, any IP
    "ip": Limit(50, M15, M15),  # any kind, per IP
    "client_secret": Limit(10, M15, M15),
    "device": Limit(10, M15, M15),
    "link_code": Limit(5, H1, H1),
    "otp": Limit(5, M5, M5),
    "mfa": Limit(5, M5, M5),
}
EVENT_NAME = {"password": "login", "client_secret": "client", "link_code": "link"}


def auth_actor(branch_id: str = "") -> Actor:
    """The system principal that records failures before anyone is known."""
    return Actor(principal=Principal(type="system", id="auth"), branch_id=branch_id)


def normalise_login(login: str) -> str:
    """Lowercased, trimmed email."""
    return login.strip().lower()


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
    stmt = (
        select(AuthAttempt)
        .where(AuthAttempt.ok == False)
        .where(col(AuthAttempt.created_at) > since)
    )
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
    return limit is not None and _over(session, now, limit, kind=kind, key=key)


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


def _locked_event(session: Session, kind: str, subject: str) -> None:
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
    session: Session,
    purpose: str,
    now: dt.datetime,
    *,
    address: str | None,
    person_id: str | None,
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
        store.update(
            session,
            row,
            {"tries": row.tries + 1},
            auth_actor(row.branch_id),
            action="auth.code_try",
        )


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


def credential(
    session: Session, person_id: str, kind: str, statuses: tuple[str, ...] = ("active",)
) -> AuthCredential | None:
    """The newest credential of a kind in one of the statuses, if any."""
    return session.exec(
        select(AuthCredential)
        .where(AuthCredential.person_id == person_id)
        .where(AuthCredential.kind == kind)
        .where(col(AuthCredential.status).in_(statuses))
        .order_by(col(AuthCredential.id).desc())
    ).first()


def set_password(
    session: Session, actor: Actor, person: Person, login: str, password: str, now: dt.datetime
) -> AuthCredential:
    """Set or replace the person's password and login. Raises ValueError on a bad login, a
    short password or a login another person holds. The caller ends other sessions."""
    login = normalise_login(login)
    if "@" not in login or " " in login:
        raise ValueError("login must be an email address")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must have at least {MIN_PASSWORD} characters")
    other = session.exec(select(AuthCredential).where(AuthCredential.login == login)).first()
    if other is not None and other.person_id != person.id:
        raise ValueError("that email is already in use")
    changes = {"login": login, "secret_hash": keys.hash_secret(password), "status": "active"}
    row = credential(session, person.id, "password", ("active", "revoked"))
    if row is None:
        return store.insert(
            session,
            AuthCredential(
                branch_id=person.branch_id, person_id=person.id, kind="password", **changes
            ),
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
    record_attempt(session, "password", key, ok, now, actor=Actor.person(found[0]) if ok else None)
    if not ok or found is None:
        if _over(session, now, LIMITS["password_login"], kind="password", prefix=f"{subject}@"):
            _locked_event(session, "password", subject)
        raise AuthError(INVALID)
    store.update(
        session,
        found[1],
        {"last_used_at": now},
        Actor.person(found[0]),
        action="auth.credential_used",
    )
    return found[0]


def needs_mfa(session: Session, person: Person) -> bool:
    """Owner, admin and accountant always; anyone who enrolled TOTP."""
    return bool(MFA_ROLES & set(person.roles)) or has_mfa(session, person)


def has_mfa(session: Session, person: Person) -> bool:
    """True when an active TOTP credential exists."""
    return credential(session, person.id, "totp") is not None


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
        store.update(
            session, old, {"status": "revoked"}, actor, action="auth.mfa_enrolment_dropped"
        )
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
    pw = credential(session, person.id, "password")
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
    for old in session.exec(
        select(AuthCredential)
        .where(AuthCredential.person_id == cred.person_id)
        .where(AuthCredential.kind == "recovery_code")
        .where(AuthCredential.status == "active")
    ):
        store.update(
            session, old, {"status": "revoked"}, actor, action="auth.recovery_code_revoked"
        )
    codes = [f"{secrets.randbelow(10**4):04d}-{secrets.randbelow(10**4):04d}" for _ in range(10)]
    for plain in codes:
        store.insert(
            session,
            AuthCredential(
                branch_id=cred.branch_id,
                person_id=cred.person_id,
                kind="recovery_code",
                secret_hash=keys.hash_secret(plain),
            ),
            actor,
            action="auth.recovery_code_created",
        )
    return codes


def check_totp(session: Session, person: Person, code: str, now: dt.datetime) -> bool:
    """True for a fresh code in the current step or one step either side. Each step once."""
    cred = credential(session, person.id, "totp")
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
                session,
                row,
                {"status": "used", "last_used_at": now},
                actor,
                action="auth.recovery_code_used",
            )
            return True
    return False


def trivial_pin(pin: str) -> bool:
    """All one digit, or a straight run up or down (123456, 654321, 012345)."""
    digits = [int(c) for c in pin]
    steps = {b - a for a, b in pairwise(digits)}
    return len(set(digits)) == 1 or steps == {1} or steps == {-1}


def set_pin(
    session: Session, actor: Actor, person: Person, pin: str, now: dt.datetime
) -> AuthCredential:
    """Set or replace the 6-digit PIN. Raises ValueError for a non-numeric or trivial PIN."""
    if len(pin) != 6 or not pin.isdigit():
        raise ValueError("the PIN is 6 digits")
    if trivial_pin(pin):
        raise ValueError("choose a less obvious PIN")
    changes = {"secret_hash": keys.hash_secret(pin), "status": "active", "last_used_at": now}
    row = credential(session, person.id, "pin", ("active", "locked"))
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
    return credential(session, person.id, "pin", ("active", "locked")) is not None


def check_pin(session: Session, person: Person, pin: str, ip: str, now: dt.datetime) -> bool:
    """True for the right PIN. Five failures since the last success lock it (Locked)."""
    cred = credential(session, person.id, "pin", ("active", "locked"))
    if cred is None:
        return False
    if cred.status == "locked":
        raise Locked("pin locked")
    key = attempt_key(person.id, ip)
    ok = bool(cred.secret_hash) and keys.verify_secret(pin, cred.secret_hash or "")
    record_attempt(session, "pin", key, ok, now, actor=Actor.person(person))
    if ok:
        store.update(
            session,
            cred,
            {"last_used_at": now},
            Actor.person(person),
            action="auth.credential_used",
        )
        return True
    since = cred.last_used_at or cred.created_at
    failures = session.exec(
        select(AuthAttempt)
        .where(AuthAttempt.kind == "pin")
        .where(col(AuthAttempt.key).startswith(f"{person.id}@"))
        .where(AuthAttempt.ok == False)
        .where(col(AuthAttempt.created_at) >= since)  # inclusive: same instant as the last success
    ).all()
    if len(failures) >= PIN_FAILURES:
        store.update(
            session, cred, {"status": "locked"}, Actor.person(person), action="auth.pin_locked"
        )
    return False


def unlock_pin(session: Session, actor: Actor, person: Person, now: dt.datetime) -> None:
    """After a login with MFA or a phone code: a locked PIN is active again."""
    cred = credential(session, person.id, "pin", ("locked",))
    if cred is not None:
        store.update(
            session,
            cred,
            {"status": "active", "last_used_at": now},
            actor,
            action="auth.pin_unlocked",
        )
