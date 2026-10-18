import asyncio
import datetime as dt
from pathlib import Path

import pytest
from sqlmodel import Session, select

from mia.agents.base import AgentDeps
from mia.agents.shift_supervisor.agent import MANIFEST, create_agent
from mia.chat import route_memory
from mia.chat.service import run_turn
from mia.core import events, store
from mia.core.models import Actor, Branch, Event, Message, Person, Thread
from mia.learning.harvest import harvest
from mia.learning.schema import Review, load_records
from mia.settings import get_settings
from mia.skills import runtime
from mia.skills.runtime import Alternative, Classification

TEXT = "Juha Laine ei pääse huomenna"
SOMETHING_ELSE_INDEX = -1


class Fixed:
    def classify(self, text: str, context: str = "") -> Classification:
        return Classification(
            intent="shift_supervisor.report_absence",
            confidence=0.5,
            band="medium",
            lang="fi",
            slots={},
            safety=0.0,
            version="v1",
            alternatives=[
                Alternative(intent="shift_supervisor.report_absence", confidence=0.5),
                Alternative(intent="shift_supervisor.my_visits", confidence=0.3),
            ],
        )


@pytest.fixture(autouse=True)
def stub_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "get_classifier", lambda role: Fixed())


def ask(session: Session, juha: Person, text: str, thread_id: str | None = None):
    reply = asyncio.run(run_turn(session, create_agent("test"), juha, text, thread_id))
    session.commit()
    return reply


def tap(session: Session, juha: Person, reply, index: int) -> None:
    label = next(b for b in reply.blocks if b.type == "quick_replies").options[index]
    ask(session, juha, label, reply.thread_id)


def original_id(session: Session, thread_id: str) -> str:
    asked = session.exec(
        select(Event)
        .where(Event.action == "intent.clarify_asked")
        .where(Event.entity_id == thread_id)
    ).all()
    return (asked[-1].after or {})["original_message_id"]


def emit_at(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    actor: Actor,
    when: dt.datetime,
) -> None:
    """Emit one event stamped `when` (the clock default is patched for this call only)."""
    with monkeypatch.context() as m:
        m.setattr(Event.model_fields["timestamp"], "default_factory", lambda: when)
        events.emit(session, action, ("thread", "x"), None, {}, actor)
    session.commit()


def agent_for(person: Person) -> Actor:
    return Actor.person(person).as_agent(MANIFEST.roles.agent_role)


def path() -> Path:
    return get_settings().MIA_LEARNING_DIR / "shift_supervisor" / "candidates.jsonl"


def test_clarified_choice_becomes_a_pending_pseudonymised_candidate(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, 0)
    out = harvest(session, "shift_supervisor", juha.branch_id)
    assert len(out) == 1
    rec = out[0]
    assert rec.id == f"shift_supervisor/real/{original_id(session, first.thread_id)}"
    assert rec.intent == "shift_supervisor.report_absence"
    assert rec.source == "real-clarification" and rec.split == "train" and rec.kind == "normal"
    assert rec.review.status == "pending"
    assert rec.text == "Person_3 ei pääse huomenna"
    assert rec.context == ""
    assert load_records(path()) == out
    assert harvest(session, "shift_supervisor", juha.branch_id) == []  # idempotent
    assert load_records(path()) == out


def test_context_is_the_previous_assistant_message(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, "moi")
    second = ask(session, juha, TEXT, first.thread_id)  # ignores the open question
    tap(session, juha, second, 0)
    previous = session.get(Message, first.message_id)
    assert previous is not None and previous.text
    (rec,) = harvest(session, "shift_supervisor", juha.branch_id)
    assert rec.context == previous.text


def test_something_else_gives_no_record(session: Session, people: dict[str, Person]) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, SOMETHING_ELSE_INDEX)
    assert harvest(session, "shift_supervisor", juha.branch_id) == []
    assert not path().exists()


