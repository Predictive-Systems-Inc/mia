"""The bookkeeper's work on the tick: the closing-count reminder an hour after the closing when
no count exists (urgent), the petty floor and undeposited cash reminders in the morning window,
the monthly profit per branch to the leads on the month's second open day (sensitive), the
quarter's tax figure five days before its deadline, and undecided large expenses closed with
the requester told.

What is due is pure code (rule 7): the window functions take the branch, its hours rows and
`now`. After-close work keeps the closing's business date after midnight
(retail_hours.after_close). Markers: `{id}.count_reminded`, `{id}.petty_reminded` and
`{id}.undeposited_reminded` per branch and date, `{id}.profit_sent` per branch and month, the
TaxFigure row per branch, regime and quarter; each is written with its send, and nothing sent
leaves no marker (checked again on the next tick). Only the count reminder is urgent; the rest
wait out quiet hours in deliver. The profit and the tax figure run the tools as each lead, so
rbac decides what they read (the payslip totals need read_all) and a denied lead is skipped.
Each branch commits alone (alerts._each_branch). The short-or-over alert is sent by
tools.record_cash_count when the count is typed.
"""

import datetime as dt

from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.agents.bookkeeper import MANIFEST, calc, replies, tax, tools
from mia.agents.bookkeeper.models import CashCount, TaxFigure
from mia.agents.sales_supervisor import due as sales_due
from mia.agents.sales_supervisor.tools import _currency
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import approvals, orgconfig, store
from mia.core.db import utcnow
from mia.core.ids import new_id
from mia.core.models import Actor, Approval, Branch, Message, Person
from mia.core.rbac import PermissionDenied
from mia.i18n import t
from mia.templates.retail import hours as retail_hours

HOUR = dt.timedelta(hours=1)
ONE_DAY = dt.timedelta(days=1)
FIGURE_BEFORE = dt.timedelta(days=5)  # the quarter's figure this long before its deadline
OVER_DAYS = 2  # business dates in a row over the undeposited limit before a reminder
COUNT_REMINDED = f"{MANIFEST.id}.count_reminded"
PETTY_REMINDED = f"{MANIFEST.id}.petty_reminded"
UNDEPOSITED_REMINDED = f"{MANIFEST.id}.undeposited_reminded"
PROFIT_SENT = f"{MANIFEST.id}.profit_sent"
Hours = retail_hours.Hours

# ---- what is due (pure) ---------------------------------------------------------------------


