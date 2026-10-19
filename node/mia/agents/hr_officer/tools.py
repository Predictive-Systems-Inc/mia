"""The hr officer's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store. Pay, leave and calendar rules are pure code in ph.py and
calendar.py; calc.py turns approved timesheets into minutes by day.

Own rows: the own-data tools answer for the acting person (read_own on the hr tables and
core.timesheet); last_contributions and resend_payslip answer for nobody else. Naming another
person needs read_all on every resource read (admin, and the owner through the hierarchy),
except `hours` for a person of the same branch, which needs the plain read (the supervisor).
Anyone else gets PermissionDenied. The manifest marks the pay, hours and leave tools
sensitive, so their tool.called events keep only ids.

Leave goes through the approvals guard: request_leave has `approval: always`. Its precheck
(check_leave) refuses a leave without a contract, in the past, without a working day or over
an approved leave before anything is asked; then the guard in agents/base.py creates the
approval (evidence: the tool call id and the validated input) and
stops before this body runs. No leave row exists while the request waits. On approve,
apply_leave_approval re-runs request_leave as the requester with the approval in
deps.approved and the input the approver saw; the row is written as approved (event
hr.leave_approved) and the requester is told. On reject, apply_leave_rejection writes no row,
logs hr.leave_rejected and tells the requester.
"""

import datetime as dt
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.hr_officer import MANIFEST, calc, calendar, ph
from mia.agents.hr_officer.models import Contract, Leave, Payslip
from mia.chat.blocks import TextBlock
from mia.chat.channels import notify
from mia.core import approvals, events, orgconfig, store
from mia.core.db import utcnow
from mia.core.models import Actor, Approval, Branch, Organisation, Person
from mia.core.money import format_money
from mia.core.rbac import Resource, get_rbac
from mia.i18n import t

REQUEST_LEAVE = f"{MANIFEST.id}.request_leave"
CONTRACTS = Resource(kind="data", name=Contract.__tablename__)
PAYSLIPS = Resource(kind="data", name=Payslip.__tablename__)
LEAVE = Resource(kind="data", name=Leave.__tablename__)
TIMESHEETS = Resource(kind="data", name="core.timesheet")
SIL_KINDS = ("vacation", "sick")  # the kinds the service incentive leave pays for
THIRTEENTH_MONTH = 12  # paid in December
HOLIDAY_RATES = {
    "regular": int(ph.REGULAR_HOLIDAY * 100),
    "special": int(ph.SPECIAL_HOLIDAY * 100),
    "none": 100,
}
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
CERTIFICATE = (
    "CERTIFICATE OF EMPLOYMENT\n\n"
    "This is to certify that {name} has been employed by {organisation} at {branch} as "
    "{position} since {start}.\n\n"
    "This certificate is issued on {today} upon the request of the employee for whatever "
    "legal purpose it may serve.\n\n"
    "{owner}\nOwner"
)

LeaveKind = Literal["vacation", "sick", "unpaid"]


# ---- shared helpers -----------------------------------------------------------------------


def _check(deps: AgentDeps, resource: Resource, action: str, tool_call_id: str) -> None:
    get_rbac().require(
        deps.actor, resource, action, session=deps.session, tool_call_id=tool_call_id
    )


def _owned(resource: Resource, person_id: str) -> Resource:
    """The resource owned by the person, so read_own and write_own apply to their own rows."""
    return resource.model_copy(update={"owner_id": person_id})


def _subject(
    deps: AgentDeps,
    person_id: str | None,
    resources: list[Resource],
    tool_call_id: str,
    *,
    branch_read: bool = False,
) -> Person:
    """The person a question is about: the acting person (read on each resource as its owner),
    or another person of the organisation after read_all on each resource; with branch_read a
    person of the acting person's branch needs only the plain read. The person row is read
    first only to tell whether they share the branch; nothing about them is returned, and no
    other lookup runs, before the checks pass (a missing person is checked as another
    branch's). Raises LookupError for a person outside the organisation."""
    if person_id is None or person_id == deps.person.id:
        for resource in resources:
            _check(deps, _owned(resource, deps.person.id), "read", tool_call_id)
        return deps.person
    person = deps.session.get(Person, person_id)
    if branch_read and person is not None and person.branch_id == deps.branch.id:
        for resource in resources:
            _check(deps, _owned(resource, person_id), "read", tool_call_id)
    else:
        for resource in resources:
            _check(deps, resource, "read_all", tool_call_id)
    branch = deps.session.get(Branch, person.branch_id) if person is not None else None
    if person is None or branch is None or branch.organisation_id != deps.organisation_id:
        raise LookupError("no such person")
    return person


