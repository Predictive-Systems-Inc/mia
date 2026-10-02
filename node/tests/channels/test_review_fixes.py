"""Regression tests for the final review's Critical and Important findings."""

import asyncio
import datetime as dt
import threading
import time
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, select

from mia.channels import inbound, outbox
from mia.channels.base import TemplateCall
from mia.channels.service import deliver
from mia.channels.simulator import SimAdapter
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.core import store
from mia.core.db import utcnow
from mia.core.models import Actor, ChannelInbound, ChannelOutbox, Event, Person
from tests.channels.conftest import LinkFn

HKI = ZoneInfo("Europe/Helsinki")
ADDR = "358401234567"


def _ask() -> list[Block]:
    return [TextBlock(text="Voitko tuurata?"), QuickRepliesBlock(options=["Hyväksyn", "En pysty"])]


def test_quiet_hours_message_is_due_at_six_local_when_now_is_utc(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    """Critical 1: the ticker passes UTC; the row must still be due at 06:00 Helsinki."""
    juha = people["Juha"]
    late = dt.datetime(2026, 10, 5, 23, 0, tzinfo=HKI)
    link(juha, ADDR, last_inbound_at=late - dt.timedelta(hours=1))
    deliver(session, juha, [TextBlock(text="Huomenna")], Actor.system(juha.branch_id), now=late)
    session.commit()
    six_utc = dt.datetime(2026, 10, 6, 6, 0, tzinfo=HKI).astimezone(dt.UTC)
    assert asyncio.run(outbox.send_due(six_utc - dt.timedelta(seconds=1))) == 0
    assert asyncio.run(outbox.send_due(six_utc)) == 1


def test_a_message_being_handled_is_not_handled_again(
    session: Session,
    people: dict[str, Person],
    sim: SimAdapter,
    link: LinkFn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critical 2: a slow turn is not re-dispatched by the pending-inbound retry."""
    link(people["Juha"], ADDR)
    from mia.channels.base import InboundMessage

    msg = InboundMessage(
        channel="sim",
        address=ADDR,
        channel_message_id="m1",
        text="Olen kipeä huomenna.",
        received_at=utcnow(),
    )
    row = ChannelInbound(
        channel="sim", channel_message_id="m1", address=ADDR, body=msg.model_dump(mode="json")
    )
    row = store.insert(session, row, Actor.system(""), action="channel.received")
    session.commit()

    turns = 0
    seen_by_ticker: list[list[str]] = []
    real_run_turn = inbound.run_turn

    async def slow_turn(*args: object, **kwargs: object) -> object:
        nonlocal turns
        turns += 1
        # While this turn runs (2 minutes in), the ticker looks for stale pending rows.
        seen_by_ticker.append(inbound.pending_inbound(utcnow() + dt.timedelta(minutes=2)))
        return await real_run_turn(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(inbound, "run_turn", slow_turn)
    asyncio.run(inbound.handle_inbound(row.id))
    asyncio.run(inbound.handle_inbound(row.id))
    assert turns == 1 and seen_by_ticker == [[]]
    session.refresh(row)
    assert row.status == "done"


def test_overlapping_sends_send_each_row_once(
    session: Session,
    people: dict[str, Person],
    sim: SimAdapter,
    link: LinkFn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Important 3: the ticker and a background task overlapping never double-send."""
    juha = people["Juha"]
    link(juha, ADDR, last_inbound_at=utcnow())
    deliver(session, juha, [TextBlock(text="Hei")], Actor.system(juha.branch_id), urgent=True)
    session.commit()
    real_update = store.update

    def slow_update(*args: object, **kwargs: object) -> object:
        time.sleep(0.2)  # widen the window between reading due rows and leasing them
        return real_update(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(outbox.store, "update", slow_update)
    threads = [
        threading.Thread(target=lambda: asyncio.run(outbox.send_due(utcnow()))) for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(sim.sent) == 1


def test_ticker_survives_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Important 4: one failing round does not stop the ticker."""
    from mia.api import main

    calls = 0

    async def flaky() -> tuple[int, int]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database is locked")
        return 0, 0

    monkeypatch.setattr(main, "run_due_work", flaky)

    async def run() -> None:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(main._ticker(0), timeout=0.05)

    asyncio.run(run())
    assert calls >= 2


def test_outside_window_error_on_a_whatsapp_template_fails_without_looping(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    """Important 5: a template row (any adapter's shape) failing with 131047 is not re-noticed."""
    juha = people["Juha"]
    link(juha, ADDR)  # window closed: a notice row (template) plus a held row
    rows = deliver(session, juha, _ask(), Actor.system(juha.branch_id), urgent=True)
    notice = rows[0]
    store.update(
        session,
        notice,
        {"payload": {"type": "template", "template": {"name": "mia_new_message"}}},
        Actor.system(juha.branch_id),
    )
    session.commit()
    sim.fail_next = "131047"
    for _ in range(5):
        asyncio.run(outbox.send_due(utcnow() + dt.timedelta(hours=1)))
    keys = [r.idempotency_key for r in session.exec(select(ChannelOutbox))]
    assert not any(k.endswith(":notice") for k in keys)  # a template is never re-noticed


def test_repeated_131047_status_for_a_held_row_is_harmless(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    """Important 5: Meta redelivering the failed status must not crash the webhook batch."""
    juha = people["Juha"]
    link(juha, ADDR, last_inbound_at=utcnow())
    (row,) = deliver(
        session, juha, [TextBlock(text="Hei")], Actor.system(juha.branch_id), urgent=True
    )
    session.commit()
    asyncio.run(outbox.send_due(utcnow()))
    session.refresh(row)
    for _ in range(2):
        outbox.apply_status(session, "sim", row.channel_message_id or "", "failed", "131047")
        session.commit()
    notices = [
        r for r in session.exec(select(ChannelOutbox)) if r.idempotency_key.endswith(":notice")
    ]
    assert len(notices) == 1


def test_specific_template_is_the_whole_message_no_held_copy(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    """Important 6: after tapping Hyväksyn on mia_cover_request, the ask is not sent again."""
    juha = people["Juha"]
    link(juha, ADDR)
    call = TemplateCall(
        name="mia_cover_request", lang="fi", params=["Juha", "Kamppi", "6.10.", "09:00"]
    )
    rows = deliver(session, juha, _ask(), Actor.system(juha.branch_id), template=call, urgent=True)
    assert [r.status for r in rows] == ["queued"]


def test_show_button_releases_held_without_a_chat_turn(
    session: Session,
    people: dict[str, Person],
    sim: SimAdapter,
    link: LinkFn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Important 7: the mia_new_message button only releases the held message."""
    juha = people["Juha"]
    link(juha, ADDR)
    deliver(
        session, juha, [TextBlock(text="Uusi vuoro")], Actor.system(juha.branch_id), urgent=True
    )
    session.commit()

    async def no_turn(*_a: object, **_k: object) -> None:
        raise AssertionError("no chat turn for the Show button")

    monkeypatch.setattr(inbound, "run_turn", no_turn)
    from mia.channels.base import InboundMessage

    msg = InboundMessage(
        channel="sim", address=ADDR, channel_message_id="m1", button="Näytä", received_at=utcnow()
    )
    row = ChannelInbound(
        channel="sim", channel_message_id="m1", address=ADDR, body=msg.model_dump(mode="json")
    )
    row = store.insert(session, row, Actor.system(""), action="channel.received")
    session.commit()
    asyncio.run(inbound.handle_inbound(row.id))
    assert any(p.body.get("text") == "Uusi vuoro" for p in sim.sent)
    session.refresh(row)
    assert row.status == "done"


def test_held_messages_expire_after_a_day(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    """Important 8: a message held for weeks is not sent when the person finally writes."""
    juha = people["Juha"]
    identity = link(juha, ADDR)
    old = utcnow() - dt.timedelta(days=3)
    deliver(
        session, juha, [TextBlock(text="Vanha")], Actor.system(juha.branch_id), urgent=True, now=old
    )
    held = session.exec(select(ChannelOutbox).where(ChannelOutbox.status == "held")).one()
    store.update(session, held, {"created_at": old}, Actor.system(juha.branch_id))
    session.commit()
    assert outbox.release_held(session, identity) == 0
    session.refresh(held)
    assert held.status == "expired"
    assert session.exec(select(Event).where(Event.action == "channel.expired")).first()
