"""Deferring turns while Jev is unreachable (spec 2026-10-18, Jev unreachable)."""

import asyncio
import dataclasses
import datetime as dt
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart
from sqlmodel import Session, select

from mia.agents.base import Turn
from mia.agents.registry import AGENTS, DEFAULT
from mia.chat import deferred
from mia.chat.blocks import ChatReply, TextBlock
from mia.chat.replies import _store
from mia.chat.service import run_turn
from mia.core import jev, orgconfig
from mia.core import people as people_service
from mia.core.db import utcnow
from mia.core.models import Actor, Event, Message, Person
from mia.i18n import t
from mia.settings import get_settings
from tests.jev_fake import choice, fake_jev

TWO = ["shift_supervisor", "sales_supervisor"]


@pytest.fixture
def jev_down(monkeypatch: pytest.MonkeyPatch, people: dict[str, Person]) -> dict[str, Any]:
    """Two agents, Jev returns 503; flip state["up"] to bring it back. Helena is the developer."""
    state: dict[str, Any] = {"up": False, "seen": []}
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings(agents=TWO))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DEVELOPER_PERSON_ID", people["Helena"].id)
    monkeypatch.setattr(jev, "BACKOFF", 0)
    get_settings.cache_clear()

    def transport() -> Any:
        if not state["up"]:
            return fake_jev(lambda b: {}, state["seen"], status=503)
        return fake_jev(lambda b: {"agent": choice("shift_supervisor")}, state["seen"])

    monkeypatch.setattr(jev, "_inner", transport)
    return state


def _turn(session: Session, person: Person, text: str, thread: str | None = None) -> ChatReply:
    reply = asyncio.run(run_turn(session, None, person, text, thread))
    session.commit()
    return reply


def _events(session: Session, action: str) -> list[Event]:
    return list(session.exec(select(Event).where(Event.action == action)).all())


def _retry(at: dt.datetime | None = None) -> int:
    return asyncio.run(deferred.retry_due(at or utcnow()))


def test_jev_down_defers_replies_once_and_alerts_once(
    session: Session, people: dict[str, Person], jev_down: dict[str, Any]
) -> None:
    first = _turn(session, people["Sanna"], "how much did we sell today?")
    second = _turn(session, people["Sanna"], "and yesterday?", first.thread_id)
    assert first.blocks and second.blocks == []
    assert len(_events(session, "turn.deferred")) == 2
    assert len(_events(session, "jev.outage_started")) == 1
    alerts = session.exec(select(Message).where(Message.role == "notification")).all()
    dev = [m for m in alerts if m.text.startswith("Jev ei vastaa")]  # Helena's language is fi
    assert len(dev) == 1 and "sell" not in dev[0].text


def test_jev_back_answers_oldest_first_once(
    session: Session, people: dict[str, Person], jev_down: dict[str, Any]
) -> None:
    first = _turn(session, people["Sanna"], "who can cover Kamppi tomorrow?")
    _turn(session, people["Sanna"], "and Pasila?", first.thread_id)
    jev_down["up"] = True
    assert _retry() == 2
    assert _retry() == 0  # never twice
    resumed = _events(session, "turn.resumed")
    deferred_ids = [e.after["message_id"] for e in _events(session, "turn.deferred")]  # type: ignore[index]
    assert [e.after["message_id"] for e in resumed] == deferred_ids  # type: ignore[index]
    replies = session.exec(
        select(Message)
        .where(Message.thread_id == first.thread_id)
        .where(Message.role == "notification")
    ).all()
    assert len(replies) == 2  # delivered proactively, one per turn
    assert len(_events(session, "jev.outage_ended")) == 1
    assert _events(session, "jev.outage_ended")[0].after["count"] == 2  # type: ignore[index]
    back = [m for m in session.exec(select(Message)) if m.text.startswith("Jev vastaa taas")]
    assert len(back) == 1 and "Kamppi" not in back[0].text


def test_still_down_stops_the_round(
    session: Session, people: dict[str, Person], jev_down: dict[str, Any]
) -> None:
    _turn(session, people["Sanna"], "how much did we sell today?")
    assert _retry() == 0
    assert _events(session, "turn.resumed") == []


