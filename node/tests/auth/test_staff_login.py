"""Staff: a code over the simulated channel, device binding, device login, the login link,
sign-out and revocation. The sim adapter stands in for WhatsApp."""

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from mia.api.main import app
from mia.channels import linking, registry
from mia.channels.simulator import SimAdapter
from mia.core import orgconfig
from mia.core.db import utcnow
from mia.core.models import Actor, AuthCode, ChannelOutbox, Event, Person
from mia.core.orgconfig import ChannelConfig, OrgSettings

ADDR = "358401234567"
DEV = {"name": "iPhone", "platform": "ios"}


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimAdapter]:
    adapter = SimAdapter()
    saved = dict(registry._adapters)
    registry._adapters.clear()
    registry.register(adapter)
    org = OrgSettings(channels={"sim": ChannelConfig(enabled=True)})
    monkeypatch.setattr(orgconfig, "load", lambda org_name=None: org)
    yield adapter
    registry._adapters.clear()
    registry._adapters.update(saved)


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


def _outbox(session: Session) -> list[ChannelOutbox]:
    session.expire_all()
    return list(session.exec(select(ChannelOutbox).order_by(col(ChannelOutbox.id))).all())


def _sent_code(session: Session) -> str:
    row = _outbox(session)[-1]
    m = re.search(r"\b(\d{6})\b", str(row.payload))
    assert m, row.payload
    return m[1]


def _verify(client: TestClient, phone: str, code: str) -> object:
    return client.post("/auth/otp/verify", json={"phone": phone, "code": code, "device": DEV})


def test_otp_flow_binds_a_device_and_device_login_works(
    client: TestClient, session: Session, linked: Person
) -> None:
    assert client.post("/auth/otp/start", json={"phone": "+358 40 1234567"}).json() == {"ok": True}
    code = _sent_code(session)
    for e in session.exec(select(Event)):
        assert code not in str(e.after) and code not in str(e.before)
    assert _verify(client, ADDR, "000000").status_code == 401  # type: ignore[attr-defined]
    res = _verify(client, ADDR, code)
    assert res.status_code == 200, res.text  # type: ignore[attr-defined]
    body = res.json()  # type: ignore[attr-defined]
    assert body["aal"] == "aal1" and len(body["device_secret"]) == 43
    assert _verify(client, ADDR, code).status_code == 401  # type: ignore[attr-defined]
    client.headers["Authorization"] = f"Bearer {body['access']}"
    assert client.get("/auth/me").json()["method"] == "phone_otp"
    assert client.post("/chat", json={"text": "hi"}).status_code == 200
    client.headers.pop("Authorization")
    dev = {"device_id": body["device_id"], "device_secret": body["device_secret"]}
    res = client.post("/auth/device", json=dev)
    assert res.status_code == 200 and res.json()["aal"] == "aal1"
    assert client.post("/auth/device", json={**dev, "device_secret": "x"}).status_code == 401
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.post("/auth/logout").json() == {"ok": True}
    client.headers.pop("Authorization")
    assert client.post("/auth/device", json=dev).status_code == 401  # sign-out revoked it


def test_unknown_number_same_response_nothing_sent_and_send_limit(
    client: TestClient, session: Session, linked: Person
) -> None:
    before = len(_outbox(session))
    assert client.post("/auth/otp/start", json={"phone": "358400000000"}).json() == {"ok": True}
    assert len(_outbox(session)) == before
    for _ in range(3):
        client.post("/auth/otp/start", json={"phone": ADDR})
    sent = len(_outbox(session))
    assert client.post("/auth/otp/start", json={"phone": ADDR}).json() == {"ok": True}
    assert len(_outbox(session)) == sent  # the fourth in an hour is silently not sent
    assert len(session.exec(select(AuthCode).where(AuthCode.purpose == "otp_login")).all()) == 3


def test_code_tries_expiry_and_wrong_number(
    client: TestClient, session: Session, linked: Person
) -> None:
    client.post("/auth/otp/start", json={"phone": ADDR})
    code = _sent_code(session)
    assert _verify(client, "358409999999", code).status_code == 401  # type: ignore[attr-defined]
    for _ in range(5):
        _verify(client, ADDR, "111111")
    assert _verify(client, ADDR, code).status_code == 401  # type: ignore[attr-defined]


def test_link_get_does_not_consume_and_post_logs_in(
    client: TestClient, session: Session, linked: Person, capsys: pytest.CaptureFixture[str]
) -> None:
    from mia.cli import main

    assert main(["auth", "link", "Juha"]) == 0
    m = re.search(r"/auth/link/(\S+)", capsys.readouterr().out)
    assert m
    code = m[1]
    page = client.get(f"/auth/link/{code}")
    assert page.status_code == 200 and "Continue as Juha" in page.text
    assert client.get(f"/auth/link/{code}").status_code == 200
    res = client.post(f"/auth/link/{code}")
    assert res.status_code == 200 and res.json()["aal"] == "aal1"
    assert client.post(f"/auth/link/{code}").status_code == 401
    assert client.get(f"/auth/link/{code}").status_code == 404
    client.headers["Authorization"] = f"Bearer {res.json()['access']}"
    assert client.get("/auth/me").json()["method"] == "wa_link"
    assert session.exec(select(Event).where(Event.action == "auth.link_sent")).first()
    assert main(["auth", "link", "Helena"]) == 1  # no channel identity


def test_deactivation_revokes_devices_sessions_and_identity(
    client: TestClient, session: Session, linked: Person, people: dict[str, Person]
) -> None:
    from mia.core import people as people_service

    client.post("/auth/otp/start", json={"phone": ADDR})
    body = _verify(client, ADDR, _sent_code(session)).json()  # type: ignore[attr-defined]
    people_service.deactivate(session, Actor.person(people["Helena"]), linked)
    session.commit()
    client.headers["Authorization"] = f"Bearer {body['access']}"
    assert client.get("/auth/me").status_code == 401  # sessions ended with the deactivation
    client.headers.pop("Authorization")
    dev = {"device_id": body["device_id"], "device_secret": body["device_secret"]}
    assert client.post("/auth/device", json=dev).status_code == 401
    assert linking.identity_for(session, "sim", ADDR) is None


def test_sending_the_code_keeps_it_out_of_events(
    client: TestClient, session: Session, linked: Person, sim: SimAdapter
) -> None:
    """The outbox row is updated when sent; that update must not snapshot the code either."""
    import asyncio

    from mia.channels import outbox

    client.post("/auth/otp/start", json={"phone": ADDR})
    code = _sent_code(session)
    asyncio.run(outbox.send_due(utcnow()))
    session.expire_all()
    for e in session.exec(select(Event)):
        assert code not in str(e.after) and code not in str(e.before), e.action


def test_link_page_escapes_the_name(
    client: TestClient, session: Session, linked: Person, capsys: pytest.CaptureFixture[str]
) -> None:
    from mia.cli import main
    from mia.core import store

    store.update(session, linked, {"name": "<b>Juha</b> X"}, Actor.person(linked))
    session.commit()
    assert main(["auth", "link", "<b>Juha</b> X"]) == 0
    m = re.search(r"/auth/link/(\S+)", capsys.readouterr().out)
    assert m
    page = client.get(f"/auth/link/{m[1]}").text
    assert "<b>" not in page and "&lt;b&gt;" in page
