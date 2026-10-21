"""A Philippine mobile number never reaches the event chain or a Jev request: events.mask_phones
keeps its last four digits; the chat message row the UI shows keeps the text as typed."""

import asyncio
import json
from typing import Any

import pytest
from sqlmodel import Session, select

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
]
KEPT = ["12,450", "₱3,210", "9870", "2026-10-21", "0817 123 4567", "01J9171234567ABCDEFGHJKMNP"]


@pytest.mark.parametrize("typed", SHAPES)
def test_every_mobile_shape_is_masked_to_its_last_four(typed: str) -> None:
    assert (
        mask_phones(f"number ni ana {typed}, salamat") == "number ni ana <number ...4567>, salamat"
    )


@pytest.mark.parametrize("text", KEPT)
def test_amounts_dates_landlines_and_ids_are_kept(text: str) -> None:
    assert mask_phones(text) == text


def _events_text(session: Session) -> str:
    return json.dumps([[e.before, e.after] for e in session.exec(select(Event))])


def test_a_number_in_a_chat_turn_never_reaches_an_event(
    session: Session, people: dict[str, Person]
) -> None:
    text = "I'm sick tomorrow, text me on 0917 123 4567"
    asyncio.run(run_turn(session, None, people["Juha"], text, None))
    session.commit()
    assert not any(d in _events_text(session) for d in ("9171234567", "917 123", "1234567"))
    assert "<number ...4567>" in _events_text(session)
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
        assert body["state"]["message"] == "call <number ...4567>, I owe ₱3,210 and 12,450"
