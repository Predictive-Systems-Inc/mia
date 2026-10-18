import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.hr_officer import MANIFEST, calendar, tools
from mia.agents.hr_officer.models import Contract, Leave, Payslip
from mia.agents.hr_officer.tools import (
    CertificateInput,
    ContributionsInput,
    HolidayInput,
    HoursInput,
    NextPaydayInput,
    PersonInput,
    RequestLeaveInput,
    SetContractInput,
)
from mia.core import approvals, events
from mia.core.models import Actor, Approval, Branch, Event, Message, Person
from mia.core.rbac import PermissionDenied

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
BINDING = {b.tool_id: b for b in tools.BINDINGS}


def today() -> dt.date:
    return dt.datetime.now(MNL).date()


def deps_for(session: Session, person: Person) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=today(),
        lang=person.language or "en",
        manifest=MANIFEST,
    )


def last_fortnight(person_id: str | None = None) -> HoursInput:
    return HoursInput(
        start=today() - dt.timedelta(days=14), end=today() - dt.timedelta(days=1),
        person_id=person_id,
    )  # fmt: skip


def file_leave(session: Session, person: Person, call_id: str = "l1") -> dict[str, object]:
    args = RequestLeaveInput(
        kind="vacation", start=today() + dt.timedelta(days=7), end=today() + dt.timedelta(days=8)
    )
    return call_tool(deps_for(session, person), BINDING[tools.REQUEST_LEAVE], args, call_id)


def decide(session: Session, approval_id: object, decider: Person, outcome: str) -> Approval:
    return approvals.decide(session, str(approval_id), Actor.person(decider), outcome)


def notifications(session: Session, person: Person) -> list[Message]:
    rows = session.exec(select(Message).where(Message.agent_id == MANIFEST.id)).all()
    return [m for m in rows if m.role == "notification" and m.branch_id == person.branch_id]


def test_the_bindings_are_the_manifest_tools() -> None:
    assert {b.tool_id for b in tools.BINDINGS} == {t.id for t in MANIFEST.tools}


