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
from mia.core.models import Actor, Event, Person

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
    raw = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    return {"Authorization": "Basic " + raw}


GRANT = {"grant_type": "client_credentials"}


def test_register_and_get_a_token(
    client: TestClient,
    session: Session,
    people: dict[str, Person],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["auth", "client", "add", "Partner", "--role", "dispatcher"]) == 0
    out = capsys.readouterr().out
    client_id = out.split("client_id: ")[1].split()[0]
    secret = out.split("client_secret: ")[1].split()[0]
    res = client.post("/auth/token", data=GRANT, headers=_basic(client_id, secret))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token_type"] == "Bearer" and body["expires_in"] == 3600
    bearer = {"Authorization": f"Bearer {body['access_token']}"}
    res = client.get("/a2a-probe", headers=bearer)
    assert res.json() == {"id": f"client:{client_id}", "roles": ["dispatcher"]}
    form = {**GRANT, "client_id": client_id, "client_secret": secret}
    assert client.post("/auth/token", data=form).status_code == 200
    res = client.post(
        "/auth/token", data={"grant_type": "password"}, headers=_basic(client_id, secret)
    )
    assert res.status_code == 400
    res = client.post("/auth/token", data=GRANT, headers=_basic(client_id, "x"))
    assert res.status_code == 401 and res.json() == {"error": "invalid_client"}
    assert main(["auth", "client", "revoke", client_id]) == 0
    assert (
        client.post("/auth/token", data=GRANT, headers=_basic(client_id, secret)).status_code == 401
    )
    assert client.get("/a2a-probe", headers=bearer).status_code == 401


def test_client_never_holds_approve_or_a_human_role(
    session: Session, people: dict[str, Person]
) -> None:
    helena = Actor.person(people["Helena"])
    with pytest.raises(ValueError, match="human"):
        auth.create_client(session, helena, "x", ["admin"], utcnow())
    with pytest.raises(ValueError, match="human"):
        auth.create_client(session, helena, "x", ["staff"], utcnow())
    # Approve is checked for every non-human role too (none in policy.csv holds it).
    assert auth._role_can_approve("admin") and not auth._role_can_approve("dispatcher")
    with pytest.raises(ValueError, match="at least one role"):
        auth.create_client(session, helena, "x", [], utcnow())
    row, secret = auth.create_client(session, helena, "x", ["dispatcher"], utcnow())
    assert row.client_id.startswith("mia_") and row.secret_hash != secret
    for e in session.exec(select(Event).where(Event.action == "auth.client_created")):
        assert e.after is not None and e.after["secret_hash"] == "<redacted>"


def test_client_token_is_refused_on_person_routes_and_cookies_on_client_routes(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    helena = Actor.person(people["Helena"])
    row, secret = auth.create_client(session, helena, "x", ["dispatcher"], utcnow())
    session.commit()
    res = client.post("/auth/token", data=GRANT, headers=_basic(row.client_id, secret))
    token = res.json()["access_token"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert client.post("/chat", json={"text": "hi"}, headers=bearer).status_code == 403
    login(client, people["Helena"])
    assert client.get("/a2a-probe").status_code == 401
    hdr = {"X-Mia-Actor": people["Helena"].id, "Authorization": ""}
    assert client.get("/a2a-probe", headers=hdr).status_code == 401


def test_client_lockout(client: TestClient, session: Session, people: dict[str, Person]) -> None:
    helena = Actor.person(people["Helena"])
    row, secret = auth.create_client(session, helena, "x", ["dispatcher"], utcnow())
    session.commit()
    for _ in range(10):
        client.post("/auth/token", data=GRANT, headers=_basic(row.client_id, "bad"))
    res = client.post("/auth/token", data=GRANT, headers=_basic(row.client_id, secret))
    assert res.status_code == 401


def test_token_endpoint_hashes_off_the_event_loop(
    client: TestClient, session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 12: scrypt and SQLite work of /auth/token run in a worker thread."""
    import asyncio

    from mia.api import auth as auth_api

    calls: list[str] = []
    real = asyncio.to_thread

    async def spy(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(fn.__name__)
        return await real(fn, *args, **kwargs)

    monkeypatch.setattr(auth_api.asyncio, "to_thread", spy)
    helena = Actor.person(people["Helena"])
    row, secret = auth.create_client(session, helena, "x", ["dispatcher"], utcnow())
    session.commit()
    assert (
        client.post("/auth/token", data=GRANT, headers=_basic(row.client_id, secret)).status_code
        == 200
    )
    assert calls == ["_token_sync"]
