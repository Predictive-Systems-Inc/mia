"""Sales supervisor tools: typed inputs and outputs, permission checked data access, writes only
through mia.core.store. Target share and totals are pure code in calc.py.

Branch scoping: every tool works on the person's own branch. Naming another branch of the
organisation (or "all") needs the read_all or write_all action on the data resource in RBAC
(admin, and the owner through the hierarchy); anyone else gets PermissionDenied. An owner or
admin who names no branch in `today` sees every branch.

The business date of a count (the retail template's hours.business_date) is the day before
only just after a late closing, before the next opening; it is never asked.
"""

import datetime as dt
from collections.abc import Sequence
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.sales_supervisor import MANIFEST, calc
from mia.agents.sales_supervisor.models import SalesCount, SalesNote, SalesTarget
from mia.core import store
from mia.core.db import utcnow
from mia.core.models import Branch, Event, Message, Person
from mia.core.rbac import Resource, get_rbac
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailBranchHours, RetailItem

LEADS = {"owner", "admin"}  # whose target wins and who sees every branch by default (not access)
COUNTS = Resource(kind="data", name=SalesCount.__tablename__)
TARGETS = Resource(kind="data", name=SalesTarget.__tablename__)
NOTES = Resource(kind="data", name=SalesNote.__tablename__)
ITEMS = Resource(kind="data", name=RetailItem.__tablename__)
WHY_ASKED = "sales.why_asked"  # the due work's marker of a why question (due.WHY)
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
    """True for an owner or admin (ranks targets and picks a default; never grants access)."""
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


def _branches(
    deps: AgentDeps, branch_id: str | None, resource: Resource, action: str, tool_call_id: str
) -> list[Branch]:
    """Every branch of the organisation by name for "all" (after the `<action>_all` check),
    else the one branch _branch gives."""
    if branch_id != "all":
        return [_branch(deps, branch_id, resource, action, tool_call_id)]
    _check(deps, resource, f"{action}_all", tool_call_id)
    stmt = select(Branch).where(Branch.organisation_id == deps.organisation_id)
    return list(deps.session.exec(stmt.order_by(col(Branch.name))))


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
    return retail_hours.load(deps.session, branch_id)


def target_share(deps: AgentDeps, branch_id: str, day: dt.date, tool_call_id: str) -> int | None:
    """The branch's money target for the day (see _share), after the targets and the
    branch-hours read checks."""
    _check(deps, TARGETS, "read", tool_call_id)
    return _share(deps.session, branch_id, _hours(deps, branch_id, tool_call_id), day)


def _share(
    session: Session, branch_id: str, hours: Sequence[RetailBranchHours], day: dt.date
) -> int | None:
    """The branch's money target for the day without a permission check (callers check, or are
    the system tick); reads only. A day target wins over a month target; between targets of the
    same period, one set by an owner or admin wins, then the newest. A zero target counts."""
    stmt = (
        select(SalesTarget)
        .where(SalesTarget.branch_id == branch_id)
        .where(col(SalesTarget.amount).is_not(None))
        .where(col(SalesTarget.starts_on) <= day)
    )
    rows = session.exec(stmt).all()
    setter_ids = {r.set_by for r in rows}
    setters = {p.id: p for p in session.exec(select(Person).where(col(Person.id).in_(setter_ids)))}
    open_day = retail_hours.open_days(hours)
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


def _reported_at(deps: AgentDeps, source_message_id: str | None) -> dt.datetime:
    """When the count was said: the source message's time for a resumed turn (answered later,
    for example after a Jev outage) when the message is the person's own, else now."""
    if deps.resumed and source_message_id is not None:
        message = deps.session.get(Message, source_message_id)
        if message is not None and message.sender_id == deps.person.id:
            return message.created_at
    return utcnow()


def _business_day(
    deps: AgentDeps, branch: Branch, tool_call_id: str, at: dt.datetime | None = None
) -> dt.date:
    """The branch's business date at `at` (default now): hours.business_date with the branch's
    hours, after the branch-hours read check."""
    rows = _hours(deps, branch.id, tool_call_id)
    return retail_hours.business_date_at(branch, rows, at or utcnow())


def _count_day(
    deps: AgentDeps, stated: dt.date | None, source_message_id: str | None, tool_call_id: str
) -> dt.date:
    """The business date of a count: the stated day when it is the local today or yesterday at
    the branch, else the rule. Raises LookupError("business_date") for any other stated day."""
    at = _reported_at(deps, source_message_id)
    if stated is None:
        return _business_day(deps, deps.branch, tool_call_id, at)
    local = at.astimezone(ZoneInfo(deps.branch.timezone)).date()
    if stated not in (local, local - dt.timedelta(days=1)):
        raise LookupError("business_date")
    return stated


