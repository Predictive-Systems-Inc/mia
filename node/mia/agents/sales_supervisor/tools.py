"""Sales supervisor tools: typed inputs and outputs, permission checked data access, writes only
through mia.core.store. Business date, target share and totals are pure code in calc.py.

Branch scoping: every tool works on the person's own branch. Naming another branch of the
organisation (or "all") needs the read_all or write_all action on the data resource in RBAC
(admin, and the owner through the hierarchy); anyone else gets PermissionDenied.
"""

import datetime as dt
from collections.abc import Callable, Sequence
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.sales_supervisor import MANIFEST, calc
from mia.agents.sales_supervisor.models import SalesCount, SalesNote, SalesTarget
from mia.core import store
from mia.core.db import utcnow
from mia.core.models import Branch, Person
from mia.core.rbac import Resource, get_rbac
from mia.templates.retail.models import RetailBranchHours, RetailItem

DEFAULT_CLOSES = dt.time(21, 0)
LEADS = {"owner", "admin"}  # whose target wins (precedence, not access)
COUNTS = Resource(kind="data", name=SalesCount.__tablename__)
TARGETS = Resource(kind="data", name=SalesTarget.__tablename__)
NOTES = Resource(kind="data", name=SalesNote.__tablename__)
ITEMS = Resource(kind="data", name=RetailItem.__tablename__)
HOURS = Resource(kind="data", name=RetailBranchHours.__tablename__)


# ---- shared helpers -----------------------------------------------------------------------


def _check(deps: AgentDeps, resource: Resource, action: str, tool_call_id: str) -> None:
    get_rbac().require(
        deps.actor, resource, action, session=deps.session, tool_call_id=tool_call_id
    )


def _as_reporter(resource: Resource, deps: AgentDeps) -> Resource:
    """The resource with the acting person as owner_id. read_own and write_own then hold for
    every row the tool touches, so this check gates by role only (a clerk may read or write
    sales data at all); which rows and which branch are in scope is decided by the queries and
    by _branch."""
    return resource.model_copy(update={"owner_id": deps.person.id})


def _is_lead(person: Person | None) -> bool:
    """True for an owner or admin (only used to rank targets, never for access)."""
    return person is not None and bool(LEADS & set(person.roles))


def _branch(
    deps: AgentDeps, branch_id: str | None, resource: Resource, action: str, tool_call_id: str
) -> Branch:
    """The person's branch, or another branch of the organisation when RBAC allows
    `<action>_all` on the resource (logged as an rbac event; PermissionDenied otherwise).
    The person's own Branch row is read without a check: it is already in deps.
    Raises LookupError for a branch outside the organisation."""
    if branch_id is None or branch_id == deps.branch.id:
        return deps.branch
    _check(deps, resource, f"{action}_all", tool_call_id)
    branch = deps.session.get(Branch, branch_id)
    if branch is None or branch.organisation_id != deps.organisation_id:
        raise LookupError("branch")
    return branch


def _catalog(session: Session, branch_id: str) -> list[RetailItem]:
    """Active items the branch sells (its own and the shared ones), in menu order."""
    stmt = (
        select(RetailItem)
        .where(col(RetailItem.active).is_(True))
        .order_by(col(RetailItem.sort_order))
    )
    return [i for i in session.exec(stmt) if i.branch_id in (None, branch_id)]


def _currency(session: Session, branch_id: str) -> str:
    # ponytail: one currency per branch in v1, taken from its first item; a mixed-currency
    # branch needs per-currency totals.
    catalog = _catalog(session, branch_id)
    if not catalog:
        raise LookupError("the branch has no items")
    return catalog[0].currency


def _hours(deps: AgentDeps, branch_id: str, tool_call_id: str) -> list[RetailBranchHours]:
    """The branch's opening hours rows, after the retail_branch_hours read check."""
    _check(deps, HOURS, "read", tool_call_id)
    stmt = select(RetailBranchHours).where(RetailBranchHours.branch_id == branch_id)
    return list(deps.session.exec(stmt))


