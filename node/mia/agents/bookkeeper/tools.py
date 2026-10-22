"""The bookkeeper's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store. Every number is code (calc.py, tax.py); the model never computes
one. The read helpers (tender_sales, balance_days, expenses_by_category) take no actor: a tool
checks rights before it calls them.

Scope: every tool works on the acting person's branch. Naming another branch needs read_all on
every resource read (admin, and the owner through the hierarchy); anyone else gets
PermissionDenied. tax_quarter and monthly_profit cover every branch the person may read_all.

Money: record_expense refuses an amount over the expense limit in its precheck (over_limit),
so a large expense has one path, record_large_expense (risk money, approval always, approvers
owner and admin, app only with the PIN step-up; the owner's own is decided by the owner with a
fresh step-up, D37). Its precheck fills the business date from the branch's clock, so the
approval carries the exact input; on approve the handler checks the limit, the date and the
category again and re-runs the tool as the requester with the approval in deps.approved.

Payslip totals: only monthly_profit reads them, after read_all on data:payslips (owner and
admin), summed per branch (never a row per person); the manifest marks it sensitive.
"""

import datetime as dt
from calendar import monthrange
from collections import defaultdict
from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, col, or_, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.bookkeeper import MANIFEST, calc, tax
from mia.agents.bookkeeper.models import (
    CashCount,
    Deposit,
    Expense,
    Payout,
    Settlement,
    TaxFigure,
)
from mia.agents.sales_supervisor.tools import (
    COUNTS,
    ITEMS,
    RECEIPT_TABLES,
    _branch,
    _business_day,
    _check,
    _count_day,
    _currency,
    _hours,
    _reported_at,
)
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import TextBlock
from mia.chat.channels import notify
from mia.core import approvals, events, orgconfig, sales, store
from mia.core.db import utcnow
from mia.core.models import (
    Actor,
    Approval,
    Branch,
    Payslip,
    Person,
    SalesSession,
    StockEvent,
    SupplierOrder,
)
from mia.core.money import format_money
from mia.core.rbac import Resource, get_rbac
from mia.i18n import t
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailItem

PETTY = "petty"  # the bank of a petty refill and the source of a petty spend


def _dates(start: dt.date, end: dt.date) -> list[dt.date]:
    """Every date from start to end, inclusive."""
    return [start + dt.timedelta(days=n) for n in range((end - start).days + 1)]


def tender_sales(
    session: Session, branch_id: str, tender: str | None, start: dt.date, end: dt.date
) -> int:
    """The branch's sales amount from start to end (inclusive) paid by tender (None: every
    tender), in minor units: per business date sales.day_sales(...).by_tender, live counts on a
    counts day and the paid receipts' payments on a receipts day."""
    # ponytail: one day_sales query pair per day of the range; a range query when it shows
    total = 0
    for day in _dates(start, end):
        by = sales.day_sales(session, branch_id, day).by_tender
        total += sum(by.values()) if tender is None else by.get(tender, 0)
    return total


def drawer_out(session: Session, branch_id: str) -> dict[dt.date, int]:
    """The cash taken from the drawer per business date other than a bank deposit: cash spends
    and petty refills (Q99 assumed: staff pay bills from the drawer). A closing count already
    holds what left before it, so the count's expected cash and the undeposited balance both
    use this one rule."""
    out: dict[dt.date, int] = defaultdict(int)
    for d in session.exec(select(Deposit).where(Deposit.branch_id == branch_id)):
        if d.bank == PETTY:
            out[d.business_date] += d.amount
    for e in session.exec(select(Expense).where(Expense.branch_id == branch_id)):
        if e.source == "cash":
            out[e.business_date] += e.amount
    return dict(out)


def balance_days(
    session: Session, branch_id: str, upto: dt.date
) -> tuple[dict[dt.date, int], dict[dt.date, int]]:
    """The petty and undeposited cash balances after each business date with a movement up to
    upto (calc.running). Petty: refills (deposits to bank petty) less petty spends.
    Undeposited: counted cash (the latest count of a date wins; on a receipts date the closed
    sessions' takings, sales.closed_takings, as the float stays in the drawer) less every bank
    deposit, less drawer_out on a date without a count (a count already holds what left before
    it)."""
    counts = session.exec(
        select(CashCount)
        .where(CashCount.branch_id == branch_id)
        .order_by(col(CashCount.created_at), col(CashCount.id))
    )
    counted = {c.business_date: c.counted for c in counts}  # later rows overwrite earlier
    branch = session.get(Branch, branch_id)
    if branch is not None:
        counted = {d: c for d, c in counted.items() if sales.source_of(branch, d) == "counts"}
        for day, taken in sales.closed_takings(session, branch_id).items():
            if sales.source_of(branch, day) == "receipts":
                counted[day] = taken
    refills: dict[dt.date, int] = defaultdict(int)
    out_cash: dict[dt.date, int] = defaultdict(int)
    out_petty: dict[dt.date, int] = defaultdict(int)
    for d in session.exec(select(Deposit).where(Deposit.branch_id == branch_id)):
        if d.bank == PETTY:
            refills[d.business_date] += d.amount
        else:
            out_cash[d.business_date] += d.amount
    for e in session.exec(select(Expense).where(Expense.branch_id == branch_id)):
        if e.source == PETTY:
            out_petty[e.business_date] += e.amount
    # ponytail: what leaves the drawer after a date's count is missed; a timestamp cut if it matters
    for day, amount in drawer_out(session, branch_id).items():
        if day not in counted:
            out_cash[day] += amount
    return calc.running(refills, out_petty, upto), calc.running(counted, out_cash, upto)