def _branch_of(session: Session, person: Person) -> Branch:
    branch = session.get(Branch, person.branch_id)
    if branch is None:
        raise LookupError("the person's branch")
    return branch


def _holidays() -> dict[dt.date, str]:
    """The organisation's holidays: date to kind (regular or special)."""
    return {h.date: h.kind for h in orgconfig.load().holidays}


def _contract(session: Session, person_id: str, today: dt.date) -> Contract:
    """The person's contract in force today (started, not ended), the latest started. Raises
    LookupError without one."""
    stmt = select(Contract).where(Contract.person_id == person_id)
    rows = [
        c
        for c in session.exec(stmt)
        if c.start_date <= today and (c.end_date is None or c.end_date >= today)
    ]
    if not rows:
        raise LookupError("no contract")
    return max(rows, key=lambda c: (c.start_date, c.id))


def _payslips(session: Session, person_id: str) -> list[Payslip]:
    """The person's issued payslips, oldest cutoff first."""
    stmt = select(Payslip).where(Payslip.person_id == person_id)
    return sorted(session.exec(stmt), key=lambda p: p.cutoff_start)


def _last_payslip(session: Session, person_id: str) -> Payslip:
    slips = _payslips(session, person_id)
    if not slips:
        raise LookupError("no payslip yet")
    return slips[-1]


def _anniversary(start: dt.date, year: int) -> dt.date:
    """The start date's day in the year (28 February for a 29 February start)."""
    try:
        return start.replace(year=year)
    except ValueError:
        return start.replace(year=year, day=28)


def _service_year(start: dt.date, today: dt.date) -> tuple[dt.date, dt.date]:
    """The current service year: from the last anniversary on or before today (the start date
    in the first year) to the day before the next one."""
    begin = _anniversary(start, today.year)
    if begin > today:
        begin = _anniversary(start, today.year - 1)
    begin = max(begin, start)
    return begin, _anniversary(start, begin.year + 1) - dt.timedelta(days=1)


# ---- hours --------------------------------------------------------------------------------


class HoursInput(BaseModel):
    start: dt.date
    end: dt.date
    person_id: str | None = Field(None, description="Another person (supervisor, owner, admin)")

    @model_validator(mode="after")
    def _ordered(self) -> "HoursInput":
        if self.end < self.start:
            raise ValueError("the period ends before it starts")
        return self


class HoursOutput(BaseModel):
    """Approved minutes in the period by pay kind; night is counted alongside the others."""

    person_id: str
    start: dt.date
    end: dt.date
    regular: int
    overtime: int
    night: int
    rest_day: int
    holiday: int
    days: int


def hours(deps: AgentDeps, args: HoursInput, tool_call_id: str) -> HoursOutput:
    """The person's approved timesheet minutes from start to end by pay kind (calc), with the
    days worked; drafts are never counted. Raises LookupError without a contract."""
    person = _subject(deps, args.person_id, [CONTRACTS, TIMESHEETS], tool_call_id, branch_read=True)
    contract = _contract(deps.session, person.id, deps.today)
    zone = ZoneInfo(_branch_of(deps.session, person).timezone)
    days = calc.minutes_by_day(
        deps.session, person.id, args.start, args.end, zone, contract.rest_day, _holidays()
    )
    return HoursOutput(
        person_id=person.id,
        start=args.start,
        end=args.end,
        regular=sum(d.regular for d in days),
        overtime=sum(d.overtime for d in days),
        night=sum(d.night for d in days),
        rest_day=sum(d.rest_day for d in days),
        holiday=sum(d.regular_holiday + d.special_holiday for d in days),
        days=len(days),
    )


# ---- next_payday --------------------------------------------------------------------------


class NextPaydayInput(BaseModel):
    pass


class NextPaydayOutput(BaseModel):
    pay_date: dt.date
    cutoff_start: dt.date
    cutoff_end: dt.date


