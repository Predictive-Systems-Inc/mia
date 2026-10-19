"""The customer service over a channel: an unlinked sender at Ferino's runs the customer turn
(a customer principal, no Person, no chat thread), replies go back as blocks, sends are leased
before the network and nothing goes out past the 24-hour window."""

import asyncio
import functools
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from mia.agents.customer_service import MANIFEST, public
from mia.agents.customer_service.models import Customer, CustomerMessage
from mia.api.main import app
from mia.channels import outbox
from mia.channels.base import ChannelPayload, DeliveryResult
from mia.channels.simulator import SimAdapter
from mia.chat.blocks import QuickRepliesBlock, TextBlock
from mia.core import db, jev, orgconfig, store
from mia.core.ids import new_id
from mia.core.models import Actor, ChannelInbound, Event, Message, Thread
from mia.core.orgconfig import ChannelConfig
from mia.i18n import t
from mia.settings import get_settings
from tests.channels.test_inbound import post, texts_to
from tests.conftest import Shop
from tests.jev_fake import answers_for, fake_jev

ADDR = "+639170000199"  # a new customer (the seed's are ...101 and ...102)
REAL_LOAD = orgconfig.load


@pytest.fixture
def shop(cs: Shop, sim: SimAdapter, monkeypatch: pytest.MonkeyPatch) -> Iterator[Shop]:
    """Ferino's with the sim channel on and the customer service as its only agent, Jev mode."""
    settings = REAL_LOAD("ferinos").model_copy(
        update={"channels": {"sim": ChannelConfig(enabled=True)}, "agents": [MANIFEST.id]}
    )
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: settings))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()
    yield cs


@pytest.fixture
def client(shop: Shop) -> TestClient:
    return TestClient(app)


def say(
    client: TestClient, sim: SimAdapter, text: str, address: str = ADDR, name: str | None = None
) -> list[str]:
    """Post one message with a fresh id; the texts sent to the address because of it."""
    before = len(texts_to(sim, address))
    m = {"from": address, "id": new_id(), "text": text, "name": name}
    assert post(client, sim, json.dumps({"messages": [m]}).encode()) == 200
    return texts_to(sim, address)[before:]


def answer(monkeypatch: pytest.MonkeyPatch, action: str, **slots: Any) -> None:
    def respond(body: dict[str, Any]) -> dict[str, Any]:
        return answers_for(body, action, **slots)

    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(respond))


def customer_in_window(session: Session) -> Customer:
    row = session.exec(select(Customer).where(Customer.language == "en")).one()
    changes = {"last_inbound_at": db.utcnow(), "channel": "sim"}  # the seed's are on whatsapp
    return store.update(session, row, changes, Actor.system(row.branch_id))


def fresh_status(payload: ChannelPayload) -> str:
    """The latest out row's status, read in a new session (what is committed)."""
    with Session(db.get_engine()) as other:
        row = other.exec(
            select(CustomerMessage)
            .where(CustomerMessage.direction == "out")
            .order_by(col(CustomerMessage.id).desc())
        ).first()
        assert row is not None
        return row.status


def test_customer_identity_stays_off_the_chain(
    shop: Shop,
    client: TestClient,
    sim: SimAdapter,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer(monkeypatch, "greeting")
    assert say(client, sim, "hello po", name="Mila Santos") == [t("cs.menu", "fil")]
    chain = json.dumps([e.model_dump(mode="json") for e in session.exec(select(Event))])
    assert ADDR not in chain and "Mila" not in chain
    hello = session.exec(select(Message).where(col(Message.text).contains("hello po"))).all()
    assert not hello and not session.exec(select(Thread)).all()


def test_every_customer_event_is_the_agent_on_behalf_of_the_customer(
    shop: Shop,
    client: TestClient,
    sim: SimAdapter,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer(monkeypatch, "greeting")
    say(client, sim, "hello po", name="Mila Santos")
    customer = session.exec(select(Customer).where(Customer.address == ADDR)).one()
    assert customer.name == "Mila Santos"  # kept on the row only
    mine = session.exec(select(Event).where(Event.on_behalf_of == customer.id)).all()
    assert {e.action for e in mine} >= {
        f"{MANIFEST.id}.customer_seen",
        f"{MANIFEST.id}.message_in",
        f"{MANIFEST.id}.message_out",
        f"{MANIFEST.id}.message_sent",
    }
    assert {(e.actor_type, e.actor_id) for e in mine} == {("agent", MANIFEST.roles.agent_role)}
    seen = [e for e in mine if e.action == f"{MANIFEST.id}.customer_seen"]
    assert seen[0].after is not None and seen[0].after["name"] == "<redacted>"
    inbound = session.exec(select(ChannelInbound)).one()
    assert (inbound.status, inbound.person_id) == ("done", None)


def test_a_held_customer_gets_one_hold_reply_then_nothing(
    shop: Shop, client: TestClient, sim: SimAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer(monkeypatch, "greeting")
    tight = orgconfig.load().model_copy(
        update={"customer_service": orgconfig.CustomerServiceSettings(messages_per_hour=2)}
    )
    monkeypatch.setattr(orgconfig, "load", lambda org=None: tight)
    got = [say(client, sim, f"hi {i}") for i in range(4)]
    assert got == [[t("cs.menu", "fil")]] * 2 + [[t("cs.held", "fil")], []]


def test_send_pending_leases_before_sending(
    shop: Shop, session: Session, sim: SimAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    async def send(payload: ChannelPayload) -> DeliveryResult:
        seen.append(fresh_status(payload))
        return DeliveryResult(ok=True, channel_message_id="w1")

    monkeypatch.setattr(sim, "send", send)
    customer = customer_in_window(session)
    public.queue(session, customer, [TextBlock(text="hi")], Actor.system(customer.branch_id))
    session.commit()
    assert asyncio.run(public.send_pending(db.utcnow())) == 1 and seen == ["sending"]
    assert fresh_status(ChannelPayload(channel="sim", address="", body={})) == "sent"


def test_nothing_is_sent_outside_the_window(shop: Shop, session: Session, sim: SimAdapter) -> None:
    mila = session.exec(select(Customer).where(Customer.language == "fil")).one()  # 3 days ago
    store.update(session, mila, {"channel": "sim"}, Actor.system(mila.branch_id))
    public.queue(session, mila, [TextBlock(text="ready na")], public.customer_actor(mila))
    session.commit()
    assert asyncio.run(public.send_pending(db.utcnow())) == 0 and sim.sent == []
    skipped = session.exec(
        select(Event).where(Event.action == f"{MANIFEST.id}.reminder_skipped")
    ).one()
    assert skipped.after is not None and skipped.after["status"] == "skipped"


def test_send_direct_renders_quick_replies_as_buttons(sim: SimAdapter, session: Session) -> None:
    blocks = [TextBlock(text="Pick"), QuickRepliesBlock(options=["08:00"])]
    asyncio.run(outbox.send_direct("sim", ADDR, blocks, "en"))  # type: ignore[arg-type]
    assert sim.sent[-1].body["buttons"] == ["08:00"]


def test_send_direct_never_sends_an_app_link(sim: SimAdapter, session: Session) -> None:
    from mia.chat.blocks import ApprovalCardBlock

    card = ApprovalCardBlock(approval_id="a1", title="Order", summary="10 Classic")
    asyncio.run(outbox.send_direct("sim", ADDR, [card, TextBlock(text="ok")], "en"))
    assert [p.body.get("text") for p in sim.sent] == ["ok"]