def _closes(hours: Sequence[RetailBranchHours], weekday: int) -> dt.time:
    """The closing time on the weekday, 21:00 when no hours are set for it."""
    row = next((h for h in hours if h.weekday == weekday), None)
    return dt.time.fromisoformat(row.closes) if row else DEFAULT_CLOSES


def _open_days(hours: Sequence[RetailBranchHours]) -> Callable[[dt.date], bool]:
    """A weekday is open when the branch has hours for it; a branch without hours is always open."""
    weekdays = {h.weekday for h in hours} or set(range(7))
    return lambda day: day.weekday() in weekdays


def target_share(deps: AgentDeps, branch_id: str, day: dt.date, tool_call_id: str) -> int | None:
    """The branch's money target for the day, after the targets read check. A day target wins
    over a month target; between targets of the same period, one set by an owner or admin
    wins, then the newest."""
    _check(deps, TARGETS, "read", tool_call_id)
    session = deps.session
    stmt = (
        select(SalesTarget)
        .where(SalesTarget.branch_id == branch_id)
        .where(col(SalesTarget.amount).is_not(None))
        .where(col(SalesTarget.starts_on) <= day)
    )
    rows = session.exec(stmt).all()
    setter_ids = {r.set_by for r in rows}
    setters = {p.id: p for p in session.exec(select(Person).where(col(Person.id).in_(setter_ids)))}
    open_day = _open_days(_hours(deps, branch_id, tool_call_id))
    ranked = []
    for row in rows:
        assert row.amount is not None
        share = calc.day_share(calc.Target(row.period, row.starts_on, row.amount), day, open_day)
        if share is not None:
            lead = _is_lead(setters.get(row.set_by))
            ranked.append((row.period == "day", lead, row.created_at, row.id, share))
    return max(ranked)[-1] if ranked else None


def _live_counts(
    session: Session,
    branch_ids: Sequence[str],
    start: dt.date,
    end: dt.date,
    item_id: str | None = None,
) -> list[SalesCount]:
    stmt = (
        select(SalesCount)
        .where(col(SalesCount.branch_id).in_(branch_ids))
        .where(col(SalesCount.business_date) >= start)
        .where(col(SalesCount.business_date) <= end)
        .where(col(SalesCount.superseded_by).is_(None))
    )
    if item_id is not None:
        stmt = stmt.where(SalesCount.item_id == item_id)
    return list(session.exec(stmt))


def _plain(rows: Sequence[SalesCount]) -> list[calc.Count]:
    return [calc.Count(r.item_id, r.quantity, r.amount, r.superseded_by) for r in rows]


def _names(session: Session) -> dict[str, RetailItem]:
    return {i.id: i for i in session.exec(select(RetailItem))}


class CountOut(BaseModel):
    count_id: str
    item_id: str
    item: str
    quantity: int
    amount: int


def _count_out(row: SalesCount, item: RetailItem) -> CountOut:
    return CountOut(
        count_id=row.id,
        item_id=row.item_id,
        item=item.name,
        quantity=row.quantity,
        amount=row.amount,
    )


def _new_count(
    deps: AgentDeps,
    item: RetailItem,
    quantity: int,
    day: dt.date,
    *,
    supersedes: str | None = None,
    source_message_id: str | None = None,
) -> SalesCount:
    return SalesCount(
        branch_id=deps.branch.id,
        item_id=item.id,
        quantity=quantity,
        amount=quantity * item.price,
        currency=item.currency,
        reported_at=utcnow(),
        reported_by=deps.person.id,
        business_date=day,
        supersedes=supersedes,
        source_message_id=source_message_id,
    )


# ---- record_counts ------------------------------------------------------------------------


class CountIn(BaseModel):
    item_id: str
    quantity: int = Field(ge=0)


