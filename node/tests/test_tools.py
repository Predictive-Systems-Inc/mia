"""Dispatcher tools, called directly with deps built on a seeded temp database."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.dispatcher import tools
from mia.agents.dispatcher.agent import MANIFEST, create_agent
from mia.agents.dispatcher.models import Absence
from mia.core import approvals
from mia.core.models import Actor, Approval, Branch, Event, Person, Visit
from mia.core.rbac import PermissionDenied


@pytest.fixture(autouse=True)
def dispatcher_role() -> None:
    create_agent("test")  # loads the agent role and registers the approval handler


def deps_for(session: Session, branch: Branch, person: Person) -> AgentDeps:
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent("agent.dispatcher"),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=dt.datetime.now(ZoneInfo(branch.timezone)).date(),
        lang="en",
        manifest=MANIFEST,
    )


def tomorrow(deps: AgentDeps) -> dt.date:
    return deps.today + dt.timedelta(days=1)


def kalasatama_input(deps: AgentDeps) -> tools.FindReplacementsInput:
    return tools.FindReplacementsInput(
        location_name="Kalasatama", date=tomorrow(deps), time=dt.time(6, 30)
    )


def test_get_my_visits_returns_only_own(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Juha"])
    out = tools.get_my_visits(deps, tools.GetMyVisitsInput(), "c1")
    assert out.person == "Juha Laine" and out.visits
    assert all("Juha Laine" in v.assigned for v in out.visits)
    assert {v.date for v in out.visits} <= {deps.today + dt.timedelta(days=i) for i in range(7)}


def test_get_my_visits_for_someone_else_is_denied_for_cleaners(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Juha"])
    with pytest.raises(PermissionDenied):
        tools.get_my_visits(deps, tools.GetMyVisitsInput(person_name="Maria"), "c1")
    out = call_tool(deps, tools.BINDINGS[0], tools.GetMyVisitsInput(person_name="Marian"), "c2")
    assert out["status"] == "denied"
    logged = session.exec(select(Event).where(Event.action == "tool.called")).all()
    assert logged[-1].after == {"output": out}


def test_supervisor_can_see_other_visits(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Sanna"])
    out = tools.get_my_visits(deps, tools.GetMyVisitsInput(person_name="Maria"), "c1")
    assert out.person == "Maria Mäkinen"


def test_unknown_person_is_invalid(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Sanna"])
    out = call_tool(deps, tools.BINDINGS[0], tools.GetMyVisitsInput(person_name="Zorro"), "c1")
    assert out["status"] == "invalid"


def test_record_absence_creates_then_updates(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Juha"])
    day = tomorrow(deps)
    first = tools.record_absence(deps, tools.RecordAbsenceInput(date=day), "c1")
    assert not first.updated and len(first.affected_visits) == 2
    second = tools.record_absence(
        deps, tools.RecordAbsenceInput(date=day, partial_day="afternoon"), "c2"
    )
    assert second.updated and second.absence_id == first.absence_id
    assert second.affected_visits == []  # both of Juha's visits are before noon
    rows = session.exec(select(Absence)).all()
    assert len(rows) == 1 and rows[0].partial_day == "afternoon"
    actions = [
        e.action
        for e in session.exec(select(Event).where(Event.entity_type == "dispatcher_absences"))
    ]
    assert actions == ["dispatcher_absences.created", "dispatcher_absences.updated"]
    # Visits are not changed by an absence.
    assert all(
        people["Juha"].id in v.assigned_person_ids
        for v in session.exec(select(Visit).where(Visit.date == day))
        if v.id in {a.visit_id for a in first.affected_visits}
    )


def test_cleaner_cannot_record_absence_for_someone_else(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Juha"])
    with pytest.raises(PermissionDenied):
        tools.record_absence(
            deps, tools.RecordAbsenceInput(date=deps.today, person_name="Aino"), "c1"
        )


def test_find_replacements_ranks_site_knowledge_first(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Sanna"])
    out = tools.find_replacements(deps, kalasatama_input(deps), "c1")
    assert out.visit.location == "Kalasatama office" and out.visit.start == "06:30"
    names = [c.name for c in out.candidates]
    assert names[0] == "Mikael Nieminen"
    assert "Juha Laine" not in names and "Liisa Heikkinen" not in names  # assigned / not available
    assert len(names) <= 3 and not out.escalated
    assert any("knows the site" in r for r in out.candidates[0].reasons)


def test_find_replacements_skips_absent_people(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Sanna"])
    mikael = deps_for(session, branch, people["Mikael"])
    tools.record_absence(mikael, tools.RecordAbsenceInput(date=tomorrow(deps)), "c0")
    out = tools.find_replacements(deps, kalasatama_input(deps), "c1")
    assert "Mikael Nieminen" not in [c.name for c in out.candidates]


def test_find_replacements_unknown_visit(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Sanna"])
    with pytest.raises(LookupError):
        tools.find_replacements(deps, tools.FindReplacementsInput(location_name="Espoo"), "c1")
    with pytest.raises(LookupError):
        tools.find_replacements(deps, tools.FindReplacementsInput(), "c1")
    with pytest.raises(LookupError):
        tools.find_replacements(deps, tools.FindReplacementsInput(visit_id="nope"), "c1")


def _assign(deps: AgentDeps, visit_id: str, person: Person) -> tools.AssignCoverOutput:
    return tools.assign_cover(
        deps, tools.AssignCoverInput(visit_id=visit_id, candidate_id=person.id), "c2"
    )


def test_instruction_is_the_approval_and_cleaner_confirms(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    juha = deps_for(session, branch, people["Juha"])
    tools.record_absence(juha, tools.RecordAbsenceInput(date=tomorrow(juha)), "c0")
    deps = deps_for(session, branch, people["Sanna"])
    found = tools.find_replacements(deps, kalasatama_input(deps), "c1")
    visit_id = found.visit.visit_id
    out = _assign(deps, visit_id, people["Mikael"])
    assert out.status == "asking" and out.approval_id is None and out.note is None
    assert session.exec(select(Approval)).all() == []  # D1: no separate approval
    instructed = session.exec(select(Event).where(Event.action == "assignment.instructed")).one()
    assert instructed.after is not None and instructed.after["approved_by"] == people["Sanna"].id
    visit = session.get(Visit, visit_id)
    assert visit is not None and visit.assigned_person_ids == [people["Juha"].id]  # unchanged

    mikael = deps_for(session, branch, people["Mikael"])
    answer = tools.respond_to_cover(mikael, tools.RespondToCoverInput(accept=True), "c3")
    assert answer.accepted
    session.refresh(visit)
    assert visit.assigned_person_ids == [people["Mikael"].id]
    ev = session.exec(select(Event).where(Event.action == "visit.reassigned")).one()
    assert ev.on_behalf_of == people["Mikael"].id


def test_rule_breaking_instruction_needs_override_approval(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Sanna"])
    found = tools.find_replacements(deps, kalasatama_input(deps), "c1")
    out = _assign(deps, found.visit.visit_id, people["Liisa"])  # available only 10 to 18
    assert out.status == "awaiting_approval" and out.approval_id
    assert out.note and "admin or owner" in out.note  # the model can tell the user who approves
    approval = session.get(Approval, out.approval_id)
    assert approval is not None and approval.approver_roles == ["admin", "owner"]
    assert "outside availability" in approval.evidence["reasons"]
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(session, approval.id, Actor.person(people["Sanna"]), "approved")
    approvals.decide(session, approval.id, Actor.person(people["Helena"]), "approved")
    from mia.agents.dispatcher.models import CoverRequest

    request = session.exec(select(CoverRequest)).one()
    assert request.status == "asking"  # now Liisa is asked to confirm


def test_assign_refuses_absent_or_unknown(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Sanna"])
    found = tools.find_replacements(deps, kalasatama_input(deps), "c1")
    maria = deps_for(session, branch, people["Maria"])
    tools.record_absence(maria, tools.RecordAbsenceInput(date=tomorrow(deps)), "c0")
    with pytest.raises(LookupError, match="absent"):
        _assign(deps, found.visit.visit_id, people["Maria"])
    with pytest.raises(LookupError, match="staff"):
        _assign(deps, found.visit.visit_id, people["Helena"])
    with pytest.raises(LookupError):
        tools.assign_cover(deps, tools.AssignCoverInput(visit_id="x", candidate_id="y"), "c3")
    with pytest.raises(LookupError):
        tools.assign_cover(deps, tools.AssignCoverInput(visit_id=found.visit.visit_id), "c4")


def test_cleaner_cannot_assign(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    deps = deps_for(session, branch, people["Juha"])
    binding = next(b for b in tools.BINDINGS if b.tool_id == "dispatcher.assign_cover")
    out = call_tool(deps, binding, tools.AssignCoverInput(visit_id="x", candidate_id="y"), "c1")
    assert out["status"] == "denied"


def test_respond_without_request_is_invalid(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    deps = deps_for(session, branch, people["Aino"])
    binding = next(b for b in tools.BINDINGS if b.tool_id == "dispatcher.respond_to_cover")
    out = call_tool(deps, binding, tools.RespondToCoverInput(accept=True), "c1")
    assert out["status"] == "invalid"


def test_running_late_affects_the_morning() -> None:
    """Decided in code, not by the model: late with no part of day given means the morning."""
    day = dt.date(2026, 10, 5)
    late = tools.RecordAbsenceInput(date=day, reason="late")
    assert late.partial_day == "morning"
    assert tools.RecordAbsenceInput(
        date=day, reason="late", partial_day="afternoon"
    ).partial_day == ("afternoon")
    assert tools.RecordAbsenceInput(date=day, reason="sick").partial_day is None
