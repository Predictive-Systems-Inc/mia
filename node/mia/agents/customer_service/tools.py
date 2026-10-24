"""The customer service's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store.

Customer tools take CustomerDeps and act for the customer in `deps.actor.on_behalf_of` (the
customer row's ULID), never for a customer named in the input. Each read and write of a
customer's row is checked with that row's customer_id as the owner, so the customer's
read_own and write_own allow only their own rows; another customer's row is an rbac deny (the
agent principal holds the plain grants). Staff tools take AgentDeps and see only their branch.

Orders go through the approvals guard: place_order has `approval: always` and
`approval_channel: chat` (D47; no money risk, the customer pays at pickup). Its
precheck (_order_precheck) refuses unknown or inactive items, too many items, a time outside
the opening hours and an area not configured, before anything is asked; then the guard creates
the approval (evidence: the tool call id and the validated input with the code-made order_id)
and stops. The caller then runs record_waiting, which writes the order `waiting` only for that
pending approval and sends the clerks and supervisors its message with Confirm and Decline
buttons. A clerk, supervisor, owner or admin of the branch decides it with a tap (decide_tap)
or in the app; apply_order_approval re-reads the waiting row (the approval's own,
items still active) and confirms it, apply_order_rejection rejects it, and each queues the
customer's reply. Both find the customer by the approval's on_behalf_of, never a Person.

Refusals raise LookupError(reason), so call_tool answers `invalid` with the reason.
"""

import contextlib
import datetime as dt
from collections.abc import Callable
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import text as sql_text
from sqlmodel import Session, col, or_, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.customer_service import MANIFEST, calc, public
from mia.agents.customer_service.actions import STAFF_ORDER_STATUSES, open_orders
from mia.agents.customer_service.models import Complaint, Customer
from mia.agents.customer_service.public import CustomerDeps
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.chat.channels import notify
from mia.core import approvals, db, orgconfig, store
from mia.core.models import Actor, Approval, Branch, CustomerOrder, Event, Message, Person, Thread
from mia.core.rbac import Resource, get_rbac
from mia.i18n import SUPPORTED, t
from mia.templates.retail import hours as shop_hours
from mia.templates.retail import items as retail_items
from mia.templates.retail.models import RetailBranchHours, RetailItem

PLACE_ORDER = f"{MANIFEST.id}.place_order"
ORDERS = Resource(kind="data", name=CustomerOrder.__tablename__)
CUSTOMERS = Resource(kind="data", name=Customer.__tablename__)
COMPLAINTS = Resource(kind="data", name=Complaint.__tablename__)
ITEMS = Resource(kind="data", name=RetailItem.__tablename__)
HOURS = Resource(kind="data", name=RetailBranchHours.__tablename__)
CANCELLABLE = ("waiting", "confirmed")
OPEN = ("pending", "escalated")
SHOWN = ("waiting", "confirmed", "ready", "picked_up")  # the statuses order_status reports
REJECT_REASONS = ("closed", "sold_out", "too_large")  # else the customer reads `other`
STAFF_ROLES = {"clerk", "supervisor"}
CONFIRM, DECLINE = "cs.staff.confirm", "cs.staff.decline"  # the order message's buttons (D47)
TAPPED = {
    t(k, lang).casefold(): o
    for k, o in ((CONFIRM, "approved"), (DECLINE, "rejected"))
    for lang in SUPPORTED
}
DONE = {  # outcome: (told after the tap, told on a later tap)
    "approved": ("cs.staff.confirmed_by", "cs.staff.already_confirmed"),
    "rejected": ("cs.staff.declined_by", "cs.staff.already_declined"),
}
RECENT = 20  # how far back a tap looks for the message whose buttons it answers


# ---- shared helpers -----------------------------------------------------------------------


def _require(
    session: Session, actor: Actor, resource: Resource, action: str, tool_call_id: str | None
) -> None:
    get_rbac().require(actor, resource, action, session=session, tool_call_id=tool_call_id)


def _owned(resource: Resource, customer_id: str | None) -> Resource:
    """The resource owned by the customer, so read_own and write_own apply to their rows."""
    return resource.model_copy(update={"owner_id": customer_id})


def _customer(deps: CustomerDeps) -> Customer:
    """The customer the agent acts for: the actor's on_behalf_of row, never an input."""
    who = deps.actor.on_behalf_of
    row = deps.session.get(Customer, who.id) if who and who.type == "customer" else None
    if row is None:
        raise LookupError("customer")
    return row


