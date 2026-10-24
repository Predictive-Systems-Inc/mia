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
        session,
        "shift_supervisor.cover_override",
        ("visit", "V"),
        "x",
        Actor.person(people["Sanna"]),
        ["admin"],
        "app_only",
    )
    session.commit()
    return row.id


def test_pin_rules_over_http(client: TestClient, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Helena"])
    assert client.post("/auth/pin", json={"pin": "123456"}).status_code == 400
    assert client.post("/auth/pin", json={"pin": "12ab"}).status_code == 422
    assert client.post("/auth/pin", json={"pin": "273916"}).json() == {"ok": True}
    assert client.get("/auth/me").json()["pin"] is True


def test_aal1_session_cannot_set_a_pin(
    client: TestClient, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
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
    session.expire_all()
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
    session.expire_all()
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
    assert client.post("/auth/pin", json={"pin": "273916"}).status_code == 200  # after a code
    assert client.get("/auth/me").json()["aal"] == "aal1"
    client.post("/auth/stepup", json={"pin": "273916"})
    assert client.get("/auth/me").json()["aal"] == "aal2"


def test_browser_link_session_cannot_step_up(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    """A wa_link session on a browser device never reaches aal2: say so instead of looping."""
    juha = people["Juha"]
    auth.set_pin(session, Actor.person(juha), juha, "273916", utcnow())
    browser, _ = auth.bind_device(session, Actor.person(juha), juha, "browser", "Safari", utcnow())
    session.commit()
    login(client, juha, aal="aal1", method="wa_link", device=browser)
    res = client.post("/auth/stepup", json={"pin": "273916"})
    assert res.status_code == 403 and "bound device" in res.json()["detail"]
