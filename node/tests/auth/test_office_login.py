"""Office login over HTTP: password then TOTP, enrolment, recovery codes, refresh, logout,
cookies and the CSRF origin check."""

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
EMAIL = "helena@example.fi"


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


@pytest.fixture
def owner(session: Session, people: dict[str, Person]) -> Person:
    helena = people["Helena"]
    auth.set_password(session, Actor.person(helena), helena, EMAIL, PW, utcnow())
    session.commit()
    return helena


def _totp_now(session: Session, person: Person) -> str:
    cred = session.exec(
        select(AuthCredential)
        .where(AuthCredential.person_id == person.id)
        .where(AuthCredential.kind == "totp")
        .where(AuthCredential.status != "revoked")
    ).one()
    session.refresh(cred)
    seed = keys.totp_seed(cred.id, cred.data["nonce"])
    step = keys.totp_step(utcnow())
    # Each step is accepted once; the window allows one step ahead for a second use.
    return keys.hotp(seed, step if int(cred.data.get("last_step", 0)) < step else step + 1)


def _enrol(client: TestClient, session: Session, person: Person) -> list[str]:
    assert client.post("/auth/mfa/enrol").status_code == 200
    res = client.post("/auth/mfa/confirm", json={"code": _totp_now(session, person)})
    assert res.status_code == 200, res.text
    return res.json()["recovery_codes"]  # type: ignore[no-any-return]