def next_payday(deps: AgentDeps, args: NextPaydayInput, tool_call_id: str) -> NextPaydayOutput:
    """The first pay date on or after today (the last cutoff's when it is still to come, else
    the current or the next one's) and the cutoff it pays (calendar.payday, Q60). Reads only
    config."""
    lag = orgconfig.load().payroll.pay_lag_days
    holidays = _holidays()
    current = calendar.cutoff(deps.today)
    following = calendar.cutoff(current[1] + dt.timedelta(days=1))
    for start, end in (calendar.previous_cutoff(deps.today), current, following):
        pay = calendar.payday(end, lag, holidays)
        if pay >= deps.today:
            return NextPaydayOutput(pay_date=pay, cutoff_start=start, cutoff_end=end)
    raise LookupError("no payday ahead")


# ---- thirteenth_month ---------------------------------------------------------------------


class PersonInput(BaseModel):
    person_id: str | None = Field(None, description="Another person (owner, admin)")


class ThirteenthOutput(BaseModel):
    """Basic pay earned this calendar year, one twelfth of it so far, the month it is paid."""

    earned_basic: int
    estimate: int
    paid_in: int
    currency: str


def thirteenth_month(deps: AgentDeps, args: PersonInput, tool_call_id: str) -> ThirteenthOutput:
    """One twelfth (rounded half up) of the regular pay lines of this calendar year's issued
    payslips (by cutoff end), paid in December. Raises LookupError without a contract."""
    person = _subject(deps, args.person_id, [CONTRACTS, PAYSLIPS], tool_call_id)
    contract = _contract(deps.session, person.id, deps.today)
    # ponytail: basic is the regular line only; holiday and rest day pay for unworked days
    # would join it when a payslip carries them.
    earned = sum(
        line["amount"]
        for slip in _payslips(deps.session, person.id)
        if slip.cutoff_end.year == deps.today.year
        for line in slip.lines
        if line.get("kind") == "regular"
    )
    return ThirteenthOutput(
        earned_basic=earned,
        estimate=(earned + 6) // 12,
        paid_in=THIRTEENTH_MONTH,
        currency=contract.currency,
    )


# ---- last_contributions -------------------------------------------------------------------


class ContributionsInput(BaseModel):
    which: Literal["sss", "philhealth", "pagibig", "all"] = "all"


class ContributionsOutput(BaseModel):
    """The employee shares on the last issued payslip; None for one not asked or not on it."""

    sss: int | None
    philhealth: int | None
    pagibig: int | None
    cutoff_end: dt.date
    currency: str


def last_contributions(
    deps: AgentDeps, args: ContributionsInput, tool_call_id: str
) -> ContributionsOutput:
    """The acting person's asked contributions from their last issued payslip's deductions
    (own only; remittance status is the bookkeeper's). Raises LookupError without a payslip."""
    person = _subject(deps, None, [PAYSLIPS], tool_call_id)
    slip = _last_payslip(deps.session, person.id)
    paid = {d["kind"]: int(d["amount"]) for d in slip.deductions}
    asked = {"sss", "philhealth", "pagibig"} if args.which == "all" else {args.which}
    return ContributionsOutput(
        sss=paid.get("sss") if "sss" in asked else None,
        philhealth=paid.get("philhealth") if "philhealth" in asked else None,
        pagibig=paid.get("pagibig") if "pagibig" in asked else None,
        cutoff_end=slip.cutoff_end,
        currency=slip.currency,
    )


# ---- request_leave ------------------------------------------------------------------------


class RequestLeaveInput(BaseModel):
    kind: LeaveKind
    start: dt.date
    end: dt.date

    @model_validator(mode="after")
    def _ordered(self) -> "RequestLeaveInput":
        if self.end < self.start:
            raise ValueError("the leave ends before it starts")
        return self


class LeaveOutput(BaseModel):
    leave_id: str
    kind: str
    start: dt.date
    end: dt.date
    days: int
    status: str
    approval_id: str | None


def _leave_out(row: Leave) -> LeaveOutput:
    return LeaveOutput(
        leave_id=row.id,
        kind=row.kind,
        start=row.start_date,
        end=row.end_date,
        days=row.days,
        status=row.status,
        approval_id=row.approval_id,
    )


