"""Sales supervisor tools: typed inputs and outputs, permission checked data access, writes only
through mia.core.store. Target share and totals are pure code in calc.py.

Branch scoping: every tool works on the person's own branch, or on the shop of her checked-in
visit of the day when she covers another (at_visit, applied once to the turn's deps). Naming another branch of the
organisation (or "all") needs the read_all or write_all action on the data resource in RBAC
(admin, and the owner through the hierarchy); anyone else gets PermissionDenied. An owner or
admin who names no branch in `today` sees every branch. A supervisor also reads the kiosks
they are assigned to (D50, deps.kiosks: home plus active assignments) without read_all, and
"all" is those kiosks for them; writes keep needing write_all.

The business date of a count (the retail template's hours.business_date) is the day before
only just after a late closing, before the next opening; it is never asked.
"""

import dataclasses
import datetime as dt
from collections.abc import Callable, Sequence
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.sales_supervisor import MANIFEST, calc
from mia.agents.sales_supervisor import report as report_form
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import TextBlock
from mia.chat.channels import notify
from mia.core import approvals, assignments, events, sales, scheduling, store
from mia.core.db import utcnow
from mia.core.models import (
    TENDERS,
    Actor,
    Approval,
    Branch,
    Event,
    Message,
    Person,
    SalesCount,
    SalesNote,
    SalesPayment,
    SalesReceipt,
    SalesReceiptLine,
    SalesSession,
    SalesTarget,
    Tender,
    Visit,
)
from mia.core.money import format_int, format_money
from mia.core.rbac import Resource, get_rbac
from mia.core.sales import live_counts
from mia.i18n import t
from mia.templates.retail import hours as retail_hours
from mia.templates.retail import items as retail_items
from mia.templates.retail.models import RetailBranchHours, RetailItem

LEADS = {"owner", "admin"}  # whose target wins and who sees every branch by default (not access)
COUNTS = Resource(kind="data", name=SalesCount.__tablename__)
TARGETS = Resource(kind="data", name=SalesTarget.__tablename__)
NOTES = Resource(kind="data", name=SalesNote.__tablename__)
ITEMS = Resource(kind="data", name=RetailItem.__tablename__)
WHY_ASKED = "sales.why_asked"  # the due work's marker of a why question (due.WHY)
HOURS = Resource(kind="data", name=RetailBranchHours.__tablename__)
SESSIONS = Resource(kind="data", name=SalesSession.__tablename__)
RECEIPT_TABLES = [
    Resource(kind="data", name=t.__tablename__)
    for t in (SalesReceipt, SalesReceiptLine, SalesPayment)
]
# What sales.sale_rows reads (sales.day_sales): the counts, or the receipt tables on a receipts day.
SALES = [COUNTS, *RECEIPT_TABLES]


# ---- shared helpers -----------------------------------------------------------------------

VISITS = Resource(kind="data", name="core.visit")


def at_visit(deps: AgentDeps) -> AgentDeps:
    """deps at the shop of the person's checked-in visit of the business date (a D39 cover's
    kiosk, the latest check-in), with that shop's local date; deps unchanged without one or
    when the visits read is not allowed. Every sales read and write of a turn then uses the
    shop she sells at: her drawer, her receipts and her counts agree. It applies to anyone
    with a checked-in visit elsewhere (D39), head staff's today and set_target included."""
    if not get_rbac().check(
        deps.actor,
        VISITS.model_copy(update={"owner_id": deps.person.id}),
        "read",
        session=deps.session,
    ):
        return deps
    rows = deps.session.exec(
        select(Visit).where(Visit.date == deps.today, col(Visit.actual_start).is_not(None))
    )
    mine = [v for v in rows if deps.person.id in v.assigned_person_ids]
    visit = max(mine, key=lambda v: v.actual_start or utcnow(), default=None)
    if visit is None or visit.branch_id == deps.branch.id:
        return deps
    branch = deps.session.get(Branch, visit.branch_id)
    if branch is None or branch.organisation_id != deps.organisation_id:
        return deps
    # ponytail: the kiosk's local date; the late-closing rule is applied by each tool as before
    today = utcnow().astimezone(ZoneInfo(branch.timezone)).date()
    return dataclasses.replace(deps, branch=branch, today=today)


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
    """The person's branch, a kiosk they are assigned to for a read (D50, deps.kiosks), or
    another branch of the organisation when RBAC allows `<action>_all` on the resource
    (logged as an rbac event; PermissionDenied otherwise). The person's own Branch row is
    read without a check: it is already in deps. Raises LookupError for a branch outside
    the organisation."""
    if branch_id is None or branch_id == deps.branch.id:
        return deps.branch
    if action != "read" or branch_id not in deps.kiosks():
        _check(deps, resource, f"{action}_all", tool_call_id)
    branch = deps.session.get(Branch, branch_id)
    if branch is None or branch.organisation_id != deps.organisation_id:
        raise LookupError("branch")
    return branch