def test_two_hours_expires_to_the_buttons(
    session: Session, people: dict[str, Person], jev_down: dict[str, Any]
) -> None:
    _turn(session, people["Sanna"], "how much did we sell today?")
    assert _retry(utcnow() + dt.timedelta(hours=2, minutes=1)) == 1
    (resumed,) = _events(session, "turn.resumed")
    assert resumed.after and resumed.after["expired"] is True
    assert _events(session, "chat.route_asked")
    assert _events(session, "jev.outage_ended") == []  # drained by expiry alone: still open


def test_egress_none_does_not_defer(
    session: Session,
    people: dict[str, Person],
    jev_down: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIA_EGRESS_LEVEL", "none")
    get_settings.cache_clear()
    _turn(session, people["Sanna"], "how much did we sell today?")
    assert _events(session, "turn.deferred") == []


def test_another_thread_of_the_same_person_is_not_held(
    session: Session, people: dict[str, Person], jev_down: dict[str, Any]
) -> None:
    _turn(session, people["Sanna"], "how much did we sell today?")
    jev_down["up"] = True
    other = _turn(session, people["Sanna"], "who can cover Kamppi tomorrow?")  # a new thread
    assert other.blocks and len(_events(session, "turn.deferred")) == 1


def test_a_deactivated_person_is_closed_silently(
    session: Session, people: dict[str, Person], jev_down: dict[str, Any]
) -> None:
    _turn(session, people["Sanna"], "how much did we sell today?")
    people_service.deactivate(session, Actor.person(people["Helena"]), people["Sanna"])
    session.commit()
    jev_down["up"] = True
    before = len(session.exec(select(Message)).all())
    assert _retry() == 1
    (resumed,) = _events(session, "turn.resumed")
    assert resumed.after and resumed.after["expired"] is True
    assert len(session.exec(select(Message)).all()) == before


def test_the_shift_supervisors_jev_decision_defers_too(
    session: Session,
    people: dict[str, Person],
    jev_down: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIA_DECIDER", "jev")
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings())
    get_settings.cache_clear()
    reply = _turn(
        session, people["Juha"], "I'm sick today"
    )  # one agent: no router, the decider fails
    (ev,) = _events(session, "turn.deferred")
    assert ev.after and ev.after["stage"] == "agent" and reply.blocks


def _spy(monkeypatch: pytest.MonkeyPatch, handle: Any) -> None:
    """Make the shift supervisor (the router's pick) answer with `handle`."""
    monkeypatch.setitem(AGENTS, DEFAULT, dataclasses.replace(AGENTS[DEFAULT], handle_turn=handle))


def test_a_failing_resume_is_closed_and_the_next_still_resumes(
    session: Session,
    people: dict[str, Person],
    jev_down: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _turn(session, people["Sanna"], "how much did we sell today?")
    _turn(session, people["Sanna"], "show my visits today")  # a new thread
    original = AGENTS[DEFAULT].handle_turn
    calls: list[str] = []

    async def handle(turn: Turn) -> ChatReply:
        calls.append(turn.text)
        if len(calls) == 1:
            raise RuntimeError("secret text")
        return await original(turn)

    _spy(monkeypatch, handle)
    jev_down["up"] = True
    assert _retry() == 2 and len(calls) == 2
    failed, ok = _events(session, "turn.resumed")
    assert failed.after == {
        "message_id": failed.after["message_id"],  # type: ignore[index]
        "deferred_event_id": failed.after["deferred_event_id"],  # type: ignore[index]
        "expired": False,
        "failed": True,
        "error": "RuntimeError",
    }
    assert ok.after and "failed" not in ok.after
    sorry = t("reply.unavailable", people["Sanna"].language)
    notes = session.exec(
        select(Message)
        .where(Message.thread_id == first.thread_id)
        .where(Message.role == "notification")
    ).all()
    assert [m.text for m in notes] == [sorry]
    assert len(_events(session, "jev.outage_ended")) == 1


def test_a_queued_turn_sees_the_reply_resumed_before_it(
    session: Session,
    people: dict[str, Person],
    jev_down: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _turn(session, people["Sanna"], "how much did we sell today?")
    _turn(session, people["Sanna"], "and yesterday?", first.thread_id)
    pasts: list[int] = []
    answer = ModelMessagesTypeAdapter.dump_python(
        [ModelResponse(parts=[TextPart("ok")])], mode="json"
    )

    async def handle(turn: Turn) -> ChatReply:
        pasts.append(len(turn.past))
        return _store(turn.session, turn.deps, turn.thread, [TextBlock(text="ok")], answer)

    _spy(monkeypatch, handle)
    jev_down["up"] = True
    assert _retry() == 2
    assert pasts == [0, 1]  # the second turn sees the first one's resumed reply


def _answers_when_up(
    monkeypatch: pytest.MonkeyPatch, state: dict[str, Any], agent_id: str
) -> list[str]:
    """`agent_id` cannot reach Jev while it is down; once up it records the text it answers."""
    texts: list[str] = []

    async def handle(turn: Turn) -> ChatReply:
        if not state["up"]:
            raise jev.JevUnreachable("status 503")
        texts.append(turn.text)
        return _store(turn.session, turn.deps, turn.thread, [TextBlock(text="ok")], [])

    spec = dataclasses.replace(AGENTS[agent_id], handle_turn=handle)
    monkeypatch.setitem(AGENTS, agent_id, spec)
    return texts


def test_first_contact_during_an_outage_resumes_with_the_original_question(
    session: Session,
    people: dict[str, Person],
    jev_down: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    langs = ["fil", "en", "ceb"]
    org = orgconfig.OrgSettings(agents=TWO, languages=langs)
    monkeypatch.setattr(orgconfig, "load", lambda org_name=None: org)
    helena = people["Helena"]
    ana = people_service.add_person(
        session,
        Actor.person(helena),
        branch_id=helena.branch_id,
        name="Ana Cruz",
        roles=["supervisor"],
        language="en",
        language_known=False,
    )
    session.commit()
    texts = _answers_when_up(monkeypatch, jev_down, DEFAULT)
    asked = _turn(session, ana, "anong oras ako bukas?")
    _turn(session, ana, "Filipino", asked.thread_id)  # the tap; then the router gets a 503
    (ev,) = _events(session, "turn.deferred")
    original = session.exec(select(Message).where(Message.text == "anong oras ako bukas?")).one()
    assert ev.after and ev.after["answer_id"] == original.id != ev.after["message_id"]
    jev_down["up"] = True
    assert _retry() == 1
    assert texts == ["anong oras ako bukas?"]


def test_a_route_tap_during_an_outage_resumes_with_the_original_and_its_agent(
    session: Session,
    people: dict[str, Person],
    jev_down: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    down = jev._inner
    monkeypatch.setattr(jev, "_inner", lambda: fake_jev(lambda b: {"agent": choice("x", 0.3)}))
    asked = _turn(session, people["Sanna"], "hmm, the numbers")
    assert _events(session, "chat.route_asked")
    monkeypatch.setattr(jev, "_inner", down)
    texts = _answers_when_up(monkeypatch, jev_down, "sales_supervisor")
    label = t("agent.sales_supervisor.label", people["Sanna"].language)
    _turn(session, people["Sanna"], label, asked.thread_id)
    (ev,) = _events(session, "turn.deferred")
    assert ev.after and ev.after["stage"] == "agent"
    jev_down["up"] = True  # the router would now pick the shift supervisor
    assert _retry() == 1
    assert texts == ["hmm, the numbers"]


def test_an_outage_drained_by_expiry_closes_silently_and_the_next_alerts_again(
    session: Session, people: dict[str, Person], jev_down: dict[str, Any]
) -> None:
    _turn(session, people["Sanna"], "how much did we sell today?")
    assert _retry(utcnow() + dt.timedelta(hours=2, minutes=1)) == 1
    _turn(session, people["Sanna"], "show my visits today")  # a new thread, Jev still down
    (ended,) = _events(session, "jev.outage_ended")
    assert ended.after == {"count": 1, "expired_only": True}
    assert len(_events(session, "jev.outage_started")) == 2
    texts = [m.text for m in session.exec(select(Message).where(Message.role == "notification"))]
    assert sum(x.startswith("Jev ei vastaa") for x in texts) == 2
    assert not any(x.startswith("Jev vastaa taas") for x in texts)