class LeaveRefused(LookupError):
    """A leave request refused before any approval is asked; reason names why (no_contract,
    in_the_past, no_working_days, overlaps) for the reply to word."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check_leave(deps: AgentDeps, args: RequestLeaveInput, tool_call_id: str) -> None:
    """The guard's precheck for request_leave (after the permission check, before the
    approval): the requester has a contract, the leave starts today or later, holds at least
    one working day and overlaps no approved leave of theirs. Raises LeaveRefused."""
    _check(deps, _owned(CONTRACTS, deps.person.id), "read", tool_call_id)
    _check(deps, _owned(LEAVE, deps.person.id), "read", tool_call_id)
    try:
        contract = _contract(deps.session, deps.person.id, deps.today)
    except LookupError:
        raise LeaveRefused("no_contract") from None
    if args.start < deps.today:
        raise LeaveRefused("in_the_past")
    if calendar.leave_days(args.start, args.end, contract.rest_day, _holidays()) == 0:
        raise LeaveRefused("no_working_days")
    stmt = (
        select(Leave)
        .where(Leave.person_id == deps.person.id)
        .where(Leave.status == "approved")
        .where(col(Leave.start_date) <= args.end)
        .where(col(Leave.end_date) >= args.start)
    )
    if deps.session.exec(stmt).first() is not None:
        raise LeaveRefused("overlaps")


def _approved(deps: AgentDeps) -> Approval | None:
    """The approved request_leave approval among deps.approved, if any."""
    for approval_id in sorted(deps.approved):
        row = deps.session.get(Approval, approval_id)
        if row is not None and row.type == REQUEST_LEAVE and row.status == "approved":
            return row
    return None


def request_leave(deps: AgentDeps, args: RequestLeaveInput, tool_call_id: str) -> LeaveOutput:
    """Write the leave of an approved request (status approved, event hr.leave_approved), its
    days the working days between start and end (calendar.leave_days with the contract's rest
    day and the holidays). Runs only with an approved approval in deps.approved (the guard asks
    for one first) and writes at most one row per approval: a second run returns the first.
    Raises LookupError without an approval or a contract."""
    _check(deps, _owned(LEAVE, deps.person.id), "write", tool_call_id)
    _check(deps, _owned(CONTRACTS, deps.person.id), "read", tool_call_id)
    approval = _approved(deps)
    if approval is None:
        raise LookupError("a leave needs an approved request")
    stmt = select(Leave).where(Leave.approval_id == approval.id)
    if (done := deps.session.exec(stmt).first()) is not None:
        return _leave_out(done)
    contract = _contract(deps.session, deps.person.id, deps.today)
    days = calendar.leave_days(args.start, args.end, contract.rest_day, _holidays())
    row = store.insert(
        deps.session,
        Leave(
            branch_id=deps.person.branch_id,
            person_id=deps.person.id,
            kind=args.kind,
            start_date=args.start,
            end_date=args.end,
            days=days,
            status="approved",
            approval_id=approval.id,
        ),
        deps.actor,
        action="hr.leave_approved",
        tool_call_id=tool_call_id,
        approval_id=approval.id,
    )
    return _leave_out(row)


def _requested_input(approval: Approval) -> RequestLeaveInput:
    """The request_leave input the approver saw: the approval's evidence `input`, written by
    the guard in agents.base. Raises LookupError when there is none."""
    raw = approval.evidence.get("input")
    if raw is None:
        raise LookupError("the approval carries no leave")
    return RequestLeaveInput.model_validate(raw)


def _requester(session: Session, approval: Approval) -> tuple[Person, Branch]:
    person = session.get(Person, approval.requester_on_behalf_of or "")
    branch = session.get(Branch, person.branch_id) if person is not None else None
    if person is None or branch is None:
        raise LookupError("the requester of the leave")
    return person, branch


def _refuse_approved(
    session: Session, approval: Approval, decider: Actor, args: RequestLeaveInput, reason: str
) -> None:
    """An approved leave that fails check_leave at decision time: no row, event
    hr.leave_refused with the reason, and the requester and the approver each told with the
    reason key hr.leave_refused.<reason> (the approval stays decided)."""
    person, branch = _requester(session, approval)
    start, end = args.start.isoformat(), args.end.isoformat()
    after = {"start": start, "end": end, "reason": reason}
    events.emit(
        session, "hr.leave_refused", approval, None, after, decider, approval_id=approval.id
    )
    approver = session.get(Person, decider.person_id or "")
    for told in [person] + ([approver] if approver is not None else []):
        text = t(f"hr.leave_refused.{reason}", told.language or "en", start=start, end=end)
        notify(session, told, [TextBlock(text=text)], Actor.system(branch.id), MANIFEST.id)


def apply_leave_approval(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: run check_leave again as the requester (their contract, no overlap
    with a leave approved meanwhile, not in the past by now); when it fails, write nothing and
    tell both sides the reason (_refuse_approved). Else re-run request_leave as the requester
    (their permissions, the approval in deps.approved, the evidence input) so the leave is
    written as approved, then tell the requester. Raises LookupError when the requester or the
    input cannot be found."""
    person, branch = _requester(session, approval)
    args = _requested_input(approval)
    lang = person.language or "en"
    deps = AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=utcnow().astimezone(ZoneInfo(branch.timezone)).date(),
        lang=lang,
        manifest=MANIFEST,
        approved={approval.id},
    )
    tool_call_id = str(approval.evidence.get("tool_call_id"))
    try:
        check_leave(deps, args, tool_call_id)
    except LeaveRefused as exc:
        _refuse_approved(session, approval, decider, args, exc.reason)
        return
    leave = request_leave(deps, args, tool_call_id)
    text = t("hr.leave_approved", lang, start=leave.start.isoformat(), end=leave.end.isoformat())
    notify(session, person, [TextBlock(text=text)], Actor.system(branch.id), MANIFEST.id)