def test_later_correction_of_the_same_message_drops_it(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, 0)
    events.emit(
        session,
        "intent.clarified",
        ("thread", first.thread_id),
        None,
        {
            "intent": "shift_supervisor.my_visits",
            "asked_event_id": "x",
            "original_message_id": original_id(session, first.thread_id),
        },
        agent_for(juha),
    )
    session.commit()
    got = harvest(session, "shift_supervisor", juha.branch_id)
    assert [r.intent for r in got] == ["shift_supervisor.my_visits"]  # only the correction survives


def test_clarification_of_another_message_is_not_a_correction(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, 0)
    second = ask(session, juha, "toinen viesti", first.thread_id)
    tap(session, juha, second, 0)
    assert len(harvest(session, "shift_supervisor", juha.branch_id)) == 2


@pytest.mark.parametrize(("minutes", "kept"), [(60, False), (60.01, True), (59, False), (61, True)])
def test_undo_within_one_hour_drops_the_record(
    session: Session,
    people: dict[str, Person],
    monkeypatch: pytest.MonkeyPatch,
    minutes: float,
    kept: bool,
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, 0)
    clarified = session.exec(select(Event).where(Event.action == "intent.clarified")).one()
    when = clarified.timestamp + dt.timedelta(minutes=minutes)
    emit_at(session, monkeypatch, "cover.cancelled", agent_for(juha), when)
    assert (len(harvest(session, "shift_supervisor", juha.branch_id)) == 1) is kept


def test_absence_cancelled_also_counts_as_undo(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, 0)
    clarified = session.exec(select(Event).where(Event.action == "intent.clarified")).one()
    when = clarified.timestamp + dt.timedelta(minutes=5)
    emit_at(session, monkeypatch, "absence.cancelled", agent_for(juha), when)
    assert harvest(session, "shift_supervisor", juha.branch_id) == []


def test_undo_by_someone_else_is_ignored(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, 0)
    clarified = session.exec(select(Event).where(Event.action == "intent.clarified")).one()
    when = clarified.timestamp + dt.timedelta(minutes=5)
    emit_at(session, monkeypatch, "cover.cancelled", agent_for(people["Sanna"]), when)
    assert len(harvest(session, "shift_supervisor", juha.branch_id)) == 1


