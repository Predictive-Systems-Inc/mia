"""The hr officer's tools on the Ferino's seed, pinned to TODAY so no test reads the wall
clock (anniversaries, cutoffs and holidays fall on known days)."""

import datetime as dt
import importlib
from collections.abc import Iterator
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlmodel import Session, col, select

from mia.agents.base import SENSITIVE_KEEP, AgentDeps, call_tool
from mia.agents.hr_officer import MANIFEST, tools
from mia.agents.hr_officer.models import Contract, Leave, Payslip
from mia.agents.hr_officer.tools import (
    CertificateInput,
    ContributionsInput,
    HolidayInput,
    HoursInput,
    LeaveRefused,
    NextPaydayInput,
    OwnInput,
    PersonInput,
    RequestLeaveInput,
    SetContractInput,
)
from mia.core import approvals, events, orgconfig, people
from mia.core.models import Actor, Approval, Branch, Event, Message, Person, Thread
from mia.core.money import format_money
from mia.core.rbac import PermissionDenied
from mia.settings import get_settings
from tests.conftest import CLOCK_USERS

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
BINDING = {b.tool_id: b for b in tools.BINDINGS}
# A Monday (the Mall kiosk's rest day): the 1st to 15th cutoff pays tomorrow, no holiday in
# the fortnight before, Ana (from 7 April 2025) is past a year, Liza (2 March 2026) is not.
TODAY = dt.date(2026, 10, 19)
NEXT_TUESDAY, NEXT_WEDNESDAY, NEXT_MONDAY = (TODAY + dt.timedelta(days=n) for n in (8, 9, 7))


def day(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


@pytest.fixture
def hr(monkeypatch: pytest.MonkeyPatch, session: Session) -> Iterator[Ferinos]:
    """The Ferino's seed on TODAY with the clock at 10:00 Manila that day (it keeps running),
    everyone set to English."""
    from mia.templates.retail import seed as retail_seed

    start = dt.datetime.now(dt.UTC)
    at = dt.datetime.combine(TODAY, dt.time(10), MNL).astimezone(dt.UTC)

    def now() -> dt.datetime:
        return at + (dt.datetime.now(dt.UTC) - start)

    for name in CLOCK_USERS:
        monkeypatch.setattr(importlib.import_module(name), "utcnow", now)
    with monkeypatch.context() as m:
        m.setenv("MIA_ORG", "ferinos")
        get_settings.cache_clear()
        orgconfig.load.cache_clear()
        kiosk = retail_seed.seed(session, today=TODAY)
        # The seed speaks Filipino; the tests read English replies (their literals).
        for person in session.exec(select(Person)).all():
            people.set_language(session, Actor.system(kiosk.id), person, "en")
        session.commit()
        yield kiosk, {p.name.split()[0]: p for p in session.exec(select(Person)).all()}
    get_settings.cache_clear()
    orgconfig.load.cache_clear()


def deps_for(session: Session, person: Person) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=TODAY,
        lang=person.language or "en",
        manifest=MANIFEST,
    )


def last_fortnight(person_id: str | None = None) -> HoursInput:
    return HoursInput(start=day(-14), end=day(-1), person_id=person_id)


def leave(start: dt.date = NEXT_TUESDAY, end: dt.date = NEXT_WEDNESDAY) -> RequestLeaveInput:
    return RequestLeaveInput(kind="vacation", start=start, end=end)


def file_leave(
    session: Session, person: Person, call_id: str = "l1", args: RequestLeaveInput | None = None
) -> dict[str, object]:
    deps = deps_for(session, person)
    return call_tool(deps, BINDING[tools.REQUEST_LEAVE], args or leave(), call_id)


def decide(session: Session, approval_id: object, decider: Person, outcome: str) -> Approval:
    return approvals.decide(session, str(approval_id), Actor.person(decider), outcome)


def notifications(session: Session, person: Person) -> list[Message]:
    rows = session.exec(select(Message).where(Message.agent_id == MANIFEST.id)).all()
    return [m for m in rows if m.role == "notification" and m.branch_id == person.branch_id]


