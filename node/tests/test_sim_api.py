"""The phones page (/sim): dev and loopback only, phones linked through the service, replies and
polls drained per address, and a tick on demand."""

import functools
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from mia.agents.customer_service import MANIFEST as CS
from mia.api.main import app
from mia.channels import linking, registry
from mia.channels.base import ChannelPayload
from mia.channels.simulator import SimAdapter
from mia.core import orgconfig
from mia.core.models import Actor, Approval, ChannelIdentity, Event, Person
from mia.core.orgconfig import ChannelConfig, OrgSettings
from mia.i18n import t
from mia.settings import get_settings
from tests.conftest import Shop
from tests.jev_fake import answers_for, fake_jev


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimAdapter]:
    adapter = SimAdapter(on_demand=True)
    registry._adapters.clear()  # the conftest restores the saved adapters afterwards
    registry.register(adapter)
    org = OrgSettings(channels={"sim": ChannelConfig(enabled=True)})
    monkeypatch.setattr(orgconfig, "load", lambda org_name=None: org)
    yield adapter


def add_phone(client: TestClient, person: Person) -> str:
    res = client.post("/sim/phones", json={"person_id": person.id})
    assert res.status_code == 200, res.text
    return str(res.json()["address"])


@pytest.mark.usefixtures("branch")
def test_every_route_is_404_outside_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    client = TestClient(app)
    assert client.get("/sim").status_code == 404
    assert client.get("/sim/phones").status_code == 404
    assert client.post("/sim/phones", json={"person_id": "x"}).status_code == 404
    assert client.post("/sim/messages", json={"address": "1", "text": "hi"}).status_code == 404
    assert client.get("/sim/messages", params={"address": "1"}).status_code == 404
    assert client.post("/sim/tick").status_code == 404
    lang = {"language": "en"}
    assert client.post("/sim/phones/x/language", json=lang).status_code == 404


@pytest.mark.usefixtures("branch")
def test_every_route_is_404_from_the_lan_or_the_tunnel() -> None:
    lan = TestClient(app, client=("192.168.1.20", 50000))
    assert lan.get("/sim").status_code == 404
    assert lan.get("/sim/phones").status_code == 404
    assert lan.post("/sim/tick").status_code == 404
    assert lan.post("/sim/phones/x/language", json={"language": "en"}).status_code == 404
    tunnel = TestClient(app)
    assert tunnel.get("/sim/phones", headers={"cf-ray": "8a1b2c3d4e5f-MNL"}).status_code == 404
    assert tunnel.get("/sim", headers={"cf-connecting-ip": "203.0.113.9"}).status_code == 404
    cf = {"cf-ray": "8a1b2c3d4e5f-MNL"}
    res = tunnel.post("/sim/phones/x/language", json={"language": "en"}, headers=cf)
    assert res.status_code == 404


def test_the_page_and_the_phone_list_answer_on_loopback(people: dict[str, Person]) -> None:
    client = TestClient(app)
    assert "Mia phones" in client.get("/sim").text
    phones = {p["name"]: p for p in client.get("/sim/phones").json()}
    juha = phones[people["Juha"].name]
    assert juha["address"] is None and juha["roles"] == people["Juha"].roles and juha["branch"]


def test_adding_a_phone_links_once_through_the_service(
    session: Session, people: dict[str, Person]
) -> None:
    client = TestClient(app)
    juha = people["Juha"]
    address = add_phone(client, juha)
    assert address.startswith("63900") and len(address) == 12
    assert add_phone(client, juha) == address  # idempotent
    rows = session.exec(select(ChannelIdentity).where(ChannelIdentity.person_id == juha.id)).all()
    assert [(r.channel, r.address) for r in rows] == [("sim", address)]
    linked = session.exec(select(Event).where(Event.action == "channel.linked")).all()
    assert [e.entity_id for e in linked] == [rows[0].id]
    phones = {p["person_id"]: p["address"] for p in client.get("/sim/phones").json()}
    assert phones[juha.id] == address
    other = add_phone(client, people["Mikael"])
    assert other != address and other.startswith("63900")