class RecordCountsInput(BaseModel):
    items: list[CountIn] = Field(min_length=1)
    total: int | None = Field(None, ge=0, description="The total the user stated, minor units")
    business_date: dt.date | None = Field(None, description="Only when the user names the day")
    source_message_id: str | None = None


class RecordCountsOutput(BaseModel):
    recorded: list[CountOut]
    business_date: dt.date
    day_total: int
    currency: str
    target_share: int | None


def _business_date(deps: AgentDeps, tool_call_id: str) -> dt.date:
    """Today's local date at the branch. Raises LookupError("business_date") within two hours
    after closing (that day's, or the day before's just after midnight) when this reporter
    already counted the day before (the turn then asks)."""
    now = utcnow()
    tz = deps.branch.timezone
    weekday = now.astimezone(ZoneInfo(tz)).weekday()
    hours = _hours(deps, deps.branch.id, tool_call_id)
    closes, closed_yesterday = _closes(hours, weekday), _closes(hours, (weekday - 1) % 7)
    day, after_closing = calc.business_date(now, tz, closes, closed_yesterday)
    if after_closing:
        stmt = (
            select(SalesCount.id)
            .where(SalesCount.branch_id == deps.branch.id)
            .where(SalesCount.reported_by == deps.person.id)
            .where(SalesCount.business_date == day - dt.timedelta(days=1))
            .where(col(SalesCount.superseded_by).is_(None))
        )
        if deps.session.exec(stmt.limit(1)).first() is not None:
            raise LookupError("business_date")
    return day


