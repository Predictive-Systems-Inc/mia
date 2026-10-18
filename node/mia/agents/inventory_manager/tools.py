"""The inventory manager's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store. The bake plan, low stock and order totals are pure code in calc.py;
the business date is the sales supervisor's calc.business_date with the branch's hours.

Branch scoping: every tool works on the person's own branch. Naming another branch needs the
read_all or write_all action on the data resource in RBAC (admin, and the owner through the
hierarchy); anyone else gets PermissionDenied.

A supplier order is money: the manifest gives draft_order risk money, so the guard in
agents/base.py creates the approval (evidence: the tool call id) and stops before this body
runs. Nothing is stored before the decision. On approve, apply_order_approval (registered with
mia.core.approvals) re-runs draft_order as the requester with the approval in deps.approved,
reading the requested input from the call's `tool.called` event; the order is written as
approved (event inventory.order_approved) and the requester is notified.
"""

import datetime as dt
from collections.abc import Sequence
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.inventory_manager import MANIFEST, calc
from mia.agents.inventory_manager.models import StockEvent, SupplierOrder
from mia.agents.sales_supervisor.calc import business_date
from mia.chat.blocks import TextBlock
from mia.chat.channels import notify
from mia.core import approvals, store
from mia.core.db import utcnow
from mia.core.models import Actor, Approval, Branch, Event, Person
from mia.core.rbac import Resource, get_rbac
from mia.i18n import t
from mia.templates.retail.models import RetailBranchHours, RetailIngredient, RetailItem

DEFAULT_OPENS = dt.time(9, 0)
DEFAULT_CLOSES = dt.time(21, 0)
PLAN_DAYS = 91  # ponytail: the plan reads 13 weeks back; a weekday unrecorded longer is `same`
DRAFT_ORDER = f"{MANIFEST.id}.draft_order"
STOCK = Resource(kind="data", name=StockEvent.__tablename__)
ORDERS = Resource(kind="data", name=SupplierOrder.__tablename__)
INGREDIENTS = Resource(kind="data", name=RetailIngredient.__tablename__)
ITEMS = Resource(kind="data", name=RetailItem.__tablename__)
HOURS = Resource(kind="data", name=RetailBranchHours.__tablename__)

Kind = Literal["sold_out", "count", "leftover", "waste", "low", "received"]
Reason = Literal["too_dry", "burnt", "expired", "dropped", "other"]
EVENT_ACTIONS = {"count": "stock.counted"}  # every other kind logs as stock.<kind>


# ---- shared helpers -----------------------------------------------------------------------


def _check(deps: AgentDeps, resource: Resource, action: str, tool_call_id: str) -> None:
    get_rbac().require(
        deps.actor, resource, action, session=deps.session, tool_call_id=tool_call_id
    )


def _as_reporter(resource: Resource, deps: AgentDeps) -> Resource:
    """The resource owned by the acting person, so read_own and write_own gate by role only;
    which rows are in scope is decided by the branch filter in each query."""
    return resource.model_copy(update={"owner_id": deps.person.id})


def _branch(
    deps: AgentDeps, branch_id: str | None, resource: Resource, action: str, tool_call_id: str
) -> Branch:
    """The person's branch, or another branch of the organisation after the `<action>_all`
    check (PermissionDenied without it). Raises LookupError for a branch outside it."""
    if branch_id is None or branch_id == deps.branch.id:
        return deps.branch
    _check(deps, resource, f"{action}_all", tool_call_id)
    branch = deps.session.get(Branch, branch_id)
    if branch is None or branch.organisation_id != deps.organisation_id:
        raise LookupError("branch")
    return branch