def test_link_sim_refuses_outside_dev_mode_and_a_taken_number(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    juha, mikael = people["Juha"], people["Mikael"]
    linking.link_sim(session, Actor.system(juha.branch_id), juha, "639000000099")
    with pytest.raises(LookupError, match="phone_taken"):
        linking.link_sim(session, Actor.system(mikael.branch_id), mikael, "639000000099")
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    with pytest.raises(PermissionError):
        linking.link_sim(session, Actor.system(mikael.branch_id), mikael, "639000000098")
    assert len(session.exec(select(ChannelIdentity)).all()) == 1


def test_a_message_returns_mias_reply_for_that_phone_only(
    sim: SimAdapter, people: dict[str, Person]
) -> None:
    client = TestClient(app)
    juha = add_phone(client, people["Juha"])
    other = ChannelPayload(
        channel="sim", address="639000000777", body={"kind": "text", "text": "x"}
    )
    sim.sent.append(other)
    res = client.post("/sim/messages", json={"address": juha, "text": "Olen kipeä huomenna."})
    assert res.status_code == 200, res.text
    replies = res.json()
    assert replies and all(r["kind"] in ("text", "buttons", "list", "template") for r in replies)
    assert any("Kirjasin poissaolosi" in str(r.get("text")) for r in replies)
    assert sim.sent == [other]  # the other phone's payload waits for its own poll


def test_a_poll_drains_only_its_own_phone(sim: SimAdapter, people: dict[str, Person]) -> None:
    client = TestClient(app)
    a, b = add_phone(client, people["Juha"]), add_phone(client, people["Mikael"])
    for address, text in ((a, "for a"), (b, "for b")):
        sim.sent.append(
            ChannelPayload(channel="sim", address=address, body={"kind": "text", "text": text})
        )
    assert client.get("/sim/messages", params={"address": b}).json() == [
        {"kind": "text", "text": "for b"}
    ]
    assert [p.address for p in sim.sent] == [a]
    assert client.get("/sim/messages", params={"address": b}).json() == []


@pytest.mark.usefixtures("sim", "branch")
def test_the_tick_route_runs_due_work_and_counts() -> None:
    res = TestClient(app).post("/sim/tick")
    assert res.status_code == 200
    out = res.json()
    assert set(out) == {"advanced", "sent", "queued"} and all(
        isinstance(v, int) for v in out.values()
    )


@pytest.mark.usefixtures("branch")
def test_messages_need_the_sim_channel_on() -> None:
    registry._adapters.clear()
    res = TestClient(app).post("/sim/messages", json={"address": "639000000001", "text": "hi"})
    assert res.status_code == 409


def answer(monkeypatch: pytest.MonkeyPatch, action: str, **slots: object) -> None:
    from mia.core import jev

    respond = lambda body: answers_for(body, action, **slots)
    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(respond, None, 200))


@pytest.fixture
def shop(cs: Shop, sim: SimAdapter, monkeypatch: pytest.MonkeyPatch) -> Shop:
    """Ferino's with the sim channel on, the customer service as its only agent, Jev mode."""
    settings = orgconfig.load("ferinos").model_copy(
        update={"channels": {"sim": ChannelConfig(enabled=True)}, "agents": [CS.id]}
    )
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: settings))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()
    return cs


def test_an_approved_order_reaches_the_customer_phone_on_its_next_poll(
    shop: Shop, sim: SimAdapter, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(app)
    customer = "639170000199"
    answer(monkeypatch, "place_order", day="d0", time="t0")
    sent = {"address": customer, "text": "pa-order 10 bibingka, pickup bukas 10am", "name": "Lorna"}
    waiting = client.post("/sim/messages", json=sent).json()
    assert [r["text"] for r in waiting] == [t("cs.order_waiting", "fil", time="10:00")]
    session.expire_all()
    approval = session.exec(select(Approval).order_by(col(Approval.id).desc())).first()
    assert approval is not None
    ana = {"X-Mia-Actor": shop.people["Ana"].id}
    decided = client.post(
        f"/approvals/{approval.id}/decide", json={"outcome": "approved"}, headers=ana
    )
    assert decided.status_code == 200, decided.text
    assert sim.sent == []  # the reply is queued, not sent: no tick ran
    got = client.get("/sim/messages", params={"address": customer}).json()
    assert [r["text"] for r in got] == [t("cs.order_confirmed", "fil", time="10:00")]


def test_the_language_route_sets_it_as_the_person_through_the_service(
    session: Session, people: dict[str, Person]
) -> None:
    client = TestClient(app)
    juha = people["Juha"]
    res = client.post(f"/sim/phones/{juha.id}/language", json={"language": "fil"})
    assert res.status_code == 200 and res.json()["language"] == "fil"
    session.expire_all()
    assert session.get(Person, juha.id).language == "fil"  # type: ignore[union-attr]
    chosen = session.exec(
        select(Event)
        .where(Event.action == "person.language_chosen")
        .where(Event.actor_id == juha.id)
    ).all()
    assert [e.entity_id for e in chosen] == [juha.id]  # the seed's own events are the system's
    phones = {p["person_id"]: p["language"] for p in client.get("/sim/phones").json()}
    assert phones[juha.id] == "fil"


def test_the_language_route_refuses_an_unsupported_language(
    session: Session, people: dict[str, Person]
) -> None:
    client = TestClient(app)
    juha = people["Juha"]
    before = juha.language
    res = client.post(f"/sim/phones/{juha.id}/language", json={"language": "xx"})
    assert res.status_code == 422
    assert client.post("/sim/phones/nobody/language", json={"language": "en"}).status_code == 404
    session.expire_all()
    assert session.get(Person, juha.id).language == before  # type: ignore[union-attr]
    by_juha = select(Event).where(Event.action == "person.language_chosen")
    assert session.exec(by_juha.where(Event.actor_id == juha.id)).all() == []
