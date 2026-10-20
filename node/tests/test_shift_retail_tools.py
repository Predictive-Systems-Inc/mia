"""The shift supervisor's kiosk tools (D39): the roster from the owner's pattern, swaps, the time
correction, closed days, the retail incidents and the cover across kiosks. Negative tests first."""

import datetime as dt
from typing import Any

import pytest
from pydantic import BaseModel
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.inventory_manager import MANIFEST as INVENTORY
from mia.agents.inventory_manager import tools as inventory
from mia.agents.shift_supervisor import MANIFEST, alerts, cover, replies, tools
from mia.agents.shift_supervisor.rules import fmt_date
from mia.agents.shift_supervisor.tools import (
    AssignCoverInput,
    CheckInInput,
    CloseDayInput,
    CorrectTimesheetInput,
    FindReplacementsInput,
    GetMyVisitsInput,
    ReportProblemInput,
    RespondToCoverInput,
    RosterInput,
    SetRosterInput,
    ShiftIn,
    SwapShiftsInput,
)
from mia.chat.blocks import TextBlock
from mia.core import approvals, orgconfig, scheduling, store
from mia.core.models import (
    Actor,
    Approval,
    Branch,
    Event,
    Incident,
    Job,
    Leave,
    Location,
    Message,
    Person,
    SupplierOrder,
    Thread,
    Timesheet,
    Visit,
)
from mia.core.rbac import PermissionDenied
from mia.i18n import t
from mia.templates.retail.models import RetailClosure, RetailIngredient
from tests.conftest import RS_TODAY, Pin
from tests.test_data_standard_1_7 import (
    MONDAY,
    NOV_1,
    SATURDAY,
    TUESDAY,
    Ferinos,
    at,
    names_on,
    stall,
    visit_of,
)

BINDING = {b.tool_id: b for b in tools.BINDINGS}
NINE, FIVE_PM = dt.time(9), dt.time(17)


def deps_for(session: Session, person: Person, day: dt.date = RS_TODAY) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=day,
        lang=person.language or "en",
        manifest=MANIFEST,
    )


def call(
    session: Session, who: Person, tool: str, args: BaseModel, day: dt.date = RS_TODAY
) -> dict[str, Any]:
    return call_tool(deps_for(session, who, day), BINDING[f"{MANIFEST.id}.{tool}"], args, "t1")


def decide(session: Session, approval_id: str, who: Person, outcome: str) -> Approval:
    return approvals.decide(
        session, approval_id, Actor.person(who), outcome, stepped_up_at=approvals.utcnow()
    )


def agree_swap(session: Session, rs: Ferinos) -> Approval:
    """Ana asks Liza for Saturday, Liza says yes (both through tools.swap_shifts)."""
    ask = SwapShiftsInput(person_name="Liza", date=SATURDAY)
    assert tools.swap_shifts(deps_for(session, rs[1]["Ana"]), ask, "s1").status == "asked"
    out = tools.swap_shifts(deps_for(session, rs[1]["Liza"]), SwapShiftsInput(accept=True), "s2")
    assert out.status == "confirming"
    approval = session.get(Approval, out.approval_id)
    assert approval is not None
    return approval


def told(session: Session, who: Person) -> list[str]:
    """The shift supervisor's notifications to the person, oldest first."""
    rows = session.exec(
        select(Message)
        .join(Thread, col(Message.thread_id) == col(Thread.id))
        .where(Thread.person_id == who.id)
        .where(Message.agent_id == MANIFEST.id)
        .where(Message.role == "notification")
        .order_by(col(Message.id))
    ).all()
    return [m.text for m in rows]


# ---- negative tests ------------------------------------------------------------------------


def test_a_clerk_cannot_set_the_roster(session: Session, rs: Ferinos) -> None:
    shift = ShiftIn(person_id=rs[1]["Ana"].id, byday=["TU"], start=NINE, end=FIVE_PM)
    out = call(session, rs[1]["Ana"], "set_roster", SetRosterInput(shifts=[shift]))
    assert out["status"] == "denied"


def test_a_clerk_cannot_close_a_day(session: Session, rs: Ferinos) -> None:
    assert (
        call(session, rs[1]["Ana"], "close_day", CloseDayInput(date=MONDAY))["status"] == "denied"
    )


def test_a_supervisor_cannot_close_the_other_kiosk(session: Session, rs: Ferinos) -> None:
    with pytest.raises(PermissionDenied):
        tools.close_day(
            deps_for(session, rs[1]["Marites"]),
            CloseDayInput(date=MONDAY, location_name="Street stall"),
            "c",
        )


