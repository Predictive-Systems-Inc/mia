"""The hr officer's work on the tick: payslips issued on payday, and head staff reminded to
approve timesheets two days before a cutoff closes.

What is due is pure code (rule 7). Payslips are due from 09:00 local on a cutoff's payday
(calendar.payday, moved back off a Sunday or a holiday) on any later tick until the branch's
marker exists, so a node down on payday issues them on its first tick after; once the next
payday comes the missed cutoff is reported to head staff (marker hr.payslips_missed), never
issued. The reminder is due from 09:00 local two days before a cutoff ends. Each send leaves a
marker event on the branch (alerts._mark) checked first, so each fires at most once per branch
and cutoff; nothing to send leaves no marker. An issued payslip is never recomputed: a person
who already has one for the cutoff is skipped, and the table's unique (person_id,
cutoff_start) backs that. All run outside quiet hours at 09:00, so nothing is held.
"""

import datetime as dt
from collections.abc import Callable, Mapping
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
MISSED = "hr.payslips_missed"  # the marker and its i18n key
Cutoff = tuple[dt.date, dt.date]

# ---- what is due (pure) ---------------------------------------------------------------------


def paid_cutoffs(
    now: dt.datetime, tz: str, payroll: Payroll, holidays: Mapping[dt.date, str]
) -> tuple[Cutoff, Cutoff]:
    """The two latest cutoffs whose payday (calendar.payday) has come by `now`, each from 09:00
    local on it: the latest first, then the one before."""
    local = now.astimezone(ZoneInfo(tz))
    found: list[Cutoff] = []
    cut = calendar.cutoff(local.date())
    while len(found) < 2:
        pay = calendar.payday(cut[1], payroll.pay_lag_days, holidays)
        if dt.datetime.combine(pay, AT, local.tzinfo) <= local:
            found.append(cut)
        cut = calendar.previous_cutoff(cut[0])
    return found[0], found[1]


def payslips_due(
    now: dt.datetime, tz: str, payroll: Payroll, holidays: Mapping[dt.date, str]
) -> Cutoff:
    """The cutoff to pay at `now`: the latest whose payday has come (from 09:00 local on it,
    on any later day until the next payday comes); the tick issues it while its marker is
    missing."""
    return paid_cutoffs(now, tz, payroll, holidays)[0]


def approval_reminder(now: dt.datetime, tz: str) -> Cutoff | None:
    """The current cutoff from 09:00 local two days before it ends to that day's end, else
    None."""
    local = now.astimezone(ZoneInfo(tz))
    start, end = calendar.cutoff(local.date())
    return (start, end) if local.date() == end - REMIND_BEFORE and local.time() >= AT else None


# ---- payslips -----------------------------------------------------------------------------


def _contracts(session: Session, branch_id: str, day: dt.date) -> list[Contract]:
    """The branch's own contracts in force on the day, one per person (the latest started), so
    a person who moved branches is paid here from this branch's contract only."""
    rows = session.exec(select(Contract).where(Contract.branch_id == branch_id))
    latest: dict[str, Contract] = {}
    for c in rows:
        if c.start_date <= day and (c.end_date is None or c.end_date >= day):
            kept = latest.get(c.person_id)
            if kept is None or (c.start_date, c.id) > (kept.start_date, kept.id):
                latest[c.person_id] = c
    return [latest[k] for k in sorted(latest)]


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


def _unpaid(session: Session, branch: Branch, cutoff: Cutoff) -> int:
    """How many of the branch's people had approved time in the cutoff and no payslip for it."""
    holidays, zone = tools._holidays(), ZoneInfo(branch.timezone)
    return sum(
        not _issued(session, c.person_id, cutoff[0])
        and bool(
            calc.minutes_by_day(
                session, c.person_id, cutoff[0], cutoff[1], zone, c.rest_day, holidays
            )
        )
        for c in _contracts(session, branch.id, cutoff[1])
    )


def report_missed(session: Session, branch: Branch, cutoff: Cutoff) -> list[Message]:
    """Head staff told that the cutoff's payslips were not issued before the next payday (the
    node was down); nothing is issued for it. Nothing when nobody is unpaid."""
    count = _unpaid(session, branch, cutoff)
    if not count:
        return []
    start, end = cutoff[0].isoformat(), cutoff[1].isoformat()
    return [
        notify(
            session,
            p,
            [TextBlock(text=t(MISSED, p.language, count=count, start=start, end=end))],
            Actor.system(branch.id),
            MANIFEST.id,
        )
        for p in alerts.supervisors(session, branch.id)
    ]


def _once(
    session: Session, branch: Branch, action: str, cutoff: Cutoff, send: Callable[[], list[Message]]
) -> int:
    """Run send unless the branch has the cutoff's marker; mark it when something was sent."""
    if alerts._marked(session, action, branch.id, cutoff[0]):
        return 0
    sent = send()
    if sent:
        _mark(session, branch, action, cutoff, sent)
    return len(sent)


# ponytail: an unmarked cutoff is rechecked on every tick until it is marked or the next payday
# comes (a few queries per branch); keep a "nothing to do" marker if ticks ever get costly.
def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    latest, before = paid_cutoffs(now, branch.timezone, orgconfig.load().payroll, tools._holidays())
    count = _once(
        session, branch, ISSUED, latest, lambda: issue_payslips(session, branch, latest, now)
    )
    if not alerts._marked(session, ISSUED, branch.id, before[0]):
        count += _once(
            session, branch, MISSED, before, lambda: report_missed(session, branch, before)
        )
    remind = approval_reminder(now, branch.timezone)
    if remind is not None:
        count += _once(
            session, branch, REMINDED, remind, lambda: remind_approvals(session, branch, remind)
        )
    return count


def run_due(session: Session, now: dt.datetime) -> int:
    """Issue the payslips and send the approval reminders due at `now` for every branch;
    returns how many notifications were sent. Each runs at most once per branch and cutoff.
    Nothing runs when the organisation does not use the hr officer."""
    if MANIFEST.id not in orgconfig.load().agents:
        return 0
    return alerts._each_branch(session, now, _branch_due)
