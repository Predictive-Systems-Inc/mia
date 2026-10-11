"""The public /health, and a scan of events and logs after a full run for secrets."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.core import auth, keys
from mia.core.db import utcnow
from mia.core.events import verify_chain
from mia.core.models import Actor, Event, Person


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


def test_health_behind_cloudflare_is_status_only(client: TestClient) -> None:
    full = client.get("/health").json()
    assert full["auth_mode"] == "dev" and "version" in full
    assert client.get("/health", headers={"CF-Ray": "abc"}).json() == {"status": "ok"}


def test_full_run_leaves_no_secret_in_events_or_logs(
    client: TestClient,
    session: Session,
    people: dict[str, Person],
    login,  # type: ignore[no-untyped-def]
    caplog: pytest.LogCaptureFixture,
) -> None:
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
    _row, secret = auth.create_client(session, Actor.person(helena), "x", ["dispatcher"], utcnow())
    session.commit()
    session.expire_all()
    events = " ".join(f"{e.before} {e.after}" for e in session.exec(select(Event)))
    haystack = events + caplog.text
    for needle in (pw, "273916", secret, tokens.get("access") or "", tokens.get("refresh") or ""):
        if needle:
            assert needle not in haystack and keys.token_hash(needle) not in haystack
    assert "scrypt$" not in haystack
    assert verify_chain(session)