def test_a_supervisor_cannot_find_cover_for_the_other_kiosk(session: Session, rs: Ferinos) -> None:
    with pytest.raises(LookupError):
        tools.find_replacements(
            deps_for(session, rs[1]["Jun"]),
            FindReplacementsInput(visit_id=visit_of(session, rs[1]["Ana"], SATURDAY).id),
            "f",
        )


def test_the_cleaning_template_keeps_cover_in_the_branch(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings())
    visit = visit_of(session, rs[1]["Ana"], TUESDAY)
    data = tools.candidate_data(session, deps_for(session, rs[1]["Marites"]), visit)
    assert [c.name for c in data] == ["Liza"]


def test_a_clerk_reads_only_her_shifts(session: Session, rs: Ferinos) -> None:
    ana = deps_for(session, rs[1]["Ana"])
    assert set(tools.roster(ana, RosterInput(), "r").people) == {"Ana"}
    with pytest.raises(PermissionDenied):
        tools.get_my_visits(ana, GetMyVisitsInput(person_name="Liza"), "g")
    marites = deps_for(session, rs[1]["Marites"])
    assert set(tools.roster(marites, RosterInput(), "r2").people) == {"Ana", "Liza"}


def test_the_incident_kinds_follow_the_template(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    ana = deps_for(session, rs[1]["Ana"])
    locked = ReportProblemInput(kind="cannot_access", text="sarado")
    assert tools.report_site_problem(ana, locked, "p1").reason == "kind"
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings())
    stove = ReportProblemInput(kind="equipment", text="the stove")
    assert tools.report_site_problem(ana, stove, "p2").reason == "kind"
    assert session.exec(select(Incident).where(Incident.text == "sarado")).first() is None


def test_a_cover_override_needs_the_owner(session: Session, rs: Ferinos) -> None:
    visit = visit_of(session, rs[1]["Ana"], TUESDAY)
    out = tools.assign_cover(
        deps_for(session, rs[1]["Marites"], MONDAY),
        AssignCoverInput(visit_id=visit.id, candidate_id=rs[1]["Pao"].id),
        "a",
    )
    approval = session.get(Approval, out.approval_id)
    assert approval is not None
    assert (approval.approver_roles, approval.channel, approval.evidence["reasons"]) == (
        ["admin", "owner"],
        "app_only",
        ["outside availability", "over the weekly hour limit"],
    )
    with pytest.raises(approvals.ApprovalError):
        decide(session, approval.id, rs[1]["Marites"], "approved")
    decide(session, approval.id, rs[1]["Rosa"], "approved")
    request = cover.open_request(session, rs[1]["Pao"])
    assert request is not None and request.visit_id == visit.id