def _first_name(customer: Customer) -> str:
    return (customer.name or "").split(" ", 1)[0]


def _who(customer: Customer) -> str:
    """How staff tell customers apart: the first name and the number's last four digits."""
    return f"{_first_name(customer)} ({calc.last_four(customer.address)})".strip()


def _active_items(session: Session, branch: Branch, ids: list[str] | None) -> list[RetailItem]:
    """The branch's active items (its own and every branch's), menu order; only `ids` if given."""
    here = or_(col(RetailItem.branch_id) == branch.id, col(RetailItem.branch_id).is_(None))
    stmt = select(RetailItem).where(RetailItem.active).where(here)
    if ids is not None:
        stmt = stmt.where(col(RetailItem.id).in_(ids))
    return list(session.exec(stmt.order_by(col(RetailItem.sort_order))))


def _area(name: str | None) -> orgconfig.DeliveryArea | None:
    """The configured delivery area of that name (case and accents ignored), else None."""
    if name is None:
        return None
    return next(
        (a for a in orgconfig.load().delivery_areas if calc.fold(a.name) == calc.fold(name)), None
    )


def _staff(session: Session, branch_id: str, roles: set[str]) -> list[Person]:
    rows = session.exec(
        select(Person).where(Person.branch_id == branch_id).where(Person.status == "active")
    ).all()
    return [p for p in rows if roles & set(p.roles)]


def _tell_staff(
    session: Session,
    branch_id: str,
    roles: set[str],
    words: Callable[[str], list[Block]],
    actor: Actor,
    asks: str | None = None,
) -> None:
    """A notification with a customer's first name and number digits to each active person of
    the branch holding one of the roles, worded in their language: sensitive (an app link on
    channels), or, when it asks for the approval `asks` (D47), plain text with its buttons on
    channels; either way the text stays out of the event log."""
    for person in _staff(session, branch_id, roles):
        blocks = words(person.language or "en")
        notify(
            session,
            person,
            blocks,
            actor,
            MANIFEST.id,
            sensitive=asks is None,
            redact_log=True,
            approval_id=asks,
        )


def _local(when: dt.datetime, branch: Branch) -> str:
    return f"{when.astimezone(ZoneInfo(branch.timezone)):%H:%M}"


class EmptyInput(BaseModel):
    """No input: the tool answers for the acting customer or the staff member's branch."""


class StatusOutput(BaseModel):
    order_id: str | None
    status: str | None


# ---- customer tools -------------------------------------------------------------------------


class HoursOutput(BaseModel):
    is_open: bool
    closes_at: dt.datetime | None
    next_open: dt.datetime


def hours(deps: CustomerDeps, args: EmptyInput, tool_call_id: str) -> HoursOutput:
    """Whether the branch is open now, until when, and its next opening."""
    _require(deps.session, deps.actor, HOURS, "read", tool_call_id)
    state = calc.open_state(deps.branch, shop_hours.load(deps.session, deps.branch.id), db.utcnow())
    return HoursOutput(is_open=state.is_open, closes_at=state.closes_at, next_open=state.next_open)


class PricesInput(BaseModel):
    item_ids: list[str] = Field(default_factory=list)  # empty: the whole menu


class PriceOut(BaseModel):
    item_id: str
    name: str
    price: int  # minor units
    currency: str


class PricesOutput(BaseModel):
    items: list[PriceOut]


def prices(deps: CustomerDeps, args: PricesInput, tool_call_id: str) -> PricesOutput:
    """The prices of the asked items that are active here (the menu when none are asked)."""
    _require(deps.session, deps.actor, ITEMS, "read", tool_call_id)
    rows = _active_items(deps.session, deps.branch, args.item_ids or None)
    return PricesOutput(
        items=[
            PriceOut(
                item_id=i.id,
                name=i.name,
                price=retail_items.price_on(deps.session, i, deps.branch.id, deps.today),
                currency=i.currency,
            )
            for i in rows
        ]
    )


class AreaInput(BaseModel):
    name: str | None = None


class AreaOutput(BaseModel):
    area: str | None  # None: not delivered there (or no area named)
    fee: int | None
    currency: str | None
    pickup_branch: str


