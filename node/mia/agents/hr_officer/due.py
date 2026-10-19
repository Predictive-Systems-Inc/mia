"""The hr officer's work on the tick: payslips issued on payday, and head staff reminded to
approve timesheets two days before a cutoff closes.

What is due is pure code (rule 7): from 09:00 local on a cutoff's payday (calendar.payday, moved
back off a Sunday or a holiday), and from 09:00 local two days before a cutoff ends. Each send
leaves a marker event on the branch (alerts._mark) checked first, so each fires at most once
per branch and cutoff; nothing to send leaves no marker. An issued payslip is never recomputed:
a person who already has one for the cutoff is skipped, and the table's unique (person_id,
cutoff_start) backs that. Both run outside quiet hours, so nothing is held (send_after).
"""

import datetime as dt
from collections.abc import Mapping
from dataclasses import asdict
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.hr_officer import MANIFEST, calc, calendar, ph, tools
from mia.agents.hr_officer.actions import WHICH
from mia.agents.hr_officer.models import Contract, Payslip
from mia.agents.hr_officer.replies import duration
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import orgconfig, store
from mia.core.models import Actor, Branch, Message, Person, Timesheet
from mia.core.money import format_money
from mia.core.orgconfig import Payroll
from mia.i18n import t

AT = dt.time(9)  # both run from 09:00 local
REMIND_BEFORE = dt.timedelta(days=2)
ISSUED = "hr.payslips_issued"
REMINDED = "hr.approval_reminded"
Cutoff = tuple[dt.date, dt.date]

# ---- what is due (pure) ---------------------------------------------------------------------


def payslips_due(
    now: dt.datetime, tz: str, payroll: Payroll, holidays: Mapping[dt.date, str]
) -> Cutoff | None:
    """The cutoff whose payday is today, from 09:00 local to the day's end, else None."""
    local = now.astimezone(ZoneInfo(tz))
    if local.time() < AT:
        return None
    today = local.date()
    for start, end in (calendar.previous_cutoff(today), calendar.cutoff(today)):
        if calendar.payday(end, payroll.pay_lag_days, holidays) == today:
            return start, end
    return None


def approval_reminder(now: dt.datetime, tz: str) -> Cutoff | None:
    """The current cutoff from 09:00 local two days before it ends to that day's end, else
    None."""
    local = now.astimezone(ZoneInfo(tz))
    start, end = calendar.cutoff(local.date())
    return (start, end) if local.date() == end - REMIND_BEFORE and local.time() >= AT else None


# ---- payslips -----------------------------------------------------------------------------


def _contracts(session: Session, branch_id: str, day: dt.date) -> list[Contract]:
    """The branch's contracts in force on the day, one per person (tools._contract's pick)."""
    people = session.exec(select(Contract.person_id).where(Contract.branch_id == branch_id))
    out = []
    for person_id in sorted(set(people)):
        try:
            out.append(tools._contract(session, person_id, day))
        except LookupError:
            continue
    return out


def _issued(session: Session, person_id: str, start: dt.date) -> bool:
    stmt = select(Payslip.id).where(Payslip.person_id == person_id)
    return session.exec(stmt.where(Payslip.cutoff_start == start)).first() is not None


def payslip_blocks(slip: Payslip, lang: str) -> list[Block]:
    """The payslip in lang: the totals line (hr.payslip_resent), one line per pay kind with
    its time and amount, one per deduction."""

    def money(amount: int) -> str:
        return format_money(amount, slip.currency, lang)

    deducted = sum(int(d["amount"]) for d in slip.deductions)
    head = t(
        "hr.payslip_resent",
        lang,
        start=slip.cutoff_start.isoformat(),
        end=slip.cutoff_end.isoformat(),
        gross=money(slip.gross),
        deductions=money(deducted),
        net=money(slip.net),
    )
    lines = [
        t(
            "hr.payslip.line",
            lang,
            kind=t(f"hr.pay.{line['kind']}", lang),
            time=duration(int(line["minutes"])),
            amount=money(int(line["amount"])),
        )
        for line in slip.lines
    ]
    lines += [
        t("hr.payslip.deduction", lang, name=WHICH[d["kind"]], amount=money(int(d["amount"])))
        for d in slip.deductions
    ]
    return [TextBlock(text=text) for text in (head, *lines)]