def test_a_covering_clerk_sees_only_his_shift_at_the_other_kiosk(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    visit = visit_of(session, rs[1]["Ana"], TUESDAY)
    approval = tools.assign_cover(
        deps_for(session, rs[1]["Marites"], MONDAY),
        AssignCoverInput(visit_id=visit.id, candidate_id=rs[1]["Pao"].id),
        "a",
    ).approval_id
    assert approval is not None
    decide(session, approval, rs[1]["Rosa"], "approved")
    rs_pin(at(MONDAY, 12))
    pao_monday = deps_for(session, rs[1]["Pao"], MONDAY)
    tools.respond_to_cover(pao_monday, RespondToCoverInput(accept=True), "y")
    rs_pin(at(TUESDAY, 8, 50))
    checked = tools.check_in(deps_for(session, rs[1]["Pao"], TUESDAY), CheckInInput(), "c")
    assert checked.visit is not None and checked.visit.visit_id == visit.id
    week = tools.roster(deps_for(session, rs[1]["Pao"], MONDAY), RosterInput(), "r").people
    assert set(week) == {"Pao"}
    assert [i.location for i in week["Pao"] if i.date == TUESDAY] == ["Mall kiosk"]


def test_a_pattern_outside_opening_hours_is_refused(session: Session, rs: Ferinos) -> None:
    n = len(session.exec(select(Job)).all())
    shift = ShiftIn(person_id=rs[1]["Pao"].id, byday=["MO"], start=dt.time(5), end=dt.time(14))
    out = tools.set_roster(
        deps_for(session, rs[1]["Rosa"]),
        SetRosterInput(shifts=[shift], location_name="Street stall"),
        "s",
    )
    assert (out.status, out.reason, out.outside, len(session.exec(select(Job)).all())) == (
        "invalid",
        "outside_hours",
        ["Pao MO"],
        n,
    )


def test_an_approved_timesheet_needs_head_staff(session: Session, rs: Ferinos) -> None:
    row = session.exec(
        select(Timesheet)
        .where(Timesheet.person_id == rs[1]["Ana"].id)
        .where(Timesheet.date == RS_TODAY - dt.timedelta(days=1))
    ).one()
    late = CorrectTimesheetInput(date=row.date, end=dt.time(17, 30))
    assert tools.correct_timesheet(deps_for(session, rs[1]["Ana"]), late, "t").reason == "approved"
    head = late.model_copy(update={"person_name": "Ana"})
    tools.correct_timesheet(deps_for(session, rs[1]["Marites"]), head, "t2")
    session.refresh(row)
    assert (row.status, row.source, row.minutes, row.entered_by) == (
        "draft",
        "correction",
        510,
        rs[1]["Marites"].id,
    )


def test_the_approved_swap_is_the_one_asked(session: Session, rs: Ferinos) -> None:
    mine = visit_of(session, rs[1]["Ana"], SATURDAY)
    theirs = visit_of(session, rs[1]["Liza"], SATURDAY)
    approval = agree_swap(session, rs)
    assert (approval.evidence["mine"], approval.evidence["theirs"], approval.expires_at) == (
        mine.id,
        theirs.id,
        mine.planned_start,
    )
    for clerk in ("Ana", "Liza"):  # the requester never decides
        with pytest.raises(approvals.ApprovalError):
            approvals.decide(session, approval.id, Actor.person(rs[1][clerk]), "approved")
    approvals.decide(session, approval.id, Actor.person(rs[1]["Marites"]), "approved")
    session.refresh(mine)
    session.refresh(theirs)
    assert (names_on(session, mine), names_on(session, theirs)) == (["Liza"], ["Ana"])


def test_a_swap_whose_shift_changed_is_refused(session: Session, rs: Ferinos) -> None:
    approval = agree_swap(session, rs)
    theirs = visit_of(session, rs[1]["Liza"], SATURDAY)
    scheduling.unassign(session, Actor.person(rs[1]["Marites"]), theirs, rs[1]["Liza"])
    with pytest.raises(LookupError):
        approvals.decide(session, approval.id, Actor.person(rs[1]["Marites"]), "approved")


def test_a_booking_at_the_other_kiosk_makes_a_swap_an_override(
    session: Session, rs: Ferinos
) -> None:
    pao_saturday = visit_of(session, rs[1]["Pao"], SATURDAY)  # 06:00 to 15:00 at the stall
    both = [rs[1]["Pao"].id, rs[1]["Liza"].id]
    store.update(
        session, pao_saturday, {"assigned_person_ids": both}, Actor.system(stall(session).id)
    )
    ask = SwapShiftsInput(person_name="Liza", date=SATURDAY)
    tools.swap_shifts(deps_for(session, rs[1]["Ana"]), ask, "s1")
    out = tools.swap_shifts(deps_for(session, rs[1]["Liza"]), SwapShiftsInput(accept=True), "s2")
    approval = session.get(Approval, out.approval_id)
    assert approval is not None
    booked = f"{rs[1]['Liza'].name}: already booked at that time"
    assert (out.status, booked in approval.evidence["reasons"]) == ("override", True)


def test_a_leave_approved_after_the_ask_refuses_the_swap(session: Session, rs: Ferinos) -> None:
    approval = agree_swap(session, rs)
    liza = rs[1]["Liza"]
    leave = Leave(
        branch_id=liza.branch_id,
        person_id=liza.id,
        kind="vacation",
        start_date=SATURDAY,
        end_date=SATURDAY,
        days=1,
        status="approved",
        reason="",
    )
    store.insert(session, leave, Actor.system(liza.branch_id))
    with pytest.raises(LookupError):
        approvals.decide(session, approval.id, Actor.person(rs[1]["Marites"]), "approved")


def test_a_clerk_booked_at_the_other_kiosk_is_a_roster_clash(session: Session, rs: Ferinos) -> None:
    pao = rs[1]["Pao"]
    mall_saturday = visit_of(session, rs[1]["Ana"], SATURDAY)  # 09:00 to 17:00 at the mall
    store.update(session, mall_saturday, {"assigned_person_ids": [pao.id]}, Actor.system(rs[0].id))
    shift = ShiftIn(person_id=pao.id, byday=["SA"], start=dt.time(6), end=dt.time(15))
    out = tools.set_roster(
        deps_for(session, rs[1]["Rosa"]),
        SetRosterInput(shifts=[shift], location_name="Street stall"),
        "s",
    )
    clash = next(c for c in out.clashes if c.reason == "already booked at that time")
    assert (out.status, clash.person, clash.dates) == ("ok", pao.name, [SATURDAY])
    job = session.exec(select(Job).where(Job.recurrence == "FREQ=WEEKLY;BYDAY=SA")).one()
    stall_saturday = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == SATURDAY)
    ).one()
    assert (stall_saturday.status, stall_saturday.assigned_person_ids) == ("unfilled", [])