def apply_leave_rejection(session: Session, approval: Approval, decider: Actor) -> None:
    """Reject handler: log hr.leave_rejected (no leave row is written) and tell the requester.
    Raises LookupError when the requester or the input cannot be found."""
    person, branch = _requester(session, approval)
    args = _requested_input(approval)
    start, end = args.start.isoformat(), args.end.isoformat()
    after = {"start": start, "end": end, "reason": approval.reason}
    events.emit(
        session, "hr.leave_rejected", approval, None, after, decider, approval_id=approval.id
    )
    text = t("hr.leave_rejected", person.language or "en", start=start, end=end)
    notify(session, person, [TextBlock(text=text)], Actor.system(branch.id), MANIFEST.id)


approvals.register_handler(REQUEST_LEAVE, apply_leave_approval)
approvals.register_reject_handler(REQUEST_LEAVE, apply_leave_rejection)


# ---- balance ------------------------------------------------------------------------------


class BalanceOutput(BaseModel):
    """Service incentive leave days this service year: earned so far, used, left."""

    total: int
    used: int
    left: int


def balance(deps: AgentDeps, args: PersonInput, tool_call_id: str) -> BalanceOutput:
    """The service incentive leave (calendar.sil_balance from the contract's start date) less
    the approved vacation and sick days starting in the current service year. Raises
    LookupError without a contract."""
    person = _subject(deps, args.person_id, [CONTRACTS, LEAVE], tool_call_id)
    contract = _contract(deps.session, person.id, deps.today)
    begin, end = _service_year(contract.start_date, deps.today)
    stmt = (
        select(Leave)
        .where(Leave.person_id == person.id)
        .where(Leave.status == "approved")
        .where(col(Leave.kind).in_(SIL_KINDS))
        .where(col(Leave.start_date) >= begin)
        .where(col(Leave.start_date) <= end)
    )
    used = sum(row.days for row in deps.session.exec(stmt))
    return BalanceOutput(
        total=calendar.sil_balance(contract.start_date, deps.today, 0),
        used=used,
        left=calendar.sil_balance(contract.start_date, deps.today, used),
    )


class LeavePreview(BaseModel):
    """What a leave request takes, for its approval card: working days and the service
    incentive leave days left once it is approved."""

    days: int
    left_after: int


def preview_leave(deps: AgentDeps, args: RequestLeaveInput, tool_call_id: str) -> LeavePreview:
    """The working days the acting person's leave would take (calendar.leave_days) and their
    balance after it (unpaid leave takes no service incentive leave). Reads only, after the
    same own-row checks as balance. Raises LookupError without a contract."""
    now = balance(deps, PersonInput(), tool_call_id)
    contract = _contract(deps.session, deps.person.id, deps.today)
    days = calendar.leave_days(args.start, args.end, contract.rest_day, _holidays())
    used = now.used + (days if args.kind in SIL_KINDS else 0)
    return LeavePreview(
        days=days, left_after=calendar.sil_balance(contract.start_date, deps.today, used)
    )