def closing(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The business date from an hour after its closing to its window's end (past midnight)."""
    return retail_hours.after_close(branch, hours, now, HOUR)


def morning(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """Today's date in the first hour after an open day's opening, else None."""
    return sales_due.morning_message(branch, hours, now)


def second_open_day(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The date of the month's second open day in its morning window, else None."""
    day = morning(branch, hours, now)
    if day is None:
        return None
    is_open = retail_hours.open_days(hours)
    earlier = sum(is_open(day.replace(day=1) + dt.timedelta(days=k)) for k in range(day.day - 1))
    return day if earlier == 1 else None


def quarter_due(branch: Branch, hours: Hours, now: dt.datetime) -> tuple[dt.date, dt.date] | None:
    """The quarter before today's (first and last day) in a morning window from FIGURE_BEFORE
    before its deadline to the deadline, else None. The TaxFigure row makes it once, so the
    figure goes on the first open morning of that span."""
    day = morning(branch, hours, now)
    if day is None:
        return None
    start, end = tax.quarter_of(tax.quarter_of(day)[0] - ONE_DAY)
    deadline = tax.deadline(end)
    return (start, end) if deadline - FIGURE_BEFORE <= day <= deadline else None


# ---- helpers ------------------------------------------------------------------------------


def _send(
    session: Session,
    branch: Branch,
    person: Person,
    text: str,
    *,
    urgent: bool = False,
    sensitive: bool = False,
) -> Message:
    blocks: list[Block] = [TextBlock(text=text)]
    actor = Actor.system(branch.id)
    return notify(session, person, blocks, actor, MANIFEST.id, urgent=urgent, sensitive=sensitive)


def _lang(person: Person) -> str:
    return person.language or tools.DEFAULT_LANGUAGE


def _once_each(people: list[Person]) -> list[Person]:
    return list({p.id: p for p in people}.values())


def _deps(session: Session, person: Person, day: dt.date) -> AgentDeps:
    """The lead acting from their own branch on day, so the tools' rbac checks apply (another
    branch needs read_all)."""
    branch = session.get(Branch, person.branch_id)
    if branch is None:
        raise LookupError("the person's branch")
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=day,
        lang=_lang(person),
        manifest=MANIFEST,
    )


def _names(session: Session, organisation_id: str) -> replies.Names:
    stmt = select(Branch).where(Branch.organisation_id == organisation_id)
    return {b.id: b.name for b in session.exec(stmt)}


def _marked_send(
    session: Session, branch: Branch, marker: str, on: dt.date, sent: list[Message]
) -> int:
    if sent:  # nothing sent leaves no marker: checked again on the next tick
        data = {"date": on.isoformat(), "message_ids": [m.id for m in sent]}
        alerts._mark(session, branch.id, marker, ("branch", branch.id), data)
    return len(sent)


# ---- senders ------------------------------------------------------------------------------


def _count_reminder(session: Session, branch: Branch, day: dt.date) -> list[Message]:
    """bk.count.reminder to the branch's supervisors (urgent) when day has no CashCount."""
    stmt = select(CashCount.id).where(CashCount.branch_id == branch.id)
    if session.exec(stmt.where(CashCount.business_date == day)).first() is not None:
        return []
    return [
        _send(session, branch, p, t("bk.count.reminder", _lang(p)), urgent=True)
        for p in alerts.supervisors(session, branch.id)
    ]


def _balance_reminders(session: Session, branch: Branch, day: dt.date) -> int:
    """bk.petty.low when the petty balance is under the floor and bk.undeposited.high when the
    undeposited cash was over the limit OVER_DAYS business dates in a row, each once per
    branch and day, to the supervisors and the leads."""
    settings = orgconfig.load().bookkeeper
    petty, undeposited = tools.balance_days(session, branch.id, day)
    people = _once_each(
        alerts.supervisors(session, branch.id) + alerts.leads(session, branch.organisation_id)
    )
    currency = _currency(session, branch.id)
    count = 0
    balance = tools._latest(petty)
    if balance < settings.petty_floor and not alerts._marked(
        session, PETTY_REMINDED, branch.id, day
    ):
        sent = [
            _send(
                session,
                branch,
                p,
                t(
                    "bk.petty.low",
                    _lang(p),
                    balance=replies.money(balance, currency, _lang(p)),
                    floor=replies.money(settings.petty_floor, currency, _lang(p)),
                ),
            )
            for p in people
        ]
        count += _marked_send(session, branch, PETTY_REMINDED, day, sent)
    days = calc.days_over(undeposited, settings.undeposited_limit)
    if days >= OVER_DAYS and not alerts._marked(session, UNDEPOSITED_REMINDED, branch.id, day):
        amount = tools._latest(undeposited)
        sent = [
            _send(
                session,
                branch,
                p,
                t(
                    "bk.undeposited.high",
                    _lang(p),
                    amount=replies.money(amount, currency, _lang(p)),
                    days=days,
                ),
            )
            for p in people
        ]
        count += _marked_send(session, branch, UNDEPOSITED_REMINDED, day, sent)
    return count


def _profit(session: Session, branch: Branch, day: dt.date) -> list[Message]:
    """Last month's profit of the branch (tools.monthly_profit as each lead, the payslip read
    checked) to the leads, sensitive: the payroll total never reaches the chain."""
    month = (day.replace(day=1) - ONE_DAY).replace(day=1)
    args = tools.ProfitInput(month=month, branch_id=branch.id)
    names = _names(session, branch.organisation_id)
    sent = []
    for person in alerts.leads(session, branch.organisation_id):
        try:
            out = tools.monthly_profit(_deps(session, person, day), args, new_id())
        except PermissionDenied:
            continue
        text = replies.profit_text(out, names, _lang(person))
        sent.append(_send(session, branch, person, text, sensitive=True))
    return sent


def _quarter(session: Session, branch: Branch, day: dt.date, start: dt.date) -> int:
    """The quarter's figure of the branch (tools.tax_quarter as each lead) to the leads, and
    its TaxFigure row (the marker) written with the first send. Nothing when the row exists."""
    regime = orgconfig.load().bookkeeper.tax_regime
    stmt = (
        select(TaxFigure.id)
        .where(TaxFigure.branch_id == branch.id)
        .where(TaxFigure.regime == regime)
        .where(TaxFigure.period_start == start)
    )
    if session.exec(stmt).first() is not None:
        return 0
    names = _names(session, branch.organisation_id)
    figure: tools.TaxOut | None = None
    sent = 0
    for person in alerts.leads(session, branch.organisation_id):
        try:
            out = tools.tax_quarter(
                _deps(session, person, day), tools.TaxInput(quarter_start=start), new_id()
            )
        except PermissionDenied:
            continue
        mine = [b for b in out.branches if b.branch_id == branch.id]
        if not mine:
            continue
        text = replies.tax_text(tools.TaxOutput(branches=mine), names, _lang(person))
        _send(session, branch, person, text)
        figure, sent = mine[0], sent + 1
    if figure is not None:
        row = TaxFigure(
            branch_id=branch.id,
            regime=figure.regime,
            period_start=figure.start,
            period_end=figure.end,
            gross=figure.gross,
            taxable=figure.taxable,
            rate=figure.rate,
            input_tax=figure.input_tax,
            due=figure.due,
            currency=figure.currency,
        )
        store.insert(session, row, Actor.system(branch.id), action=f"{MANIFEST.id}.tax_figured")
    return sent


def close_undecided(session: Session, branch: Branch, now: dt.datetime) -> int:
    """The branch's open large expense approvals past their TTL through approvals.expire_if_due
    (escalated once, then expired); each expired one tells its requester bk.expense.expired
    (tools.apply_expense_rejection). Marker-free: an expired approval is no longer open.
    Returns how many expired."""
    actor, count = Actor.system(branch.id), 0
    stmt = (
        select(Approval)
        .where(Approval.branch_id == branch.id)
        .where(Approval.type == tools.LARGE_EXPENSE)
        .where(col(Approval.status).in_(("pending", "escalated")))
    )
    for approval in list(session.exec(stmt)):
        if approvals.expire_if_due(session, approval, actor).status == "expired":
            tools.apply_expense_rejection(session, approval, actor)
            count += 1
    return count


# ---- the tick -------------------------------------------------------------------------------


def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    hours = retail_hours.load(session, branch.id)
    count = close_undecided(session, branch, now)
    day = closing(branch, hours, now)
    if day is not None and not alerts._marked(session, COUNT_REMINDED, branch.id, day):
        sent = _count_reminder(session, branch, day)
        count += _marked_send(session, branch, COUNT_REMINDED, day, sent)
    today = morning(branch, hours, now)
    if today is None:
        return count
    count += _balance_reminders(session, branch, today)
    month = today.replace(day=1)
    if second_open_day(branch, hours, now) and not alerts._marked(
        session, PROFIT_SENT, branch.id, month
    ):
        count += _marked_send(session, branch, PROFIT_SENT, month, _profit(session, branch, today))
    quarter = quarter_due(branch, hours, now)
    if quarter is not None:
        count += _quarter(session, branch, today, quarter[0])
    return count


def run_due(session: Session, now: dt.datetime | None = None) -> int:
    """Run the bookkeeper's due work at `now` for every branch; returns how many notifications
    were sent and large expenses closed. Nothing runs when the organisation does not use the
    bookkeeper."""
    if MANIFEST.id not in orgconfig.load().agents:
        return 0
    return alerts._each_branch(session, now or utcnow(), _branch_due)