def test_a_start_correction_on_shift_does_not_check_the_clerk_out(
    session: Session, rs: Ferinos
) -> None:
    ana = deps_for(session, rs[1]["Ana"])
    assert tools.check_in(ana, CheckInInput(), "c").status == "ok"  # 10:00, the 09:00 shift
    early = CorrectTimesheetInput(start=dt.time(8, 45))
    assert tools.correct_timesheet(ana, early, "t").reason == "in_progress"
    assert visit_of(session, rs[1]["Ana"], RS_TODAY).status == "in_progress"


def test_a_clerk_naming_an_unknown_kiosk_is_denied(session: Session, rs: Ferinos) -> None:
    with pytest.raises(PermissionDenied):
        tools.close_day(
            deps_for(session, rs[1]["Ana"]),
            CloseDayInput(date=MONDAY, location_name="Nowhere"),
            "c",
        )


def test_a_closed_day_refuses_a_past_date(session: Session, rs: Ferinos) -> None:
    out = tools.close_day(
        deps_for(session, rs[1]["Marites"]),
        CloseDayInput(date=RS_TODAY - dt.timedelta(days=1)),
        "c",
    )
    assert (out.status, out.reason) == ("invalid", "past")


def test_a_full_kiosk_name_matches_its_location(session: Session, rs: Ferinos) -> None:
    rows = session.exec(select(Location)).all()
    for name in ("Mall kiosk", "Street stall", "mall kiosk"):
        found = [loc.name for loc in rows if tools._location_matches(loc, name)]
        assert found == [name.capitalize()], name


CLEANING_CALLS: list[tuple[str, BaseModel]] = [
    (
        "set_roster",
        SetRosterInput(shifts=[ShiftIn(person_id="p", byday=["TU"], start=NINE, end=FIVE_PM)]),
    ),
    ("close_day", CloseDayInput(date=MONDAY)),
    ("swap_shifts", SwapShiftsInput(person_name="Liza", date=SATURDAY)),
    ("correct_timesheet", CorrectTimesheetInput(end=FIVE_PM)),
    ("roster", RosterInput()),
]


@pytest.mark.parametrize(("tool", "args"), CLEANING_CALLS, ids=[c[0] for c in CLEANING_CALLS])
def test_a_cleaning_org_is_not_offered_the_kiosk_tools(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, tool: str, args: BaseModel
) -> None:
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings())
    n = len(session.exec(select(Event)).all())
    out = getattr(tools, tool)(deps_for(session, rs[1]["Marites"]), args, "c")
    assert (out.status, out.reason) == ("invalid", "not_offered")
    assert len(session.exec(select(Event)).all()) == n


def test_a_future_end_on_shift_does_not_check_the_clerk_out(session: Session, rs: Ferinos) -> None:
    ana = deps_for(session, rs[1]["Ana"])
    assert tools.check_in(ana, CheckInInput(), "c").status == "ok"  # 10:00, the 09:00 shift
    later = CorrectTimesheetInput(end=dt.time(21))
    assert tools.correct_timesheet(ana, later, "t").reason == "in_progress"
    assert visit_of(session, rs[1]["Ana"], RS_TODAY).status == "in_progress"


def test_an_end_before_the_check_in_writes_nothing(session: Session, rs: Ferinos) -> None:
    ana = deps_for(session, rs[1]["Ana"])
    assert tools.check_in(ana, CheckInInput(), "c").status == "ok"  # 10:00
    early = CorrectTimesheetInput(end=dt.time(9, 30))
    assert tools.correct_timesheet(ana, early, "t").reason == "end_before_start"
    assert visit_of(session, rs[1]["Ana"], RS_TODAY).status == "in_progress"
    sheets = select(Timesheet).where(Timesheet.person_id == rs[1]["Ana"].id)
    assert session.exec(sheets.where(Timesheet.date == RS_TODAY)).first() is None