def record_counts(
    deps: AgentDeps, args: RecordCountsInput, tool_call_id: str
) -> RecordCountsOutput:
    """Record one count row per item for the business date (event sales.counted per row).
    Amounts are quantity times price; day_total is the stated total when within 5% of the sum,
    else the sum. Raises LookupError for an item the branch does not sell."""
    _check(deps, _as_reporter(COUNTS, deps), "write", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    catalog = {i.id: i for i in _catalog(deps.session, deps.branch.id)}
    for count in args.items:
        if count.item_id not in catalog:
            raise LookupError(f"no item {count.item_id!r} at this branch")
    day = args.business_date or _business_date(deps, tool_call_id)
    rows = [
        store.insert(
            deps.session,
            _new_count(
                deps,
                catalog[c.item_id],
                c.quantity,
                day,
                source_message_id=args.source_message_id,
            ),
            deps.actor,
            action="sales.counted",
            tool_call_id=tool_call_id,
        )
        for c in args.items
    ]
    return RecordCountsOutput(
        recorded=[_count_out(r, catalog[r.item_id]) for r in rows],
        business_date=day,
        day_total=calc.reconcile_total(sum(r.amount for r in rows), args.total),
        currency=rows[0].currency,  # ponytail: one currency per branch in v1
        target_share=target_share(deps, deps.branch.id, day, tool_call_id),
    )


# ---- correct_count ------------------------------------------------------------------------


class CorrectCountInput(BaseModel):
    item_id: str
    quantity: int = Field(ge=0)
    business_date: dt.date | None = Field(None, description="Only when the user names the day")


class CorrectCountOutput(BaseModel):
    corrected: CountOut
    previous_quantity: int
    business_date: dt.date


def correct_count(
    deps: AgentDeps, args: CorrectCountInput, tool_call_id: str
) -> CorrectCountOutput:
    """Replace the reporter's latest live count of the item on the business date (resolved as
    record_counts does) with a new row (event sales.corrected); the old row is marked
    superseded, other reporters' rows and other days stay live. Raises LookupError("count")
    when the reporter has no live count of the item that day, LookupError("business_date")
    in the ambiguous window after closing."""
    _check(deps, _as_reporter(COUNTS, deps), "write", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    day = args.business_date or _business_date(deps, tool_call_id)
    stmt = (
        select(SalesCount)
        .where(SalesCount.branch_id == deps.branch.id)
        .where(SalesCount.reported_by == deps.person.id)
        .where(SalesCount.item_id == args.item_id)
        .where(SalesCount.business_date == day)
        .where(col(SalesCount.superseded_by).is_(None))
        .order_by(col(SalesCount.reported_at).desc(), col(SalesCount.id).desc())
    )
    latest = deps.session.exec(stmt).first()
    item = deps.session.get(RetailItem, args.item_id)
    if latest is None or item is None:
        raise LookupError("count")
    row = store.insert(
        deps.session,
        _new_count(deps, item, args.quantity, latest.business_date, supersedes=latest.id),
        deps.actor,
        action="sales.corrected",
        tool_call_id=tool_call_id,
    )
    store.update(
        deps.session, latest, {"superseded_by": row.id}, deps.actor, tool_call_id=tool_call_id
    )
    return CorrectCountOutput(
        corrected=_count_out(row, item),
        previous_quantity=latest.quantity,
        business_date=latest.business_date,
    )


# ---- today --------------------------------------------------------------------------------


class TodayInput(BaseModel):
    branch_id: str | None = Field(None, description="Another branch, only when the user names one")


class ItemTotal(BaseModel):
    item_id: str
    item: str
    quantity: int
    amount: int


class TodayOutput(BaseModel):
    branch: str
    items: list[ItemTotal]
    total: int
    currency: str
    target_share: int | None
    percent: int | None


def today(deps: AgentDeps, args: TodayInput, tool_call_id: str) -> TodayOutput:
    """Today's live totals per item for the branch, the day's target share and the percent
    difference from it (None without a target)."""
    branch = _branch(deps, args.branch_id, COUNTS, "read", tool_call_id)
    _check(deps, _as_reporter(COUNTS, deps), "read", tool_call_id)
    rows = _live_counts(deps.session, [branch.id], deps.today, deps.today)
    sums = calc.totals(_plain(rows))
    names = _names(deps.session)
    items = [
        ItemTotal(item_id=i, item=names[i].name, quantity=q, amount=a)
        for i, (q, a) in sorted(sums.items(), key=lambda kv: names[kv[0]].sort_order)
    ]
    total = sum(i.amount for i in items)
    share = target_share(deps, branch.id, deps.today, tool_call_id)
    return TodayOutput(
        branch=branch.name,
        items=items,
        total=total,
        currency=_currency(deps.session, branch.id),
        target_share=share,
        percent=calc.compare(total, share),
    )


# ---- period_report ------------------------------------------------------------------------


class PeriodReportInput(BaseModel):
    start: dt.date
    end: dt.date
    branch_id: str | None = Field(
        None, description='Another branch, or "all" (only an owner or admin)'
    )
    item_id: str | None = None


class PeriodRow(BaseModel):
    branch: str
    item_id: str
    item: str
    quantity: int
    amount: int


class PeriodReportOutput(BaseModel):
    rows: list[PeriodRow]
    best_day: dt.date | None
    total: int
    currency: str


def period_report(
    deps: AgentDeps, args: PeriodReportInput, tool_call_id: str
) -> PeriodReportOutput:
    """Live totals per (branch, item) from start to end inclusive, the day with the highest
    amount and the grand total. Raises LookupError when end is before start."""
    if args.branch_id == "all":
        _check(deps, COUNTS, "read_all", tool_call_id)
        stmt = select(Branch).where(Branch.organisation_id == deps.organisation_id)
        branches = list(deps.session.exec(stmt.order_by(col(Branch.name))))
    else:
        branches = [_branch(deps, args.branch_id, COUNTS, "read", tool_call_id)]
    _check(deps, _as_reporter(COUNTS, deps), "read", tool_call_id)
    if args.end < args.start:
        raise LookupError("end is before start")
    names = _names(deps.session)
    rows = _live_counts(deps.session, [b.id for b in branches], args.start, args.end, args.item_id)
    out: list[PeriodRow] = []
    for branch in branches:
        sums = calc.totals(_plain([r for r in rows if r.branch_id == branch.id]))
        for item_id, (quantity, amount) in sorted(
            sums.items(), key=lambda kv: names[kv[0]].sort_order
        ):
            out.append(
                PeriodRow(
                    branch=branch.name,
                    item_id=item_id,
                    item=names[item_id].name,
                    quantity=quantity,
                    amount=amount,
                )
            )
    by_day: dict[dt.date, int] = {}
    for row in rows:
        by_day[row.business_date] = by_day.get(row.business_date, 0) + row.amount
    return PeriodReportOutput(
        rows=out,
        best_day=max(by_day, key=lambda d: by_day[d]) if by_day else None,
        total=sum(by_day.values()),
        currency=_currency(deps.session, branches[0].id),
    )


# ---- set_target ---------------------------------------------------------------------------


class SetTargetInput(BaseModel):
    period: Literal["day", "month"]
    starts_on: dt.date = Field(description="The day, or any day of the month")
    amount: int = Field(gt=0, description="Money target in minor units")
    branch_id: str | None = Field(None, description="Another branch, only when the user names one")


class SetTargetOutput(BaseModel):
    target_id: str
    period: str
    starts_on: dt.date
    amount: int
    currency: str


def set_target(deps: AgentDeps, args: SetTargetInput, tool_call_id: str) -> SetTargetOutput:
    """Store a day or month money target for the branch (event sales.target_set). A month
    target starts on the first of its month."""
    branch = _branch(deps, args.branch_id, TARGETS, "write", tool_call_id)
    _check(deps, TARGETS, "write", tool_call_id)
    starts_on = args.starts_on.replace(day=1) if args.period == "month" else args.starts_on
    row = store.insert(
        deps.session,
        SalesTarget(
            branch_id=branch.id,
            period=args.period,
            starts_on=starts_on,
            amount=args.amount,
            currency=_currency(deps.session, branch.id),
            set_by=deps.person.id,
        ),
        deps.actor,
        action="sales.target_set",
        tool_call_id=tool_call_id,
    )
    return SetTargetOutput(
        target_id=row.id,
        period=row.period,
        starts_on=row.starts_on,
        amount=args.amount,
        currency=row.currency,
    )


# ---- record_note --------------------------------------------------------------------------


class RecordNoteInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000, description="The user's own words")
    asked_message_id: str | None = None


class RecordNoteOutput(BaseModel):
    note_id: str
    business_date: dt.date


def record_note(deps: AgentDeps, args: RecordNoteInput, tool_call_id: str) -> RecordNoteOutput:
    """Store the person's words about today's sales as data (event sales.note_recorded)."""
    _check(deps, _as_reporter(NOTES, deps), "write", tool_call_id)
    row = store.insert(
        deps.session,
        SalesNote(
            branch_id=deps.branch.id,
            business_date=deps.today,
            person_id=deps.person.id,
            text=args.text,
            asked_message_id=args.asked_message_id,
        ),
        deps.actor,
        action="sales.note_recorded",
        tool_call_id=tool_call_id,
    )
    return RecordNoteOutput(note_id=row.id, business_date=row.business_date)


BINDINGS = [
    ToolBinding(
        f"{MANIFEST.id}.record_counts",
        record_counts,
        RecordCountsInput,
        "Record how many of each item the user sold. Give business_date only when the user "
        "names the day.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.correct_count",
        correct_count,
        CorrectCountInput,
        "Replace the user's last count of an item with the corrected quantity.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.today",
        today,
        TodayInput,
        "Today's sales per item for the branch, with the day's target and percent.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.period_report",
        period_report,
        PeriodReportInput,
        "Sales per branch and item between two dates, with the best day.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.set_target",
        set_target,
        SetTargetInput,
        "Set a day or month sales target for the branch.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.record_note",
        record_note,
        RecordNoteInput,
        "Store what the user says about why today's sales were up or down.",
    ),
]
