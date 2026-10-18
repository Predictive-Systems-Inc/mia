"""The reply language: asked once on first contact, kept, changed with the change words."""

import asyncio

import pytest
from sqlmodel import Session, select

from mia.chat.blocks import ChatReply, QuickRepliesBlock
from mia.chat.service import run_turn
from mia.core import orgconfig
from mia.core import people as people_service
from mia.core.models import Actor, Event, Person


def _turn(session: Session, person: Person, text: str, thread: str | None = None) -> ChatReply:
    reply = asyncio.run(run_turn(session, None, person, text, thread))
    session.commit()
    return reply


def _buttons(reply: ChatReply) -> list[str]:
    return next(b.options for b in reply.blocks if isinstance(b, QuickRepliesBlock))


@pytest.fixture
def ph_org(monkeypatch: pytest.MonkeyPatch) -> None:
    langs = ["fil", "en", "ceb"]
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings(languages=langs))


@pytest.fixture
def newcomer(session: Session, people: dict[str, Person]) -> Person:
    helena = people["Helena"]
    p = people_service.add_person(
        session,
        Actor.person(helena),
        branch_id=helena.branch_id,
        name="Ana Cruz",
        roles=["staff"],
        language="en",
        language_known=False,
    )
    session.commit()
    return p


def test_seeded_people_have_chosen_their_language(
    session: Session, people: dict[str, Person]
) -> None:
    chosen = session.exec(select(Event).where(Event.action == "person.language_chosen")).all()
    assert {e.entity_id for e in chosen} == {p.id for p in people.values()}


def test_first_contact_asks_then_answers_the_original_message(
    session: Session, newcomer: Person, ph_org: None
) -> None:
    asked = _turn(session, newcomer, "anong oras ako bukas?")
    assert _buttons(asked) == ["Filipino", "English", "Cebuano"]
    answered = _turn(session, newcomer, "Filipino", asked.thread_id)
    session.refresh(newcomer)
    assert newcomer.language == "fil"
    assert session.exec(
        select(Event)
        .where(Event.action == "person.language_chosen")
        .where(Event.entity_id == newcomer.id)
    ).one()
    assert answered.blocks  # the original question was answered, not the word "Filipino"


def test_one_language_organisations_never_ask(session: Session, newcomer: Person) -> None:
    reply = _turn(session, newcomer, "hello")
    assert not any(
        isinstance(b, QuickRepliesBlock) and "English" in b.options for b in reply.blocks
    )


@pytest.mark.parametrize(
    "word", ["language", "/wika", " WIKA ", "/Language", "pinulongan", "lengguahe"]
)
def test_the_change_words_show_the_buttons(
    session: Session, people: dict[str, Person], ph_org: None, word: str
) -> None:
    reply = _turn(session, people["Juha"], word)
    assert _buttons(reply) == ["Filipino", "English", "Cebuano"]


def test_a_change_tap_confirms_in_the_new_language(
    session: Session, people: dict[str, Person], ph_org: None
) -> None:
    asked = _turn(session, people["Juha"], "wika")
    done = _turn(session, people["Juha"], "Cebuano", asked.thread_id)
    session.refresh(people["Juha"])
    assert people["Juha"].language == "ceb"
    assert "Cebuano" in done.blocks[0].text  # type: ignore[union-attr]


def test_a_stale_language_button_is_plain_text(
    session: Session, people: dict[str, Person], ph_org: None
) -> None:
    asked = _turn(session, people["Juha"], "wika")
    _turn(session, people["Juha"], "what are my visits today?", asked.thread_id)
    _turn(session, people["Juha"], "English", asked.thread_id)
    session.refresh(people["Juha"])
    assert people["Juha"].language == "fi"


def test_the_reply_language_is_the_persons_not_the_messages(
    session: Session, people: dict[str, Person]
) -> None:
    from mia.chat.service import _prepare

    _, _, deps, _ = _prepare(session, people["Juha"], "Thank you, see you tomorrow", None)
    assert deps.lang == "fi"  # Juha chose Finnish; an English message does not change it


def test_an_emergency_gets_the_script_before_the_language_question(
    session: Session, newcomer: Person, ph_org: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.chat import service

    sentinel = ChatReply(thread_id="t", message_id="m", agent_id="", blocks=[])
    monkeypatch.setattr(service, "safety_reply", lambda *a: sentinel)
    assert _turn(session, newcomer, "help, fire!") is sentinel