def test_a_clerk_asks_their_hours_this_cutoff(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = tools.hours(deps_for(session, people["Ana"]), last_fortnight(), "h1")
    sheets = 14 - 2  # a fortnight less two Monday rest days
    assert out.days == sheets and out.person_id == people["Ana"].id
    assert out.regular + out.holiday == sheets * 480
    assert (out.overtime, out.night, out.rest_day) == (0, 0, 0)


def test_the_late_shift_shows_overtime_and_night(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = tools.hours(deps_for(session, people["Liza"]), last_fortnight(), "h1")
    assert out.night == 90  # 22:00 to 23:30 on the latest day
    assert out.overtime in (150, 0)  # 150 unless that day is a holiday (paid wholly as one)


def test_a_clerk_cannot_read_another_persons_hours(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = call_tool(
        deps_for(session, people["Ana"]),
        BINDING[f"{MANIFEST.id}.hours"],
        last_fortnight(people["Liza"].id),
        "h1",
    )
    assert out["status"] == "denied"


def test_a_supervisor_reads_hours_of_their_branch_only(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    marites = deps_for(session, people["Marites"])
    assert tools.hours(marites, last_fortnight(people["Ana"].id), "h1").days == 12
    with pytest.raises(PermissionDenied):  # Pao works at the stall
        tools.hours(marites, last_fortnight(people["Pao"].id), "h2")
    with pytest.raises(PermissionDenied):  # the branch read is for hours only
        tools.thirteenth_month(marites, PersonInput(person_id=people["Ana"].id), "t1")
    owner = deps_for(session, people["Rosa"])
    assert tools.hours(owner, last_fortnight(people["Pao"].id), "h3").days > 0


def test_an_unknown_person_is_invalid_for_the_owner(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    with pytest.raises(LookupError):
        tools.hours(deps_for(session, people["Rosa"]), last_fortnight("nobody"), "h1")
    with pytest.raises(ValidationError):
        HoursInput(start=today(), end=today() - dt.timedelta(days=1))


def test_payday_is_the_next_one_after_the_cutoff(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = tools.next_payday(deps_for(session, people["Ana"]), NextPaydayInput(), "p1")
    assert out.pay_date >= today()
    assert (out.cutoff_start, out.cutoff_end) in (
        calendar.cutoff(today()),
        calendar.previous_cutoff(today()),
    )
    holidays = tools._holidays()
    assert out.pay_date == calendar.payday(out.cutoff_end, 5, holidays)
    deps = deps_for(session, people["Ana"])
    deps.today = dt.date(2026, 10, 19)  # the 1st to 15th cutoff pays on the 20th
    out = tools.next_payday(deps, NextPaydayInput(), "p2")
    assert (out.pay_date, out.cutoff_end) == (dt.date(2026, 10, 20), dt.date(2026, 10, 15))
    deps.today = dt.date(2026, 10, 21)
    assert tools.next_payday(deps, NextPaydayInput(), "p3").pay_date == dt.date(2026, 11, 5)


def test_thirteenth_month_is_a_twelfth_of_basic_earned(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    ana = people["Ana"]
    slips = session.exec(select(Payslip).where(Payslip.person_id == ana.id)).all()
    earned = sum(
        line["amount"]
        for s in slips
        if s.cutoff_end.year == today().year
        for line in s.lines
        if line["kind"] == "regular"
    )
    out = tools.thirteenth_month(deps_for(session, ana), PersonInput(), "t1")
    assert (out.earned_basic, out.estimate, out.paid_in) == (earned, (earned + 6) // 12, 12)
    assert out.currency == "PHP"


def test_contributions_come_from_the_last_payslip(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    ana = people["Ana"]
    last = max(
        session.exec(select(Payslip).where(Payslip.person_id == ana.id)).all(),
        key=lambda s: s.cutoff_start,
    )
    out = tools.last_contributions(deps_for(session, ana), ContributionsInput(), "c1")
    assert out.sss == last.deductions[0]["amount"] and out.cutoff_end == last.cutoff_end
    assert out.philhealth is None  # not on the seeded payslip
    only = tools.last_contributions(
        deps_for(session, ana), ContributionsInput(which="pagibig"), "c2"
    )
    assert only.sss is None


def test_a_clerk_cannot_read_another_persons_payslip(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    other = PersonInput(person_id=people["Liza"].id)
    for name in ("thirteenth_month", "last_contributions", "balance", "resend_payslip"):
        args = (
            ContributionsInput(person_id=other.person_id) if name == "last_contributions" else other
        )
        out = call_tool(
            deps_for(session, people["Ana"]), BINDING[f"{MANIFEST.id}.{name}"], args, name
        )
        assert out["status"] == "denied", name
    assert notifications(session, people["Liza"]) == []


def test_a_leave_request_waits_for_head_staff(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = file_leave(session, people["Ana"])
    assert out["status"] == "approval_required"
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None and approval.status == "pending"
    assert approval.type == tools.REQUEST_LEAVE
    assert approval.approver_roles == ["supervisor", "owner", "admin"]
    assert approval.channel == "any"  # not money: a supervisor can tap it in chat
    assert approval.evidence["input"]["kind"] == "vacation"
    assert session.exec(select(Leave).where(Leave.approval_id == approval.id)).all() == []
    with pytest.raises(LookupError):  # the body never runs without the approval
        tools.request_leave(
            deps_for(session, people["Ana"]),
            RequestLeaveInput(kind="sick", start=today(), end=today()),
            "l2",
        )


def test_an_approved_leave_tells_the_requester_and_updates_the_balance(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    ana = people["Ana"]
    before = tools.balance(deps_for(session, ana), PersonInput(), "b1")
    out = file_leave(session, ana)
    decide(session, out["approval_id"], people["Marites"], "approved")
    row = session.exec(select(Leave).where(Leave.approval_id == out["approval_id"])).one()
    contract = session.exec(select(Contract).where(Contract.person_id == ana.id)).one()
    days = calendar.leave_days(row.start_date, row.end_date, contract.rest_day, tools._holidays())
    assert (row.status, row.kind, row.person_id, row.days) == ("approved", "vacation", ana.id, days)
    assert session.exec(
        select(Event).where(Event.action == "hr.leave_approved").where(Event.entity_id == row.id)
    ).one()
    (note,) = notifications(session, ana)
    assert note.sender_id == "system" and row.start_date.isoformat() in note.text
    after = tools.balance(deps_for(session, ana), PersonInput(), "b2")
    assert after.used == before.used + days
    assert after.left == max(0, after.total - after.used)
    deps = deps_for(session, ana)
    deps.approved = {str(out["approval_id"])}
    again = tools.request_leave(
        deps, RequestLeaveInput(kind="sick", start=today(), end=today()), "x"
    )
    assert again.leave_id == row.id  # one leave per approval


def test_a_supervisor_cannot_approve_their_own_leave(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = file_leave(session, people["Marites"])
    with pytest.raises(approvals.ApprovalError):
        decide(session, out["approval_id"], people["Marites"], "approved")
    assert session.exec(select(Leave).where(Leave.approval_id == out["approval_id"])).all() == []


def test_a_clerk_cannot_approve_a_leave(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = file_leave(session, people["Ana"])
    with pytest.raises(approvals.ApprovalError):
        decide(session, out["approval_id"], people["Liza"], "approved")


def test_the_approved_leave_is_the_one_requested(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    ana = people["Ana"]
    out = file_leave(session, ana, "seen")
    longer = RequestLeaveInput(
        kind="unpaid", start=today() + dt.timedelta(days=1), end=today() + dt.timedelta(days=30)
    )
    events.emit(
        session,
        "tool.called",
        ("tool", tools.REQUEST_LEAVE),
        {"input": longer.model_dump(mode="json")},
        {"output": {}},
        deps_for(session, ana).actor,
        tool_call_id="seen",
    )  # a forged later event with the same call id is ignored
    approval = decide(session, out["approval_id"], people["Rosa"], "approved")
    row = session.exec(select(Leave).where(Leave.approval_id == approval.id)).one()
    assert row.kind == "vacation" == approval.evidence["input"]["kind"]
    assert row.end_date.isoformat() == approval.evidence["input"]["end"]


def test_a_rejected_leave_writes_nothing_and_tells_the_requester(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    ana = people["Ana"]
    out = file_leave(session, ana)
    decide(session, out["approval_id"], people["Marites"], "rejected")
    assert session.exec(select(Leave).where(Leave.approval_id == out["approval_id"])).all() == []
    assert session.exec(select(Event).where(Event.action == "hr.leave_rejected")).one()
    (note,) = notifications(session, ana)
    assert note.sender_id == "system"


def test_the_balance_counts_this_service_years_leave(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    ana = tools.balance(deps_for(session, people["Ana"]), PersonInput(), "b1")
    assert (ana.total, ana.used, ana.left) == (5, 0, 5)  # over a year, no leave taken
    liza = tools.balance(deps_for(session, people["Liza"]), PersonInput(), "b2")
    assert liza.used == 2 and liza.left == max(0, liza.total - 2)  # the seeded vacation


def test_holiday_pay_question_reads_the_calendar(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    deps = deps_for(session, people["Ana"])
    christmas = tools.holiday(deps, HolidayInput(day=dt.date(2026, 12, 25)), "d1")
    assert (christmas.kind, christmas.rate_percent, christmas.name) == (
        "regular",
        200,
        "Christmas Day",
    )
    assert tools.holiday(deps, HolidayInput(day=dt.date(2026, 11, 1)), "d2").rate_percent == 130
    plain = tools.holiday(deps, HolidayInput(day=dt.date(2026, 10, 20)), "d3")
    assert (plain.kind, plain.rate_percent, plain.name) == ("none", 100, None)


def test_a_payslip_is_resent(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    ana = people["Ana"]
    out = tools.resend_payslip(deps_for(session, ana), PersonInput(), "r1")
    last = max(
        session.exec(select(Payslip).where(Payslip.person_id == ana.id)).all(),
        key=lambda s: s.cutoff_start,
    )
    assert (out.payslip_id, out.lines, out.net) == (last.id, last.lines, last.net)
    (note,) = notifications(session, ana)
    assert note.id == out.message_id and note.sender_id == "system"
    assert last.cutoff_start.isoformat() in note.text


def test_the_owner_gets_a_certificate_text(session: Session, ferinos: Ferinos) -> None:
    kiosk, people = ferinos
    ana = people["Ana"]
    out = tools.certificate_text(
        deps_for(session, people["Rosa"]), CertificateInput(person_id=ana.id), "e1"
    )
    for part in (ana.name, "Clerk", kiosk.name, "April 7, 2025", people["Rosa"].name):
        assert part in out.text
    assert session.exec(select(Event).where(Event.action == "hr.certificate_issued")).one()


def test_a_clerk_cannot_ask_a_certificate(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    for name in ("Ana", "Marites"):
        out = call_tool(
            deps_for(session, people[name]),
            BINDING[f"{MANIFEST.id}.certificate_text"],
            CertificateInput(person_id=people["Liza"].id),
            "e1",
        )
        assert out["status"] == "denied", name


def test_the_owner_sets_a_contract_and_a_supervisor_cannot(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    ana = people["Ana"]
    args = SetContractInput(
        person_id=ana.id,
        employment_type="regular",
        daily_rate=65000,
        currency="PHP",
        rest_day=0,
        start_date=dt.date(2025, 4, 7),
        position="Senior clerk",
    )
    binding = BINDING[f"{MANIFEST.id}.set_contract"]
    assert (
        call_tool(deps_for(session, people["Marites"]), binding, args, "s1")["status"] == "denied"
    )
    out = tools.set_contract(deps_for(session, people["Rosa"]), args, "s2")
    contract = session.exec(select(Contract).where(Contract.person_id == ana.id)).one()
    assert (contract.id, contract.daily_rate, contract.position) == (
        out.contract_id,
        65000,
        "Senior clerk",
    )
    assert contract.set_by == people["Rosa"].id
    event = session.exec(select(Event).where(Event.action == "hr.contract_set")).one()
    assert "65000" not in str(event.after)  # the rate stays off the chain
