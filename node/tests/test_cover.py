"""Cover confirmation: instruction, message, call, next candidate, quiet hours (D1, D10, D11).

Every test drives the state machine with an explicit clock, so timings are exact.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.agents.dispatcher import cover, tools
from mia.agents.dispatcher.agent import MANIFEST, create_agent
from mia.agents.dispatcher.models import CoverRequest
from mia.chat.channels import NOTIFICATION, CallResult, StubCallAdapter, set_call_adapter
from mia.core import store
from mia.core.models import Actor, Branch, Event, Job, Message, Person, Thread, Visit
from mia.core.orgconfig import OrgSettings, QuietHours

HEL = ZoneInfo("Europe/Helsinki")
ORG = OrgSettings()


@pytest.fixture(autouse=True)
def dispatcher_role() -> None:
    create_agent("test")


def local(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=HEL)


def deps_for(session: Session, branch: Branch, person: Person) -> AgentDeps:
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent("agent.dispatcher"),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=dt.datetime.now(HEL).date(),
        lang="en",
        manifest=MANIFEST,
    )


def kamppi_visit(session: Session, days_ahead: int) -> Visit:
    """The daily 09:00 Kamppi visit (assigned to Juha) some days from today."""
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    day = dt.datetime.now(HEL).date() + dt.timedelta(days=days_ahead)
    return session.exec(select(Visit).where(Visit.job_id == job.id).where(Visit.date == day)).one()


def instruct(
    session: Session,
    branch: Branch,
    people: dict[str, Person],
    visit: Visit,
    who: str,
    queue: list[str],
    now: dt.datetime,
) -> CoverRequest:
    deps = deps_for(session, branch, people["Sanna"])
    pool = {c.person_id: c for c in tools.candidate_data(session, deps, visit)}
    return cover.instruct(
        session,
        deps.actor,
        visit,
        tools._slot(session, visit, branch.timezone),
        pool[people[who].id],
        [people[q].id for q in queue],
        list(visit.assigned_person_ids),
        now,
    )


def inbox(session: Session, person: Person) -> list[Message]:
    return list(
        session.exec(
            select(Message)
            .join(Thread, col(Thread.id) == col(Message.thread_id))
            .where(Thread.person_id == person.id)
            .where(Message.role == NOTIFICATION)
            .order_by(col(Message.id))
        )
    )


# ---- pure timing rules --------------------------------------------------------------------


def test_quiet_hours_wrap_midnight() -> None:
    quiet = QuietHours()
    assert quiet.contains(dt.time(23, 0)) and quiet.contains(dt.time(5, 59))
    assert not quiet.contains(dt.time(6, 0)) and not quiet.contains(dt.time(20, 59))
    daytime = QuietHours(start=dt.time(12), end=dt.time(13))
    assert daytime.contains(dt.time(12, 30)) and not daytime.contains(dt.time(13, 30))


def test_urgency_and_permissions() -> None:
    day = dt.date(2026, 10, 1)
    night = local(day, 23)
    assert cover.quiet_end_after(night, "Europe/Helsinki", ORG) == local(
        day + dt.timedelta(days=1), 6
    )
    assert cover.is_urgent_overnight(
        night, local(day + dt.timedelta(days=1), 9), "Europe/Helsinki", ORG
    )
    assert not cover.is_urgent_overnight(
        night, local(day + dt.timedelta(days=1), 11), "Europe/Helsinki", ORG
    )
    assert cover.may_message(
        night, local(day + dt.timedelta(days=1), 6, 30), "Europe/Helsinki", ORG
    )
    assert not cover.may_message(
        night, local(day + dt.timedelta(days=1), 13), "Europe/Helsinki", ORG
    )
    assert not cover.may_call(night, "Europe/Helsinki", ORG)
    assert cover.may_call(local(day, 14), "Europe/Helsinki", ORG)
    assert cover.is_soon(local(day, 8), local(day, 9), ORG)
    assert not cover.is_soon(local(day, 7), local(day, 9), ORG)


# ---- escalation ---------------------------------------------------------------------------


def test_message_then_call_then_next_candidate(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    visit = kamppi_visit(session, 2)
    now = local(visit.date - dt.timedelta(days=1), 15)  # daytime, the day before
    first = instruct(session, branch, people, visit, "Mikael", ["Maria"], now)
    assert (first.status, first.stage) == ("asking", "message")
    assert first.next_action_at == now + dt.timedelta(minutes=15)
    ask = inbox(session, people["Mikael"])[-1]
    assert "Kamppi" in ask.text and ask.blocks[-1]["options"] == ["Hyväksyn", "En pysty"]

    assert cover.process_due(session, now + dt.timedelta(minutes=14)) == 0
    assert cover.process_due(session, now + dt.timedelta(minutes=15)) == 1
    session.refresh(first)
    assert first.stage == "call"
    call = session.exec(select(Event).where(Event.action == "call.requested")).one()
    assert call.entity_id == people["Mikael"].id and call.after is not None
    assert "AI assistant" in call.after["script"] or "tekoälyavustaja" in call.after["script"]

    assert cover.process_due(session, now + dt.timedelta(minutes=25)) == 1
    session.refresh(first)
    assert first.status == "timed_out"
    second = session.exec(
        select(CoverRequest).where(CoverRequest.candidate_id == people["Maria"].id)
    ).one()
    assert second.status == "asking" and second.queue == []
    told = inbox(session, people["Sanna"])[-1].text
    assert "Mikael Nieminen" in told and "Maria Mäkinen" in told
    visit_now = session.get(Visit, visit.id)
    assert visit_now is not None and visit_now.assigned_person_ids == [people["Juha"].id]


def test_decline_moves_on_and_nobody_left_is_reported(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    visit = kamppi_visit(session, 2)
    now = local(visit.date - dt.timedelta(days=1), 15)
    instruct(session, branch, people, visit, "Mikael", ["Maria"], now)
    cover.respond(session, people["Mikael"], False, Actor.person(people["Mikael"]), now)
    assert "Maria Mäkinen" in inbox(session, people["Sanna"])[-1].text
    cover.respond(session, people["Maria"], False, Actor.person(people["Maria"]), now)
    assert "eikä muita ehdokkaita" in inbox(session, people["Sanna"])[-1].text
    with pytest.raises(cover.CoverError):
        cover.respond(session, people["Maria"], True, Actor.person(people["Maria"]), now)


def test_accept_reassigns_and_cancels_other_asks(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    visit = kamppi_visit(session, 2)
    now = local(visit.date - dt.timedelta(days=1), 15)
    old = instruct(session, branch, people, visit, "Maria", [], now)
    new = instruct(session, branch, people, visit, "Mikael", [], now)  # a new instruction wins
    session.refresh(old)
    assert old.status == "cancelled" and new.status == "asking"
    cover.respond(session, people["Mikael"], True, Actor.person(people["Mikael"]), now)
    session.refresh(visit)
    assert visit.assigned_person_ids == [people["Mikael"].id]
    assert cover.process_due(session, now + dt.timedelta(hours=1)) == 0


def test_visit_soon_calls_at_once(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    visit = kamppi_visit(session, 2)
    now = visit.planned_start - dt.timedelta(minutes=30)  # 08:30, not quiet
    request = instruct(session, branch, people, visit, "Mikael", [], now)
    assert request.stage == "call" and request.next_action_at == now + dt.timedelta(minutes=5)
    assert session.exec(select(Event).where(Event.action == "call.requested")).first()


def test_quiet_hours_hold_non_urgent_messages(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    visit = kamppi_visit(session, 3)
    now = local(visit.date - dt.timedelta(days=2), 22)  # quiet, visit not next morning
    request = instruct(session, branch, people, visit, "Mikael", [], now)
    assert request.stage == "waiting_quiet"
    assert request.next_action_at == local(visit.date - dt.timedelta(days=1), 6)
    assert inbox(session, people["Mikael"]) == []
    cover.process_due(session, local(visit.date - dt.timedelta(days=1), 6))
    session.refresh(request)
    assert request.stage == "message" and len(inbox(session, people["Mikael"])) == 1


def test_urgent_cover_messages_at_night_but_never_calls(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    visit = kamppi_visit(session, 2)
    now = local(visit.date - dt.timedelta(days=1), 23)  # quiet, visit 09:00 next morning
    request = instruct(session, branch, people, visit, "Mikael", [], now)
    assert request.stage == "message" and len(inbox(session, people["Mikael"])) == 1
    cover.process_due(session, now + dt.timedelta(minutes=20))
    session.refresh(request)
    assert request.stage == "message" and request.next_action_at == local(visit.date, 6)
    assert session.exec(select(Event).where(Event.action == "call.requested")).first() is None
    cover.process_due(session, local(visit.date, 6))
    session.refresh(request)
    assert request.stage == "call"


def test_no_call_for_people_who_refused_calls(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    mikael = people["Mikael"]
    store.update(session, mikael, {"accepts_calls": False}, Actor.system(branch.id))
    visit = kamppi_visit(session, 2)
    now = local(visit.date - dt.timedelta(days=1), 15)
    request = instruct(session, branch, people, visit, "Mikael", [], now)
    cover.process_due(session, now + dt.timedelta(minutes=15))
    session.refresh(request)
    assert request.status == "timed_out"
    assert session.exec(select(Event).where(Event.action == "call.requested")).first() is None


def test_call_adapter_is_pluggable(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    calls: list[str] = []

    class Recorder:
        def call(self, session: Session, person: Person, script: str, actor: Actor) -> CallResult:
            calls.append(person.name)
            return CallResult(placed=True, detail="ok")

    set_call_adapter(Recorder())
    try:
        visit = kamppi_visit(session, 2)
        instruct(
            session,
            branch,
            people,
            visit,
            "Mikael",
            [],
            visit.planned_start - dt.timedelta(minutes=30),
        )
    finally:
        set_call_adapter(StubCallAdapter())
    assert calls == ["Mikael Nieminen"]


def test_instructor_replacing_themselves_needs_approval(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    visit = kamppi_visit(session, 2)
    juha = people["Juha"]
    actor = Actor.person(juha).as_agent("agent.dispatcher")
    deps = deps_for(session, branch, juha)
    pool = {c.person_id: c for c in tools.candidate_data(session, deps, visit)}
    request = cover.instruct(
        session,
        actor,
        visit,
        tools._slot(session, visit, branch.timezone),
        pool[people["Mikael"].id],
        [],
        [juha.id],
        local(visit.date - dt.timedelta(days=1), 15),
    )
    assert request.status == "awaiting_approval"