def record_counts(
    deps: AgentDeps, args: RecordCountsInput, tool_call_id: str
) -> RecordCountsOutput:
    """Record one count row per item for the business date (event sales.counted per row).
    Amounts are quantity times price; a stated total is not stored (Q44). day_total is the
    branch's live total for the business date after the insert, every reporter included.
    Raises LookupError for an item the branch does not sell, LookupError("business_date") for a
    stated day other than today or yesterday."""
    _check(deps, _as_reporter(COUNTS, deps), "write", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    catalog = {i.id: i for i in _catalog(deps.session, deps.branch.id)}
    for count in args.items:
        if count.item_id not in catalog:
            raise LookupError(f"no item {count.item_id!r} at this branch")
    day = _count_day(deps, args.business_date, args.source_message_id, tool_call_id)
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
    live = _live_counts(deps.session, [deps.branch.id], day, day)
    return RecordCountsOutput(
        recorded=[_count_out(r, catalog[r.item_id]) for r in rows],
        business_date=day,
        day_total=sum(a for _, a in calc.totals(_plain(live)).values()),
        currency=rows[0].currency,  # ponytail: one currency per branch in v1
        target_share=target_share(deps, deps.branch.id, day, tool_call_id),
    )


# ---- correct_count ------------------------------------------------------------------------


class CorrectCountInput(BaseModel):
    item_id: str
    quantity: int = Field(ge=0)
    business_date: dt.date | None = Field(None, description="Only when the user names the day")
    source_message_id: str | None = None


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
    for a stated day other than today or yesterday."""
    _check(deps, _as_reporter(COUNTS, deps), "write", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    day = _count_day(deps, args.business_date, args.source_message_id, tool_call_id)
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
    branch_id: str | None = Field(
        None, description='Another branch, or "all" (only an owner or admin)'
    )


class ItemTotal(BaseModel):
    item_id: str
    item: str
    quantity: int
    amount: int


class BranchToday(BaseModel):
    branch: str
    items: list[ItemTotal]
    total: int
    currency: str
    target_share: int | None
    percent: int | None


class TodayOutput(BaseModel):
    branches: list[BranchToday]


def _branch_today(deps: AgentDeps, branch: Branch, tool_call_id: str) -> BranchToday:
    day = _business_day(deps, branch, tool_call_id)
    sums = calc.totals(_plain(_live_counts(deps.session, [branch.id], day, day)))
    names = _names(deps.session)
    items = [
        ItemTotal(item_id=i, item=names[i].name, quantity=q, amount=a)
        for i, (q, a) in sorted(sums.items(), key=lambda kv: names[kv[0]].sort_order)
    ]
    total = sum(i.amount for i in items)
    share = target_share(deps, branch.id, day, tool_call_id)
    return BranchToday(
        branch=branch.name,
        items=items,
        total=total,
        currency=_currency(deps.session, branch.id),
        target_share=share,
        percent=calc.compare(total, share),
    )


def today(deps: AgentDeps, args: TodayInput, tool_call_id: str) -> TodayOutput:
    """The live totals per item for each branch's business date (hours.business_date), with the
    day's target share and the percent difference from it (None without a target). One entry
    for the branch named, every branch for "all", and for an owner or admin who names none."""
    branch_id = args.branch_id
    if branch_id is None and _is_lead(deps.person):
        branch_id = "all"
    branches = _branches(deps, branch_id, COUNTS, "read", tool_call_id)
    _check(deps, _as_reporter(COUNTS, deps), "read", tool_call_id)
    return TodayOutput(branches=[_branch_today(deps, b, tool_call_id) for b in branches])


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
    branches = _branches(deps, args.branch_id, COUNTS, "read", tool_call_id)
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
    branch_id: str | None = Field(
        None, description='Another branch, or "all" (only an owner or admin)'
    )


class SetTargetOutput(BaseModel):
    target_ids: list[str]
    period: str
    starts_on: dt.date
    amount: int
    currency: str


def set_target(deps: AgentDeps, args: SetTargetInput, tool_call_id: str) -> SetTargetOutput:
    """Store a day or month money target for the branch, or the same target on every branch for
    "all" (one row and one event sales.target_set per branch). A month target starts on the
    first of its month."""
    branches = _branches(deps, args.branch_id, TARGETS, "write", tool_call_id)
    _check(deps, TARGETS, "write", tool_call_id)
    starts_on = args.starts_on.replace(day=1) if args.period == "month" else args.starts_on
    rows = [
        store.insert(
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
        for branch in branches
    ]
    return SetTargetOutput(
        target_ids=[r.id for r in rows],
        period=args.period,
        starts_on=starts_on,
        amount=args.amount,
        currency=rows[0].currency,  # ponytail: one currency per organisation in v1
    )


# ---- record_note --------------------------------------------------------------------------


class RecordNoteInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000, description="The user's own words")
    asked_message_id: str | None = None
    themes: list[str] = Field(default_factory=list, description="Why sales went well, by theme")


class RecordNoteOutput(BaseModel):
    note_id: str
    business_date: dt.date


def _asked_day(session: Session, branch_id: str, message_id: str | None) -> dt.date | None:
    """The business date of the why question `message_id`, from its sales.why_asked marker."""
    if message_id is None:
        return None
    stmt = select(Event).where(Event.action == WHY_ASKED).where(Event.entity_id == branch_id)
    for marker in session.exec(stmt):
        after = marker.after or {}
        if message_id in (after.get("message_ids") or []):
            return dt.date.fromisoformat(str(after["date"]))
    return None


def record_note(deps: AgentDeps, args: RecordNoteInput, tool_call_id: str) -> RecordNoteOutput:
    """Store the person's words about a day's sales as data (event sales.note_recorded). The
    note's business date is the asked why question's (its sales.why_asked marker), else the
    branch's business date now."""
    _check(deps, _as_reporter(NOTES, deps), "write", tool_call_id)
    day = _asked_day(deps.session, deps.branch.id, args.asked_message_id)
    row = store.insert(
        deps.session,
        SalesNote(
            branch_id=deps.branch.id,
            business_date=day or _business_day(deps, deps.branch, tool_call_id),
            person_id=deps.person.id,
            text=args.text,
            asked_message_id=args.asked_message_id,
            themes=args.themes,
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