# ---- holiday ------------------------------------------------------------------------------


class HolidayInput(BaseModel):
    day: dt.date


class HolidayOutput(BaseModel):
    """The day's kind and the pay rate for working it (100 when it is no holiday)."""

    kind: Literal["regular", "special", "none"]
    rate_percent: int
    name: str | None


def holiday(deps: AgentDeps, args: HolidayInput, tool_call_id: str) -> HolidayOutput:
    """The organisation's holiday on the day (OrgSettings.holidays) and its rate when worked:
    200 for a regular holiday, 130 for a special day, 100 otherwise. Reads only config."""
    found = next((h for h in orgconfig.load().holidays if h.date == args.day), None)
    if found is None:
        return HolidayOutput(kind="none", rate_percent=HOLIDAY_RATES["none"], name=None)
    return HolidayOutput(kind=found.kind, rate_percent=HOLIDAY_RATES[found.kind], name=found.name)


# ---- resend_payslip -----------------------------------------------------------------------


class PayslipOutput(BaseModel):
    payslip_id: str
    cutoff_start: dt.date
    cutoff_end: dt.date
    pay_date: dt.date
    lines: list[dict[str, object]]
    gross: int
    deductions: list[dict[str, object]]
    net: int
    currency: str
    message_id: str


class OwnInput(BaseModel):
    pass


def resend_payslip(deps: AgentDeps, args: OwnInput, tool_call_id: str) -> PayslipOutput:
    """The acting person's last issued payslip (own only), sent again to them as a sensitive
    notification (outside channels get a link to the app) from the system. Raises LookupError
    without a payslip."""
    person = _subject(deps, None, [PAYSLIPS], tool_call_id)
    slip = _last_payslip(deps.session, person.id)
    lang = person.language or "en"

    def money(amount: int) -> str:
        return format_money(amount, slip.currency, lang)

    text = t(
        "hr.payslip_resent",
        lang,
        start=slip.cutoff_start.isoformat(),
        end=slip.cutoff_end.isoformat(),
        gross=money(slip.gross),
        deductions=money(sum(int(d["amount"]) for d in slip.deductions)),
        net=money(slip.net),
    )
    message = notify(
        deps.session,
        person,
        [TextBlock(text=text)],
        Actor.system(person.branch_id),
        MANIFEST.id,
        sensitive=True,
    )
    return PayslipOutput(
        payslip_id=slip.id,
        cutoff_start=slip.cutoff_start,
        cutoff_end=slip.cutoff_end,
        pay_date=slip.pay_date,
        lines=slip.lines,
        gross=slip.gross,
        deductions=slip.deductions,
        net=slip.net,
        currency=slip.currency,
        message_id=message.id,
    )


# ---- certificate_text ---------------------------------------------------------------------


class CertificateInput(BaseModel):
    person_id: str


class CertificateOutput(BaseModel):
    text: str


def _long_date(day: dt.date) -> str:
    return f"{MONTHS[day.month - 1]} {day.day}, {day.year}"


def _owner_name(session: Session, deps: AgentDeps) -> str:
    """The acting person when they are an owner, else the organisation's first owner (the
    acting person when it has none)."""
    if "owner" in deps.person.roles:
        return deps.person.name
    branches = select(Branch.id).where(Branch.organisation_id == deps.organisation_id)
    stmt = select(Person).where(col(Person.branch_id).in_(branches)).order_by(col(Person.id))
    owner = next((p for p in session.exec(stmt) if "owner" in p.roles), deps.person)
    return owner.name


def certificate_text(
    deps: AgentDeps, args: CertificateInput, tool_call_id: str
) -> CertificateOutput:
    """A certificate of employment from a fixed English template (name, position and start
    date from the contract, organisation and branch, today, the owner to sign), formatted by
    code; event hr.certificate_issued. Raises LookupError without a contract."""
    person = _subject(deps, args.person_id, [CONTRACTS], tool_call_id)
    contract = _contract(deps.session, person.id, deps.today)
    branch = _branch_of(deps.session, person)
    organisation = deps.session.get(Organisation, branch.organisation_id)
    text = CERTIFICATE.format(
        name=person.name,
        organisation=organisation.name if organisation is not None else branch.name,
        branch=branch.name,
        position=contract.position,
        start=_long_date(contract.start_date),
        today=_long_date(deps.today),
        owner=_owner_name(deps.session, deps),
    )
    events.emit(
        deps.session,
        "hr.certificate_issued",
        person,
        None,
        {"person_id": person.id, "issued_by": deps.person.id},
        deps.actor,
        tool_call_id=tool_call_id,
    )
    return CertificateOutput(text=text)