def _issue_one(
    session: Session, branch: Branch, contract: Contract, cutoff: Cutoff, now: dt.datetime
) -> Message | None:
    person = session.get(Person, contract.person_id)
    start, end = cutoff
    if person is None or _issued(session, person.id, start):
        return None
    holidays = tools._holidays()
    days = calc.minutes_by_day(
        session, person.id, start, end, ZoneInfo(branch.timezone), contract.rest_day, holidays
    )
    if not days:
        # ponytail: no approved time, no payslip (a zero gross would net negative after the
        # contributions). Ceiling: no final pay and no payslip for a no-work cutoff; both are
        # follow-ups.
        return None
    pay = ph.payslip(days, contract.daily_rate, ph.monthly_basic(contract.daily_rate))
    slip = Payslip(
        branch_id=branch.id,
        person_id=person.id,
        cutoff_start=start,
        cutoff_end=end,
        pay_date=calendar.payday(end, orgconfig.load().payroll.pay_lag_days, holidays),
        lines=[asdict(line) for line in pay.lines],
        gross=pay.gross,
        deductions=[{"kind": d.kind, "amount": d.amount} for d in pay.deductions],
        net=pay.net,
        currency=contract.currency,
        issued_at=now,
    )
    actor = Actor.system(branch.id)
    message = notify(
        session, person, payslip_blocks(slip, person.language), actor, MANIFEST.id, sensitive=True
    )
    slip.message_id = message.id
    store.insert(session, slip, actor, action="hr.payslip_issued")
    return message


def issue_payslips(
    session: Session, branch: Branch, cutoff: Cutoff, now: dt.datetime
) -> list[Message]:
    """One payslip per person of the branch with a contract in force at the cutoff's end and
    approved time in it, from calc and ph.payslip (event hr.payslip_issued each), told to the
    person in their language. A person already issued one for the cutoff is skipped. Returns
    the notifications sent."""
    sent = [
        _issue_one(session, branch, c, cutoff, now)
        for c in _contracts(session, branch.id, cutoff[1])
    ]
    return [m for m in sent if m is not None]


# ---- the approval reminder ------------------------------------------------------------------


def _drafts(session: Session, branch_id: str, cutoff: Cutoff) -> int:
    stmt = (
        select(Timesheet.id)
        .where(Timesheet.branch_id == branch_id)
        .where(Timesheet.status == "draft")
        .where(col(Timesheet.date) >= cutoff[0])
        .where(col(Timesheet.date) <= cutoff[1])
    )
    return len(session.exec(stmt).all())


def remind_approvals(session: Session, branch: Branch, cutoff: Cutoff) -> list[Message]:
    """The branch's head staff (alerts.supervisors) told how many timesheets of the cutoff are
    still drafts; nothing when there are none."""
    count = _drafts(session, branch.id, cutoff)
    if not count:
        return []
    actor = Actor.system(branch.id)
    return [
        notify(
            session,
            p,
            [
                TextBlock(
                    text=t(
                        "hr.approval_reminder", p.language, count=count, end=cutoff[1].isoformat()
                    )
                )
            ],
            actor,
            MANIFEST.id,
        )
        for p in alerts.supervisors(session, branch.id)
    ]


# ---- the tick -------------------------------------------------------------------------------


def _mark(
    session: Session, branch: Branch, action: str, cutoff: Cutoff, sent: list[Message]
) -> None:
    data = {
        "date": cutoff[0].isoformat(),
        "cutoff_end": cutoff[1].isoformat(),
        "message_ids": [m.id for m in sent],
    }
    alerts._mark(session, branch.id, action, ("branch", branch.id), data)


def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    settings = orgconfig.load()
    count = 0
    pay = payslips_due(now, branch.timezone, settings.payroll, tools._holidays())
    if pay is not None and not alerts._marked(session, ISSUED, branch.id, pay[0]):
        sent = issue_payslips(session, branch, pay, now)
        if sent:
            _mark(session, branch, ISSUED, pay, sent)
        count += len(sent)
    remind = approval_reminder(now, branch.timezone)
    if remind is not None and not alerts._marked(session, REMINDED, branch.id, remind[0]):
        sent = remind_approvals(session, branch, remind)
        if sent:
            _mark(session, branch, REMINDED, remind, sent)
        count += len(sent)
    return count


def run_due(session: Session, now: dt.datetime) -> int:
    """Issue the payslips and send the approval reminders due at `now` for every branch;
    returns how many notifications were sent. Each runs at most once per branch and cutoff.
    Nothing runs when the organisation does not use the hr officer."""
    if MANIFEST.id not in orgconfig.load().agents:
        return 0
    return alerts._each_branch(session, now, _branch_due)
