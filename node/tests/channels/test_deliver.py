"""deliver(): app copy always, then each enabled linked channel, within its window rules."""

import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.channels import outbox
from mia.channels.base import TemplateCall
from mia.channels.service import deliver
from mia.channels.simulator import SimAdapter
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.chat.channels import notify
from mia.core.db import utcnow
from mia.core.models import Actor, ChannelOutbox, Message, Person
from tests.channels.conftest import LinkFn

HKI = ZoneInfo("Europe/Helsinki")
NOON = dt.datetime(2026, 10, 5, 12, 0, tzinfo=HKI)
ADDR = "358401234567"


def _blocks() -> list[Block]:
    return [TextBlock(text="Voitko tuurata?"), QuickRepliesBlock(options=["Hyväksyn", "En pysty"])]


def _rows(session: Session) -> list[ChannelOutbox]:
    return list(session.exec(select(ChannelOutbox).order_by(ChannelOutbox.id)).all())  # type: ignore[arg-type]


def test_window_open_queues_rendered_payloads(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    link(juha, ADDR, last_inbound_at=NOON - dt.timedelta(hours=2))
    rows = deliver(session, juha, _blocks(), Actor.system(juha.branch_id), now=NOON)
    assert [(r.status, r.payload["kind"]) for r in rows] == [("queued", "buttons")]
    assert rows[0].address == ADDR and rows[0].send_after is None


def test_window_closed_uses_the_kind_template_and_holds_the_message(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    link(juha, ADDR, last_inbound_at=NOON - dt.timedelta(days=14))
    call = TemplateCall(
        name="mia_cover_request", lang="fi", params=["Juha", "Kamppi", "6.10.", "09:00"]
    )
    rows = deliver(
        session, juha, _blocks(), Actor.system(juha.branch_id), template=call, urgent=True, now=NOON
    )
    assert [(r.status, r.payload["kind"]) for r in rows] == [
        ("queued", "template"),
        ("held", "buttons"),
    ]
    assert rows[0].payload["name"] == "mia_cover_request"


def test_window_closed_without_template_sends_new_message_notice(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    link(juha, ADDR)  # never wrote to Mia
    rows = deliver(session, juha, _blocks(), Actor.system(juha.branch_id), now=NOON)
    assert rows[0].payload == {
        "kind": "template",
        "name": "mia_new_message",
        "lang": "fi",
        "params": [],
        "buttons": [],
    }
    assert rows[1].status == "held"


def test_release_held_sends_the_held_message_once_before_later_ones(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    identity = link(juha, ADDR)
    deliver(session, juha, _blocks(), Actor.system(juha.branch_id), now=NOON)
    session.commit()
    asyncio.run(outbox.send_due(NOON))
    assert [p.body["kind"] for p in sim.sent] == ["template"]

    assert outbox.release_held(session, identity) == 1
    assert outbox.release_held(session, identity) == 0
    deliver(
        session,
        juha,
        [TextBlock(text="Reply")],
        Actor.system(juha.branch_id),
        urgent=True,
        now=NOON,
    )
    session.commit()
    asyncio.run(outbox.send_due(NOON))
    assert [p.body["kind"] for p in sim.sent] == ["template", "buttons", "template"]  # held first


def test_non_urgent_message_in_quiet_hours_waits_until_they_end(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    late = dt.datetime(2026, 10, 5, 23, 0, tzinfo=HKI)
    link(juha, ADDR, last_inbound_at=late - dt.timedelta(hours=1))
    (row,) = deliver(
        session, juha, [TextBlock(text="Huomenna")], Actor.system(juha.branch_id), now=late
    )
    six = dt.datetime(2026, 10, 6, 6, 0, tzinfo=HKI)
    assert row.send_after == six
    session.commit()
    assert asyncio.run(outbox.send_due(six - dt.timedelta(seconds=1))) == 0
    assert asyncio.run(outbox.send_due(six)) == 1


def test_urgent_message_ignores_quiet_hours(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    late = dt.datetime(2026, 10, 5, 23, 0, tzinfo=HKI)
    link(juha, ADDR, last_inbound_at=late - dt.timedelta(hours=1))
    (row,) = deliver(
        session, juha, [TextBlock(text="Nyt")], Actor.system(juha.branch_id), urgent=True, now=late
    )
    assert row.send_after is None


def test_sensitive_content_never_reaches_the_channel(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    link(juha, ADDR, last_inbound_at=utcnow())
    deliver(
        session,
        juha,
        [TextBlock(text="Palkka 2 345,00 EUR")],
        Actor.system(juha.branch_id),
        sensitive=True,
        urgent=True,
    )
    session.commit()
    asyncio.run(outbox.send_due(utcnow()))
    assert sim.sent and all("2 345" not in str(p.body) for p in sim.sent)


def test_disabled_or_unlinked_channel_queues_nothing(
    session: Session, people: dict[str, Person], link: LinkFn
) -> None:
    juha = people["Juha"]
    link(juha, ADDR, last_inbound_at=utcnow())  # linked, but no adapter is switched on
    assert deliver(session, juha, _blocks(), Actor.system(juha.branch_id)) == []


def test_same_source_is_queued_once(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    link(juha, ADDR, last_inbound_at=utcnow())
    actor = Actor.system(juha.branch_id)
    assert len(deliver(session, juha, _blocks(), actor, source_id="M1", urgent=True)) == 1
    assert deliver(session, juha, _blocks(), actor, source_id="M1", urgent=True) == []


def test_notify_keeps_the_app_copy_and_delivers(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    juha = people["Juha"]
    link(juha, ADDR, last_inbound_at=utcnow())
    notify(
        session,
        juha,
        [TextBlock(text="Hei")],
        Actor.system(juha.branch_id),
        "dispatcher",
        urgent=True,
    )
    assert session.exec(select(Message).where(Message.text == "Hei")).one()
    assert len(_rows(session)) == 1
