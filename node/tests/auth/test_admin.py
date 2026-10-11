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


def test_own_sessions_and_devices(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
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
    assert client.get("/auth/me").status_code == 401  # revoking the current device ends this too


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
    session.expire_all()
    ev = session.exec(select(Event).where(Event.action == "auth.device_revoked")).one()
    assert ev.actor_id == people["Sanna"].id


def test_admin_reset_writes_both_actors(
    client: TestClient, session: Session, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Sanna"])
    assert client.post(f"/auth/people/{people['Juha'].id}/reset").status_code == 403
    admin = TestClient(app)
    login(admin, people["Helena"])
    res = admin.post(f"/auth/people/{people['Juha'].id}/reset")
    assert res.status_code == 200 and "/auth/enrol/" in res.json()["enrol_url"]
    assert admin.post("/auth/people/nope/reset").status_code == 404
    session.expire_all()
    ev = session.exec(select(Event).where(Event.action == "auth.reset")).one()
    assert ev.actor_id == people["Helena"].id and ev.entity_id == people["Juha"].id