@pytest.mark.parametrize("intent", ["conversation.privacy_request", "conversation.health_report"])
def test_special_category_intents_are_never_written(
    session: Session, people: dict[str, Person], intent: str
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    events.emit(
        session,
        "intent.clarified",
        ("thread", first.thread_id),
        None,
        {
            "intent": intent,
            "asked_event_id": "x",
            "original_message_id": original_id(session, first.thread_id),
        },
        agent_for(juha),
    )
    session.commit()
    assert harvest(session, "shift_supervisor", juha.branch_id) == []
    assert not path().exists()


def test_existing_reviewed_lines_are_kept_byte_identical(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, 0)
    (rec,) = harvest(session, "shift_supervisor", juha.branch_id)
    reviewed = rec.model_copy(update={"review": Review(status="kept", note="ok")})
    path().write_text(reviewed.model_dump_json() + "\n", encoding="utf-8")
    before = path().read_bytes()
    second = ask(session, juha, "toinen viesti", first.thread_id)
    tap(session, juha, second, 0)
    (new,) = harvest(session, "shift_supervisor", juha.branch_id)
    after = path().read_bytes()
    assert after.startswith(before)
    assert after[len(before) :] == (new.model_dump_json() + "\n").encode()
    assert [r.review.status for r in load_records(path())] == ["kept", "pending"]


def test_names_in_the_previous_assistant_message_are_pseudonymised(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, "moi")
    store.insert(
        session,
        Message(
            branch_id=juha.branch_id,
            thread_id=first.thread_id,
            role="assistant",
            sender_id="shift_supervisor",
            text="Sanna Virtanen hoitaa huomisen",
        ),
        agent_for(juha),
    )
    session.commit()
    second = ask(session, juha, TEXT, first.thread_id)
    tap(session, juha, second, 0)
    (rec,) = harvest(session, "shift_supervisor", juha.branch_id)
    assert rec.context == "Person_2 hoitaa huomisen"


@pytest.mark.parametrize("who", ["Sanna", "system"])
def test_cancel_by_another_or_system_actor_does_not_drop_the_record(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch, who: str
) -> None:
    """Known limit: undo is matched by actor, so these are not seen."""
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    tap(session, juha, first, 0)
    clarified = session.exec(select(Event).where(Event.action == "intent.clarified")).one()
    actor = Actor.system(juha.branch_id) if who == "system" else agent_for(people[who])
    emit_at(session, monkeypatch, "cover.cancelled", actor, clarified.timestamp)
    assert len(harvest(session, "shift_supervisor", juha.branch_id)) == 1


def test_clarification_of_a_missing_message_is_skipped(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    first = ask(session, juha, TEXT)
    events.emit(
        session,
        "intent.clarified",
        ("thread", first.thread_id),
        None,
        {
            "intent": "shift_supervisor.report_absence",
            "asked_event_id": "x",
            "original_message_id": "01NOSUCHMESSAGE0000000000",
        },
        agent_for(juha),
    )
    session.commit()
    assert harvest(session, "shift_supervisor", juha.branch_id) == []
    assert not path().exists()


ROUTER = "shift_supervisor"


def tap_route(session: Session, juha: Person, text: str = TEXT) -> tuple[Event, Thread]:
    """A user message in a new thread, then a route tap for ROUTER through route_memory.remember."""
    reply = ask(session, juha, text)
    thread = session.get(Thread, reply.thread_id)
    branch = session.get(Branch, juha.branch_id)
    assert thread is not None and branch is not None
    deps = AgentDeps(
        session=session,
        actor=agent_for(juha),
        person=juha,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=dt.datetime.now(dt.UTC).date(),
        lang="fi",
        manifest=MANIFEST,
    )
    first = session.exec(
        select(Message).where(Message.thread_id == thread.id).where(Message.role == "user")
    ).first()
    assert first is not None
    route_memory.remember(session, deps, thread, first.id, ROUTER, ROUTER, 0.4, [ROUTER, "x"])
    session.commit()
    chosen = session.exec(select(Event).where(Event.action == route_memory.CHOSEN)).one()
    return chosen, thread


def test_route_choice_becomes_a_pending_pseudonymised_router_candidate(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    chosen, _ = tap_route(session, juha)
    (rec,) = harvest(session, "router", juha.branch_id)
    assert rec.id == f"router/real/{(chosen.after or {})['original_message_id']}"
    assert rec.role == "router" and rec.intent == ROUTER and rec.source == "real-route-choice"
    assert rec.review.status == "pending"
    assert rec.text == "Person_3 ei pääse huomenna"
    assert harvest(session, "router", juha.branch_id) == []  # idempotent
    assert not path().exists()  # the intent role's file is untouched


@pytest.mark.parametrize(
    ("minutes", "frm", "kept"), [(10, ROUTER, False), (61, ROUTER, True), (10, "other", True)]
)
def test_route_switch_away_within_the_hour_drops_the_record(
    session: Session,
    people: dict[str, Person],
    monkeypatch: pytest.MonkeyPatch,
    minutes: int,
    frm: str,
    kept: bool,
) -> None:
    juha = people["Juha"]
    chosen, thread = tap_route(session, juha)
    when = chosen.timestamp + dt.timedelta(minutes=minutes)
    with monkeypatch.context() as m:
        m.setattr(Event.model_fields["timestamp"], "default_factory", lambda: when)
        events.emit(
            session,
            "chat.agent_switched",
            ("thread", thread.id),
            None,
            {"from": frm},
            agent_for(juha),
        )
    session.commit()
    assert (len(harvest(session, "router", juha.branch_id)) == 1) is kept


def test_route_forgotten_after_the_tap_drops_the_record(
    session: Session, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    chosen, _ = tap_route(session, juha)
    events.emit(
        session,
        route_memory.FORGOTTEN,
        ("branch", juha.branch_id),
        None,
        {"key": (chosen.after or {})["key"], "agent_id": ROUTER},
        Actor.system(juha.branch_id),
    )
    session.commit()
    assert harvest(session, "router", juha.branch_id) == []
