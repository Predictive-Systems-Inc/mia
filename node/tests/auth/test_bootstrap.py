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
    assert client.post("/auth/password", json={"password": PW}).status_code == 400  # no email yet
    res = client.post("/auth/password", json={"password": PW, "email": "owner@example.fi"})
    assert res.status_code == 200
    assert client.get("/auth/me").json()["roles"] == ["owner"]
    with Session(engine) as s:  # type: ignore[arg-type]
        found = auth.person_by_login(s, "owner@example.fi")
        assert found is not None and "owner" in found[0].roles
    assert main(["auth", "bootstrap", "--email", "second@example.fi"]) == 1  # an owner exists
    assert "already" in capsys.readouterr().out


def test_reset_ends_sessions_and_unlock_clears_the_lockout(
    capsys: pytest.CaptureFixture[str],
    engine: object,
    session: Session,
    people: dict[str, Person],
    login,  # type: ignore[no-untyped-def]
) -> None:
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
    client.headers.pop("Authorization")
    for _ in range(20):
        client.post("/auth/login", json={"email": "helena@example.fi", "password": "nope"})
    locked = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW})
    assert locked.status_code == 401
    assert main(["auth", "unlock", "helena@example.fi"]) == 0
    assert "unlocked" in capsys.readouterr().out
    res = client.post("/auth/login", json={"email": "helena@example.fi", "password": PW})
    assert res.status_code == 200