def _hours(
    deps: AgentDeps, branch: Branch, weekday: int, tool_call_id: str
) -> tuple[dt.time, dt.time]:
    """The branch's opening and closing time on the weekday (09:00 to 21:00 when unset), after
    the retail_branch_hours read check."""
    _check(deps, HOURS, "read", tool_call_id)
    stmt = (
        select(RetailBranchHours)
        .where(RetailBranchHours.branch_id == branch.id)
        .where(RetailBranchHours.weekday == weekday)
    )
    row = deps.session.exec(stmt).first()
    if row is None:
        return DEFAULT_OPENS, DEFAULT_CLOSES
    return dt.time.fromisoformat(row.opens), dt.time.fromisoformat(row.closes)


def _business_day(deps: AgentDeps, branch: Branch, at: dt.datetime, tool_call_id: str) -> dt.date:
    """The branch's business date at `at`: the day before only just after a late closing."""
    weekday = at.astimezone(ZoneInfo(branch.timezone)).weekday()
    opens, _ = _hours(deps, branch, weekday, tool_call_id)
    _, closed = _hours(deps, branch, (weekday - 1) % 7, tool_call_id)
    return business_date(at, branch.timezone, opens, closed)


def _when(branch: Branch, hhmm: str | None, now: dt.datetime) -> dt.datetime:
    """The latest moment at or before `now` with the local clock time "HH:MM" in the branch's
    zone (yesterday's when today's is still to come); `now` without one. Raises LookupError for
    a time that does not exist."""
    if hhmm is None:
        return now
    try:
        clock = dt.time.fromisoformat(hhmm.zfill(5))
    except ValueError as exc:
        raise LookupError(f"no time {hhmm!r}") from exc
    local = now.astimezone(ZoneInfo(branch.timezone))
    at = dt.datetime.combine(local.date(), clock, local.tzinfo)
    return at - dt.timedelta(days=1) if at > local else at


def _items(session: Session, branch_id: str) -> dict[str, RetailItem]:
    """Active items the branch sells (its own and the shared ones), in menu order."""
    stmt = select(RetailItem).where(col(RetailItem.active).is_(True))
    rows = [i for i in session.exec(stmt.order_by(col(RetailItem.sort_order)))]
    return {i.id: i for i in rows if i.branch_id in (None, branch_id)}


def _ingredients(session: Session, branch_id: str) -> dict[str, RetailIngredient]:
    """Active ingredients the branch stocks (its own and the shared ones), by name."""
    stmt = select(RetailIngredient).where(col(RetailIngredient.active).is_(True))
    rows = [i for i in session.exec(stmt.order_by(col(RetailIngredient.name)))]
    return {i.id: i for i in rows if i.branch_id in (None, branch_id)}


class EventOut(BaseModel):
    event_id: str
    kind: str
    item_id: str | None
    ingredient_id: str | None
    name: str
    quantity: int | None
    unit: str | None
    reason: str | None
    at: dt.datetime
    business_date: dt.date


def _event_out(row: StockEvent, name: str) -> EventOut:
    return EventOut(
        event_id=row.id,
        kind=row.kind,
        item_id=row.item_id,
        ingredient_id=row.ingredient_id,
        name=name,
        quantity=row.quantity,
        unit=row.unit,
        reason=row.reason,
        at=row.at,
        business_date=row.business_date,
    )


# ---- record_events ------------------------------------------------------------------------


class EventIn(BaseModel):
    kind: Kind
    item_id: str | None = None
    ingredient_id: str | None = None
    quantity: int | None = Field(None, ge=0)
    unit: str | None = None
    reason: Reason | None = None
    at: str | None = Field(
        None, pattern=r"^\d{1,2}:\d{2}$", description="Local HH:MM when said; none means now"
    )

    @model_validator(mode="after")
    def _one_subject(self) -> "EventIn":
        if (self.item_id is None) == (self.ingredient_id is None):
            raise ValueError("an event is about one item or one ingredient")
        return self


class RecordEventsInput(BaseModel):
    events: list[EventIn] = Field(min_length=1)
    source_message_id: str | None = None


class RecordEventsOutput(BaseModel):
    recorded: list[EventOut]
    business_date: dt.date


