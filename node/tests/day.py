"""A day at the shop for end-to-end tests: the pinned clock, one message as a person to one
agent with the fake Jev, a customer's channel message, the tick, and what each step wrote.

An agent is addressed directly: for the turn the organisation runs only that agent (the
Ferino's settings kept), so the turn goes to it as `_choose` sends a one-agent person; the
tick runs every agent of the full settings. The router is not exercised: each turn goes to
the named agent as it would for a person with one agent. Jev is the fake transport (tests/jev_fake.py),
never the real service.
"""

import asyncio
import datetime as dt
import functools
from dataclasses import dataclass
from typing import Any

import pytest
from sqlmodel import Session, col, select

from mia.agents.customer_service import public
from mia.agents.registry import AGENTS
from mia.agents.sales_supervisor import tools as sales_tools
from mia.channels.base import InboundMessage
from mia.chat.blocks import ChatReply
from mia.chat.service import run_turn
from mia.core import db, jev, orgconfig
from mia.core.ids import new_id
from mia.core.models import Event, Message, Person, SalesCount, Thread
from mia.settings import get_settings
from tests.conftest import Shop
from tests.jev_fake import answers_for, fake_jev


@dataclass
class Said:
    """One step's outcome: the reply (None for a customer or the tick) and the events it wrote."""

    reply: ChatReply | None
    events: list[Event]

    def actions(self) -> list[str]:
        return [e.action for e in self.events]

    def text(self) -> str:
        return self.reply.text() if self.reply is not None else ""


class Day:
    """The shop's day: `at` moves the clock, `say` sends a message to an agent, `customer` a
    customer's channel message, `tick` runs the due work; each returns what it wrote."""

    def __init__(self, session: Session, monkeypatch: pytest.MonkeyPatch, shop: Shop) -> None:
        self.session, self.mp, self.shop = session, monkeypatch, shop
        self.full = orgconfig.load()  # Ferino's settings with every agent
        self.people = shop.people
        monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
        monkeypatch.setenv("MIA_DECIDER", "jev")
        monkeypatch.setattr(public, "send_pending", _no_send)  # replies stay queued, read here
        get_settings.cache_clear()
        self._only(None)

    def at(self, hour: int, minute: int = 0) -> dt.datetime:
        """Pin the clock at hour:minute Manila on the shop's day; returns the local moment."""
        return self.shop.pin(hour, minute)

    def _only(self, agent: str | None) -> None:
        settings = self.full if agent is None else self.full.model_copy(update={"agents": [agent]})
        self.mp.setattr(orgconfig, "load", functools.cache(lambda org=None: settings))

    def _jev(self, action: str, slots: dict[str, Any]) -> None:
        def answer(body: dict[str, Any]) -> dict[str, Any]:
            return answers_for(body, action, **slots)

        self.mp.setattr(jev, "_inner", lambda: fake_jev(answer))

    def _ids(self) -> set[str]:
        return set(self.session.exec(select(Event.id)).all())

    def _since(self, before: set[str]) -> list[Event]:
        rows = self.session.exec(select(Event).where(col(Event.id).not_in(before)))
        return sorted(rows, key=lambda e: e.timestamp)

    def say(
        self, who: str, agent: str, text: str, action: str, thread: str | None = None, **slots: Any
    ) -> Said:
        """`who` (a first name) sends `text` to `agent`; the fake Jev picks `action` with the
        slots. Returns the reply and the events the turn wrote."""
        self._only(agent)
        self._jev(action, slots)
        before = self._ids()
        reply = asyncio.run(run_turn(self.session, None, self.people[who], text, thread))
        self.session.commit()
        self._only(None)
        return Said(reply, self._since(before))

    def customer(self, address: str, text: str, action: str, **slots: Any) -> Said:
        """A customer's WhatsApp message to the customer service (public_turn at the clock)."""
        self._only("customer_service")
        self._jev(action, slots)
        before = self._ids()
        msg = InboundMessage(
            channel="whatsapp",
            address=address,
            channel_message_id=new_id(),
            text=text,
            received_at=db.utcnow(),
        )
        asyncio.run(public.public_turn(self.session, new_id(), msg, db.utcnow()))
        self.session.commit()
        self._only(None)
        return Said(None, self._since(before))

    def tick(self) -> Said:
        """Every agent's due work once at the clock (api.main.tick, on the test session)."""
        before = self._ids()
        for spec in AGENTS.values():
            if spec.run_due is not None:
                spec.run_due(self.session, db.utcnow())
                self.session.commit()
        return Said(None, self._since(before))

    def told(self, who: str, agent: str | None = None, step: Said | None = None) -> list[str]:
        """The notifications `who` got (from `agent` when given, in `step` when given)."""
        threads = select(Thread.id).where(Thread.person_id == self.people[who].id)
        stmt = select(Message).where(col(Message.thread_id).in_(threads))
        stmt = stmt.where(Message.role == "notification")
        if agent is not None:
            stmt = stmt.where(Message.agent_id == agent)
        rows = list(self.session.exec(stmt.order_by(col(Message.id))))
        if step is not None:
            ids = {e.entity_id for e in step.events if e.action == "notification.sent"}
            rows = [m for m in rows if m.id in ids]
        return [m.text for m in rows]

    def counts(self, day: dt.date, who: str | None = None) -> list[SalesCount]:
        """The live counts of `day` at the Mall kiosk (by `who` when given)."""
        rows = sales_tools._live_counts(self.session, [self.shop.kiosk.id], day, day)
        person: Person | None = self.people[who] if who else None
        return [r for r in rows if person is None or r.reported_by == person.id]


async def _no_send(now: dt.datetime) -> int:
    return 0