def _swap_said(session: Session, rs: Ferinos, key: str) -> dict[str, list[str]]:
    """Each clerk's notifications after the ask that are the key's text naming the other."""
    mine = visit_of(session, rs[1]["Ana"], SATURDAY)
    out = {}
    for who, other in (("Ana", "Liza"), ("Liza", "Ana")):
        lang = rs[1][who].language
        params = cover._visit_text(session, mine, rs[0].timezone, lang)
        text = t(key, lang, **params, name=other)
        out[who] = [m for m in told(session, rs[1][who]) if m == text]
    return out


def test_a_rejected_swap_tells_both_clerks(session: Session, rs: Ferinos) -> None:
    approval = agree_swap(session, rs)
    decide(session, approval.id, rs[1]["Marites"], "rejected")
    said = _swap_said(session, rs, "shift.swap.rejected")
    assert (len(said["Ana"]), len(said["Liza"])) == (1, 1)


def test_a_swap_tapped_after_its_deadline_is_expired_and_told_once(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    approval = agree_swap(session, rs)
    session.commit()
    now = rs_pin(at(SATURDAY, 9, 5))
    with pytest.raises(approvals.ApprovalError, match="expired"):
        decide(session, approval.id, rs[1]["Marites"], "approved")
    assert alerts.close_undecided_swaps(session, now) == 0
    mine = visit_of(session, rs[1]["Ana"], SATURDAY)
    assert names_on(session, mine) == ["Ana"]  # no swap written
    said = _swap_said(session, rs, "shift.swap.expired")
    assert (len(said["Ana"]), len(said["Liza"])) == (1, 1)


def test_a_swap_expired_by_the_due_work_tells_both_once(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    approval = agree_swap(session, rs)
    session.commit()
    assert alerts.close_undecided_swaps(session, rs_pin(at(SATURDAY, 9, 5))) == 1
    with pytest.raises(approvals.ApprovalError):
        decide(session, approval.id, rs[1]["Marites"], "approved")
    said = _swap_said(session, rs, "shift.swap.expired")
    assert (len(said["Ana"]), len(said["Liza"])) == (1, 1)


def test_a_refused_swap_approval_tells_both_clerks(session: Session, rs: Ferinos) -> None:
    approval = agree_swap(session, rs)
    approvals.close_refused(session, approval.id, Actor.person(rs[1]["Marites"]), "changed")
    said = _swap_said(session, rs, "shift.swap.gone")
    assert (len(said["Ana"]), len(said["Liza"])) == (1, 1)


def test_a_roster_skips_a_closed_date(session: Session, rs: Ferinos) -> None:
    pao = rs[1]["Pao"]
    shift = ShiftIn(person_id=pao.id, byday=["SU"], start=dt.time(7), end=dt.time(15))
    out = tools.set_roster(
        deps_for(session, rs[1]["Rosa"]),
        SetRosterInput(shifts=[shift], location_name="Street stall"),
        "s",
    )
    assert out.status == "ok"
    on_nov_1 = session.exec(
        select(Visit)
        .where(Visit.branch_id == stall(session).id)
        .where(Visit.date == NOV_1)
        .where(Visit.status != "cancelled")  # the seed's shift, cancelled by the closure
    ).all()
    assert [(v.status, v.assigned_person_ids) for v in on_nov_1] == [("unfilled", [])]


# ---- the flows -----------------------------------------------------------------------------


def test_a_closed_day_cancels_the_shifts_and_tells_the_clerks(
    session: Session, rs: Ferinos
) -> None:
    ana, liza = (
        visit_of(session, rs[1]["Ana"], SATURDAY),
        visit_of(session, rs[1]["Liza"], SATURDAY),
    )
    marites = deps_for(session, rs[1]["Marites"])
    out = tools.close_day(marites, CloseDayInput(date=SATURDAY, reason="fiesta"), "c")
    session.refresh(ana)
    session.refresh(liza)
    assert (out.status, out.cancelled, ana.status, liza.status) == (
        "ok",
        2,
        "cancelled",
        "cancelled",
    )
    assert session.exec(select(RetailClosure).where(RetailClosure.date == SATURDAY)).one()
    lang = rs[1]["Ana"].language
    assert told(session, rs[1]["Ana"])[-1] == t(
        "shift.closed.told", lang, location="Mall kiosk", date=fmt_date(SATURDAY.isoformat(), lang)
    )
    again = tools.close_day(marites, CloseDayInput(date=SATURDAY), "c2")
    assert again.reason == "already"


def test_a_new_pattern_replaces_the_clerks_job(session: Session, rs: Ferinos) -> None:
    shift = ShiftIn(
        person_id=rs[1]["Ana"].id,
        byday=["TU", "WE", "TH", "FR", "SA", "SU"],
        start=dt.time(10),
        end=dt.time(18),
    )
    out = tools.set_roster(deps_for(session, rs[1]["Rosa"]), SetRosterInput(shifts=[shift]), "s")
    assert (out.status, out.jobs, out.clashes) == ("ok", ["Mid Ana"], [])
    assert out.planned > 0
    week = scheduling.week(session, rs[0].id, SATURDAY, person_id=rs[1]["Ana"].id)
    starts = [(v.planned_start, v.status) for v in week if v.date == SATURDAY]
    assert starts == [(at(SATURDAY, 9), "cancelled"), (at(SATURDAY, 10), "planned")]
    old = session.exec(select(Job).where(Job.name == "Opening Ana")).one()
    assert old.recurrence.endswith(";UNTIL=" + (RS_TODAY - dt.timedelta(days=1)).strftime("%Y%m%d"))
    again = tools.set_roster(deps_for(session, rs[1]["Rosa"]), SetRosterInput(shifts=[shift]), "s2")
    assert (again.jobs, again.planned) == (["Mid Ana"], 0)  # an equal job is kept


def test_an_incident_without_a_shift_attaches_to_the_kiosks_open_shift(
    session: Session, rs: Ferinos
) -> None:
    report = ReportProblemInput(kind="customer", text="a customer is shouting")
    out = tools.report_site_problem(deps_for(session, rs[1]["Marites"]), report, "p")
    row = session.get(Incident, out.problem_id)
    assert row is not None and row.visit_id == visit_of(session, rs[1]["Ana"], RS_TODAY).id


def test_a_missed_delivery_names_the_open_order(session: Session, rs: Ferinos) -> None:
    marites, rosa, ana = rs[1]["Marites"], rs[1]["Rosa"], rs[1]["Ana"]
    eggs = session.exec(select(RetailIngredient).where(RetailIngredient.name == "Eggs")).one()
    branch = session.get(Branch, marites.branch_id)
    assert branch is not None
    order_deps = AgentDeps(
        session=session,
        actor=Actor.person(marites).as_agent(INVENTORY.roles.agent_role),
        person=marites,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=RS_TODAY,
        lang="en",
        manifest=INVENTORY,
    )
    args = inventory.DraftOrderInput(
        supplier="Aling Nena", lines=[inventory.LineIn(ingredient_id=eggs.id, quantity=10)]
    )
    binding = next(b for b in inventory.BINDINGS if b.tool_id == inventory.DRAFT_ORDER)
    asked = call_tool(order_deps, binding, args, "o1")
    decide(session, str(asked["approval_id"]), rosa, "approved")
    order = session.exec(select(SupplierOrder).where(SupplierOrder.status == "approved")).one()
    assert tools.open_order(session, branch.id) == ("Aling Nena", order.business_date)
    report = ReportProblemInput(kind="no_delivery", text="walang dumating na itlog")
    tools.report_site_problem(deps_for(session, ana), report, "p")
    lang = rosa.language
    named = t(
        "retail.alert.order",
        lang,
        supplier="Aling Nena",
        date=fmt_date(order.business_date.isoformat(), lang),
    )
    assert told(session, rosa)[-1] == t(
        "retail.alert.no_delivery",
        lang,
        name=ana.name,
        location="Mall kiosk",
        text="walang dumating na itlog",
        order=named,
    )
    assert told(session, ana) == []  # the reporter is never paged about her own report


def test_an_incident_on_a_closed_day_is_told_and_not_written(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    rs_pin(at(NOV_1, 10))  # the seed closes the Street stall on All Saints' Day
    n = len(session.exec(select(Incident)).all())
    report = ReportProblemInput(kind="equipment", text="the freezer")
    out = tools.report_site_problem(deps_for(session, rs[1]["Jun"], NOV_1), report, "p")
    assert (out.status, out.problem_id, len(session.exec(select(Incident)).all())) == (
        "ok",
        None,
        n,
    )
    assert told(session, rs[1]["Rosa"])
    words = replies.tool_reply("report_site_problem", out.model_dump(mode="json"), "fil")
    assert [b.text for b in words if isinstance(b, TextBlock)] == [
        t("retail.problem.reported", "fil", location=stall(session).name)
    ]
