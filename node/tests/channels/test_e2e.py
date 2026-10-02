"""The README demo over a channel: invite, link, report sick, cover with a template, confirm."""

import asyncio
import json

from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from mia.api.main import app
from mia.channels import linking, outbox
from mia.channels.simulator import SimAdapter
from mia.core import people as people_service
from mia.core.db import utcnow
from mia.core.events import verify_chain
from mia.core.models import Actor, Branch, ChannelOutbox, Message, Person, Visit
from tests.channels.conftest import LinkFn
from tests.channels.kits import _hub_sign
from tests.test_chat import say


def inbound(
    client: TestClient,
    sim: SimAdapter,
    address: str,
    msg_id: str,
    text: str = "",
    button: str | None = None,
) -> None:
    m = {"from": address, "id": msg_id, "text": text, "button": button}
    body = json.dumps({"messages": [m]}).encode()
    assert (
        client.post(
            "/channels/sim/webhook", content=body, headers=_hub_sign(sim.secret)(body)
        ).status_code
        == 200
    )


def sent_to(sim: SimAdapter, address: str) -> list[dict[str, object]]:
    return [p.body for p in sim.sent if p.address == address]


def test_whole_demo_over_a_channel(
    session: Session, branch: Branch, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    client = TestClient(app)
    sanna, juha, mikael = people["Sanna"], people["Juha"], people["Mikael"]

    # A supervisor adds and invites a new person, who links by sending the code.
    aada = people_service.add_person(
        session, Actor.person(sanna), branch_id=branch.id, name="Aada Koski", roles=["staff"]
    )
    code = linking.create_code(session, Actor.person(sanna), aada, "invite")
    session.commit()
    inbound(client, sim, "358400000001", "a1", f"LINK {code}")
    assert any("Aada" in str(b.get("text")) for b in sent_to(sim, "358400000001"))

    # Juha links the same way and reports sick over the channel.
    code = linking.create_code(session, Actor.person(sanna), juha, "invite")
    session.commit()
    inbound(client, sim, "358400000002", "j1", f"LINK {code}")
    inbound(client, sim, "358400000002", "j2", "Olen kipeä huomenna.")
    assert any("Kirjasin poissaolosi" in str(b.get("text")) for b in sent_to(sim, "358400000002"))

    # Mikael is linked but has not written for weeks; Sanna wrote recently.
    link(mikael, "358400000003")
    link(sanna, "358400000004", last_inbound_at=utcnow())

    # Sanna, in the app, finds cover and assigns Mikael: his ask goes out as a template.
    reply = say(client, sanna, "Who can cover Kalasatama tomorrow at 6:30?")
    say(client, sanna, "Assign Mikael.", reply["thread_id"])
    asyncio.run(outbox.send_due(utcnow()))
    (ask,) = sent_to(sim, "358400000003")
    assert ask["kind"] == "template" and ask["name"] == "mia_cover_request"

    # Mikael taps the template's button: the visit is his, and the ask is not repeated.
    inbound(client, sim, "358400000003", "m1", button="Hyväksyn")
    visits = session.exec(select(Visit)).all()
    assert any(mikael.id in v.assigned_person_ids for v in visits)
    assert [b["kind"] for b in sent_to(sim, "358400000003")] == ["template", "text"]

    # Sanna is told on her channel, and every proactive channel message has its app copy.
    asyncio.run(outbox.send_due(utcnow()))
    assert any("Mikael" in str(b.get("text")) for b in sent_to(sim, "358400000004"))
    for row in session.exec(
        select(ChannelOutbox).where(col(ChannelOutbox.person_id).in_([mikael.id, sanna.id]))
    ):
        source = row.idempotency_key.split(":")[0]
        assert session.get(Message, source) is not None, row.idempotency_key
    assert verify_chain(session)