def last_payslip(session: Session, person: Person) -> Payslip:
    slips = session.exec(select(Payslip).where(Payslip.person_id == person.id)).all()
    return max(slips, key=lambda s: s.cutoff_start)


def test_the_bindings_are_the_manifest_tools() -> None:
    assert {b.tool_id for b in tools.BINDINGS} == {t.id for t in MANIFEST.tools}


def test_a_clerk_asks_their_hours_this_cutoff(session: Session, hr: Ferinos) -> None:
    _, people = hr
    out = tools.hours(deps_for(session, people["Ana"]), last_fortnight(), "h1")
    assert (out.days, out.person_id) == (12, people["Ana"].id)  # less two Monday rest days
    assert (out.regular, out.overtime, out.night, out.rest_day, out.holiday) == (
        12 * 480, 0, 0, 0, 0,
    )  # fmt: skip


def test_the_late_shift_shows_overtime_and_night(session: Session, hr: Ferinos) -> None:
    _, people = hr
    out = tools.hours(deps_for(session, people["Liza"]), last_fortnight(), "h1")
    assert (out.overtime, out.night) == (150, 90)  # Sunday 13:00 to 23:30


def test_a_clerk_reads_only_their_own_hours(session: Session, hr: Ferinos) -> None:
    _, people = hr
    out = call_tool(
        deps_for(session, people["Ana"]),
        BINDING[f"{MANIFEST.id}.hours"],
        last_fortnight(people["Liza"].id),
        "h1",
    )
    assert out["status"] == "denied"


def test_a_supervisor_reads_their_branch_only(session: Session, hr: Ferinos) -> None:
    _, people = hr
    marites = deps_for(session, people["Marites"])
    assert tools.hours(marites, last_fortnight(people["Ana"].id), "h1").days == 12
    with pytest.raises(PermissionDenied):  # Pao works at the stall
        tools.hours(marites, last_fortnight(people["Pao"].id), "h2")
    with pytest.raises(PermissionDenied):  # the branch read is for hours only
        tools.thirteenth_month(marites, PersonInput(person_id=people["Ana"].id), "t1")
    owner = deps_for(session, people["Rosa"])
    assert tools.hours(owner, last_fortnight(people["Pao"].id), "h3").days == 11  # one sick day


def test_an_unknown_person_is_invalid_for_the_owner(session: Session, hr: Ferinos) -> None:
    _, people = hr
    with pytest.raises(LookupError):
        tools.hours(deps_for(session, people["Rosa"]), last_fortnight("nobody"), "h1")
    with pytest.raises(PermissionDenied):  # a clerk learns nothing about a missing person
        tools.hours(deps_for(session, people["Ana"]), last_fortnight("nobody"), "h2")
    with pytest.raises(ValidationError):
        HoursInput(start=TODAY, end=day(-1))


def test_payday_is_the_next_one_after_the_cutoff(session: Session, hr: Ferinos) -> None:
    _, people = hr
    deps = deps_for(session, people["Ana"])
    out = tools.next_payday(deps, NextPaydayInput(), "p1")  # the 1st to 15th pays on the 20th
    assert (out.pay_date, out.cutoff_start, out.cutoff_end) == (
        dt.date(2026, 10, 20), dt.date(2026, 10, 1), dt.date(2026, 10, 15),
    )  # fmt: skip
    deps.today = day(2)
    assert tools.next_payday(deps, NextPaydayInput(), "p2").pay_date == dt.date(2026, 11, 5)


def test_thirteenth_month_is_a_twelfth_of_basic_earned(session: Session, hr: Ferinos) -> None:
    _, people = hr
    out = tools.thirteenth_month(deps_for(session, people["Ana"]), PersonInput(), "t1")
    earned = 2 * 11 * 61000  # the September 16 to 30 and October 1 to 15 payslips
    assert (out.earned_basic, out.estimate, out.paid_in) == (earned, 111833, 12)
    assert out.currency == "PHP"


