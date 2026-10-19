"""The customer service in chat, through run_turn with the fake Jev: a greeting, and the staff
side (scenario 8): today's orders, an order marked ready and picked up, and a tapped decision
outside STAFF asked to rephrase."""

import asyncio
import functools
import json
from typing import Any

import pytest
from sqlmodel import Session, col, select

from mia.agents.customer_service import MANIFEST
from mia.agents.customer_service.models import CustomerMessage
from mia.agents.decider import Decision
from mia.chat.access import agents_for
from mia.chat.blocks import ChatReply, TextBlock
from mia.chat.service import run_turn
from mia.core import events, jev, orgconfig
from mia.core.models import Actor, Branch, Event, Person
from mia.i18n import t
from mia.settings import get_settings
from tests.conftest import Shop
from tests.jev_fake import answers_for, fake_jev
from tests.test_customer_service_tools import seeded_order

Ferinos = tuple[Branch, dict[str, Person]]


@pytest.fixture
def sender(monkeypatch: pytest.MonkeyPatch, session: Session, ferinos: Ferinos) -> Person:
    """Jev mode with this agent as the org's only agent; a seeded person who may use it."""
    only = orgconfig.OrgSettings(agents=[MANIFEST.id])
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()
    _, people = ferinos
    return next(p for p in people.values() if agents_for(session, p))


def _answers(monkeypatch: pytest.MonkeyPatch, action: str, **slots: Any) -> None:
    def answer(body: dict[str, Any]) -> dict[str, Any]:
        return answers_for(body, action, **slots)

    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(answer))


def _texts(
    session: Session, sender: Person, monkeypatch: pytest.MonkeyPatch, kind: str
) -> list[str]:
    _answers(monkeypatch, "greeting", conversation=kind)
    reply = asyncio.run(run_turn(session, None, sender, "hello po", None))
    session.commit()
    return [b.text for b in reply.blocks if isinstance(b, TextBlock)]


def test_a_greeting_is_answered_with_the_greeting_only(
    session: Session, sender: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    texts = _texts(session, sender, monkeypatch, "greeting")
    assert texts == [t("conversation.greeting", sender.language)]


def test_a_question_about_what_it_can_do_gets_the_not_built_line(
    session: Session, sender: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    texts = _texts(session, sender, monkeypatch, "capabilities")
    assert texts == [t("reply.not_built", sender.language)]


def test_only_the_given_roles_are_offered_the_agent(
    session: Session, sender: Person, ferinos: Ferinos
) -> None:
    """The scaffold was given roles clerk, supervisor, owner, admin; a role outside them (and what inherits them) is not
    offered the agent, so the policy lines are the whole door."""
    branch, _ = ferinos
    for role in ["clerk", "supervisor", "owner", "admin"]:
        person = Person(name="x", roles=[role], branch_id=branch.id)
        assert [a.id for a in agents_for(session, person)] == [MANIFEST.id], role
    outsider = Person(name="x", roles=["viewer"], branch_id=branch.id)
    assert agents_for(session, outsider) == []


# ---- the staff side (scenario 8) ------------------------------------------------------------


@pytest.fixture
def staff(monkeypatch: pytest.MonkeyPatch, cs: Shop) -> Shop:
    """The cs seed in Jev mode with this agent as the org's only agent."""
    only = orgconfig.OrgSettings(agents=[MANIFEST.id])
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    get_settings.cache_clear()
    return cs


def _turn(session: Session, person: Person, text: str, thread: str | None = None) -> ChatReply:
    reply = asyncio.run(run_turn(session, None, person, text, thread))
    session.commit()
    return reply


def _said(reply: ChatReply) -> list[str]:
    return [b.text for b in reply.blocks if isinstance(b, TextBlock)]


def _last_out(session: Session) -> CustomerMessage:
    return session.exec(
        select(CustomerMessage)
        .where(CustomerMessage.direction == "out")
        .order_by(col(CustomerMessage.id).desc())
    ).first() or pytest.fail("no out message")


def _tap(
    session: Session, person: Person, monkeypatch: pytest.MonkeyPatch, action: str
) -> ChatReply:
    """Tap a button whose decision is `action`, on a question asked in the person's thread."""
    _answers(monkeypatch, "greeting", conversation="greeting")
    first = _turn(session, person, "hi")
    chosen = Decision(action=action, confidence=1.0).model_dump(mode="json")
    after = {"options": {"Go": chosen}, "message_id": first.message_id}
    thread = ("thread", first.thread_id)
    events.emit(
        session, "decision.clarify_asked", thread, None, after, Actor.system(person.branch_id)
    )
    session.commit()
    return _turn(session, person, "Go", first.thread_id)


def test_staff_list_todays_orders(
    staff: Shop, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, "staff_orders_today")
    reply = _turn(session, staff.people["Liza"], "orders today")
    assert _said(reply) == [t("cs.orders_today", "fil", orders="15:00 Mila R. (Classic x10)")]


def test_staff_mark_ready_and_picked_up(
    staff: Shop, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    liza = staff.people["Liza"]
    _answers(monkeypatch, "staff_mark_ready")  # the only open order today, so no pick needed
    reply = _turn(session, liza, "ready na yung kay Mila")
    assert _said(reply) == [t("cs.staff.marked_ready", "fil", who="Mila R.")]
    assert _last_out(session).text == t("cs.order_ready", "fil", time="15:00")
    _answers(monkeypatch, "staff_mark_picked_up")
    reply = _turn(session, liza, "picked up na")
    assert _said(reply) == [t("cs.staff.marked_picked_up", "fil", who="Mila R.")]
    assert seeded_order(session, "fil").status == "picked_up"


def test_marking_with_no_open_order_asks_to_rephrase(
    staff: Shop, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, "staff_mark_picked_up")
    _turn(session, staff.people["Liza"], "picked up na")
    reply = _turn(session, staff.people["Liza"], "picked up na ulit")  # nothing open is left
    assert _said(reply) == [t("clarify.rephrase", "fil")]


@pytest.mark.parametrize("action", ["record_counts", "hours", "place_order"])
def test_a_tapped_decision_outside_staff_asks_to_rephrase(
    staff: Shop, session: Session, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    """Another agent's decision, or a customer's: nothing runs."""
    reply = _tap(session, staff.people["Liza"], monkeypatch, action)
    assert _said(reply) == [t("clarify.rephrase", "fil")]
    assert seeded_order(session, "fil").status == "confirmed"


def test_staff_text_reaches_jev_without_the_customer_name(
    staff: Shop, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A customer is not a Person, so the egress pseudonymiser does not know the name; the
    query scrubs the branch customers' first names (the order is still found by it)."""
    seen: list[dict[str, Any]] = []

    def answer(body: dict[str, Any]) -> dict[str, Any]:
        return answers_for(body, "staff_mark_ready")

    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(answer, seen))
    reply = _turn(session, staff.people["Liza"], "ready na yung kay Mila")
    assert _said(reply) == [t("cs.staff.marked_ready", "fil", who="Mila R.")]
    assert seen and "Mila" not in json.dumps(seen)


def test_the_picked_up_reply_is_redacted_on_the_chain(
    staff: Shop, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, "staff_mark_picked_up")
    reply = _turn(session, staff.people["Liza"], "picked up na")
    assert _said(reply) == [t("cs.staff.marked_picked_up", "fil", who="Mila R.")]
    created = session.exec(
        select(Event)
        .where(Event.entity_id == reply.message_id)
        .where(Event.action == "chat_messages.created")
    ).one()
    assert created.after is not None and created.after["text"] == "<redacted>"