# ---- set_contract -------------------------------------------------------------------------


class SetContractInput(BaseModel):
    person_id: str
    employment_type: Literal["regular", "probationary", "part_time"]
    daily_rate: int = Field(gt=0, description="Minor units")
    currency: str = Field(min_length=3, max_length=3)
    rest_day: int = Field(ge=0, le=6, description="Weekday, 0 is Monday")
    start_date: dt.date
    position: str = Field(min_length=1)


class ContractOutput(BaseModel):
    contract_id: str
    person_id: str
    employment_type: str
    daily_rate: int
    currency: str
    rest_day: int
    start_date: dt.date
    position: str


def set_contract(deps: AgentDeps, args: SetContractInput, tool_call_id: str) -> ContractOutput:
    """Write the person's new terms as a dated contract row from start_date (event
    hr.contract_set, the rate redacted) in the person's branch, and end every contract still
    open on that date the day before (event hr.contract_ended), so the rate history stays in
    the rows. Needs write_all on contracts (owner, admin). Raises LookupError for a person
    outside the organisation."""
    _check(deps, CONTRACTS, "write_all", tool_call_id)
    person = deps.session.get(Person, args.person_id)
    branch = deps.session.get(Branch, person.branch_id) if person is not None else None
    if person is None or branch is None or branch.organisation_id != deps.organisation_id:
        raise LookupError("no such person")
    ended = args.start_date - dt.timedelta(days=1)
    for old in deps.session.exec(select(Contract).where(Contract.person_id == person.id)):
        if old.end_date is None or old.end_date > ended:
            store.update(
                deps.session,
                old,
                {"end_date": ended},
                deps.actor,
                action="hr.contract_ended",
                tool_call_id=tool_call_id,
            )
    terms = args.model_dump(exclude={"person_id"}) | {"set_by": deps.person.id}
    row = store.insert(
        deps.session,
        Contract(branch_id=person.branch_id, person_id=person.id, **terms),
        deps.actor,
        action="hr.contract_set",
        tool_call_id=tool_call_id,
    )
    return ContractOutput(
        contract_id=row.id,
        person_id=row.person_id,
        employment_type=row.employment_type,
        daily_rate=row.daily_rate,
        currency=row.currency,
        rest_day=row.rest_day,
        start_date=row.start_date,
        position=row.position,
    )


BINDINGS = [
    ToolBinding(
        f"{MANIFEST.id}.hours",
        hours,
        HoursInput,
        "Approved hours in a period by pay kind (regular, overtime, night, rest day, holiday).",
    ),
    ToolBinding(
        f"{MANIFEST.id}.next_payday",
        next_payday,
        NextPaydayInput,
        "The next pay date and the cutoff it pays.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.thirteenth_month",
        thirteenth_month,
        PersonInput,
        "The 13th month pay earned so far this year.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.last_contributions",
        last_contributions,
        ContributionsInput,
        "SSS, PhilHealth and Pag-IBIG shares on the last payslip.",
    ),
    ToolBinding(
        REQUEST_LEAVE,
        request_leave,
        RequestLeaveInput,
        "File a leave. A supervisor, owner or admin approves it first.",
        precheck=check_leave,
    ),
    ToolBinding(
        f"{MANIFEST.id}.balance",
        balance,
        PersonInput,
        "Service incentive leave days earned, used and left this service year.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.holiday",
        holiday,
        HolidayInput,
        "Whether a day is a holiday and its pay rate when worked.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.resend_payslip",
        resend_payslip,
        OwnInput,
        "Send the last payslip again.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.certificate_text",
        certificate_text,
        CertificateInput,
        "The certificate of employment text for the owner to sign.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.set_contract",
        set_contract,
        SetContractInput,
        "Set or change a person's contract terms.",
    ),
]
