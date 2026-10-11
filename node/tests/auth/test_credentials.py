"""Lockouts, one-time codes, passwords, TOTP, recovery codes and PINs."""

import datetime as dt

import pytest
from sqlmodel import Session, col, select

from mia.core import auth, keys
from mia.core.db import utcnow
from mia.core.models import Actor, AuthCode, AuthCredential, Event, Person

IP = "203.0.113.5"


def _owner(people: dict[str, Person]) -> tuple[Person, Actor]:
    helena = people["Helena"]
    return helena, Actor.person(helena)


def _actions(session: Session) -> list[str]:
    return [
        e.action for e in session.exec(select(Event).where(col(Event.action).startswith("auth.")))
    ]


def test_password_round_trip_and_generic_failure(
    session: Session, people: dict[str, Person]
) -> None:
    helena, actor = _owner(people)
    now = utcnow()
    cred = auth.set_password(session, actor, helena, " Helena@Example.FI ", "correct horse 1", now)
    assert cred.login == "helena@example.fi"
    assert cred.secret_hash and cred.secret_hash != "correct horse 1"
    found = auth.check_password(session, "HELENA@example.fi", "correct horse 1", IP, now)
    assert found.id == helena.id
    for login, pw in (("helena@example.fi", "nope"), ("nobody@example.fi", "nope")):
        with pytest.raises(auth.AuthError, match="invalid credentials"):
            auth.check_password(session, login, pw, IP, now)
    actions = _actions(session)
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
        auth.set_password(
            session, actor, people["Sanna"], "h@e.fi", "another long password", utcnow()
        )


def test_lockout_per_pair_login_and_ip(session: Session, people: dict[str, Person]) -> None:
    helena, actor = _owner(people)
    now = utcnow()
    auth.set_password(session, actor, helena, "h@e.fi", "long enough password", now)
    for _ in range(5):
        with pytest.raises(auth.AuthError):
            auth.check_password(session, "h@e.fi", "wrong", IP, now)
    with pytest.raises(auth.Locked):  # the (login, IP) pair is blocked, right password or not
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


def test_codes_single_use_expiry_tries_and_sends(
    session: Session, people: dict[str, Person]
) -> None:
    juha, actor = people["Juha"], Actor.person(people["Juha"])
    now = utcnow()
    code = auth.create_code(session, actor, juha, "otp_login", now, address="358401")
    assert code.isdigit() and len(code) == 6
    row = session.exec(select(AuthCode)).one()
    assert row.code_hmac == keys.code_hmac(code) and row.address == "358401" and row.tries == 0
    assert auth.check_code(session, "otp_login", "000000", now).status == "invalid"
    assert auth.check_code(session, "mfa", code, now).status == "invalid"  # wrong purpose
    six = now + dt.timedelta(minutes=6)
    assert auth.check_code(session, "otp_login", code, six).status == "expired"
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
    step = keys.totp_step(now)
    assert not auth.check_totp(session, helena, keys.hotp(seed, step), now)  # still pending
    with pytest.raises(auth.AuthError):
        auth.confirm_totp(session, actor, cred, "000000", now)
    recovery = auth.confirm_totp(session, actor, cred, keys.hotp(seed, step), now)
    assert len(recovery) == 10 and cred.status == "active" and auth.has_mfa(session, helena)
    assert not auth.check_totp(session, helena, keys.hotp(seed, step), now)  # used at confirm
    assert auth.check_totp(session, helena, keys.hotp(seed, step + 1), now)  # one step either side
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