def _login_mfa(
    client: TestClient, session: Session, person: Person, code: str | None = None, **headers: str
) -> dict:  # type: ignore[type-arg]
    res = client.post("/auth/login", json={"email": EMAIL, "password": PW}, headers=headers)
    assert res.status_code == 200 and res.json()["mfa_required"] is True, res.text
    res = client.post(
        "/auth/mfa",
        json={"mfa_token": res.json()["mfa_token"], "code": code or _totp_now(session, person)},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res  # type: ignore[return-value]


def test_owner_without_mfa_gets_an_enrol_session_then_full_access(
    client: TestClient, session: Session, owner: Person
) -> None:
    res = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    assert res.status_code == 200 and res.json()["enrol"] is True
    assert res.json()["aal"] == "enrol"
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.post("/chat", json={"text": "hi"}).status_code == 403
    assert client.get("/auth/me").status_code == 200
    res = client.post("/auth/mfa/enrol")
    assert res.json()["uri"].startswith("otpauth://")
    assert client.post("/auth/mfa/confirm", json={"code": "000000"}).status_code == 401
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


def test_dev_header_never_works_on_auth_routes(client: TestClient, owner: Person) -> None:
    assert client.get("/auth/me", headers={"X-Mia-Actor": owner.id}).status_code == 401


def test_password_then_totp_then_refresh_then_logout(
    client: TestClient, session: Session, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    recovery = _enrol(client, session, owner)
    client.headers.pop("Authorization")
    res = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    mfa_token = res.json()["mfa_token"]
    bad = client.post("/auth/mfa", json={"mfa_token": mfa_token, "code": "000000"})
    assert bad.status_code == 401
    res = client.post("/auth/mfa", json={"mfa_token": mfa_token, "code": _totp_now(session, owner)})
    assert res.status_code == 200 and res.json()["aal"] == "aal2"
    tokens = res.json()
    used = client.post("/auth/mfa", json={"mfa_token": mfa_token, "code": "1"})
    assert used.status_code == 401  # the mfa token is single use
    client.headers["Authorization"] = f"Bearer {tokens['access']}"
    me = client.get("/auth/me").json()
    assert me["person_id"] == owner.id and me["method"] == "password_totp"
    res = client.post("/auth/refresh", json={"refresh": tokens["refresh"]})
    assert res.status_code == 200 and res.json()["access"] != tokens["access"]
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout").json() == {"ok": True}
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/refresh", json={"refresh": tokens["refresh"]}).status_code == 401
    # A recovery code in place of TOTP, once.
    res = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    res = client.post("/auth/mfa", json={"mfa_token": res.json()["mfa_token"], "code": recovery[0]})
    assert res.status_code == 200
    res = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    res = client.post("/auth/mfa", json={"mfa_token": res.json()["mfa_token"], "code": recovery[0]})
    assert res.status_code == 401


def test_wrong_password_unknown_login_and_lockout_look_the_same(
    client: TestClient, owner: Person
) -> None:
    bad = client.post("/auth/login", json={"email": EMAIL, "password": "nope"})
    unknown = client.post("/auth/login", json={"email": "x@example.fi", "password": "nope"})
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()
    for _ in range(5):
        client.post("/auth/login", json={"email": EMAIL, "password": "nope"})
    locked = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    assert locked.status_code == 401 and locked.json() == bad.json()


def test_mfa_token_void_after_five_tries(
    client: TestClient, session: Session, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    _enrol(client, session, owner)
    client.headers.pop("Authorization")
    res = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    token = res.json()["mfa_token"]
    for _ in range(5):
        client.post("/auth/mfa", json={"mfa_token": token, "code": "000000"})
    res = client.post("/auth/mfa", json={"mfa_token": token, "code": _totp_now(session, owner)})
    assert res.status_code == 401


def test_cookie_flags_follow_public_url_and_csrf_origin(
    client: TestClient, session: Session, owner: Person, login, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    recovery = _enrol(client, session, owner)
    client.headers.pop("Authorization")
    res = _login_mfa(client, session, owner, **{"X-Mia-Client": "web"})
    cookies = res.headers.get_list("set-cookie")
    at = next(c for c in cookies if c.startswith("mia_at="))
    rt = next(c for c in cookies if c.startswith("mia_rt="))
    assert "HttpOnly" in at and "samesite=strict" in at.lower() and "Secure" not in at
    assert "Path=/auth/refresh" in rt
    assert res.json()["access"] is None  # web clients get cookies, not tokens in the body
    assert client.get("/auth/me").status_code == 200
    # Cookie auth on an unsafe method needs the right Origin.
    assert client.post("/chat", json={"text": "hi"}).status_code == 403
    evil = {"Origin": "https://evil.example"}
    assert client.post("/chat", json={"text": "hi"}, headers=evil).status_code == 403
    good = {"Origin": "http://localhost:8000"}
    assert client.post("/chat", json={"text": "hi"}, headers=good).status_code == 200
    assert client.post("/auth/refresh", headers=good).status_code == 200
    monkeypatch.setenv("MIA_PUBLIC_URL", "https://mia.example.fi")
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    client.cookies.clear()
    res = _login_mfa(client, session, owner, recovery[0], **{"X-Mia-Client": "web"})
    at = next(c for c in res.headers.get_list("set-cookie") if c.startswith("mia_at="))
    assert "Secure" in at


def test_password_change_ends_other_sessions(
    client: TestClient, session: Session, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    first = login(client, owner)
    other = TestClient(app)
    login(other, owner)
    body = {"password": "a brand new long password", "current": PW}
    res = client.post("/auth/password", json=body)
    assert res.status_code == 200, res.text
    assert client.get("/auth/me").status_code == 200  # the session that changed it stays
    assert other.get("/auth/me").status_code == 401
    assert session.exec(select(Event).where(Event.action == "auth.password_set")).all()
    session.refresh(first.row)
    assert first.row.status == "active"


def test_no_secret_in_events_or_responses(
    client: TestClient, session: Session, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    recovery = _enrol(client, session, owner)
    client.headers.pop("Authorization")
    res = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    body = res.json()
    res = client.post(
        "/auth/mfa", json={"mfa_token": body["mfa_token"], "code": _totp_now(session, owner)}
    )
    tokens = res.json()
    text = " ".join(str(e.after) + str(e.before) for e in session.exec(select(Event)))
    for secret in (PW, body["mfa_token"], tokens["access"], tokens["refresh"], *recovery):
        assert secret not in text
        assert keys.token_hash(secret) not in text
    assert not re.search(r"scrypt\$", text)


def test_password_change_needs_the_current_password(
    client: TestClient, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    new = {"password": "a brand new long password"}
    assert client.post("/auth/password", json=new).status_code == 401
    assert client.post("/auth/password", json={**new, "current": "nope"}).status_code == 401
    assert client.post("/auth/password", json={**new, "current": PW}).status_code == 200
    client.headers.pop("Authorization")
    res = client.post("/auth/login", json={"email": EMAIL, "password": "a brand new long password"})
    assert res.status_code == 200


def test_staff_session_cannot_set_password_or_enrol_mfa(
    client: TestClient, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    """A phone or device session (aal1) must not become an office login."""
    login(client, people["Juha"], aal="aal1", method="phone_otp")
    body = {"password": "a long enough password", "email": "juha@example.fi"}
    assert client.post("/auth/password", json=body).status_code == 403
    assert client.post("/auth/mfa/enrol").status_code == 403


def test_mfa_guesses_are_limited_per_person_not_per_token(
    client: TestClient, session: Session, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    _enrol(client, session, owner)
    client.headers.pop("Authorization")
    for _ in range(5):
        token = client.post("/auth/login", json={"email": EMAIL, "password": PW}).json()[
            "mfa_token"
        ]
        client.post("/auth/mfa", json={"mfa_token": token, "code": "000000"})
    token = client.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["mfa_token"]
    res = client.post("/auth/mfa", json={"mfa_token": token, "code": _totp_now(session, owner)})
    assert (
        res.status_code == 401
    )  # five wrong guesses in five minutes: blocked, fresh tokens or not


def test_current_password_guesses_are_limited_without_locking_the_login(
    client: TestClient, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    new = {"password": "a brand new long password"}
    for _ in range(5):
        client.post("/auth/password", json={**new, "current": "nope"})
    assert client.post("/auth/password", json={**new, "current": PW}).status_code == 401
    other = TestClient(app)  # the login itself is not locked by those guesses
    res = other.post("/auth/login", json={"email": EMAIL, "password": PW})
    assert res.status_code == 200


def test_mfa_guesses_are_capped_per_person_across_ips(
    session: Session, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    """Rotating IPs must not give unlimited TOTP guesses with a stolen password."""
    first = TestClient(app)
    login(first, owner)
    _enrol(first, session, owner)
    for ip in range(4):
        far = TestClient(app, client=(f"10.0.0.{ip}", 4000))
        for _ in range(5):
            token = far.post("/auth/login", json={"email": EMAIL, "password": PW}).json()[
                "mfa_token"
            ]
            far.post("/auth/mfa", json={"mfa_token": token, "code": "000000"})
    fresh = TestClient(app, client=("10.0.1.1", 4000))
    token = fresh.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["mfa_token"]
    res = fresh.post("/auth/mfa", json={"mfa_token": token, "code": _totp_now(session, owner)})
    assert res.status_code == 401  # 20 failures in an hour: the person's MFA is paused


def test_non_ascii_code_is_refused_not_a_crash(
    client: TestClient, session: Session, owner: Person, login
) -> None:  # type: ignore[no-untyped-def]
    login(client, owner)
    client.post("/auth/mfa/enrol")
    assert client.post("/auth/mfa/confirm", json={"code": "12345ä"}).status_code == 401
    _enrol(client, session, owner)
    client.headers.pop("Authorization")
    token = client.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["mfa_token"]
    res = client.post("/auth/mfa", json={"mfa_token": token, "code": "12345ä"})
    assert res.status_code == 401
    session.expire_all()
    assert session.exec(select(Event).where(Event.action == "auth.mfa_failed")).first()