def expenses_by_category(
    session: Session, branch_id: str, start: dt.date, end: dt.date
) -> dict[str, int]:
    """The branch's expenses from start to end (inclusive, by business date) summed per
    category, every source included, in minor units."""
    out: dict[str, int] = defaultdict(int)
    stmt = (
        select(Expense)
        .where(Expense.branch_id == branch_id)
        .where(col(Expense.business_date) >= start)
        .where(col(Expense.business_date) <= end)
    )
    for e in session.exec(stmt):
        out[e.category] += e.amount
    return dict(out)


# ---- shared helpers -----------------------------------------------------------------------

Category = Literal["utilities", "rent", "supplies", "transport", "repairs", "other"]
Bank = Literal[
    "bdo", "bpi", "metrobank", "landbank", "unionbank", "security_bank", "chinabank", "pnb",
    "rcbc",
]  # fmt: skip  # a petty refill is record_petty kind refill, never a deposit

LARGE_EXPENSE = f"{MANIFEST.id}.record_large_expense"
CASH = Resource(kind="data", name=CashCount.__tablename__)
SETTLEMENTS = Resource(kind="data", name=Settlement.__tablename__)
PAYOUTS = Resource(kind="data", name=Payout.__tablename__)
EXPENSES = Resource(kind="data", name=Expense.__tablename__)
DEPOSITS = Resource(kind="data", name=Deposit.__tablename__)
PAYSLIPS = Resource(kind="data", name=Payslip.__tablename__)
ORDERS = Resource(kind="data", name=SupplierOrder.__tablename__)
STOCK = Resource(kind="data", name=StockEvent.__tablename__)
TAX = Resource(kind="data", name=TaxFigure.__tablename__)
SESSIONS = Resource(kind="data", name=SalesSession.__tablename__)
# What tender_sales reads (sales.day_sales): the counts, or the receipt tables on a receipts day.
SOURCES = [COUNTS, *RECEIPT_TABLES]
DEFAULT_LANGUAGE = "en"


def _settings() -> orgconfig.BookkeeperSettings:
    return orgconfig.load().bookkeeper


def _read(
    deps: AgentDeps, branches: list[Branch], resources: list[Resource], tool_call_id: str
) -> None:
    """The read check on every resource, and read_all on each when a branch is not the
    person's own (PermissionDenied otherwise)."""
    other = any(b.id != deps.branch.id for b in branches)
    for resource in resources:
        _check(deps, resource, "read", tool_call_id)
        if other:
            _check(deps, resource, "read_all", tool_call_id)


def _scoped(
    deps: AgentDeps, branch_id: str | None, resources: list[Resource], tool_call_id: str
) -> Branch:
    """The person's branch, or the named branch of the organisation after read_all on every
    resource. Raises PermissionDenied, or LookupError for a branch outside the organisation."""
    branch = _branch(deps, branch_id, resources[0], "read", tool_call_id)
    _read(deps, [branch], resources, tool_call_id)
    return branch


def _all_or_own(deps: AgentDeps, resources: list[Resource], tool_call_id: str) -> list[Branch]:
    """Every branch of the organisation when the person may read_all every resource, else
    their own (the read check on every resource either way)."""
    for resource in resources:
        _check(deps, resource, "read", tool_call_id)
    rbac = get_rbac()
    if not all(
        rbac.check(deps.actor, r, "read_all", session=deps.session, tool_call_id=tool_call_id)
        for r in resources
    ):
        return [deps.branch]
    return retail_hours.shops(deps.session, deps.organisation_id)  # never the commissary


def _month(day: dt.date) -> tuple[dt.date, dt.date]:
    first = day.replace(day=1)
    return first, first.replace(day=monthrange(first.year, first.month)[1])


def _latest(balances: dict[dt.date, int]) -> int:
    return balances[max(balances)] if balances else 0


def _money(amount: int, currency: str, person: Person) -> str:
    return format_money(amount, currency, person.language or DEFAULT_LANGUAGE)


def _tell(
    session: Session, person: Person, key: str, *, urgent: bool = False, **params: object
) -> None:
    text = t(key, person.language or DEFAULT_LANGUAGE, **params)
    notify(
        session,
        person,
        [TextBlock(text=text)],
        Actor.system(person.branch_id),
        MANIFEST.id,
        urgent=urgent,
    )


# ---- record_cash_count --------------------------------------------------------------------


class CashCountInput(BaseModel):
    counted: int = Field(ge=0, description="The cash counted, minor units")
    business_date: dt.date | None = Field(None, description="Only when the user names the day")
    source_message_id: str | None = None
    drawer: str | None = Field(None, description="The open sales session counted (a tap only)")


class CashCountOut(BaseModel):
    id: str
    business_date: dt.date
    counted: int
    expected: int
    difference: int
    flagged: bool
    currency: str
    clerk: str | None = None  # a receipts day: the first name of the drawer's clerk
    opening_float: int | None = None
    cash: int | None = None  # the drawer's cash receipts less the drawer_out taken from it
    still_open: list[str] = Field(default_factory=list)  # the other open drawers' clerks


def closing_date(branch: Branch, hours: retail_hours.Hours, said: dt.datetime) -> dt.date:
    """The business date of a closing count said at `said`: the closing's date from its close
    until the next opening (retail_hours.after_close, the window the count reminder asks in),
    else the branch's business date (the late-report rule)."""
    day = retail_hours.after_close(branch, hours, said, dt.timedelta(0))
    return day or retail_hours.business_date_at(branch, hours, said)


