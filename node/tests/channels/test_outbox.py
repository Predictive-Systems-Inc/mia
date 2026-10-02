"""Outbox sending: retries at 1, 5 and 30 minutes, then failed; 131047 falls back to a template."""

import asyncio
import datetime as dt

import httpx
import pytest
from sqlmodel import Session, select

from mia.channels import outbox
from mia.channels.service import deliver
from mia.channels.simulator import SimAdapter
from mia.channels.transport import ChannelBlocked, ChannelTransport
from mia.chat.blocks import TextBlock
from mia.core.db import utcnow
from mia.core.models import Actor, ChannelOutbox, Event, Person
from tests.channels.conftest import LinkFn

ADDR = "358401234567"


def _queue(session: Session, person: Person, link: LinkFn) -> ChannelOutbox:
    link(person, ADDR, last_inbound_at=utcnow())
    (row,) = deliver(
        session, person, [TextBlock(text="Hei")], Actor.system(person.branch_id), urgent=True
    )
    session.commit()
    return row


def test_success_marks_sent_with_channel_id_and_logs_hash_only(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    row = _queue(session, people["Juha"], link)
    assert asyncio.run(outbox.send_due(utcnow())) == 1
    session.refresh(row)
    assert row.status == "sent" and row.channel_message_id and row.attempts == 1
    event = session.exec(select(Event).where(Event.action == "channel.sent")).one()
    assert event.after and "payload_hash" in event.after and "Hei" not in str(event.after)


def test_failures_retry_at_1_5_30_minutes_then_fail(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    row = _queue(session, people["Juha"], link)
    now = utcnow()
    for wait in (1, 5, 30):
        sim.fail_next = "500"
        asyncio.run(outbox.send_due(now))
        session.refresh(row)
        assert row.status == "queued" and row.send_after == now + dt.timedelta(minutes=wait)
        now = row.send_after
    sim.fail_next = "500"
    asyncio.run(outbox.send_due(now))
    session.refresh(row)
    assert (row.status, row.error_code, row.attempts) == ("failed", "500", 4)
    assert session.exec(select(Event).where(Event.action == "channel.failed")).one()


def test_outside_window_error_resends_once_as_new_message_notice(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    row = _queue(session, people["Juha"], link)
    sim.fail_next = "131047"
    asyncio.run(outbox.send_due(utcnow()))
    session.refresh(row)
    assert row.status == "held"
    asyncio.run(outbox.send_due(utcnow()))
    assert [p.body.get("name") for p in sim.sent] == ["mia_new_message"]


def test_channel_transport_refuses_requests_outside_an_outbox_send() -> None:
    client = httpx.AsyncClient(
        transport=ChannelTransport(httpx.MockTransport(lambda r: httpx.Response(200)))
    )

    async def call() -> None:
        await client.post("https://graph.example/messages", json={})

    with pytest.raises(ChannelBlocked):
        asyncio.run(call())


def test_tick_runs_cover_escalation_and_sends_the_outbox(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    from mia.api.main import run_due_work

    _queue(session, people["Juha"], link)
    advanced, sent = asyncio.run(run_due_work())
    assert (advanced, sent) == (0, 1)
    assert len(sim.sent) == 1


def test_health_reports_failed_channel_messages(
    session: Session, people: dict[str, Person], sim: SimAdapter, link: LinkFn
) -> None:
    from fastapi.testclient import TestClient

    from mia.api.main import app

    row = _queue(session, people["Juha"], link)
    from mia.core import store

    store.update(
        session, row, {"status": "failed", "error_code": "131026"}, Actor.system(row.branch_id)
    )
    session.commit()
    body = TestClient(app).get("/health").json()
    assert body["channels"] == {"sim": {"enabled": True, "failed_24h": 1}}