def delivery_area(deps: CustomerDeps, args: AreaInput, tool_call_id: str) -> AreaOutput:
    """The configured area and its fee, or none; always the branch to pick up from. Reads the
    organisation's configuration, no table, so the guard's tool execute check is the only one.
    With no area named, public._act lists the configured areas from that same configuration
    (no customer data, nothing to check)."""
    area = _area(args.name)
    return AreaOutput(
        area=area.name if area else None,
        fee=area.fee if area else None,
        currency=area.currency if area else None,
        pickup_branch=deps.branch.name,
    )


class LineIn(BaseModel):
    item_id: str
    quantity: int = Field(ge=1)


class PlaceOrderInput(BaseModel):
    order_id: str  # made by code (new_id) before the call, so the approval names its row
    lines: list[LineIn] = Field(min_length=1)
    fulfilment: Literal["pickup", "delivery"]
    pickup_at: AwareDatetime  # rule 10
    delivery_area: str | None = None
    delivery_note: str | None = None


def _order_branch(deps: CustomerDeps) -> Branch:
    """The branch an order belongs to: the customer's row branch (precheck and row agree)."""
    branch = deps.session.get(Branch, _customer(deps).branch_id)
    if branch is None:
        raise LookupError("branch")
    return branch


def _order_precheck(deps: CustomerDeps, args: PlaceOrderInput, tool_call_id: str) -> None:
    """The guard's precheck for place_order (after the permission check, before the approval):
    a new order_id, every item active at the customer's branch, at most max_order_quantity
    items, a pickup still ahead and within the opening hours, a delivery to a configured area,
    every price and the fee in one currency (the settings validator already keeps the areas to
    one, so the area half of that guard is a belt), and no other order of the customer's still
    waiting. Raises LookupError order, pending, item, currency, too_large, past, closed or
    area."""
    _require(deps.session, deps.actor, ITEMS, "read", tool_call_id)
    _require(deps.session, deps.actor, HOURS, "read", tool_call_id)
    if deps.session.get(CustomerOrder, args.order_id) is not None:
        raise LookupError("order")
    if _latest(deps, ("waiting",), "read", tool_call_id) is not None:
        raise LookupError("pending")  # each waiting order asks every clerk and supervisor
    branch = _order_branch(deps)
    ids = {line.item_id for line in args.lines}
    items = _active_items(deps.session, branch, list(ids))
    if len(items) != len(ids):
        raise LookupError("item")
    area = _area(args.delivery_area) if args.fulfilment == "delivery" else None
    if len({i.currency for i in items} | ({area.currency} if area else set())) > 1:
        raise LookupError("currency")  # one total in one currency (record_waiting adds them)
    limit = orgconfig.load().customer_service.max_order_quantity
    if sum(line.quantity for line in args.lines) > limit:
        raise LookupError("too_large")
    if args.pickup_at <= db.utcnow():
        raise LookupError("past")
    rows = shop_hours.load(deps.session, branch.id)
    if not calc.within_hours(branch, rows, args.pickup_at):
        raise LookupError("closed")
    if args.fulfilment == "delivery" and area is None:
        raise LookupError("area")


def read_order(deps: CustomerDeps, order_id: str, tool_call_id: str) -> CustomerOrder:
    """One of the customer's orders. Checked with the row's customer_id as the owner before
    anything is returned, so another customer's (or a missing) order is PermissionDenied."""
    row = deps.session.get(CustomerOrder, order_id)
    owner = row.customer_id if row else None
    _require(deps.session, deps.actor, _owned(ORDERS, owner), "read", tool_call_id)
    if row is None:
        raise LookupError("order")
    return row


def place_order(deps: CustomerDeps, args: PlaceOrderInput, tool_call_id: str) -> StatusOutput:
    """Runs only with an approved place_order approval (the guard asks first, and the approve
    handler confirms the row itself): the order's status."""
    row = read_order(deps, args.order_id, tool_call_id)
    return StatusOutput(order_id=row.id, status=row.status)


def _order_ask(
    session: Session, order: CustomerOrder, customer: Customer, branch: Branch, lang: str
) -> list[Block]:
    """The staff's order message (D47): items, pickup time, the customer's first name and the
    last four digits of their number, with the Confirm and Decline buttons."""
    names = {i.id: i.name for i in session.exec(select(RetailItem)).all()}
    items = ", ".join(f"{ln['quantity']} {names.get(ln['item_id'], '?')}" for ln in order.lines)
    text = t(
        "cs.staff.new_order",
        lang,
        items=items,
        time=_local(order.pickup_at, branch),
        name=_first_name(customer),
        last4=calc.last_four(customer.address),
    )
    return [TextBlock(text=text), QuickRepliesBlock(options=[t(CONFIRM, lang), t(DECLINE, lang)])]