def test_contributions_come_from_the_last_payslip(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = people["Ana"]
    out = tools.last_contributions(deps_for(session, ana), ContributionsInput(), "c1")
    assert (out.sss, out.cutoff_end) == (11 * 61000 // 20, dt.date(2026, 10, 15))
    assert out.philhealth is None  # not on the seeded payslip
    only = tools.last_contributions(
        deps_for(session, ana), ContributionsInput(which="pagibig"), "c2"
    )
    assert only.sss is None


def test_a_clerk_cannot_read_another_persons_pay_or_leave(session: Session, hr: Ferinos) -> None:
    _, people = hr
    other = PersonInput(person_id=people["Liza"].id)
    for name in ("thirteenth_month", "balance"):
        binding = BINDING[f"{MANIFEST.id}.{name}"]
        assert (
            call_tool(deps_for(session, people["Ana"]), binding, other, name)["status"] == "denied"
        )
    assert "person_id" not in ContributionsInput.model_fields  # own only: nobody to name
    assert "person_id" not in OwnInput.model_fields


def test_a_leave_request_waits_for_head_staff(session: Session, hr: Ferinos) -> None:
    _, people = hr
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
        tools.request_leave(deps_for(session, people["Ana"]), leave(), "l2")


@pytest.mark.parametrize(
    ("name", "args", "reason"),
    [
        ("Ana", leave(day(-1), day(1)), "in_the_past"),
        ("Ana", leave(NEXT_MONDAY, NEXT_MONDAY), "no_working_days"),  # the rest day
        ("Rosa", leave(), "no_contract"),  # the owner has none
    ],
)
def test_a_leave_is_refused_before_any_approval(
    session: Session, hr: Ferinos, name: str, args: RequestLeaveInput, reason: str
) -> None:
    _, people = hr
    out = file_leave(session, people[name], args=args)
    assert (out["status"], out["message"]) == ("invalid", reason)
    assert session.exec(select(Approval)).all() == []
    with pytest.raises(LeaveRefused):
        tools.check_leave(deps_for(session, people[name]), args, "c1")


def test_a_leave_over_an_approved_one_is_refused(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = people["Ana"]
    decide(session, file_leave(session, ana)["approval_id"], people["Marites"], "approved")
    out = file_leave(session, ana, "l2", leave(NEXT_WEDNESDAY, day(12)))
    assert (out["status"], out["message"]) == ("invalid", "overlaps")
    assert file_leave(session, ana, "l3", leave(day(12), day(12)))["status"] == "approval_required"


def told(session: Session, person: Person) -> list[str]:
    """The texts of the hr officer's notifications in the person's own threads."""
    threads = select(Thread.id).where(Thread.person_id == person.id)
    stmt = select(Message).where(col(Message.thread_id).in_(threads))
    return [m.text for m in session.exec(stmt) if m.role == "notification"]


def test_an_overlap_found_at_approval_writes_nothing(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana, marites = people["Ana"], people["Marites"]
    first = file_leave(session, ana, "l1")
    second = file_leave(session, ana, "l2", leave(NEXT_WEDNESDAY, day(10)))  # both pending
    assert second["status"] == "approval_required"
    decide(session, first["approval_id"], marites, "approved")
    approval = decide(session, second["approval_id"], marites, "approved")
    assert approval.status == "approved"  # the approval closes
    assert session.exec(select(Leave).where(Leave.approval_id == approval.id)).all() == []
    assert len(session.exec(select(Leave).where(Leave.person_id == ana.id)).all()) == 1
    assert session.exec(select(Event).where(Event.action == "hr.leave_refused")).one()
    said = "The leave from 2026-10-28 to 2026-10-29 overlaps a leave already approved."
    assert said in told(session, ana)
    assert said in told(session, marites)


def test_an_approved_leave_tells_the_requester_and_updates_the_balance(
    session: Session, hr: Ferinos
) -> None:
    _, people = hr
    ana = people["Ana"]
    assert tools.balance(deps_for(session, ana), PersonInput(), "b1").used == 0
    out = file_leave(session, ana)
    decide(session, out["approval_id"], people["Marites"], "approved")
    row = session.exec(select(Leave).where(Leave.approval_id == out["approval_id"])).one()
    assert (row.status, row.kind, row.person_id, row.days) == ("approved", "vacation", ana.id, 2)
    assert (row.start_date, row.end_date) == (NEXT_TUESDAY, NEXT_WEDNESDAY)
    assert session.exec(
        select(Event).where(Event.action == "hr.leave_approved").where(Event.entity_id == row.id)
    ).one()
    (note,) = notifications(session, ana)
    assert note.sender_id == "system" and NEXT_TUESDAY.isoformat() in note.text
    after = tools.balance(deps_for(session, ana), PersonInput(), "b2")
    assert (after.total, after.used, after.left) == (5, 2, 3)
    deps = deps_for(session, ana)
    deps.approved = {str(out["approval_id"])}
    again = tools.request_leave(deps, RequestLeaveInput(kind="sick", start=TODAY, end=TODAY), "x")
    assert again.leave_id == row.id  # one leave per approval


def test_a_supervisor_cannot_approve_their_own_leave(session: Session, hr: Ferinos) -> None:
    _, people = hr
    out = file_leave(session, people["Marites"])
    with pytest.raises(approvals.ApprovalError):
        decide(session, out["approval_id"], people["Marites"], "approved")
    assert session.exec(select(Leave).where(Leave.approval_id == out["approval_id"])).all() == []


def test_a_clerk_cannot_approve_a_leave(session: Session, hr: Ferinos) -> None:
    _, people = hr
    out = file_leave(session, people["Ana"])
    with pytest.raises(approvals.ApprovalError):
        decide(session, out["approval_id"], people["Liza"], "approved")


def test_the_approved_leave_is_the_one_requested(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = people["Ana"]
    out = file_leave(session, ana, "seen")
    longer = RequestLeaveInput(kind="unpaid", start=day(1), end=day(30))
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
    assert (row.kind, row.start_date, row.end_date) == ("vacation", NEXT_TUESDAY, NEXT_WEDNESDAY)


def test_a_rejected_leave_writes_nothing_and_tells_the_requester(
    session: Session, hr: Ferinos
) -> None:
    _, people = hr
    ana = people["Ana"]
    out = file_leave(session, ana)
    decide(session, out["approval_id"], people["Marites"], "rejected")
    assert session.exec(select(Leave).where(Leave.approval_id == out["approval_id"])).all() == []
    assert session.exec(select(Event).where(Event.action == "hr.leave_rejected")).one()
    (note,) = notifications(session, ana)
    assert note.sender_id == "system"


def test_the_leave_and_pay_stay_off_the_chain(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = people["Ana"]
    hours = BINDING[f"{MANIFEST.id}.hours"]
    call_tool(deps_for(session, ana), hours, last_fortnight(), "s1")
    contributions = BINDING[f"{MANIFEST.id}.last_contributions"]
    call_tool(deps_for(session, ana), contributions, ContributionsInput(), "s2")
    out = file_leave(session, ana, "s3", RequestLeaveInput(kind="sick", start=day(8), end=day(8)))
    decide(session, out["approval_id"], people["Marites"], "approved")
    assert session.exec(select(Leave).where(Leave.kind == "sick")).first() is not None
    payday = BINDING[f"{MANIFEST.id}.next_payday"]
    call_tool(deps_for(session, ana), payday, NextPaydayInput(), "s4")
    logged = session.exec(select(Event)).all()
    assert "sick" not in " ".join(str(e.before) + str(e.after) for e in logged)
    for e in logged:
        if e.action == "tool.called" and e.tool_call_id in ("s1", "s2", "s3"):
            values = {**(e.before or {})["input"], **(e.after or {})["output"]}
            hidden = {k for k, v in values.items() if v != "<redacted>"}
            assert hidden <= SENSITIVE_KEEP, (e.tool_call_id, hidden)
        if e.action == "approval.requested":
            assert (e.after or {})["evidence"] == "<redacted>"
    (called,) = [e for e in logged if e.action == "tool.called" and e.tool_call_id == "s4"]
    assert called.after == {"output": {"pay_date": "2026-10-20", "cutoff_start": "2026-10-01",
                                       "cutoff_end": "2026-10-15"}}  # fmt: skip


def test_the_balance_counts_this_service_years_leave(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = tools.balance(deps_for(session, people["Ana"]), PersonInput(), "b1")
    assert (ana.total, ana.used, ana.left) == (5, 0, 5)  # over a year, no leave taken
    liza = tools.balance(deps_for(session, people["Liza"]), PersonInput(), "b2")
    assert (liza.total, liza.used, liza.left) == (0, 2, 0)  # the seeded vacation, under a year


def test_holiday_pay_question_reads_the_calendar(session: Session, hr: Ferinos) -> None:
    _, people = hr
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


def test_a_payslip_is_resent(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = people["Ana"]
    out = tools.resend_payslip(deps_for(session, ana), OwnInput(), "r1")
    last = last_payslip(session, ana)
    assert (out.payslip_id, out.lines, out.net) == (last.id, last.lines, last.net)
    (note,) = notifications(session, ana)
    assert note.id == out.message_id and note.sender_id == "system"
    assert "2026-10-01" in note.text


def test_a_resent_payslip_stays_off_the_chain(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = people["Ana"]
    out = tools.resend_payslip(deps_for(session, ana), OwnInput(), "r1")
    net = format_money(out.net, out.currency, ana.language)
    row = session.get(Message, out.message_id)
    assert row is not None and net in row.text  # the person reads it in the app
    sent = session.exec(
        select(Event)
        .where(Event.action == "notification.sent")
        .where(Event.entity_id == out.message_id)
    ).one()
    assert net not in str(sent.after) and str(out.net) not in str(sent.after)


def test_the_owner_gets_a_certificate_text(session: Session, hr: Ferinos) -> None:
    kiosk, people = hr
    ana = people["Ana"]
    out = tools.certificate_text(
        deps_for(session, people["Rosa"]), CertificateInput(person_id=ana.id), "e1"
    )
    for part in (ana.name, "Clerk", kiosk.name, "April 7, 2025", "October 19, 2026"):
        assert part in out.text
    assert out.text.endswith(f"{people['Rosa'].name}\nOwner")
    assert session.exec(select(Event).where(Event.action == "hr.certificate_issued")).one()


def test_a_clerk_cannot_ask_a_certificate(session: Session, hr: Ferinos) -> None:
    _, people = hr
    for name in ("Ana", "Marites"):
        out = call_tool(
            deps_for(session, people[name]),
            BINDING[f"{MANIFEST.id}.certificate_text"],
            CertificateInput(person_id=people["Liza"].id),
            "e1",
        )
        assert out["status"] == "denied", name


def test_a_new_contract_ends_the_old_one(session: Session, hr: Ferinos) -> None:
    _, people = hr
    ana = people["Ana"]
    args = SetContractInput(
        person_id=ana.id,
        employment_type="regular",
        daily_rate=65000,
        currency="PHP",
        rest_day=0,
        start_date=dt.date(2026, 11, 1),
        position="Senior clerk",
    )
    binding = BINDING[f"{MANIFEST.id}.set_contract"]
    assert (
        call_tool(deps_for(session, people["Marites"]), binding, args, "s1")["status"] == "denied"
    )
    out = tools.set_contract(deps_for(session, people["Rosa"]), args, "s2")
    rows = session.exec(select(Contract).where(Contract.person_id == ana.id)).all()
    old, new = sorted(rows, key=lambda c: c.start_date)
    assert (old.daily_rate, old.end_date) == (61000, dt.date(2026, 10, 31))  # history kept
    assert (new.id, new.daily_rate, new.end_date, new.set_by) == (
        out.contract_id, 65000, None, people["Rosa"].id,
    )  # fmt: skip
    deps = deps_for(session, ana)
    assert tools._contract(session, ana.id, deps.today).id == old.id  # until the new start
    assert tools._contract(session, ana.id, dt.date(2026, 11, 1)).id == new.id
    event = session.exec(select(Event).where(Event.action == "hr.contract_set")).one()
    assert "65000" not in str(event.after)  # the rate stays off the chain