def _branches(
    deps: AgentDeps, branch_id: str | None, resource: Resource, action: str, tool_call_id: str
) -> list[Branch]:
    """Every shop of the organisation by name for "all" (after the `<action>_all` check; the
    commissary sells nothing), for a read without it the shops of deps.kiosks when there are
    two or more (D50: an assigned supervisor's kiosks, never others), else the one branch
    _branch gives."""
    if branch_id != "all":
        return [_branch(deps, branch_id, resource, action, tool_call_id)]
    shops = retail_hours.shops(deps.session, deps.organisation_id)
    mine = [b for b in shops if b.id in deps.kiosks()] if action == "read" else []
    if len(mine) > 1 and not get_rbac().check(deps.actor, resource, f"{action}_all"):
        return mine
    _check(deps, resource, f"{action}_all", tool_call_id)
    return shops


def _beyond(deps: AgentDeps, branches: Sequence[Branch]) -> bool:
    """True when a branch is outside the person's kiosks (deps.kiosks): its reads need
    read_all."""
    kiosks = deps.kiosks()
    return any(b.id not in kiosks for b in branches)


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
    tender: str


def _count_out(row: SalesCount, item: RetailItem) -> CountOut:
    return CountOut(
        count_id=row.id,
        item_id=row.item_id,
        item=item.name,
        quantity=row.quantity,
        amount=row.amount,
        tender=row.tender,
    )


