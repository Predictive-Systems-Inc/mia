"""The inventory manager in chat, through run_turn with the fake Jev. Scaffolded with one test (a
greeting); the plan's scenarios add the rest here."""

import asyncio
import functools
from typing import Any

import pytest
from sqlmodel import Session

from mia.agents.inventory_manager import MANIFEST
from mia.chat.access import agents_for
from mia.chat.blocks import TextBlock
from mia.chat.service import run_turn
from mia.core import jev, orgconfig
from mia.core.models import Branch, Person
from mia.i18n import t
from mia.settings import get_settings
from tests.jev_fake import answers_for, fake_jev

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
    _answers(monkeypatch, "reply_only", conversation=kind)
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
    """The scaffold was given roles clerk, supervisor, owner; a role outside them (and what inherits them) is not
    offered the agent, so the policy lines are the whole door."""
    branch, _ = ferinos
    for role in ["clerk", "supervisor", "owner"]:
        person = Person(name="x", roles=[role], branch_id=branch.id)
        assert [a.id for a in agents_for(session, person)] == [MANIFEST.id], role
    outsider = Person(name="x", roles=["viewer"], branch_id=branch.id)
    assert agents_for(session, outsider) == []