def record_events(
    deps: AgentDeps, args: RecordEventsInput, tool_call_id: str
) -> RecordEventsOutput:
    """Record one stock event per input (event stock.<kind>, stock.counted for a count) at the
    stated local time or now, each on the business date of its time. business_date is the
    branch's business date now. Raises LookupError for an item or ingredient the branch does
    not have, or a time that does not exist."""
    _check(deps, _as_reporter(STOCK, deps), "write", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    _check(deps, INGREDIENTS, "read", tool_call_id)
    items = _items(deps.session, deps.branch.id)
    ingredients = _ingredients(deps.session, deps.branch.id)
    names: dict[str, str] = {k: v.name for k, v in items.items()}
    names |= {k: v.name for k, v in ingredients.items()}
    for e in args.events:
        subject = e.item_id or e.ingredient_id
        if (e.item_id and e.item_id not in items) or (
            e.ingredient_id and e.ingredient_id not in ingredients
        ):
            raise LookupError(f"no item or ingredient {subject!r} at this branch")
    now = utcnow()
    rows = []
    for e in args.events:
        at = _when(deps.branch, e.at, now)
        unit = e.unit or (ingredients[e.ingredient_id].unit if e.ingredient_id else None)
        row = StockEvent(
            branch_id=deps.branch.id,
            kind=e.kind,
            item_id=e.item_id,
            ingredient_id=e.ingredient_id,
            quantity=e.quantity,
            unit=unit,
            reason=e.reason,
            at=at,
            reported_by=deps.person.id,
            business_date=_business_day(deps, deps.branch, at, tool_call_id),
            source_message_id=args.source_message_id,
        )
        action = EVENT_ACTIONS.get(e.kind, f"stock.{e.kind}")
        rows.append(
            store.insert(deps.session, row, deps.actor, action=action, tool_call_id=tool_call_id)
        )
    return RecordEventsOutput(
        recorded=[_event_out(r, names[r.item_id or r.ingredient_id or ""]) for r in rows],
        business_date=_business_day(deps, deps.branch, now, tool_call_id),
    )


# ---- low_stock ----------------------------------------------------------------------------


class LowStockInput(BaseModel):
    branch_id: str | None = Field(None, description="Another branch (only an owner or admin)")


class LowOut(BaseModel):
    ingredient_id: str
    name: str
    unit: str
    latest_count: int | None
    reorder_point: int
    supplier: str | None


class LowStockOutput(BaseModel):
    ingredients: list[LowOut]


def _stock_rows(session: Session, branch_id: str, kinds: Sequence[str]) -> list[StockEvent]:
    stmt = (
        select(StockEvent)
        .where(StockEvent.branch_id == branch_id)
        .where(col(StockEvent.kind).in_(kinds))
    )
    # In Python: the stored text keeps each row's offset, so SQL ordering is not by instant.
    return sorted(session.exec(stmt), key=lambda r: (r.at, r.id))


def _on_hand(rows: Sequence[StockEvent]) -> dict[str, int]:
    """Per ingredient: its latest count plus what was received after it (rows oldest first)."""
    out: dict[str, int] = {}
    for r in rows:
        if r.ingredient_id is None or r.quantity is None:
            continue
        if r.kind == "count":
            out[r.ingredient_id] = r.quantity
        elif r.ingredient_id in out:  # a delivery after a count
            out[r.ingredient_id] += r.quantity
    return out


def low_stock(deps: AgentDeps, args: LowStockInput, tool_call_id: str) -> LowStockOutput:
    """The branch's active ingredients at or under their reorder point by the latest count (plus
    deliveries since), or reported low on today's business date (calc.low), by name."""
    branch = _branch(deps, args.branch_id, STOCK, "read", tool_call_id)
    _check(deps, _as_reporter(STOCK, deps), "read", tool_call_id)
    _check(deps, INGREDIENTS, "read", tool_call_id)
    ingredients = _ingredients(deps.session, branch.id)
    rows = _stock_rows(deps.session, branch.id, ["count", "received", "low"])
    today = _business_day(deps, branch, utcnow(), tool_call_id)
    on_hand = _on_hand([r for r in rows if r.kind != "low"])
    low_today = {
        r.ingredient_id
        for r in rows
        if r.kind == "low" and r.business_date == today and r.ingredient_id
    }
    reorder = {k: v.reorder_point for k, v in ingredients.items()}
    return LowStockOutput(
        ingredients=[
            LowOut(
                ingredient_id=i,
                name=ingredients[i].name,
                unit=ingredients[i].unit,
                latest_count=on_hand.get(i),
                reorder_point=ingredients[i].reorder_point,
                supplier=ingredients[i].supplier,
            )
            for i in calc.low(on_hand, reorder, low_today)
        ]
    )


# ---- plan_tomorrow ------------------------------------------------------------------------


class PlanTomorrowInput(BaseModel):
    branch_id: str | None = Field(None, description="Another branch (only an owner or admin)")


class PlanLine(BaseModel):
    item_id: str
    item: str
    plan: calc.Plan


class PlanOutput(BaseModel):
    lines: list[PlanLine]
    note_heuristic: bool = True  # the reply says the plan is a suggestion (Q54)


def plan_tomorrow(deps: AgentDeps, args: PlanTomorrowInput, tool_call_id: str) -> PlanOutput:
    """More, same or fewer per active item for the day after the branch's business date
    (calc.plan over this agent's stock events, tomorrow's closing time), in menu order."""
    branch = _branch(deps, args.branch_id, STOCK, "read", tool_call_id)
    _check(deps, _as_reporter(STOCK, deps), "read", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    today = _business_day(deps, branch, utcnow(), tool_call_id)
    tomorrow = today + dt.timedelta(days=1)
    _, closes = _hours(deps, branch, tomorrow.weekday(), tool_call_id)
    stmt = (
        select(StockEvent)
        .where(StockEvent.branch_id == branch.id)
        .where(col(StockEvent.item_id).is_not(None))
        .where(col(StockEvent.business_date) >= today - dt.timedelta(days=PLAN_DAYS))
    )
    zone = ZoneInfo(branch.timezone)
    records = [
        calc.Record(r.kind, r.item_id, r.at.astimezone(zone), r.business_date)
        for r in deps.session.exec(stmt)
    ]
    items = _items(deps.session, branch.id)
    plans = calc.plan(records, list(items), today, closes)
    return PlanOutput(lines=[PlanLine(item_id=i, item=items[i].name, plan=plans[i]) for i in items])


# ---- draft_order --------------------------------------------------------------------------


class LineIn(BaseModel):
    ingredient_id: str
    quantity: int = Field(gt=0)
    unit: str | None = Field(None, description="The ingredient's own unit when not said")


class DraftOrderInput(BaseModel):
    supplier: str = Field(min_length=1)
    lines: list[LineIn] = Field(min_length=1)
    branch_id: str | None = Field(None, description="Another branch (only an owner or admin)")


class OrderOut(BaseModel):
    order_id: str
    supplier: str
    status: str
    lines: list[dict[str, Any]]
    total: int | None
    currency: str
    approval_id: str | None


def _order_out(row: SupplierOrder) -> OrderOut:
    return OrderOut(
        order_id=row.id,
        supplier=row.supplier,
        status=row.status,
        lines=row.lines,
        total=row.total,
        currency=row.currency,
        approval_id=row.approval_id,
    )


def _approved(deps: AgentDeps) -> Approval | None:
    """The approved draft_order approval among deps.approved, if any."""
    for approval_id in sorted(deps.approved):
        row = deps.session.get(Approval, approval_id)
        if row is not None and row.type == DRAFT_ORDER and row.status == "approved":
            return row
    return None


def draft_order(deps: AgentDeps, args: DraftOrderInput, tool_call_id: str) -> OrderOut:
    """Write the supplier order of an approved request (status approved, event
    inventory.order_approved, approval_id set); a unit price is the ingredient's pack price when
    the line is in its unit, and the total is None without every price (Q55). Runs only with an
    approved approval in deps.approved (the guard asks for one first) and writes at most one
    order per approval: a second run returns the first. Raises LookupError without an approval,
    or for an ingredient the branch does not stock."""
    branch = _branch(deps, args.branch_id, ORDERS, "write", tool_call_id)
    _check(deps, ORDERS, "write", tool_call_id)
    _check(deps, INGREDIENTS, "read", tool_call_id)
    approval = _approved(deps)
    if approval is None:
        raise LookupError("an order needs an approved request")
    stmt = select(SupplierOrder).where(SupplierOrder.approval_id == approval.id)
    if (done := deps.session.exec(stmt).first()) is not None:
        return _order_out(done)
    stocked = _ingredients(deps.session, branch.id)
    lines: list[dict[str, Any]] = []
    for line in args.lines:
        ingredient = stocked.get(line.ingredient_id)
        if ingredient is None:
            raise LookupError(f"no ingredient {line.ingredient_id!r} at this branch")
        unit = line.unit or ingredient.unit
        price = ingredient.pack_price if unit == ingredient.unit else None
        lines.append(
            {
                "ingredient_id": ingredient.id,
                "quantity": line.quantity,
                "unit": unit,
                "unit_price": price,
            }
        )
    prices = {line["ingredient_id"]: line["unit_price"] for line in lines}
    # ponytail: one currency per branch in v1, taken from the first ingredient
    currency = stocked[args.lines[0].ingredient_id].currency
    row = store.insert(
        deps.session,
        SupplierOrder(
            branch_id=branch.id,
            supplier=args.supplier,
            lines=lines,
            currency=currency,
            total=calc.order_total([(x.ingredient_id, x.quantity) for x in args.lines], prices),
            status="approved",
            approval_id=approval.id,
            requested_by=deps.person.id,
            business_date=_business_day(deps, branch, utcnow(), tool_call_id),
        ),
        deps.actor,
        action="inventory.order_approved",
        tool_call_id=tool_call_id,
        approval_id=approval.id,
    )
    return _order_out(row)


def _requested_input(session: Session, approval: Approval) -> DraftOrderInput:
    """The draft_order input of the tool call that raised the approval (its tool.called event,
    written by agents.base.call_tool). Raises LookupError when there is none."""
    call_id = approval.evidence.get("tool_call_id")
    stmt = (
        select(Event)
        .where(Event.action == "tool.called")
        .where(Event.entity_id == DRAFT_ORDER)
        .where(Event.tool_call_id == call_id)
    )
    called = session.exec(stmt).first()
    if call_id is None or called is None or called.before is None:
        raise LookupError("the requested order is not in the events log")
    return DraftOrderInput.model_validate(called.before["input"])


def apply_order_approval(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: re-run draft_order as the requester (their permissions, the approval
    in deps.approved) so the order is written as approved, then notify the requester.
    Raises LookupError when the requester or the requested input cannot be found."""
    person = session.get(Person, approval.requester_on_behalf_of or "")
    branch = session.get(Branch, person.branch_id) if person is not None else None
    if person is None or branch is None:
        raise LookupError("the requester of the order")
    args = _requested_input(session, approval)
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
    order = draft_order(deps, args, str(approval.evidence.get("tool_call_id")))
    text = t("stock.order_approved", lang, supplier=order.supplier)
    notify(session, person, [TextBlock(text=text)], deps.actor, MANIFEST.id)


approvals.register_handler(DRAFT_ORDER, apply_order_approval)


# ---- receive_delivery ---------------------------------------------------------------------


class ReceiveDeliveryInput(BaseModel):
    lines: list[LineIn] = Field(min_length=1)
    order_id: str | None = Field(None, description="The order delivered, when known")


class ReceiveDeliveryOutput(BaseModel):
    recorded: list[EventOut]
    received_order_ids: list[str]


def _open_line(lines: list[dict[str, Any]], ingredient_id: str) -> dict[str, Any] | None:
    for line in lines:
        if line["ingredient_id"] == ingredient_id and line.get("received", 0) < line["quantity"]:
            return line
    return None


def receive_delivery(
    deps: AgentDeps, args: ReceiveDeliveryInput, tool_call_id: str
) -> ReceiveDeliveryOutput:
    """Record a received stock event per line (event stock.received) and add it to the order
    line it delivers: the named order, else the branch's oldest approved order with that
    ingredient still open; a receipt without an order is recorded alone. An order whose every
    line is received becomes received (event inventory.order_received). Raises LookupError for
    an ingredient the branch does not stock or a named order that is not open at the branch."""
    _check(deps, _as_reporter(STOCK, deps), "write", tool_call_id)
    _check(deps, ORDERS, "write", tool_call_id)
    _check(deps, INGREDIENTS, "read", tool_call_id)
    stocked = _ingredients(deps.session, deps.branch.id)
    stmt = (
        select(SupplierOrder)
        .where(SupplierOrder.branch_id == deps.branch.id)
        .where(SupplierOrder.status == "approved")
        .order_by(col(SupplierOrder.id))
    )
    if args.order_id is not None:
        stmt = stmt.where(SupplierOrder.id == args.order_id)
    orders = list(deps.session.exec(stmt))
    if args.order_id is not None and not orders:
        raise LookupError(f"no open order {args.order_id!r} at this branch")
    now = utcnow()
    day = _business_day(deps, deps.branch, now, tool_call_id)
    working = {o.id: [dict(x) for x in o.lines] for o in orders}
    rows = []
    for line in args.lines:
        ingredient = stocked.get(line.ingredient_id)
        if ingredient is None:
            raise LookupError(f"no ingredient {line.ingredient_id!r} at this branch")
        order_id = None
        for order in orders:
            target = _open_line(working[order.id], ingredient.id)
            if target is not None:
                target["received"] = target.get("received", 0) + line.quantity
                order_id = order.id
                break
        row = StockEvent(
            branch_id=deps.branch.id,
            kind="received",
            ingredient_id=ingredient.id,
            quantity=line.quantity,
            unit=line.unit or ingredient.unit,
            at=now,
            reported_by=deps.person.id,
            business_date=day,
            order_id=order_id,
        )
        rows.append(
            store.insert(
                deps.session, row, deps.actor, action="stock.received", tool_call_id=tool_call_id
            )
        )
    received = []
    for order in orders:
        lines = working[order.id]
        if lines == order.lines:
            continue
        done = all(x.get("received", 0) >= x["quantity"] for x in lines)
        update: dict[str, Any] = {"lines": lines} | ({"status": "received"} if done else {})
        action = "inventory.order_received" if done else "inventory.order_line_received"
        store.update(
            deps.session, order, update, deps.actor, action=action, tool_call_id=tool_call_id
        )
        if done:
            received.append(order.id)
    return ReceiveDeliveryOutput(
        recorded=[_event_out(r, stocked[r.ingredient_id or ""].name) for r in rows],
        received_order_ids=received,
    )


BINDINGS = [
    ToolBinding(
        f"{MANIFEST.id}.record_events",
        record_events,
        RecordEventsInput,
        "Record sell-outs, counts, leftovers, waste and low stock the user reports.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.low_stock",
        low_stock,
        LowStockInput,
        "The ingredients at or under their reorder point, or reported low today.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.plan_tomorrow",
        plan_tomorrow,
        PlanTomorrowInput,
        "More, same or fewer per item for tomorrow's bake.",
    ),
    ToolBinding(
        DRAFT_ORDER,
        draft_order,
        DraftOrderInput,
        "Order ingredients from a supplier. The owner approves it first.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.receive_delivery",
        receive_delivery,
        ReceiveDeliveryInput,
        "Record a supplier delivery and close the order lines it delivers.",
    ),
]