def _closing_day(deps: AgentDeps, args: CashCountInput, tool_call_id: str) -> dt.date:
    """closing_date when no day is stated (after the branch-hours read check), else
    _count_day's stated today or yesterday."""
    if args.business_date is not None:
        return _count_day(deps, args.business_date, args.source_message_id, tool_call_id)
    said = _reported_at(deps, args.source_message_id)
    return closing_date(deps.branch, _hours(deps, deps.branch.id, tool_call_id), said)


def record_cash_count(deps: AgentDeps, args: CashCountInput, tool_call_id: str) -> CashCountOut:
    """Store the closing count of the business date (closing_date, or a stated today or
    yesterday; event bookkeeper.cash_counted) against the date's cash sales less drawer_out.
    A difference over the threshold tells the owners and admins, urgent; a count that replaces
    a flagged one tells them first that the earlier alert is withdrawn. Raises
    LookupError("business_date") for another stated day.

    On a receipts day (sales.source_of) the count closes one open drawer (sales.close_session)
    and is held against that session's expected cash less drawer_out (the first count of the
    date only); each count is its own drawer, so no earlier alert is withdrawn. Before any
    write: LookupError("no_session") when no drawer is open, LookupError("which_drawer") when
    args.drawer is unset and more than one is open or the date already has a count."""
    _check(deps, CASH, "write", tool_call_id)
    for source in SOURCES:
        _check(deps, source, "read", tool_call_id)
    _read(deps, [deps.branch], [CASH, EXPENSES, DEPOSITS], tool_call_id)
    day = _closing_day(deps, args, tool_call_id)
    if sales.source_of(deps.branch, day) == "receipts":
        return _close_drawer(deps, args, day, tool_call_id)
    expected = tender_sales(deps.session, deps.branch.id, "cash", day, day) - drawer_out(
        deps.session, deps.branch.id
    ).get(day, 0)
    threshold = _settings().threshold
    m = calc.match(args.counted, expected, 0, threshold)
    currency = _currency(deps.session, deps.branch.id)
    earlier = deps.session.exec(
        select(CashCount)
        .where(CashCount.branch_id == deps.branch.id)
        .where(CashCount.business_date == day)
        .order_by(col(CashCount.created_at).desc(), col(CashCount.id).desc())
    ).first()
    row = store.insert(
        deps.session,
        CashCount(
            branch_id=deps.branch.id,
            business_date=day,
            counted=args.counted,
            expected=expected,
            difference=m.gap,
            currency=currency,
            counted_by=deps.person.id,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.cash_counted",
        tool_call_id=tool_call_id,
    )
    if earlier is not None and abs(earlier.difference) > threshold:
        for lead in alerts.leads(deps.session, deps.organisation_id):
            _tell(
                deps.session,
                lead,
                "bk.count.withdrawn",
                branch=deps.branch.name,
                date=day.isoformat(),
                counted=_money(args.counted, currency, lead),
            )
    if m.flagged:
        key, side = (
            ("bk.count.short_owner", "short") if m.gap < 0 else ("bk.count.over_owner", "over")
        )
        for lead in alerts.leads(deps.session, deps.organisation_id):
            _tell(
                deps.session,
                lead,
                key,
                urgent=True,
                branch=deps.branch.name,
                counted=_money(args.counted, currency, lead),
                expected=_money(expected, currency, lead),
                **{side: _money(abs(m.gap), currency, lead)},
            )
    return CashCountOut(
        id=row.id,
        business_date=day,
        counted=row.counted,
        expected=expected,
        difference=m.gap,
        flagged=m.flagged,
        currency=currency,
    )


def first_name(session: Session, person_id: str) -> str:
    """The person's first name, "?" when the row is gone."""
    person = session.get(Person, person_id)
    return person.name.split()[0] if person else "?"


def _close_drawer(
    deps: AgentDeps, args: CashCountInput, day: dt.date, tool_call_id: str
) -> CashCountOut:
    """record_cash_count on a receipts day: close the named open session (args.drawer; the
    only one when one is open and the date has no count yet) with the count, store the
    CashCount against its expected less drawer_out and tell the leads when flagged. A recount
    or a second drawer never closes a drawer nobody named (LookupError("which_drawer"))."""
    _check(deps, SESSIONS, "read", tool_call_id)
    _check(deps, SESSIONS, "write", tool_call_id)
    events.write_lock(deps.session)  # the open drawers and the date's count decide the close
    open_ = sales.open_sessions(deps.session, deps.branch.id)
    if not open_:
        raise LookupError("no_session")
    counted_before = deps.session.exec(
        select(CashCount.id).where(
            CashCount.branch_id == deps.branch.id, CashCount.business_date == day
        )
    ).first()
    if args.drawer is None and (len(open_) > 1 or counted_before):
        raise LookupError("which_drawer")
    chosen = next((s for s in open_ if args.drawer in (None, s.id)), None)
    if chosen is None:
        raise LookupError("session_closed")  # the tapped drawer was closed meanwhile
    try:
        closed = sales.close_session(
            deps.session, deps.actor, chosen, args.counted, deps.person.id, utcnow()
        )
    except sales.SalesError as exc:
        raise LookupError(str(exc)) from exc
    assert closed.expected is not None
    # ponytail (Q126): which drawer a cash spend left is unknown, so the day's drawer_out is
    # taken once, from the first drawer counted; a session on the spend would place it
    taken = 0 if counted_before else drawer_out(deps.session, deps.branch.id).get(day, 0)
    expected = closed.expected - taken
    m = calc.match(args.counted, expected, 0, _settings().threshold)
    currency, clerk = closed.currency, first_name(deps.session, closed.person_id)
    row = store.insert(
        deps.session,
        CashCount(
            branch_id=deps.branch.id,
            business_date=day,
            counted=args.counted,
            expected=expected,
            difference=m.gap,
            currency=currency,
            counted_by=deps.person.id,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.cash_counted",
        tool_call_id=tool_call_id,
    )
    if m.flagged:
        side = "short" if m.gap < 0 else "over"
        for lead in alerts.leads(deps.session, deps.organisation_id):
            _tell(
                deps.session,
                lead,
                f"bk.count.drawer.{side}_owner",
                urgent=True,
                branch=deps.branch.name,
                clerk=clerk,
                counted=_money(args.counted, currency, lead),
                expected=_money(expected, currency, lead),
                **{side: _money(abs(m.gap), currency, lead)},
            )
    return CashCountOut(
        id=row.id,
        business_date=day,
        counted=row.counted,
        expected=expected,
        difference=m.gap,
        flagged=m.flagged,
        currency=currency,
        clerk=clerk,
        opening_float=closed.opening_float,
        cash=expected - closed.opening_float,  # less drawer_out: the reply's figures add up
        still_open=[first_name(deps.session, s.person_id) for s in open_ if s.id != chosen.id],
    )


# ---- record_settlement and record_payout --------------------------------------------------


class SettlementInput(BaseModel):
    provider: Literal["gcash", "maya"]
    amount: int = Field(ge=0, description="The amount received, minor units")
    start: dt.date
    end: dt.date


class PayoutInput(BaseModel):
    provider: Literal["grab", "foodpanda"]
    amount: int = Field(ge=0, description="The amount received, minor units")
    start: dt.date
    end: dt.date


class MatchOut(BaseModel):
    id: str
    provider: str
    start: dt.date
    end: dt.date
    amount: int
    sales: int
    expected: int
    cut: int
    gap: int
    flagged: bool
    currency: str


def _matched(
    deps: AgentDeps, args: SettlementInput | PayoutInput, percent: int, tool_call_id: str
) -> tuple[int, calc.Match, str]:
    for source in SOURCES:
        _check(deps, source, "read", tool_call_id)
    if args.end < args.start:
        raise LookupError("end is before start")
    sales = tender_sales(deps.session, deps.branch.id, args.provider, args.start, args.end)
    m = calc.match(args.amount, sales, percent, _settings().threshold)
    return sales, m, _currency(deps.session, deps.branch.id)


def _match_out(
    row_id: str, args: SettlementInput | PayoutInput, sales: int, m: calc.Match, currency: str
) -> MatchOut:
    return MatchOut(
        id=row_id,
        provider=args.provider,
        start=args.start,
        end=args.end,
        amount=args.amount,
        sales=sales,
        expected=m.expected,
        cut=m.cut,
        gap=m.gap,
        flagged=m.flagged,
        currency=currency,
    )


def record_settlement(deps: AgentDeps, args: SettlementInput, tool_call_id: str) -> MatchOut:
    """Match a GCash or Maya settlement to the period's sales by that tender less the fee
    (settings; event bookkeeper.settlement_matched). Raises LookupError when end is before
    start."""
    _check(deps, SETTLEMENTS, "write", tool_call_id)
    percent = _settings().fees.get(args.provider, 0)
    sales, m, currency = _matched(deps, args, percent, tool_call_id)
    row = store.insert(
        deps.session,
        Settlement(
            branch_id=deps.branch.id,
            provider=args.provider,
            period_start=args.start,
            period_end=args.end,
            amount=args.amount,
            expected=m.expected,
            fee=m.cut,
            currency=currency,
            matched_by=deps.person.id,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.settlement_matched",
        tool_call_id=tool_call_id,
    )
    return _match_out(row.id, args, sales, m, currency)


def record_payout(deps: AgentDeps, args: PayoutInput, tool_call_id: str) -> MatchOut:
    """Match a Grab or Foodpanda payout to the period's sales by that tender less the
    commission (settings; event bookkeeper.payout_matched). Raises LookupError when end is
    before start."""
    _check(deps, PAYOUTS, "write", tool_call_id)
    percent = _settings().commissions.get(args.provider, 0)
    sales, m, currency = _matched(deps, args, percent, tool_call_id)
    row = store.insert(
        deps.session,
        Payout(
            branch_id=deps.branch.id,
            provider=args.provider,
            period_start=args.start,
            period_end=args.end,
            amount=args.amount,
            expected=m.expected,
            commission=m.cut,
            currency=currency,
            recorded_by=deps.person.id,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.payout_matched",
        tool_call_id=tool_call_id,
    )
    return _match_out(row.id, args, sales, m, currency)


# ---- record_expense and record_large_expense ----------------------------------------------


class ExpenseInput(BaseModel):
    category: Category
    amount: int = Field(gt=0, description="Minor units")
    vat_amount: int | None = Field(None, ge=0, description="Only when the receipt shows it")
    receipt_no: str | None = Field(None, max_length=32)
    source: Literal["cash", "bank"] = "cash"
    business_date: dt.date | None = Field(None, description="Only when the user names the day")


class ExpenseOut(BaseModel):
    id: str
    category: str
    amount: int
    vat_amount: int | None
    receipt_no: str | None
    source: str
    month_total: int
    currency: str


def _check_entry(deps: AgentDeps, args: ExpenseInput, tool_call_id: str) -> None:
    """A VAT amount above the amount refuses (vat); the business date is filled in place from
    the branch's clock, a stated one is today or yesterday (business_date)."""
    if args.vat_amount is not None and args.vat_amount > args.amount:
        raise LookupError("vat")
    args.business_date = _count_day(deps, args.business_date, None, tool_call_id)


def check_expense(deps: AgentDeps, args: ExpenseInput, tool_call_id: str) -> None:
    """The precheck of record_expense: an amount over the expense limit has its own tool with
    the owner's approval, so it is refused here (over_limit)."""
    if args.amount > _settings().expense_limit:
        raise LookupError("over_limit")
    _check_entry(deps, args, tool_call_id)


def check_large_expense(deps: AgentDeps, args: ExpenseInput, tool_call_id: str) -> None:
    """The precheck of record_large_expense (before any approval is asked): the amount is over
    the expense limit (else under_limit) and the entry checks pass; the input then carries the
    business date the approver sees."""
    if args.amount <= _settings().expense_limit:
        raise LookupError("under_limit")
    _check_entry(deps, args, tool_call_id)


def _expense_out(deps: AgentDeps, row: Expense) -> ExpenseOut:
    start, end = _month(row.business_date)
    totals = expenses_by_category(deps.session, deps.branch.id, start, end)
    return ExpenseOut(
        id=row.id,
        category=row.category,
        amount=row.amount,
        vat_amount=row.vat_amount,
        receipt_no=row.receipt_no,
        source=row.source,
        month_total=totals.get(row.category, 0),
        currency=row.currency,
    )


def _insert_expense(
    deps: AgentDeps,
    args: ExpenseInput,
    tool_call_id: str,
    *,
    source: str,
    approval_id: str | None = None,
) -> Expense:
    _check(deps, EXPENSES, "write", tool_call_id)
    day = args.business_date or _business_day(deps, deps.branch, tool_call_id)
    return store.insert(
        deps.session,
        Expense(
            branch_id=deps.branch.id,
            business_date=day,
            category=args.category,
            amount=args.amount,
            currency=_currency(deps.session, deps.branch.id),
            vat_amount=args.vat_amount,
            receipt_no=args.receipt_no,
            source=source,
            approval_id=approval_id,
            recorded_by=deps.person.id,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.expense_recorded",
        tool_call_id=tool_call_id,
        approval_id=approval_id,
    )


def record_expense(deps: AgentDeps, args: ExpenseInput, tool_call_id: str) -> ExpenseOut:
    """Store an expense up to the limit (check_expense ran first through the guard; event
    bookkeeper.expense_recorded) with the category's total for the month."""
    if args.amount > _settings().expense_limit:  # a direct call skips the guard's precheck
        raise LookupError("over_limit")
    _check(deps, EXPENSES, "read", tool_call_id)
    return _expense_out(deps, _insert_expense(deps, args, tool_call_id, source=args.source))


def _approved(deps: AgentDeps) -> Approval | None:
    """The approved record_large_expense approval among deps.approved that this person asked
    for on this branch, if any."""
    for approval_id in sorted(deps.approved):
        row = deps.session.get(Approval, approval_id)
        if (
            row is not None
            and row.type == LARGE_EXPENSE
            and row.status == "approved"
            and row.requester_on_behalf_of == deps.person.id
            and row.branch_id == deps.branch.id
        ):
            return row
    return None


def record_large_expense(deps: AgentDeps, args: ExpenseInput, tool_call_id: str) -> ExpenseOut:
    """Store an expense over the limit: runs only with its approved approval in deps.approved
    (the guard asks for one first) and writes at most one row per approval, carrying its id.
    Raises LookupError without an approval."""
    _check(deps, EXPENSES, "write", tool_call_id)
    _check(deps, EXPENSES, "read", tool_call_id)
    approval = _approved(deps)
    if approval is None:
        raise LookupError("a large expense needs an approved request")
    stmt = select(Expense).where(Expense.approval_id == approval.id)
    row = deps.session.exec(stmt).first() or _insert_expense(
        deps, args, tool_call_id, source=args.source, approval_id=approval.id
    )
    return _expense_out(deps, row)


def person_deps(
    session: Session, person: Person, day: dt.date, approved: frozenset[str] = frozenset()
) -> AgentDeps | None:
    """The person acting from their own branch on day as the bookkeeper's agent role, so the
    tools' rbac checks apply (another branch needs read_all); None when their branch row is
    gone."""
    branch = session.get(Branch, person.branch_id)
    if branch is None:
        return None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=day,
        lang=person.language or DEFAULT_LANGUAGE,
        manifest=MANIFEST,
        approved=set(approved),
    )


def _requester_deps(session: Session, approval: Approval) -> AgentDeps:
    """The requester's deps on their branch's business date now, with the approval approved."""
    person = session.get(Person, approval.requester_on_behalf_of or "")
    branch = session.get(Branch, person.branch_id) if person is not None else None
    if person is None or branch is None:
        raise LookupError("the requester")
    today = retail_hours.business_date_at(branch, retail_hours.load(session, branch.id), utcnow())
    deps = person_deps(session, person, today, frozenset([approval.id]))
    assert deps is not None  # the branch row was read above
    return deps


def _requested(approval: Approval) -> ExpenseInput:
    """The evidence input, validated again (an unknown category refuses here)."""
    raw = approval.evidence.get("input")
    if raw is None:
        raise LookupError("the approval carries no input")
    return ExpenseInput.model_validate(raw)


def _category(category: str, lang: str) -> str:
    return t(f"bk.category.{category}", lang)


def apply_expense_approval(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: check again as the requester that the amount is still over the limit
    (under_limit), the business date is set and not after the branch's business date now
    (business_date) and the category is a fixed one, then re-run record_large_expense as the
    requester (their permissions, the approval in deps.approved, the evidence input) and tell
    them. Raises LookupError (nothing is written; the decide route answers 409)."""
    deps = _requester_deps(session, approval)
    args = _requested(approval)
    tool_call_id = str(approval.evidence.get("tool_call_id") or approval.id)
    if args.amount <= _settings().expense_limit:
        raise LookupError("under_limit")
    if args.business_date is None or args.business_date > _business_day(
        deps, deps.branch, tool_call_id
    ):
        raise LookupError("business_date")
    out = record_large_expense(deps, args, tool_call_id)
    _tell(
        session,
        deps.person,
        "bk.expense.approved",
        amount=_money(out.amount, out.currency, deps.person),
        category=_category(out.category, deps.lang),
    )


def apply_expense_rejection(session: Session, approval: Approval, decider: Actor) -> None:
    """Reject handler: no row; the requester is told bk.expense.rejected, or bk.expense.expired
    when the request closed as expired (approvals.close_refused after the approve handler
    refused it, or the due work)."""
    deps = _requester_deps(session, approval)
    args = _requested(approval)
    key = "bk.expense.expired" if approval.status == "expired" else "bk.expense.rejected"
    _tell(
        session,
        deps.person,
        key,
        amount=_money(args.amount, _currency(session, deps.branch.id), deps.person),
        category=_category(args.category, deps.lang),
    )


approvals.register_handler(LARGE_EXPENSE, apply_expense_approval)
approvals.register_reject_handler(LARGE_EXPENSE, apply_expense_rejection, on_refused=True)


# ---- record_petty and record_deposit ------------------------------------------------------


class PettyInput(BaseModel):
    kind: Literal["spend", "refill"]
    amount: int = Field(gt=0, description="Minor units")
    category: Category = "supplies"


class PettyOut(BaseModel):
    id: str
    kind: str
    amount: int
    balance: int
    below_floor: bool
    currency: str


def check_petty(deps: AgentDeps, args: PettyInput, tool_call_id: str) -> None:
    """The precheck of record_petty: a spend over the expense limit is a large expense
    (over_limit), so no path writes one without the owner's approval."""
    if args.kind == "spend" and args.amount > _settings().expense_limit:
        raise LookupError("over_limit")


def _balances(deps: AgentDeps, branch: Branch, tool_call_id: str) -> tuple[int, int, int]:
    """The petty balance, the undeposited cash and the days in a row over the limit as of the
    branch's business date (callers check the reads)."""
    upto = _business_day(deps, branch, tool_call_id)
    petty, undeposited = balance_days(deps.session, branch.id, upto)
    days = calc.days_over(undeposited, _settings().undeposited_limit)
    return _latest(petty), _latest(undeposited), days


def record_petty(deps: AgentDeps, args: PettyInput, tool_call_id: str) -> PettyOut:
    """A petty spend (an expense with source petty) or a refill (a deposit to bank petty) on
    the business date (event bookkeeper.petty_recorded), with the petty balance after it and
    whether it is below the floor."""
    check_petty(deps, args, tool_call_id)
    resource = EXPENSES if args.kind == "spend" else DEPOSITS
    _check(deps, resource, "write", tool_call_id)
    _read(deps, [deps.branch], [CASH, EXPENSES, DEPOSITS], tool_call_id)
    day = _business_day(deps, deps.branch, tool_call_id)
    currency = _currency(deps.session, deps.branch.id)
    row: Expense | Deposit
    if args.kind == "spend":
        row = Expense(
            branch_id=deps.branch.id,
            business_date=day,
            category=args.category,
            amount=args.amount,
            currency=currency,
            source=PETTY,
            recorded_by=deps.person.id,
        )
    else:
        row = Deposit(
            branch_id=deps.branch.id,
            business_date=day,
            bank=PETTY,
            amount=args.amount,
            currency=currency,
            recorded_by=deps.person.id,
        )
    row = store.insert(
        deps.session,
        row,
        deps.actor,
        action=f"{MANIFEST.id}.petty_recorded",
        tool_call_id=tool_call_id,
    )
    petty, _, _ = _balances(deps, deps.branch, tool_call_id)
    return PettyOut(
        id=row.id,
        kind=args.kind,
        amount=args.amount,
        balance=petty,
        below_floor=petty < _settings().petty_floor,
        currency=currency,
    )


class DepositInput(BaseModel):
    bank: Bank
    amount: int = Field(gt=0, description="Minor units")
    reference: str | None = Field(None, max_length=32)
    business_date: dt.date | None = Field(None, description="Only when the user names the day")


class DepositOut(BaseModel):
    id: str
    bank: str
    amount: int
    undeposited: int
    currency: str


def record_deposit(deps: AgentDeps, args: DepositInput, tool_call_id: str) -> DepositOut:
    """Cash taken from the drawer to a bank (a petty refill is record_petty) on the business
    date (the branch's clock, or a stated today or yesterday; event bookkeeper.deposit_recorded),
    with the undeposited cash after it. Raises LookupError("business_date") for another day."""
    _check(deps, DEPOSITS, "write", tool_call_id)
    _read(deps, [deps.branch], [CASH, EXPENSES, DEPOSITS], tool_call_id)
    day = _count_day(deps, args.business_date, None, tool_call_id)
    currency = _currency(deps.session, deps.branch.id)
    row = store.insert(
        deps.session,
        Deposit(
            branch_id=deps.branch.id,
            business_date=day,
            bank=args.bank,
            amount=args.amount,
            currency=currency,
            reference=args.reference,
            recorded_by=deps.person.id,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.deposit_recorded",
        tool_call_id=tool_call_id,
    )
    _, undeposited, _ = _balances(deps, deps.branch, tool_call_id)
    return DepositOut(
        id=row.id, bank=row.bank, amount=row.amount, undeposited=undeposited, currency=currency
    )


# ---- balances, sales_journal, tax_quarter, monthly_profit (reads) ---------------------------


class BalancesInput(BaseModel):
    branch_id: str | None = Field(None, description="Another branch (only an owner or admin)")


class BalancesOut(BaseModel):
    branch_id: str
    petty: int
    undeposited: int
    days_over: int
    currency: str


def balances(deps: AgentDeps, args: BalancesInput, tool_call_id: str) -> BalancesOut:
    """The branch's petty balance, undeposited cash and the business dates in a row it was over
    the limit. Another branch needs read_all on every table read."""
    branch = _scoped(deps, args.branch_id, [CASH, EXPENSES, DEPOSITS], tool_call_id)
    petty, undeposited, days = _balances(deps, branch, tool_call_id)
    return BalancesOut(
        branch_id=branch.id,
        petty=petty,
        undeposited=undeposited,
        days_over=days,
        currency=_currency(deps.session, branch.id),
    )


class JournalInput(BaseModel):
    month: dt.date = Field(description="Any day of the month")
    branch_id: str | None = Field(None, description="Another branch (only an owner or admin)")


class JournalOut(BaseModel):
    branch_id: str
    month: dt.date
    days: dict[dt.date, dict[str, int]]
    total: int
    currency: str


def sales_journal(deps: AgentDeps, args: JournalInput, tool_call_id: str) -> JournalOut:
    """The BIR sales journal of the month: gross by business date and tender (tax.journal),
    each day from its one source (sales.day_sales(...).by_tender: counts, or the paid receipts'
    payments with refunds as negatives)."""
    branch = _scoped(deps, args.branch_id, [*SOURCES, ITEMS], tool_call_id)
    start, end = _month(args.month)
    rows = [
        (day, tender, amount)
        for day in _dates(start, end)
        for tender, amount in sales.day_sales(deps.session, branch.id, day).by_tender.items()
    ]
    return JournalOut(
        branch_id=branch.id,
        month=start,
        days=tax.journal(rows),
        total=sum(amount for _, _, amount in rows),
        currency=_currency(deps.session, branch.id),
    )


class TaxInput(BaseModel):
    quarter_start: dt.date | None = Field(None, description="Any day of the quarter; None: now")


class TaxOut(BaseModel):
    branch_id: str
    regime: str
    start: dt.date
    end: dt.date
    gross: int
    taxable: int
    rate: int
    output_tax: int
    input_tax: int
    due: int
    deadline: dt.date
    currency: str


class TaxOutput(BaseModel):
    branches: list[TaxOut]


def _input_vat(session: Session, branch_id: str, start: dt.date, end: dt.date) -> int:
    """The VAT amounts typed on the branch's expenses of the period (Q89: none typed, none)."""
    stmt = (
        select(Expense.vat_amount)
        .where(Expense.branch_id == branch_id)
        .where(col(Expense.business_date) >= start)
        .where(col(Expense.business_date) <= end)
    )
    return sum(v or 0 for v in session.exec(stmt))


def _carried(session: Session, branch_id: str, regime: str, start: dt.date) -> int:
    """The excess of the quarter before `start`: minus the due of its TaxFigure row (written by
    the due work) when negative, else 0."""
    previous = tax.quarter_of(start - dt.timedelta(days=1))[0]
    stmt = (
        select(TaxFigure.due)
        .where(TaxFigure.branch_id == branch_id)
        .where(TaxFigure.regime == regime)
        .where(TaxFigure.period_start == previous)
    )
    due = session.exec(stmt).first()
    return max(0, -due) if due is not None else 0


def tax_quarter(deps: AgentDeps, args: TaxInput, tool_call_id: str) -> TaxOutput:
    """The quarter's VAT or percentage tax figure (the regime from settings, tax.quarter_tax)
    per branch: every branch the person may read_all, else their own. Input VAT comes from the
    quarter's expenses plus the previous quarter's excess (_carried)."""
    branches = _all_or_own(deps, [*SOURCES, EXPENSES, TAX], tool_call_id)
    day = args.quarter_start or _business_day(deps, deps.branch, tool_call_id)
    start, end = tax.quarter_of(day)
    regime = _settings().tax_regime
    out = []
    for branch in branches:
        gross = tender_sales(deps.session, branch.id, None, start, end)
        typed = _input_vat(deps.session, branch.id, start, end)
        carried = _carried(deps.session, branch.id, regime, start)
        q = tax.quarter_tax(regime, start, gross, typed, carried)
        out.append(
            TaxOut(
                branch_id=branch.id,
                regime=q.regime,
                start=q.start,
                end=q.end,
                gross=q.gross,
                taxable=q.taxable,
                rate=q.rate,
                output_tax=q.output_tax,
                input_tax=q.input_tax,
                due=q.due,
                deadline=tax.deadline(q.end),
                currency=_currency(deps.session, branch.id),
            )
        )
    return TaxOutput(branches=out)


class ProfitInput(BaseModel):
    month: dt.date = Field(description="Any day of the month")
    branch_id: str | None = Field(None, description="One branch; None: every branch")


class BranchProfit(BaseModel):
    branch_id: str
    sales: int
    fees: int
    expenses: int
    supplier: int
    payroll: int
    cost_of_goods: int | None
    waste: int
    profit: int
    currency: str


class ProfitOutput(BaseModel):
    month: dt.date
    branches: list[BranchProfit]


def _payroll(session: Session, branch_id: str, start: dt.date, end: dt.date) -> int:
    """The gross of the branch's payslips whose cutoff ends in the period, one sum (never a
    row per person)."""
    stmt = (
        select(Payslip.gross)
        .where(Payslip.branch_id == branch_id)
        .where(col(Payslip.cutoff_end) >= start)
        .where(col(Payslip.cutoff_end) <= end)
    )
    return sum(session.exec(stmt))


def _supplier(session: Session, branch_id: str, start: dt.date, end: dt.date) -> int:
    """The totals of the branch's received supplier orders by business date in the period."""
    stmt = (
        select(SupplierOrder.total)
        .where(SupplierOrder.branch_id == branch_id)
        .where(SupplierOrder.status == "received")
        .where(col(SupplierOrder.business_date) >= start)
        .where(col(SupplierOrder.business_date) <= end)
    )
    return sum(v or 0 for v in session.exec(stmt))


def _at_cost(
    session: Session, branch_id: str, start: dt.date, end: dt.date
) -> tuple[int | None, int]:
    """Cost of goods (units sold times cost, per day from sales.day_sales(...).by_item, refunds
    as negatives; None while any sold item has no cost) and item waste at cost (an item without
    a cost adds nothing)."""
    mine = or_(col(RetailItem.branch_id) == branch_id, col(RetailItem.branch_id).is_(None))
    costs = {i.id: i.cost for i in session.exec(select(RetailItem).where(mine))}
    sold = [
        (item_id, quantity)
        for day in _dates(start, end)
        for item_id, (quantity, _) in sales.day_sales(session, branch_id, day).by_item.items()
    ]
    known = all(costs.get(i) is not None for i, q in sold if q)
    goods = sum(q * (costs.get(i) or 0) for i, q in sold) if known else None
    stmt = (
        select(StockEvent)
        .where(StockEvent.branch_id == branch_id)
        .where(StockEvent.kind == "waste")
        .where(col(StockEvent.business_date) >= start)
        .where(col(StockEvent.business_date) <= end)
    )
    waste = sum((e.quantity or 0) * (costs.get(e.item_id or "") or 0) for e in session.exec(stmt))
    return goods, waste


def _fees(session: Session, branch_id: str, start: dt.date, end: dt.date) -> int:
    """The e-wallet fees and platform commissions on the period's sales by tender (settings)."""
    s = _settings()
    return sum(
        calc.percent_of(tender_sales(session, branch_id, tender, start, end), percent)
        for tender, percent in (s.fees | s.commissions).items()
    )


def monthly_profit(deps: AgentDeps, args: ProfitInput, tool_call_id: str) -> ProfitOutput:
    """The month's cash basis profit per branch (calc.profit): sales less fees and commissions,
    expenses, received supplier orders and payroll (payslip totals). Needs read_all on
    data:payslips first (owner and admin); covers every branch, or the one named."""
    _check(deps, PAYSLIPS, "read_all", tool_call_id)
    resources = [*SOURCES, EXPENSES, ORDERS, STOCK, ITEMS]
    if args.branch_id is None:
        branches = _all_or_own(deps, resources, tool_call_id)
    else:
        branches = [_scoped(deps, args.branch_id, resources, tool_call_id)]
    start, end = _month(args.month)
    out = []
    for branch in branches:
        goods, waste = _at_cost(deps.session, branch.id, start, end)
        p = calc.profit(
            sales=tender_sales(deps.session, branch.id, None, start, end),
            fees=_fees(deps.session, branch.id, start, end),
            expenses=sum(expenses_by_category(deps.session, branch.id, start, end).values()),
            supplier=_supplier(deps.session, branch.id, start, end),
            payroll=_payroll(deps.session, branch.id, start, end),
            cost_of_goods=goods,
            waste=waste,
        )
        out.append(
            BranchProfit(
                branch_id=branch.id, currency=_currency(deps.session, branch.id), **asdict(p)
            )
        )
    return ProfitOutput(month=start, branches=out)


# ---- bindings -----------------------------------------------------------------------------


BINDINGS = [
    ToolBinding(
        f"{MANIFEST.id}.record_cash_count",
        record_cash_count,
        CashCountInput,
        "Record the closing cash count against the day's cash sales.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.record_settlement",
        record_settlement,
        SettlementInput,
        "Match a GCash or Maya settlement to the period's sales less the fee.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.record_payout",
        record_payout,
        PayoutInput,
        "Match a Grab or Foodpanda payout to the period's sales less the commission.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.record_expense",
        record_expense,
        ExpenseInput,
        "Record an expense up to the limit, with its category and receipt.",
        precheck=check_expense,
    ),
    ToolBinding(
        LARGE_EXPENSE,
        record_large_expense,
        ExpenseInput,
        "Record an expense over the limit; the owner decides.",
        precheck=check_large_expense,
    ),
    ToolBinding(
        f"{MANIFEST.id}.record_petty",
        record_petty,
        PettyInput,
        "Record a petty cash spend or refill, with the petty balance.",
        precheck=check_petty,
    ),
    ToolBinding(
        f"{MANIFEST.id}.record_deposit",
        record_deposit,
        DepositInput,
        "Record cash deposited to a bank, with the undeposited cash left.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.balances",
        balances,
        BalancesInput,
        "The petty cash balance and the undeposited cash of the branch.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.sales_journal",
        sales_journal,
        JournalInput,
        "The month's sales journal: gross by day and tender.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.tax_quarter",
        tax_quarter,
        TaxInput,
        "The quarter's VAT or percentage tax figure per branch.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.monthly_profit",
        monthly_profit,
        ProfitInput,
        "The month's profit per branch, payroll as payslip totals.",
    ),
]
