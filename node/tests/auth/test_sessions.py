"""Sessions: issue, verify, rotate, reuse detection, lifetimes, devices, the auth dependency,
the dev header rules and the approval step-up."""

import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.core import auth
from mia.core.db import utcnow
from mia.core.models import Actor, AuthClient, Event, Person
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
    helena = people["Helena"]
    t = auth.issue_session(session, helena, method="password_totp", aal="aal2", ip=IP, now=now)
    assert t.refresh
    at = now + auth.OFFICE_MAX + dt.timedelta(seconds=1)
    with pytest.raises(auth.AuthError):
        auth.refresh_session(session, t.refresh, at)
    assert t.row.status == "revoked"
    idle = auth.issue_session(session, helena, method="password_totp", aal="aal2", ip=IP, now=now)
    assert idle.refresh
    with pytest.raises(auth.AuthError):
        auth.refresh_session(
            session, idle.refresh, now + auth.OFFICE_IDLE + dt.timedelta(seconds=1)
        )


def test_staff_device_lifetimes_and_revoke(session: Session, people: dict[str, Person]) -> None:
    juha, actor = people["Juha"], Actor.person(people["Juha"])
    now = utcnow()
    device, secret = auth.bind_device(session, actor, juha, "mobile", "iPhone", now)
    assert secret and len(secret) == 43 and device.secret_hash != secret
    t = auth.issue_session(
        session, juha, method="phone_otp", aal="aal1", ip=IP, now=now, device=device
    )
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
    helena = people["Helena"]
    client = AuthClient(
        branch_id=helena.branch_id,
        name="n",
        client_id="mia_x",
        secret_hash="s",
        roles=["dispatcher"],
        created_by=helena.id,
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
    assert client.post("/chat", json={"text": "hi"}).status_code == 200
    assert client.get("/notifications").status_code == 200


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
    hdr = {"X-Mia-Actor": juha}
    assert client.post("/chat", json={"text": "hi"}, headers=hdr).status_code == 200
    via_cf = {"X-Mia-Actor": juha, "CF-Connecting-IP": "198.51.100.7"}
    assert client.post("/chat", json={"text": "hi"}, headers=via_cf).status_code == 401
    client.post("/chat", json={"text": "again"}, headers=hdr)
    from mia.core.db import session_scope

    with session_scope() as s:  # auth.dev_header_used is written once per process and person
        rows = s.exec(select(Event).where(Event.action == "auth.dev_header_used")).all()
        assert len([r for r in rows if r.actor_id == juha]) == 1


def test_inactive_person_gets_403_and_roles_are_read_fresh(
    client: TestClient, people: dict[str, Person], session: Session, login
) -> None:  # type: ignore[no-untyped-def]
    from mia.core import people as people_service
    from mia.core import store

    sanna = people["Sanna"]
    login(client, sanna)
    assert client.get("/notifications").status_code == 200
    store.update(session, sanna, {"roles": ["staff"]}, Actor.person(people["Helena"]))
    session.commit()
    assert client.get("/notifications").status_code == 200  # still signed in, roles now staff
    store.update(session, sanna, {"status": "inactive"}, Actor.person(people["Helena"]))
    session.commit()
    assert client.get("/notifications").status_code == 403  # a valid token, an inactive person
    store.update(session, sanna, {"status": "active"}, Actor.person(people["Helena"]))
    people_service.deactivate(session, Actor.person(people["Helena"]), sanna)
    session.commit()
    assert client.get("/notifications").status_code == 401  # deactivation revoked the session


def test_enrol_session_reaches_only_auth_routes(
    client: TestClient, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Helena"], aal="enrol", method="enrol")
    assert client.post("/chat", json={"text": "hi"}).status_code == 403


def test_dev_mode_refuses_a_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from mia.api.deps import check_mode

    monkeypatch.setenv("MIA_PUBLIC_URL", "https://mia.example.fi")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="MIA_AUTH_MODE=dev"):
        check_mode(get_settings())
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    check_mode(get_settings())


def test_client_ip_trusts_cf_header_only_from_a_trusted_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mia.api.deps import client_ip

    req = SimpleNamespace(
        client=SimpleNamespace(host="172.18.0.9"), headers={"cf-connecting-ip": "198.51.100.7"}
    )
    assert client_ip(req) == "172.18.0.9"  # type: ignore[arg-type]
    monkeypatch.setenv("MIA_TRUSTED_PROXIES", "172.18.0.9, 10.0.0.1")
    get_settings.cache_clear()
    assert client_ip(req) == "198.51.100.7"  # type: ignore[arg-type]
    monkeypatch.setenv("MIA_TRUSTED_PROXIES", "172.16.0.0/12")  # the compose network (CIDR)
    get_settings.cache_clear()
    assert client_ip(req) == "198.51.100.7"  # type: ignore[arg-type]
    monkeypatch.setenv("MIA_TRUSTED_PROXIES", "10.0.0.0/8")
    get_settings.cache_clear()
    assert client_ip(req) == "172.18.0.9"  # type: ignore[arg-type]


# ---- approvals need a step-up ------------------------------------------------------------


def test_app_only_approval_needs_aal2_and_a_fresh_step_up(
    session: Session, people: dict[str, Person]
) -> None:
    from mia.core import approvals

    helena = Actor.person(people["Helena"])
    row = approvals.request(
        session,
        "dispatcher.cover_override",
        ("visit", "V"),
        "x",
        Actor.person(people["Sanna"]),
        ["admin"],
        "app_only",
    )
    now = utcnow()
    stale = now - auth.STEP_UP_TTL - dt.timedelta(seconds=1)
    for kw in (
        {"aal": "aal1", "stepped_up_at": now},
        {"aal": "aal2", "stepped_up_at": None},
        {"aal": "aal2", "stepped_up_at": stale},
        {"aal": "aal2", "stepped_up_at": now, "channel": "whatsapp"},
    ):
        with pytest.raises(approvals.ApprovalError):
            approvals.decide(session, row.id, helena, "approved", **kw)  # type: ignore[arg-type]
    denied = session.exec(select(Event).where(Event.action == "approval.refused")).all()
    assert len(denied) == 4
    approvals.decide(session, row.id, helena, "approved", aal="aal2", stepped_up_at=now)
    assert row.status == "approved"


def test_dev_header_refused_from_a_non_loopback_peer(
    branch: object, people: dict[str, Person]
) -> None:
    """The peer address decides, not a name: only loopback peers may use the header."""
    far = TestClient(app, client=("10.0.0.5", 4000))
    assert (
        far.post(
            "/chat", json={"text": "hi"}, headers={"X-Mia-Actor": people["Juha"].id}
        ).status_code
        == 401
    )
    named = TestClient(app, client=("testclient", 4000))
    assert (
        named.post(
            "/chat", json={"text": "hi"}, headers={"X-Mia-Actor": people["Juha"].id}
        ).status_code
        == 401
    )


def test_refused_decision_over_http_keeps_its_event(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    """A refusal raised inside a request must not roll its approval.refused event back."""
    from mia.core import approvals

    row = approvals.request(
        session,
        "dispatcher.cover_override",
        ("visit", "V"),
        "x",
        Actor.person(people["Sanna"]),
        ["admin"],
        "app_only",
    )
    session.commit()
    login(client, people["Helena"])
    res = client.post(f"/approvals/{row.id}/decide", json={"outcome": "approved"})
    assert res.status_code == 403 and res.json()["detail"] == "step_up_required"
    from mia.core.db import session_scope

    with session_scope() as s:
        refused = s.exec(select(Event).where(Event.action == "approval.refused")).all()
        assert len(refused) == 1 and refused[0].approval_id == row.id


def test_refresh_rotation_is_single_use_under_a_race(
    engine: object, session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two requests present the same refresh token at once: the one that takes the write lock
    second must see the rotation, lose, and revoke the session as a reuse."""
    import threading

    from mia.core import events

    now = utcnow()
    t = auth.issue_session(
        session, people["Helena"], method="password_totp", aal="aal2", ip=IP, now=now
    )
    session.commit()
    assert t.refresh
    real_lock = events.write_lock
    a_locked, b_waiting = threading.Event(), threading.Event()
    outcome: dict[str, object] = {}

    def lock(s: Session) -> None:
        if threading.current_thread().name == "A":
            real_lock(s)
            a_locked.set()
            b_waiting.wait(2)  # B is now blocked on the lock (or about to be)
        else:
            b_waiting.set()
            real_lock(s)  # blocks until A commits

    monkeypatch.setattr(events, "write_lock", lock)

    def run(name: str) -> None:
        with Session(engine) as s:  # type: ignore[arg-type]
            try:
                auth.refresh_session(s, t.refresh or "", now)
                s.commit()
                outcome[name] = "ok"
            except auth.AuthError:
                s.commit()
                outcome[name] = "refused"

    a, b = (
        threading.Thread(target=run, args=("A",), name="A"),
        threading.Thread(target=run, args=("B",), name="B"),
    )
    a.start()
    a_locked.wait(2)
    b.start()
    a.join(5)
    b.join(5)
    assert outcome == {"A": "ok", "B": "refused"}
    session.expire_all()
    row = session.get(auth.AuthSession, t.row.id)
    assert row is not None and row.status == "revoked"
    assert session.exec(select(Event).where(Event.action == "auth.refresh_reused")).first()


def test_enrol_sessions_have_no_refresh_and_end_with_the_link(
    session: Session, people: dict[str, Person]
) -> None:
    now = utcnow()
    t = auth.issue_session(session, people["Helena"], method="enrol", aal="enrol", ip=IP, now=now)
    assert t.refresh is None and t.row.refresh_hash is None
    assert t.row.absolute_expires_at == now + auth.CODE_TTL["enrol"]


def test_client_token_dies_with_the_client_expiry(
    client: TestClient, session: Session, people: dict[str, Person]
) -> None:
    helena = Actor.person(people["Helena"])
    now = utcnow()
    row, _secret = auth.create_client(
        session, helena, "x", ["dispatcher"], now, expires_at=now + dt.timedelta(minutes=1)
    )
    t = auth.issue_session(session, row, method="client", aal="client", ip=IP, now=now)
    session.commit()
    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {t.access}"}).status_code == 200
    )
    from mia.core import store

    store.update(session, row, {"expires_at": now - dt.timedelta(seconds=1)}, helena)
    session.commit()
    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {t.access}"}).status_code == 401
    )


def test_dev_header_actor_can_decide_app_only_approvals(
    client: TestClient, session: Session, people: dict[str, Person]
) -> None:
    """Dev mode has no session to step up; loopback dev counts as stepped up."""
    from mia.core import approvals

    row = approvals.request(
        session,
        "dispatcher.cover_override",
        ("visit", "V"),
        "x",
        Actor.person(people["Sanna"]),
        ["admin"],
        "app_only",
    )
    session.commit()
    res = client.post(
        f"/approvals/{row.id}/decide",
        json={"outcome": "approved"},
        headers={"X-Mia-Actor": people["Helena"].id},
    )
    assert res.status_code == 200, res.text