def _new_count(
    deps: AgentDeps,
    item: RetailItem,
    quantity: int,
    day: dt.date,
    *,
    supersedes: str | None = None,
    source_message_id: str | None = None,
    tender: str = "cash",
) -> SalesCount:
    return SalesCount(
        branch_id=deps.branch.id,
        item_id=item.id,
        quantity=quantity,
        amount=quantity * retail_items.price_on(deps.session, item, deps.branch.id, day),
        currency=item.currency,
        reported_at=utcnow(),
        reported_by=deps.person.id,
        business_date=day,
        supersedes=supersedes,
        source_message_id=source_message_id,
        tender=tender,
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
    tender: Tender = Field("cash", description="How it was paid; cash unless the user says")


class RecordCountsOutput(BaseModel):
    status: Literal["recorded", "total_differs"] = "recorded"
    recorded: list[CountOut]
    total: int  # the computed sum of quantity times price of this count's lines
    typed_total: int | None = None  # the stated total
    business_date: dt.date
    reported_at: dt.datetime  # when the count was said, in the branch's time zone
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
    Amounts are quantity times price; a stated total is never stored, and one that differs
    from the computed sum writes nothing (total_differs, both figures; Q44). day_total is the
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
    total = sum(
        c.quantity * retail_items.price_on(deps.session, catalog[c.item_id], deps.branch.id, day)
        for c in args.items
    )
    reported_at = _reported_at(deps, args.source_message_id).astimezone(
        ZoneInfo(deps.branch.timezone)
    )
    if args.total is not None and args.total != total:
        return RecordCountsOutput(
            status="total_differs",
            recorded=[],
            total=total,
            typed_total=args.total,
            business_date=day,
            reported_at=reported_at,
            day_total=0,  # nothing recorded; the reply asks
            currency=catalog[args.items[0].item_id].currency,
            target_share=None,
        )
    rows = [
        store.insert(
            deps.session,
            _new_count(
                deps,
                catalog[c.item_id],
                c.quantity,
                day,
                source_message_id=args.source_message_id,
                tender=args.tender,
            ),
            deps.actor,
            action="sales.counted",
            tool_call_id=tool_call_id,
        )
        for c in args.items
    ]
    live = live_counts(deps.session, [deps.branch.id], day, day)
    return RecordCountsOutput(
        recorded=[_count_out(r, catalog[r.item_id]) for r in rows],
        total=total,
        typed_total=args.total,
        business_date=day,
        reported_at=reported_at,
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
        _new_count(
            deps,
            item,
            args.quantity,
            latest.business_date,
            supersedes=latest.id,
            tender=latest.tender,
        ),
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
    """The branch's business date from its one source (sales.day_sales), after the read check
    on that source's tables (counts, or the three receipt tables on a receipts kiosk)."""
    day = _business_day(deps, branch, tool_call_id)
    tables = [COUNTS] if sales.source_of(branch, day) == "counts" else RECEIPT_TABLES
    for table in tables:
        _check(deps, _as_reporter(table, deps), "read", tool_call_id)
    sums = sales.day_sales(deps.session, branch.id, day).by_item
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
    return TodayOutput(branches=[_branch_today(deps, b, tool_call_id) for b in branches])


# ---- period_report ------------------------------------------------------------------------


class PeriodReportInput(BaseModel):
    start: dt.date
    end: dt.date
    branch_id: str | None = Field(
        None, description='Another branch, or "all" (only an owner or admin)'
    )
    item_id: str | None = None
    breakdown: Literal["item", "kiosk"] | None = Field(
        None, description="Per item or per kiosk, when the message asks (code reads the words)"
    )


class PeriodRow(BaseModel):
    branch: str
    item_id: str
    item: str
    quantity: int
    amount: int


class BreakdownLine(BaseModel):
    name: str  # the item or the kiosk
    quantity: int
    amount: int


class PeriodReportOutput(BaseModel):
    rows: list[PeriodRow]
    best_day: dt.date | None
    total: int
    currency: str
    breakdown: list[BreakdownLine] = []  # per item (menu order) or per kiosk, when asked


def period_report(
    deps: AgentDeps, args: PeriodReportInput, tool_call_id: str
) -> PeriodReportOutput:
    """Totals per (branch, item) from start to end inclusive, each date from its one source
    (sales.sale_rows: counts, or receipts on a receipts day), the day with the highest amount
    and the grand total; with a breakdown, the period's sums per item (menu order, every
    branch read together) or per kiosk (the branches' order). Raises LookupError when end is
    before start, and sales.SalesRangeError("range") for more than MAX_SALES_DAYS days."""
    branches = _branches(deps, args.branch_id, COUNTS, "read", tool_call_id)
    if _beyond(deps, branches):
        for table in RECEIPT_TABLES:
            _check(deps, table, "read_all", tool_call_id)
    for table in SALES:
        _check(deps, _as_reporter(table, deps), "read", tool_call_id)
    if args.end < args.start:
        raise LookupError("end is before start")
    names = _names(deps.session)
    rows = sales.sale_rows(
        deps.session, [b.id for b in branches], args.start, args.end, args.item_id
    )
    out: list[PeriodRow] = []
    for branch in branches:
        mine = [r for r in rows if r.branch_id == branch.id]
        sums = calc.totals([calc.Count(r.item_id, r.quantity, r.amount, None) for r in mine])
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
        breakdown=_breakdown(out, args.breakdown, names),
    )


def _breakdown(
    rows: list[PeriodRow], by: str | None, names: dict[str, RetailItem]
) -> list[BreakdownLine]:
    """The (branch, item) rows summed per item in menu order or per kiosk in row order; empty
    without a breakdown."""
    if by is None:
        return []
    sums: dict[str, BreakdownLine] = {}
    for r in rows:
        key, name = (r.item_id, r.item) if by == "item" else (r.branch, r.branch)
        line = sums.setdefault(key, BreakdownLine(name=name, quantity=0, amount=0))
        line.quantity += r.quantity
        line.amount += r.amount
    keys = sorted(sums, key=lambda k: names[k].sort_order) if by == "item" else list(sums)
    return [sums[k] for k in keys]


# ---- report (teach-Mia 4c) ----------------------------------------------------------------


class ReportInput(BaseModel):
    form: report_form.ReportForm


class ReportOutput(BaseModel):
    result: report_form.Result


def _report_branches(deps: AgentDeps, form: report_form.ReportForm, tcid: str) -> list[Branch]:
    """The shops a form reads: every shop for "all" or a kiosk grouping with no kiosk named,
    else the named kiosks, else the person's own; another kiosk needs read_all (_branch)."""
    if report_form.ALL in form.kiosks or (form.group_by == "kiosk" and not form.kiosks):
        return _branches(deps, "all", COUNTS, "read", tcid)
    named: list[str | None] = [*form.kiosks] or [None]
    found = [_branch(deps, k, COUNTS, "read", tcid) for k in named]
    return list({b.id: b for b in found}.values())


def report(deps: AgentDeps, args: ReportInput, tool_call_id: str) -> ReportOutput:
    """A report form run by code (report.run) after period_report's checks: another kiosk or
    every kiosk needs read_all on the counts and the receipt tables; the sales read is checked
    as the reporter (a clerk then reads her own kiosk only, D49); a clerk grouping needs read on
    sales_counts without that shortcut (never another clerk's figures for a clerk). Raises
    LookupError with the report.ReportError code (range answers sales.refused.range, also for
    more than MAX_SALES_DAYS days times shops), "form" for
    an unknown item id and "branch" for a kiosk outside the organisation."""
    form = args.form
    branches = _report_branches(deps, form, tool_call_id)
    if _beyond(deps, branches):
        for table in RECEIPT_TABLES:
            _check(deps, table, "read_all", tool_call_id)
    for table in SALES:
        _check(deps, _as_reporter(table, deps), "read", tool_call_id)
    if form.group_by == "clerk":
        _check(deps, COUNTS, "read", tool_call_id)
    try:
        start, end = report_form.resolve(form, deps.today, deps.lang)
    except report_form.ReportError as exc:
        raise LookupError(exc.code) from exc
    days = (end - start).days + 1
    reads = days * len(branches) * (1 if form.compare_to == "none" else 2)
    if reads > sales.MAX_SALES_DAYS:  # days times shops: one read stays bounded
        raise LookupError("range")
    names = _names(deps.session)
    if any(i not in names for i in form.items):
        raise LookupError("form")
    clerks = {p.id: p.name for p in deps.session.exec(select(Person))}
    deps.session.commit()  # rule 11: the rbac events are written; the long read holds no lock
    result = report_form.run(deps.session, branches, form, start, end, names, clerks)
    return ReportOutput(result=result)


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


# ---- record_receipt -----------------------------------------------------------------------


class RecordReceiptInput(BaseModel):
    items: list[CountIn] = Field(min_length=1)
    tender: Tender
    typed_total: int | None = Field(None, ge=0, description="The total typed, minor units")
    source_message_id: str | None = None
    confirm: bool = False  # a count rung as a receipt: computed and asked, never written


class ReceiptLineOut(BaseModel):
    item_id: str
    item: str
    quantity: int
    unit_price: int
    line_total: int


class RecordReceiptOutput(BaseModel):
    status: Literal["recorded", "total_differs", "no_session", "confirm"]
    receipt_no: str | None
    lines: list[ReceiptLineOut]
    total: int
    typed_total: int | None
    tender: str
    currency: str


def _next_receipt_no(session: Session, branch_id: str) -> str:
    """One more than the highest all-digit receipt number of the branch, from "1". Call it
    under events.write_lock so two receipts never take the same number."""
    # ponytail: a running integer over the branch's own numbers, a full scan per receipt; a max
    # query or a per-branch counter when that is slow. A till brings its own numbering.
    numbers = session.exec(
        select(SalesReceipt.receipt_no).where(SalesReceipt.branch_id == branch_id)
    )
    return str(1 + max((int(n) for n in numbers if n.isascii() and n.isdigit()), default=0))


def record_receipt(
    deps: AgentDeps, args: RecordReceiptInput, tool_call_id: str
) -> RecordReceiptOutput:
    """Ring up one sale on the clerk's open session of the business date, paid in full by one
    tender, at the dated prices (core.sales.record_receipt, source chat). Nothing is written
    when the typed total differs from the computed one (total_differs), when args.confirm asks
    first (confirm: the computed receipt, for the turn's question) or the clerk has no open
    session of the business date (no_session; a session is never opened here). Raises
    LookupError("counts_kiosk") on a kiosk that reports counts, LookupError for an item the
    branch does not sell, LookupError(<code>) for a refused core write."""
    for table in RECEIPT_TABLES:
        _check(deps, _as_reporter(table, deps), "write", tool_call_id)
    _check(deps, _as_reporter(SESSIONS, deps), "read", tool_call_id)  # her open session
    _check(deps, _as_reporter(RECEIPT_TABLES[0], deps), "read", tool_call_id)  # the next number
    _check(deps, ITEMS, "read", tool_call_id)
    day = _business_day(deps, deps.branch, tool_call_id)
    if sales.source_of(deps.branch, day) == "counts":
        raise LookupError("counts_kiosk")
    catalog = {i.id: i for i in _catalog(deps.session, deps.branch.id)}
    lines = []
    for c in args.items:
        found = catalog.get(c.item_id)
        if found is None:
            raise LookupError(f"no item {c.item_id!r} at this branch")
        price = retail_items.price_on(deps.session, found, deps.branch.id, day)
        line = ReceiptLineOut(
            item_id=found.id,
            item=found.name,
            quantity=c.quantity,
            unit_price=price,
            line_total=c.quantity * price,
        )
        lines.append(line)
    total = sum(line.line_total for line in lines)

    def out(
        status: Literal["recorded", "total_differs", "no_session", "confirm"],
        no: str | None = None,
    ) -> RecordReceiptOutput:
        return RecordReceiptOutput(
            status=status,
            receipt_no=no,
            lines=lines,
            total=total,
            typed_total=args.typed_total,
            tender=args.tender,
            currency=catalog[lines[0].item_id].currency,
        )

    if args.typed_total is not None and args.typed_total != total:
        return out("total_differs")
    if args.confirm:
        return out("confirm")
    events.write_lock(deps.session)  # the session and the next number decide the write
    mine = deps.session.exec(
        select(SalesSession).where(
            SalesSession.branch_id == deps.branch.id,
            SalesSession.person_id == deps.person.id,
            SalesSession.state == "open",
            SalesSession.business_date == day,
        )
    ).first()
    if mine is None:
        return out("no_session")
    no = _next_receipt_no(deps.session, deps.branch.id)
    try:
        sales.record_receipt(
            deps.session,
            deps.actor,
            mine,
            no,
            utcnow(),
            [sales.LineIn(item_id=c.item_id, quantity=c.quantity) for c in args.items],
            [sales.PaymentIn(tender=args.tender, amount=total)],
            source="chat",
            source_message_id=args.source_message_id,
        )
    except sales.SalesError as exc:
        raise LookupError(str(exc)) from exc
    return out("recorded", no)


# ---- void_receipt and refund_receipt (risk money, approval always) --------------------------

VOID_TOOL = f"{MANIFEST.id}.void_receipt"
REFUND_TOOL = f"{MANIFEST.id}.refund_receipt"
RECEIPTS = RECEIPT_TABLES[0]


class VoidReceiptInput(BaseModel):
    receipt_no: str = Field(min_length=1, max_length=32)
    reason: str = Field("", max_length=200, description="The sender's words, stored as data")


class RefundReceiptInput(BaseModel):
    receipt_no: str = Field(min_length=1, max_length=32)
    items: list[CountIn] = Field(
        default_factory=list, description="What comes back; empty is every line in full"
    )
    reason: str = Field("", max_length=200, description="The sender's words, stored as data")


class ReceiptOut(BaseModel):
    receipt_no: str
    kind: str
    status: str
    time: str  # HH:MM at the branch
    lines: list[ReceiptLineOut]
    total: int
    tender: str  # the one payment's tender, else "split"
    currency: str


def receipt_out(session: Session, branch: Branch, r: SalesReceipt) -> ReceiptOut:
    """The receipt with its lines (item names), its local time and its tender. Reads only."""
    names = _names(session)
    rows = session.exec(
        select(SalesReceiptLine)
        .where(SalesReceiptLine.receipt_id == r.id)
        .order_by(col(SalesReceiptLine.id))
    )
    lines = [
        ReceiptLineOut(
            item_id=x.item_id,
            item=names[x.item_id].name,
            quantity=x.quantity,
            unit_price=x.unit_price,
            line_total=x.line_total,
        )
        for x in rows
    ]
    tenders = {
        p.tender for p in session.exec(select(SalesPayment).where(SalesPayment.receipt_id == r.id))
    }
    return ReceiptOut(
        receipt_no=r.receipt_no,
        kind=r.kind,
        status=r.status,
        time=r.sold_at.astimezone(ZoneInfo(branch.timezone)).strftime("%H:%M"),
        lines=lines,
        total=r.total,
        tender=tenders.pop() if len(tenders) == 1 else "split",
        currency=r.currency,
    )


def _find_receipt(deps: AgentDeps, receipt_no: str, tool_call_id: str) -> SalesReceipt:
    """The branch's receipt by number: the person's own, or another clerk's only with the
    data:sales_receipts read right (head staff). LookupError("receipt") otherwise, the same
    answer as an unknown number."""
    _check(deps, _as_reporter(RECEIPTS, deps), "read", tool_call_id)
    r = deps.session.exec(
        select(SalesReceipt).where(
            SalesReceipt.branch_id == deps.branch.id, SalesReceipt.receipt_no == receipt_no
        )
    ).first()
    mine = r is not None and r.clerk_id == deps.person.id
    if r is None or not (mine or get_rbac().check(deps.actor, RECEIPTS, "read")):
        raise LookupError("receipt")
    return r


class ReceiptsInput(BaseModel):
    which: Literal["today", "last"] = "today"


class ReceiptsOutput(BaseModel):
    branch: str
    receipts: list[ReceiptOut]
    by_tender: dict[str, int]  # the paid receipts' payments, refunds negative
    total: int
    currency: str


def receipts(deps: AgentDeps, args: ReceiptsInput, tool_call_id: str) -> ReceiptsOutput:
    """The branch's receipts of the business date the person may read (sales.receipts checks
    the rights: a clerk gets her own, head staff the branch's), oldest first; `last` keeps only
    the latest. by_tender and total are over the kept paid receipts' payments (head staff's
    today equals day_sales(...).by_tender). LookupError("counts_kiosk") on a counts kiosk."""
    for table in RECEIPT_TABLES:
        _check(deps, _as_reporter(table, deps), "read", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    day = _business_day(deps, deps.branch, tool_call_id)
    if sales.source_of(deps.branch, day) == "counts":
        raise LookupError("counts_kiosk")
    rows = sales.receipts(deps.session, deps.actor, deps.branch.id, day)
    if args.which == "last":
        rows = rows[-1:]
    paid = [r.id for r in rows if r.status == "paid"]
    by_tender: dict[str, int] = {}
    for p in deps.session.exec(select(SalesPayment).where(col(SalesPayment.receipt_id).in_(paid))):
        by_tender[p.tender] = by_tender.get(p.tender, 0) + p.amount
    return ReceiptsOutput(
        branch=deps.branch.name,
        receipts=[receipt_out(deps.session, deps.branch, r) for r in rows],
        by_tender=by_tender,
        total=sum(by_tender.values()),
        currency=_currency(deps.session, deps.branch.id),
    )


# ---- item_codes ---------------------------------------------------------------------------


class ItemCodesInput(BaseModel):
    pass


class ItemCode(BaseModel):
    item: str
    codes: list[str]
    price: int  # minor units, the branch's dated price on its business date


class ItemCodesOutput(BaseModel):
    branch: str
    items: list[ItemCode]
    currency: str


def item_codes(deps: AgentDeps, args: ItemCodesInput, tool_call_id: str) -> ItemCodesOutput:
    """Every active item of the person's branch in menu order with its short codes and its
    price on the branch's business date (items.price_on: the dated price, else the default),
    after the items read check. LookupError when the branch has no items."""
    _check(deps, ITEMS, "read", tool_call_id)
    day = _business_day(deps, deps.branch, tool_call_id)
    catalog = _catalog(deps.session, deps.branch.id)
    return ItemCodesOutput(
        branch=deps.branch.name,
        items=[
            ItemCode(
                item=i.name,
                codes=i.short_codes,
                price=retail_items.price_on(deps.session, i, deps.branch.id, day),
            )
            for i in catalog
        ],
        currency=_currency(deps.session, deps.branch.id),
    )


def _on_receipts(deps: AgentDeps, tool_call_id: str) -> None:
    if sales.source_of(deps.branch, _business_day(deps, deps.branch, tool_call_id)) == "counts":
        raise LookupError("counts_kiosk")


def refund_lines(
    session: Session, sale: SalesReceipt, items: Sequence[CountIn]
) -> list[sales.LineIn]:
    """Each item to the first sale line of that item, its quantity negative; no items is every
    line in full. LookupError("refunded_line") for an item not on the sale."""
    rows = list(
        session.exec(
            select(SalesReceiptLine)
            .where(SalesReceiptLine.receipt_id == sale.id)
            .order_by(col(SalesReceiptLine.id))
        )
    )
    if not items:
        pairs = [(x, x.quantity) for x in rows]
    else:
        pairs = []
        for c in items:
            line = next((x for x in rows if x.item_id == c.item_id), None)
            if line is None:
                raise LookupError("refunded_line")
            pairs.append((line, c.quantity))
    return [sales.LineIn(item_id=x.item_id, quantity=-q, refunded_line_id=x.id) for x, q in pairs]


def _refund_amount(deps: AgentDeps, sale: SalesReceipt, lines: Sequence[sales.LineIn]) -> int:
    try:
        return sales.refund_total(deps.session, sale, lines)
    except sales.SalesError as exc:
        raise LookupError(str(exc)) from exc


def check_void(deps: AgentDeps, args: VoidReceiptInput, tool_call_id: str) -> None:
    """The precheck of void_receipt (before any card): a receipts kiosk (counts_kiosk), a
    receipt the person may void (receipt) and core's void checks (session_closed, status,
    kind, refunded)."""
    _on_receipts(deps, tool_call_id)
    r = _find_receipt(deps, args.receipt_no, tool_call_id)
    try:
        sales.check_void(deps.session, r)
    except sales.SalesError as exc:
        raise LookupError(str(exc)) from exc


def check_refund(deps: AgentDeps, args: RefundReceiptInput, tool_call_id: str) -> None:
    """The precheck of refund_receipt (before any card): a receipts kiosk, a clerk with a
    drawer to pay it out of (needs_drawer for head staff), a receipt the person may refund,
    and lines core would accept (refund_of, refunded_line, quantity)."""
    _on_receipts(deps, tool_call_id)
    if not scheduling.is_staff(deps.person):
        raise LookupError("needs_drawer")  # head staff have no drawer to pay it out of
    sale = _find_receipt(deps, args.receipt_no, tool_call_id)
    _refund_amount(deps, sale, refund_lines(deps.session, sale, args.items))


def _first(person: Person) -> str:
    return person.name.split()[0]


def _lang(person: Person) -> str:
    return person.language or "en"


def _line_words(rows: Sequence[tuple[int, str]], lang: str) -> str:
    """ "3 Ube, 1 Classic": each (quantity, item name), the quantity without its sign."""
    return ", ".join(
        t("sales.recorded.line", lang, quantity=format_int(abs(q), lang), item=item)
        for q, item in rows
    )


def _tender_words(tender: str, lang: str) -> str:
    return t(f"bk.tender.{tender}", lang) if tender in TENDERS else tender


def _tell(session: Session, person: Person, key: str, **params: object) -> None:
    text = t(key, _lang(person), **params)
    notify(session, person, [TextBlock(text=text)], Actor.system(person.branch_id), MANIFEST.id)


def _others(deps: AgentDeps, people: list[Person]) -> list[Person]:
    """The people other than the requester whose branch scope holds the requester's branch
    (home or an assignment, D50): only they can decide (approvals.decide refuses another
    branch)."""
    here, day = deps.branch.id, deps.today
    return [
        p
        for p in people
        if p.id != deps.person.id and here in assignments.branches_of(deps.session, p, day)
    ]


def _request_void(deps: AgentDeps, args: VoidReceiptInput, tool_call_id: str) -> Approval:
    """The void's approval (type sales.void, subject the receipt, its total as the amount) at
    the receipt's branch (a cover's visit kiosk, not her home) and its card to that branch's
    head staff other than the requester (none: the owners and admins). It writes nothing to
    the receipt."""
    r = _find_receipt(deps, args.receipt_no, tool_call_id)
    out = receipt_out(deps.session, deps.branch, r)

    def card(lang: str) -> str:
        return t(
            "sales.void.card",
            lang,
            who=_first(deps.person),
            no=r.receipt_no,
            lines=_line_words([(x.quantity, x.item) for x in out.lines], lang),
            total=format_money(r.total, r.currency, lang),
            tender=_tender_words(out.tender, lang),
            reason=args.reason,
        )

    approval = approvals.request(
        deps.session,
        sales.VOID,
        ("sales_receipts", r.id),
        card("en"),
        deps.actor,
        MANIFEST.roles.approvers[VOID_TOOL],
        risk="money",
        evidence={
            "input": args.model_dump(mode="json"),
            "tool_call_id": tool_call_id,
            "receipt_no": r.receipt_no,
            "amount": r.total,
            "reason": args.reason,
        },
        tool_call_id=tool_call_id,
        branch_id=r.branch_id,
    )
    heads = _others(deps, alerts.supervisors(deps.session, r.branch_id))
    for p in heads or _others(deps, alerts.leads(deps.session, deps.organisation_id)):
        notify(deps.session, p, [TextBlock(text=card(_lang(p)))], deps.actor, MANIFEST.id)
    return approval


def _request_refund(deps: AgentDeps, args: RefundReceiptInput, tool_call_id: str) -> Approval:
    """The refund's approval (type sales.refund, subject the sale, the computed refund as the
    amount) at the sale's branch (a cover's visit kiosk) and its card to the owners and admins
    other than the requester."""
    sale = _find_receipt(deps, args.receipt_no, tool_call_id)
    lines = refund_lines(deps.session, sale, args.items)
    amount = _refund_amount(deps, sale, lines)
    names = _names(deps.session)
    shown = [(x.quantity, names[x.item_id].name) for x in lines]

    def card(lang: str) -> str:
        return t(
            "sales.refund.card",
            lang,
            who=_first(deps.person),
            amount=format_money(amount, sale.currency, lang),
            no=sale.receipt_no,
            lines=_line_words(shown, lang),
            reason=args.reason,
        )

    approval = approvals.request(
        deps.session,
        sales.REFUND,
        ("sales_receipts", sale.id),
        card("en"),
        deps.actor,
        MANIFEST.roles.approvers[REFUND_TOOL],
        risk="money",
        evidence={
            "input": args.model_dump(mode="json"),
            "tool_call_id": tool_call_id,
            "receipt_no": sale.receipt_no,
            "amount": amount,
            "reason": args.reason,
        },
        tool_call_id=tool_call_id,
        branch_id=sale.branch_id,
    )
    for p in _others(deps, alerts.leads(deps.session, deps.organisation_id)):
        notify(deps.session, p, [TextBlock(text=card(_lang(p)))], deps.actor, MANIFEST.id)
    return approval


def _approval_of(deps: AgentDeps, kind: str, subject_id: str) -> Approval:
    """The approved approval of this kind and receipt among deps.approved that this person
    asked for; LookupError("approval") without one (the guard asks first)."""
    for approval_id in sorted(deps.approved):
        row = deps.session.get(Approval, approval_id)
        if (
            row is not None
            and (row.type, row.subject_id, row.status) == (kind, subject_id, "approved")
            and row.requester_on_behalf_of == deps.person.id
        ):
            return row
    raise LookupError("approval")


def void_receipt(deps: AgentDeps, args: VoidReceiptInput, tool_call_id: str) -> ReceiptOut:
    """Void the receipt with its approved sales.void approval in deps.approved (run by the
    approval handler; the guard asks first). core.sales.void_receipt refuses a second use, a
    closed drawer and a refunded sale; each SalesError becomes LookupError."""
    _check(deps, _as_reporter(RECEIPTS, deps), "write", tool_call_id)
    r = _find_receipt(deps, args.receipt_no, tool_call_id)
    approval = _approval_of(deps, sales.VOID, r.id)
    try:
        sales.void_receipt(deps.session, deps.actor, r, approval.id, args.reason)
    except sales.SalesError as exc:
        raise LookupError(str(exc)) from exc
    return receipt_out(deps.session, deps.branch, r)


def refund_receipt(deps: AgentDeps, args: RefundReceiptInput, tool_call_id: str) -> ReceiptOut:
    """Record the refund with its approved sales.refund approval in deps.approved (run by the
    approval handler): a new receipt in the requester's open drawer of the business date
    (none: LookupError("no_session")), paid back in the sale's one tender (else cash).
    core.sales refuses a second use and more than the approved amount."""
    for table in RECEIPT_TABLES:
        _check(deps, _as_reporter(table, deps), "write", tool_call_id)
    _check(deps, _as_reporter(SESSIONS, deps), "read", tool_call_id)
    _check(deps, _as_reporter(RECEIPT_TABLES[2], deps), "read", tool_call_id)  # the sale's tender
    sale = _find_receipt(deps, args.receipt_no, tool_call_id)
    approval = _approval_of(deps, sales.REFUND, sale.id)
    lines = refund_lines(deps.session, sale, args.items)
    amount = _refund_amount(deps, sale, lines)
    events.write_lock(deps.session)  # the drawer and the next number decide the write
    drawers = sales.open_sessions(deps.session, deps.branch.id)
    # the requester's own drawer pays it out, never another clerk's (her count would be short)
    s = next(
        (d for d in drawers if d.person_id == deps.person.id and d.business_date == deps.today),
        None,
    )  # never a stale drawer of an earlier date
    if s is None:
        raise LookupError("no_session")
    tenders = {
        p.tender
        for p in deps.session.exec(select(SalesPayment).where(SalesPayment.receipt_id == sale.id))
    }
    tender = tenders.pop() if len(tenders) == 1 else "cash"  # a split sale pays back in cash
    try:
        refund = sales.record_receipt(
            deps.session,
            deps.actor,
            s,
            _next_receipt_no(deps.session, deps.branch.id),
            utcnow(),
            lines,
            [sales.PaymentIn.model_validate({"tender": tender, "amount": -amount})],
            refund_of=sale.id,
            approval_id=approval.id,
            source="chat",
        )
    except sales.SalesError as exc:
        raise LookupError(str(exc)) from exc
    return receipt_out(deps.session, deps.branch, refund)


def _requester_deps(session: Session, approval: Approval) -> AgentDeps:
    """The requester's deps at the receipt's branch (a cover's sale is at the visit's kiosk,
    at_visit) on its business date now, with the approval approved
    (bookkeeper.tools._requester_deps, which this module cannot import)."""
    person = session.get(Person, approval.requester_on_behalf_of or "")
    receipt = session.get(SalesReceipt, approval.subject_id)  # the voided or refunded sale
    branch = session.get(Branch, receipt.branch_id) if receipt is not None else None
    if person is None or branch is None:
        raise LookupError("the requester")
    today = retail_hours.business_date_at(branch, retail_hours.load(session, branch.id), utcnow())
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=today,
        lang=_lang(person),
        manifest=MANIFEST,
        approved={approval.id},
    )


def apply_void_approval(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: void the receipt as the requester (the evidence input revalidated)
    and tell them sales.void.done. An approval without a chat input (a till's) runs nothing.
    Raises LookupError (nothing written; the decide route closes the request)."""
    if "input" not in approval.evidence:
        return  # ponytail: a till's approval; the till voids with it itself
    deps = _requester_deps(session, approval)
    args = VoidReceiptInput.model_validate(approval.evidence["input"])
    out = void_receipt(deps, args, str(approval.evidence.get("tool_call_id") or approval.id))
    _tell(session, deps.person, "sales.void.done", no=out.receipt_no)


def apply_refund_approval(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: record the refund as the requester (the evidence input revalidated)
    and tell them sales.refund.done. An approval without a chat input (a till's) runs
    nothing. Raises LookupError (nothing written; the decide route closes the request)."""
    if "input" not in approval.evidence:
        return  # ponytail: a till's approval; the till records the refund with it itself
    deps = _requester_deps(session, approval)
    args = RefundReceiptInput.model_validate(approval.evidence["input"])
    out = refund_receipt(deps, args, str(approval.evidence.get("tool_call_id") or approval.id))
    _tell(
        session,
        deps.person,
        "sales.refund.done",
        refund_no=out.receipt_no,
        amount=format_money(-out.total, out.currency, deps.lang),
        no=args.receipt_no,
        tender=_tender_words(out.tender, deps.lang),
    )


def _rejected(kind: str, refused: str, other: str) -> Callable[[Session, Approval, Actor], None]:
    """The reject handler of a void or refund, telling the requester sales.<kind>.<key>:
    rejected for a rejection; for a request closed as expired, `refused` when close_refused
    gave the reason in REFUSED, `other` for any other refusal reason (the run was refused, the
    receipt changed), and expired only for a real timeout (no reason)."""

    def handler(session: Session, approval: Approval, decider: Actor) -> None:
        if "input" not in approval.evidence:
            return
        person = session.get(Person, approval.requester_on_behalf_of or "")
        if person is None:
            return
        key = "rejected"
        if approval.status == "expired":
            # ponytail: a timeout (expire_if_due) leaves no reason; close_refused always gives one
            key = (
                "expired"
                if approval.reason is None
                else refused
                if approval.reason == REFUSED[kind]
                else other
            )
        _tell(session, person, f"sales.{kind}.{key}", no=approval.evidence.get("receipt_no", ""))

    return handler


REFUSED = {"void": "session_closed", "refund": "no_session"}  # close_refused reason -> key
approvals.register_handler(sales.VOID, apply_void_approval)
approvals.register_handler(sales.REFUND, apply_refund_approval)
approvals.register_reject_handler(
    sales.VOID, _rejected("void", "closed", "not_done"), on_refused=True
)
approvals.register_reject_handler(
    sales.REFUND, _rejected("refund", "not_done", "changed"), on_refused=True
)


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
        f"{MANIFEST.id}.report",
        report,
        ReportInput,
        "A report form (measure, period, grouping, filters, compare) summed by code.",
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
    ToolBinding(
        f"{MANIFEST.id}.record_receipt",
        record_receipt,
        RecordReceiptInput,
        "Ring up one customer's sale on the clerk's open drawer.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.receipts",
        receipts,
        ReceiptsInput,
        "Today's receipts of the branch the person may read, or the last one.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.item_codes",
        item_codes,
        ItemCodesInput,
        "The branch's menu: each item's short codes and today's price.",
    ),
    ToolBinding(
        VOID_TOOL,
        void_receipt,
        VoidReceiptInput,
        "Void a receipt just rung up; head staff decide.",
        precheck=check_void,
        request=_request_void,
    ),
    ToolBinding(
        REFUND_TOOL,
        refund_receipt,
        RefundReceiptInput,
        "Refund a paid sale, all of it or some items; the owner decides.",
        precheck=check_refund,
        request=_request_refund,
    ),
]
