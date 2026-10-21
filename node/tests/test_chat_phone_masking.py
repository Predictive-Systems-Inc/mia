"""A Philippine mobile number never reaches the event chain or a Jev request: events.mask_phones
keeps its last four digits on the chain and none at egress; the chat message row the UI shows
keeps the text as typed. The mask and the linking parser share one normaliser."""

import asyncio
import json
import random
from typing import Any

import pytest
from sqlmodel import Session, select

from mia.channels.linking import ph_mobile
from mia.chat.service import run_turn
from mia.core import jev
from mia.core.egress import egress_context
from mia.core.events import mask_phones
from mia.core.models import Branch, Event, Message, Person, Thread
from tests.jev_fake import answers_for, fake_jev
from tests.test_jev_decider import _ctx, _query, _run, key  # noqa: F401 (the key fixture)

SHAPES = [
    "09171234567",
    "0917 123 4567",
    "0917-123-4567",
    "(0917) 123.4567",
    "+63 917 123 4567",
    "+639171234567",
    "63-917-123-4567",
    "639171234567",
    "9171234567",
    "917-123-4567",
    "0 9 1 7 1 2 3 4 5 6 7",
    "0917-123-45-67",
    "(0917) 123 4567",
    "0917 - 123 -- 45 . 67",
]
KEPT = ["12,450", "₱3,210", "9870", "2026-10-21", "0817 123 4567", "01J9171234567ABCDEFGHJKMNP"]
NUMBER_DIGITS = ("9171234567", "917", "123", "4567")


@pytest.mark.parametrize("typed", SHAPES)
def test_every_mobile_shape_is_masked_to_its_last_four(typed: str) -> None:
    assert (
        mask_phones(f"number ni ana {typed}, salamat") == "number ni ana <number ...4567>, salamat"
    )


@pytest.mark.parametrize("text", KEPT)
def test_amounts_dates_landlines_and_ids_are_kept(text: str) -> None:
    assert mask_phones(text) == text and ph_mobile(text) is None


def test_a_number_beside_a_date_or_an_amount_is_still_masked() -> None:
    text = "on 2026-10-21 0917 123 4567 at 12,450"
    assert mask_phones(text, keep_last=0) == "on 2026-10-21 <number> at 12,450"


def test_a_random_mobile_with_random_separators_gets_the_same_decision_from_both() -> None:
    """For any valid mobile with any separators, the parser accepts it and the mask hides it."""
    rnd = random.Random(42)
    for _ in range(200):
        prefix = rnd.choice(["0", "+63", "63", ""])
        digits = prefix.lstrip("+") + "9" + "".join(rnd.choice("0123456789") for _ in range(9))
        typed = "".join(
            d
            + "".join(rnd.choice(" .-()") for _ in range(rnd.randint(0, 3)) if i < len(digits) - 1)
            for i, d in enumerate(digits)
        )
        typed = ("+" if prefix.startswith("+") else "") + typed
        assert ph_mobile(typed) == "63" + digits[-10:], typed
        assert mask_phones(f"call {typed} now") == f"call <number ...{digits[-4:]}> now", typed


def _events_text(session: Session) -> str:
    return json.dumps([[e.before, e.after] for e in session.exec(select(Event))])


def test_a_number_in_a_chat_turn_never_reaches_an_event(
    session: Session, people: dict[str, Person]
) -> None:
    text = "I'm sick tomorrow, text me on 0917 123 4567"
    asyncio.run(run_turn(session, None, people["Juha"], text, None))
    session.commit()
    assert not any(d in _events_text(session) for d in ("9171234567", "917 123", "1234567"))
    assert "<number>" in _events_text(session)  # the chain keeps no digit of it
    thread = session.exec(select(Thread).where(Thread.person_id == people["Juha"].id)).one()
    assert thread.title == "I'm sick tomorrow, text me on <number ...4567>"
    stored = session.exec(select(Message).where(Message.role == "user")).one()
    assert stored.text == text


def test_a_message_without_a_number_is_unchanged_in_its_event(
    session: Session, people: dict[str, Person]
) -> None:
    text = "I'm sick tomorrow, ₱3,210 owed, 12,450 on 2026-10-21"
    asyncio.run(run_turn(session, None, people["Juha"], text, None))
    session.commit()
    stored = session.exec(select(Message).where(Message.role == "user")).one()
    created = session.exec(select(Event).where(Event.entity_id == stored.id)).one()
    assert created.after and created.after["text"] == text


def test_a_decider_request_leaves_with_the_number_masked(
    session: Session,
    people: dict[str, Person],
    branch: Branch,
    monkeypatch: pytest.MonkeyPatch,
    key: None,  # noqa: F811
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        jev, "_inner", lambda: fake_jev(lambda b: answers_for(b, "reply_only"), seen)
    )
    for typed in SHAPES:
        with egress_context(_ctx(session, people, branch)):
            _run(_query(message=f"call {typed}, I owe ₱3,210 and 12,450"))
    assert len(seen) == len(SHAPES)
    for body in seen:
        assert body["state"]["message"] == "call <number>, I owe ₱3,210 and 12,450"
        assert not any(d in json.dumps(body) for d in NUMBER_DIGITS)


@pytest.mark.parametrize("action", ["tool.called", "decision.made", "decision.clarify_asked"])
def test_an_event_given_free_text_keeps_no_digit_of_a_number(
    session: Session, people: dict[str, Person], action: str
) -> None:
    """emit masks every payload fully before the hash, not only row snapshots."""
    from mia.core import events
    from mia.core.models import Actor

    after = {"input": {"note": "call 0917 123 4567"}, "alternatives": ["+63 917-123-4567"]}
    ev = events.emit(session, action, ("thread", "t1"), {"q": "0917 123 4567"}, after,
                     Actor.person(people["Juha"]))  # fmt: skip
    text = json.dumps([ev.before, ev.after])
    assert not any(d in text for d in NUMBER_DIGITS) and "<number>" in text
    assert events.verify_chain(session)