def record_waiting(deps: CustomerDeps, args: PlaceOrderInput, approval_id: str) -> CustomerOrder:
    """Write the order `waiting` (event customer_service.order_placed) for the pending
    place_order approval the guard just made for exactly this input and customer, and send its
    card to the branch's clerks and supervisors (sensitive). Raises LookupError for any other
    approval, so no order row exists without its approval."""
    session, customer = deps.session, _customer(deps)
    approval = session.get(Approval, approval_id)
    ours = (
        approval is not None
        and approval.type == PLACE_ORDER
        and approval.status == "pending"
        and approval.requester_on_behalf_of == customer.id
        and approval.evidence.get("input") == args.model_dump(mode="json")
    )
    if approval is None or not ours:
        raise LookupError("approval")
    tool_call_id = str(approval.evidence.get("tool_call_id"))
    _require(session, deps.actor, _owned(ORDERS, customer.id), "write", tool_call_id)
    branch = _order_branch(deps)
    items = {i.id: i for i in _active_items(session, branch, [ln.item_id for ln in args.lines])}
    area = _area(args.delivery_area) if args.fulfilment == "delivery" else None
    day = shop_hours.business_date_at(branch, shop_hours.load(session, branch.id), args.pickup_at)
    unit = {i: retail_items.price_on(session, items[i], branch.id, day) for i in items}
    lines = [
        {"item_id": ln.item_id, "quantity": ln.quantity, "unit_price": unit[ln.item_id]}
        for ln in args.lines
    ]
    total = calc.order_total(
        [(ln.quantity, unit[ln.item_id]) for ln in args.lines], area.fee if area else 0
    )
    order = store.insert(
        session,
        CustomerOrder(
            id=args.order_id,
            branch_id=branch.id,
            customer_id=customer.id,
            lines=lines,
            total=total,
            currency=items[args.lines[0].item_id].currency,
            fulfilment=args.fulfilment,
            pickup_at=args.pickup_at,
            delivery_area=area.name if area else None,
            delivery_note=args.delivery_note,
            status="waiting",
            approval_id=approval.id,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.order_placed",
        tool_call_id=tool_call_id,
        approval_id=approval.id,
    )

    def words(lang: str) -> list[Block]:
        return _order_ask(session, order, customer, branch, lang)

    _tell_staff(session, customer.branch_id, STAFF_ROLES, words, deps.actor, asks=approval.id)
    return order


def _latest(
    deps: CustomerDeps, statuses: tuple[str, ...], action: str, tool_call_id: str
) -> CustomerOrder | None:
    customer = _customer(deps)
    _require(deps.session, deps.actor, _owned(ORDERS, customer.id), action, tool_call_id)
    return deps.session.exec(
        select(CustomerOrder)
        .where(CustomerOrder.customer_id == customer.id)
        .where(col(CustomerOrder.status).in_(statuses))
        .order_by(col(CustomerOrder.id).desc())
    ).first()


def order_status(deps: CustomerDeps, args: EmptyInput, tool_call_id: str) -> StatusOutput:
    """The customer's latest order that is not cancelled or rejected, or none."""
    row = _latest(deps, SHOWN, "read", tool_call_id)
    return StatusOutput(order_id=row.id if row else None, status=row.status if row else None)


def cancel_order(deps: CustomerDeps, args: EmptyInput, tool_call_id: str) -> StatusOutput:
    """Cancel the customer's latest open order while it is waiting or confirmed (event
    customer_service.order_cancelled), withdraw a waiting order's approval so nobody decides
    it, and tell the branch's clerks and supervisors. Raises LookupError ready for a ready
    order (the customer calls the shop) and no_order for none."""
    row = _latest(deps, (*CANCELLABLE, "ready"), "write", tool_call_id)
    if row is None:
        raise LookupError("no_order")
    if row.status == "ready":
        raise LookupError("ready")
    approval = deps.session.get(Approval, row.approval_id) if row.approval_id else None
    if approval is not None and approval.status in ("pending", "escalated"):
        approvals.withdraw(deps.session, approval, deps.actor, "cancelled")
    store.update(
        deps.session,
        row,
        {"status": "cancelled"},
        deps.actor,
        action=f"{MANIFEST.id}.order_cancelled",
        tool_call_id=tool_call_id,
    )
    customer, branch = _customer(deps), deps.branch

    def words(lang: str) -> list[Block]:
        who = _who(customer)
        text = t("cs.staff.order_cancelled", lang, who=who, time=_local(row.pickup_at, branch))
        return [TextBlock(text=text)]

    _tell_staff(deps.session, branch.id, STAFF_ROLES, words, deps.actor)
    return StatusOutput(order_id=row.id, status=row.status)


class ComplainInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ComplaintOutput(BaseModel):
    complaint_id: str


def complain(deps: CustomerDeps, args: ComplainInput, tool_call_id: str) -> ComplaintOutput:
    """Log the customer's complaint (event customer_service.complaint_logged, text redacted)
    and tell the branch's supervisors its text in a sensitive notification."""
    customer = _customer(deps)
    _require(deps.session, deps.actor, _owned(COMPLAINTS, customer.id), "write", tool_call_id)
    row = store.insert(
        deps.session,
        Complaint(branch_id=customer.branch_id, customer_id=customer.id, text=args.text),
        deps.actor,
        action=f"{MANIFEST.id}.complaint_logged",
        tool_call_id=tool_call_id,
    )

    def words(lang: str) -> list[Block]:
        who = _who(customer)
        return [TextBlock(text=t("cs.staff.complaint", lang, who=who, text=args.text))]

    _tell_staff(deps.session, customer.branch_id, {"supervisor"}, words, deps.actor)
    return ComplaintOutput(complaint_id=row.id)


class LanguageInput(BaseModel):
    language: str


class LanguageOutput(BaseModel):
    language: str


def set_language(deps: CustomerDeps, args: LanguageInput, tool_call_id: str) -> LanguageOutput:
    """The acting customer's reply language (event customer_service.language_set), checked
    write_own on their own row. LookupError language for a code not in i18n.SUPPORTED."""
    customer = _customer(deps)
    _require(deps.session, deps.actor, _owned(CUSTOMERS, customer.id), "write", tool_call_id)
    if args.language not in SUPPORTED:
        raise LookupError("language")
    store.update(
        deps.session,
        customer,
        {"language": args.language},
        deps.actor,
        action=public.LANGUAGE,
        tool_call_id=tool_call_id,
    )
    return LanguageOutput(language=customer.language)


# ---- staff tools ----------------------------------------------------------------------------


class LineOut(BaseModel):
    item_id: str
    name: str
    quantity: int


class OrderOut(BaseModel):
    order_id: str
    status: str
    pickup_at: dt.datetime
    fulfilment: str
    lines: list[LineOut]
    total: int
    currency: str
    customer: str  # the first name only


class OrdersOutput(BaseModel):
    orders: list[OrderOut]


def orders_today(deps: AgentDeps, args: EmptyInput, tool_call_id: str) -> OrdersOutput:
    """The branch's confirmed and ready orders picked up today (local), by pickup time."""
    for resource in (ORDERS, CUSTOMERS, ITEMS):
        _require(deps.session, deps.actor, resource, "read", tool_call_id)
    today = open_orders(deps.session, deps.branch, day=deps.today)
    names = {i.id: i.name for i in deps.session.exec(select(RetailItem)).all()}
    return OrdersOutput(
        orders=[
            OrderOut(
                order_id=o.id,
                status=o.status,
                pickup_at=o.pickup_at,
                fulfilment=o.fulfilment,
                lines=[
                    LineOut(
                        item_id=ln["item_id"],
                        name=names.get(ln["item_id"], "?"),
                        quantity=ln["quantity"],
                    )
                    for ln in o.lines
                ],
                total=o.total,
                currency=o.currency,
                customer=_first_name(c),
            )
            for o, c in today
        ]
    )


class OrderRef(BaseModel):
    order_id: str


def _branch_order(deps: AgentDeps, order_id: str, tool_call_id: str) -> CustomerOrder:
    _require(deps.session, deps.actor, ORDERS, "write", tool_call_id)
    row = deps.session.get(CustomerOrder, order_id)
    if row is None or row.branch_id != deps.branch.id:
        raise LookupError("order")
    return row


def mark_ready(deps: AgentDeps, args: OrderRef, tool_call_id: str) -> StatusOutput:
    """A confirmed order of the branch becomes ready (event customer_service.order_ready) and
    the customer's reply is queued (sent only inside their 24-hour window). LookupError status
    for any other status."""
    row = _branch_order(deps, args.order_id, tool_call_id)
    if row.status != "confirmed":
        raise LookupError("status")
    action = f"{MANIFEST.id}.order_ready"
    store.update(
        deps.session, row, {"status": "ready"}, deps.actor, action=action, tool_call_id=tool_call_id
    )
    customer = deps.session.get(Customer, row.customer_id)
    if customer is not None:
        text = t("cs.order_ready", customer.language, time=_local(row.pickup_at, deps.branch))
        public.queue(deps.session, customer, [TextBlock(text=text)], deps.actor)
    return StatusOutput(order_id=row.id, status=row.status)


def mark_picked_up(deps: AgentDeps, args: OrderRef, tool_call_id: str) -> StatusOutput:
    """A confirmed or ready order of the branch is picked up (event
    customer_service.order_picked_up). LookupError status for any other status."""
    row = _branch_order(deps, args.order_id, tool_call_id)
    if row.status not in STAFF_ORDER_STATUSES:
        raise LookupError("status")
    action = f"{MANIFEST.id}.order_picked_up"
    store.update(
        deps.session,
        row,
        {"status": "picked_up"},
        deps.actor,
        action=action,
        tool_call_id=tool_call_id,
    )
    return StatusOutput(order_id=row.id, status=row.status)


class ComplaintRef(BaseModel):
    complaint_id: str


def resolve_complaint(deps: AgentDeps, args: ComplaintRef, tool_call_id: str) -> StatusOutput:
    """An open complaint of the branch is resolved by the acting person (event
    customer_service.complaint_resolved). LookupError complaint when there is none open."""
    _require(deps.session, deps.actor, COMPLAINTS, "write", tool_call_id)
    row = deps.session.get(Complaint, args.complaint_id)
    if row is None or row.branch_id != deps.branch.id or row.status != "open":
        raise LookupError("complaint")
    changes = {"status": "resolved", "resolved_by": deps.person.id, "resolved_at": db.utcnow()}
    action = f"{MANIFEST.id}.complaint_resolved"
    store.update(deps.session, row, changes, deps.actor, action=action, tool_call_id=tool_call_id)
    return StatusOutput(order_id=row.order_id, status=row.status)


# ---- the order approval -----------------------------------------------------------------


def _decided(
    session: Session, approval: Approval, decider: Actor
) -> tuple[CustomerOrder, Customer, Actor]:
    """The order and customer of a place_order approval, and the agent acting for the decider
    (checked: the agent and the decider may write orders). The customer is the approval's
    on_behalf_of (a customer row, never a Person); the order is the evidence's order_id, and
    must name this approval and this customer. Raises LookupError otherwise."""
    public.ensure_role()  # decide runs outside any turn: no agent has loaded the role
    customer = session.get(Customer, approval.requester_on_behalf_of or "")
    raw = approval.evidence.get("input")
    order = session.get(CustomerOrder, str(raw.get("order_id"))) if isinstance(raw, dict) else None
    if customer is None or order is None:
        raise LookupError("order")
    if order.approval_id != approval.id or order.customer_id != customer.id:
        raise LookupError("order")
    actor = decider.as_agent(MANIFEST.roles.agent_role)
    _require(session, actor, ORDERS, "write", None)
    return order, customer, actor


def apply_order_approval(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: the order row must still be waiting and every item still active;
    then it is confirmed with decided_by (event customer_service.order_confirmed) and the
    customer's reply is queued. Raises LookupError otherwise (the decision rolls back); a
    pickup already past is first rejected (reason other, the customer told), the approval
    expired (reason past) and committed."""
    order, customer, actor = _decided(session, approval, decider)
    if order.status != "waiting":
        raise LookupError("status")
    ids = {ln["item_id"] for ln in order.lines}
    branch = session.get(Branch, order.branch_id)
    if branch is None or len(_active_items(session, branch, list(ids))) != len(ids):
        raise LookupError("item")
    if order.pickup_at <= db.utcnow():  # approved too late: the customer is told, not served
        _reject(session, order, customer, actor, "other", decider.principal.id)
        # The pickup passed before anyone acted. decide already set the approval approved, so
        # approvals.expire (open requests only) does not apply; the row is closed here.
        expired = {"status": "expired", "reason": "past"}
        store.update(
            session, approval, expired, actor, action="approval.expired", approval_id=approval.id
        )
        session.commit()  # raised inside a request: the rollback must not lose the reply
        raise LookupError("past")
    changes = {"status": "confirmed", "decided_by": decider.principal.id}
    action = f"{MANIFEST.id}.order_confirmed"
    store.update(session, order, changes, actor, action=action, approval_id=approval.id)
    text = t("cs.order_confirmed", customer.language, time=_local(order.pickup_at, branch))
    public.queue(session, customer, [TextBlock(text=text)], public.customer_actor(customer))


def apply_order_rejection(session: Session, approval: Approval, decider: Actor) -> None:
    """Reject handler: a waiting order becomes rejected with decided_by (event
    customer_service.order_rejected with the reason key) and the customer is told the reason
    (closed, sold_out, too_large, else other); nothing is owed. An order no longer waiting
    (cancelled meanwhile) is left as it is."""
    order, customer, actor = _decided(session, approval, decider)
    if order.status != "waiting":
        return
    reason = approval.reason if approval.reason in REJECT_REASONS else "other"
    _reject(session, order, customer, actor, reason, decider.principal.id)


def _reject(
    session: Session,
    order: CustomerOrder,
    customer: Customer,
    actor: Actor,
    reason: str,
    decided_by: str | None,
) -> None:
    """The order rejected (event customer_service.order_rejected), with decided_by when a
    person decided, and the customer's reply with the reason key queued."""
    branch = session.get(Branch, order.branch_id)
    changes: dict[str, object] = {"status": "rejected"}
    if decided_by is not None:
        changes["decided_by"] = decided_by
    action = f"{MANIFEST.id}.order_rejected"
    store.update(session, order, changes, actor, action=action, approval_id=order.approval_id)
    time = _local(order.pickup_at, branch) if branch else ""
    text = t(f"cs.order_rejected.{reason}", customer.language, time=time)
    public.queue(session, customer, [TextBlock(text=text)], public.customer_actor(customer))


def close_undecided(session: Session, branch: Branch, now: dt.datetime) -> int:
    """The tick's sweep of the branch's waiting orders nobody decided in time: one whose pickup
    has passed, or whose approval is past its TTL or no longer open, gets its approval expired
    (reason past or timeout; not escalated, the customer is waiting) and is rejected with reason
    other, no decided_by, and the customer is told. A system path (Actor.system). Marker-free:
    the order leaves `waiting`, so a second sweep finds nothing. Returns how many it closed."""
    actor, count = Actor.system(branch.id), 0
    for order, customer in open_orders(session, branch, ("waiting",)):
        approval = session.get(Approval, order.approval_id) if order.approval_id else None
        is_open = approval is not None and approval.status in ("pending", "escalated")
        expires = approval.expires_at if approval is not None else None
        passed = order.pickup_at <= now
        if not (passed or not is_open or (expires is not None and expires <= now)):
            continue
        if approval is not None and is_open:
            approvals.expire(session, approval, actor, "past" if passed else "timeout")
        _reject(session, order, customer, actor, "other", None)
        count += 1
    return count


# ---- the order buttons in the chat (D47) --------------------------------------------------


def _buttons(message: Message) -> list[str]:
    return [o for b in message.blocks if b.get("type") == "quick_replies" for o in b["options"]]


def _tapped_order(session: Session, person: Person, label: str) -> Approval | None:
    """The chat-decided place_order approval asked by the person's latest message with
    buttons, when `label` is one of them; None otherwise (another message's button)."""
    rows = session.exec(
        select(Message)
        .join(Thread, col(Thread.id) == col(Message.thread_id))
        .where(Thread.person_id == person.id)
        .where(Message.role != "user")
        .order_by(col(Message.id).desc())
        .limit(RECENT)  # ponytail: a tap answers a recent message, older buttons go the chat way
    ).all()
    last = next((m for m in rows if _buttons(m)), None)
    if last is None or label.strip().casefold() not in {b.casefold() for b in _buttons(last)}:
        return None
    asked = session.exec(
        select(Event).where(Event.action == "notification.sent").where(Event.entity_id == last.id)
    ).first()
    approval = session.get(Approval, asked.approval_id) if asked and asked.approval_id else None
    ours = approval is not None and approval.type == PLACE_ORDER and approval.channel == "chat"
    return approval if ours else None


def _first(session: Session, person_id: str | None) -> str:
    person = session.get(Person, person_id or "")
    return person.name.split()[0] if person and person.name else "?"


def _asked(session: Session, approval_id: str) -> list[Person]:
    """Everyone the approval's order message went to."""
    sent = select(Event.entity_id).where(
        Event.action == "notification.sent", Event.approval_id == approval_id
    )
    return list(
        session.exec(
            select(Person)
            .join(Thread, col(Thread.person_id) == col(Person.id))
            .join(Message, col(Message.thread_id) == col(Thread.id))
            .where(col(Message.id).in_(sent))
            .distinct()
        )
    )


def decide_tap(session: Session, person: Person, label: str) -> str | None:
    """A Confirm or Decline tap on the order message (D47), decided through approvals.decide
    with channel chat and the tapping person as the actor (their approver role and branch
    checked there, no step-up). Returns the reply for the tapper: decided by them (the others
    asked are told the same), already decided by someone (nothing changes, the first tap
    wins), expired, closed, or not allowed. None when the label is no order button of the
    person's latest message with buttons. Commits the caller's work before deciding, and
    reads the status under the write lock (rule 11)."""
    outcome = TAPPED.get(label.strip().casefold())
    approval = _tapped_order(session, person, label) if outcome else None
    if approval is None or outcome is None:
        return None
    lang, approval_id = person.language or "en", approval.id
    session.commit()  # a refused handler rolls back only the decision
    session.execute(sql_text(f"UPDATE {Approval.__tablename__} SET id = id WHERE 0"))
    approval = session.get(Approval, approval_id, populate_existing=True)
    assert approval is not None
    if approval.status in DONE:
        return t(DONE[approval.status][1], lang, name=_first(session, approval.decided_by))
    actor = Actor.person(person)
    try:
        approvals.decide(session, approval_id, actor, outcome, channel="chat", aal="aal1")
    except (approvals.ApprovalError, LookupError) as exc:
        if isinstance(exc, LookupError):  # the handler refused: the row changed (the app's 409)
            session.rollback()
            with contextlib.suppress(approvals.ApprovalError):
                approvals.close_refused(session, approval_id, actor, str(exc))
        approval = session.get(Approval, approval_id, populate_existing=True)
        status = approval.status if approval else "expired"
        if status == "expired":
            return t("cs.staff.order_expired", lang)
        return t("cs.staff.order_closed" if status not in OPEN else "denied.generic", lang)
    name = _first(session, person.id)
    for other in _asked(session, approval_id):
        if other.id != person.id:
            text = t(DONE[outcome][0], other.language or "en", name=name)
            notify(session, other, [TextBlock(text=text)], actor, MANIFEST.id, urgent=True)
    return t(DONE[outcome][0], lang, name=name)


approvals.register_handler(PLACE_ORDER, apply_order_approval)
approvals.register_reject_handler(PLACE_ORDER, apply_order_rejection)


BINDINGS: list[ToolBinding] = [
    ToolBinding(
        f"{MANIFEST.id}.hours",
        hours,
        EmptyInput,
        "Whether the shop is open now, and when it opens or closes.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.prices",
        prices,
        PricesInput,
        "Prices of menu items (the whole menu when none are named).",
    ),
    ToolBinding(
        f"{MANIFEST.id}.delivery_area",
        delivery_area,
        AreaInput,
        "Whether the shop delivers to an area, and the fee.",
    ),
    ToolBinding(
        PLACE_ORDER,
        place_order,
        PlaceOrderInput,
        "Place an order for pickup or delivery. A clerk or supervisor confirms it first.",
        precheck=_order_precheck,
    ),
    ToolBinding(
        f"{MANIFEST.id}.order_status",
        order_status,
        EmptyInput,
        "The status of the customer's latest order.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.cancel_order",
        cancel_order,
        EmptyInput,
        "Cancel the customer's latest order before it is ready.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.complain",
        complain,
        ComplainInput,
        "Log a complaint and tell the supervisor.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.set_language",
        set_language,
        LanguageInput,
        "Reply to the customer in another language from now on.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.orders_today",
        orders_today,
        EmptyInput,
        "Today's confirmed and ready customer orders.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.mark_ready", mark_ready, OrderRef, "Mark a customer order ready for pickup."
    ),
    ToolBinding(
        f"{MANIFEST.id}.mark_picked_up",
        mark_picked_up,
        OrderRef,
        "Mark a customer order picked up.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.resolve_complaint",
        resolve_complaint,
        ComplaintRef,
        "Resolve a customer complaint.",
    ),
]
