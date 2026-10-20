"""The production planner's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store. No tool is bound yet (Task 4); this module holds the read and write
helpers they call, which the seed calls too (the seeded day comes from the same code).

Every number is forecast.py or capacity.py; the model never computes one. The served kiosks'
counts, stock and confirmed orders are read by the agent alone (agent_actor, no on_behalf_of)
with read_all, after the kiosk is checked against the settings' `serves` (D39, Q96). Of an
order only its lines and pickup time are read, never its note or customer. Each write helper
takes the actor it logs; the caller has checked that actor's rights."""

import copy
import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from mia.agents.base import ToolBinding
from mia.agents.inventory_manager import tools as inventory_tools
from mia.agents.production_planner import MANIFEST, forecast
from mia.agents.production_planner.models import Batch, Dispatch, Plan, Recipe
from mia.agents.sales_supervisor.tools import _live_counts
from mia.core import store
from mia.core.db import utcnow
from mia.core.models import Actor, Branch, CustomerOrder, Person, Principal, SalesCount, StockEvent
from mia.core.orgconfig import ProductionPlannerSettings
from mia.core.orgconfig import load as load_settings
from mia.core.rbac import Resource, get_rbac
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailItem

BINDINGS: list[ToolBinding] = []

COUNTS = Resource(kind="data", name=SalesCount.__tablename__)
STOCK = Resource(kind="data", name=StockEvent.__tablename__)
ORDERS = Resource(kind="data", name=CustomerOrder.__tablename__)
ONE_DAY = dt.timedelta(days=1)


def agent_actor(branch_id: str) -> Actor:
    """The planner's agent role acting alone (no person behind it) at the branch."""
    role = MANIFEST.roles.agent_role
    return Actor(principal=Principal(type="agent", id=role, roles=[role]), branch_id=branch_id)


def production_day(commissary: Branch, s: ProductionPlannerSettings, now: dt.datetime) -> dt.date:
    """The production date at now: the commissary's local date while its local time is before
    the end of production, else the next date."""
    local = now.astimezone(ZoneInfo(commissary.timezone))
    return local.date() if local.time() < s.hours.end else local.date() + ONE_DAY


def served(session: Session, commissary: Branch) -> list[Branch]:
    """The kiosks the commissary bakes for, in the settings' `serves` order (same organisation)."""
    names = load_settings().production_planner.serves
    rows = session.exec(
        select(Branch)
        .where(Branch.organisation_id == commissary.organisation_id)
        .where(col(Branch.name).in_(names))
    ).all()
    return sorted(rows, key=lambda b: names.index(b.name))


def recipes(session: Session, commissary_id: str) -> list[Recipe]:
    """The commissary's active recipes in menu order."""
    stmt = (
        select(Recipe)
        .join(RetailItem, col(RetailItem.id) == col(Recipe.item_id))
        .where(Recipe.branch_id == commissary_id)
        .where(col(Recipe.active).is_(True))
        .order_by(col(RetailItem.sort_order))
    )
    return list(session.exec(stmt))


def _recipe(session: Session, commissary_id: str, item_id: str) -> Recipe:
    found = next((r for r in recipes(session, commissary_id) if r.item_id == item_id), None)
    if found is None:
        raise LookupError("no_recipe")
    return found


def _components(session: Session) -> dict[str, list[str]]:
    return {i.id: list(i.components) for i in session.exec(select(RetailItem))}


@dataclass(frozen=True)
class KioskData:
    """What one kiosk tells the plan of a date: units per date of the 28 days before (bundles
    expanded), confirmed order pieces with pickup that date, expected leftovers (items whose
    recipe keeps overnight) and the items the inventory manager's plan says `more` for."""

    daily: dict[dt.date, dict[str, int]]
    orders: dict[str, int]
    leftovers: dict[str, int]
    more: set[str]


def kiosk_data(session: Session, commissary: Branch, kiosk: Branch, day: dt.date) -> KioskData:
    """The kiosk's numbers for production date day, read by the agent alone with read_all on
    counts, stock and orders (each check logged). Raises LookupError("not_served") for a branch
    the commissary does not bake for, PermissionDenied without the agent role's rights."""
    if kiosk.id not in {b.id for b in served(session, commissary)}:
        raise LookupError("not_served")
    actor = agent_actor(kiosk.id)
    for resource in (COUNTS, STOCK, ORDERS):
        get_rbac().require(actor, resource, "read_all", session=session)
    components = _components(session)
    counts = _live_counts(
        session, [kiosk.id], day - dt.timedelta(days=forecast.FORECAST_DAYS), day - ONE_DAY
    )
    daily = forecast.units(((c.business_date, c.item_id, c.quantity) for c in counts), components)
    zone = ZoneInfo(kiosk.timezone)
    picked = session.exec(
        select(CustomerOrder.lines, CustomerOrder.pickup_at)
        .where(CustomerOrder.branch_id == kiosk.id)
        .where(CustomerOrder.status == "confirmed")
    ).all()
    lines = [x for row, at in picked if at.astimezone(zone).date() == day for x in row]
    keeps = {r.item_id for r in recipes(session, commissary.id) if r.keeps_overnight}
    leftovers: dict[str, int] = {}
    if keeps:
        rows = session.exec(
            select(StockEvent)
            .where(StockEvent.branch_id == kiosk.id)
            .where(StockEvent.kind == "leftover")
            .where(col(StockEvent.item_id).in_(keeps))
            .where(col(StockEvent.business_date) < day)
            .order_by(col(StockEvent.business_date), col(StockEvent.at))
        )
        for r in rows:  # the last one per item wins
            leftovers[str(r.item_id)] = r.quantity or 0
    closes = retail_hours.closes(retail_hours.load(session, kiosk.id), day.weekday())
    plans = inventory_tools.plan_lines(session, kiosk.id, day - ONE_DAY, closes)
    return KioskData(
        daily=daily,
        orders=forecast.order_pieces(lines, components),
        leftovers=leftovers,
        more={p.item_id for p in plans if p.plan == "more"},
    )


def plan_lines(session: Session, commissary: Branch, day: dt.date) -> list[forecast.Line]:
    """The plan of production date day per active recipe in menu order: per served kiosk its
    forecast, orders and leftover (kiosk_data), batches and split by forecast.plan_line."""
    kiosks = served(session, commissary)
    data = {k.id: kiosk_data(session, commissary, k, day) for k in kiosks}
    out = []
    for r in recipes(session, commissary.id):
        numbers = [
            forecast.Kiosk(
                k.id,
                forecast.mean_for(data[k.id].daily, r.item_id, day),
                data[k.id].orders.get(r.item_id, 0),
                data[k.id].leftovers.get(r.item_id, 0),
            )
            for k in kiosks
        ]
        more = any(r.item_id in data[k.id].more for k in kiosks)
        out.append(forecast.plan_line(r.item_id, numbers, r.batch_yield, more))
    return out


def _line_json(
    line: forecast.Line, changed_by: str | None = None, note: str = ""
) -> dict[str, Any]:
    out = asdict(line)
    out["kiosks"] = list(out["kiosks"])
    return out | {"changed_by": changed_by, "change_note": note}


def plan_for(session: Session, commissary_id: str, day: dt.date) -> Plan | None:
    """The commissary's plan row of production date day, if any."""
    stmt = select(Plan).where(Plan.branch_id == commissary_id).where(Plan.production_date == day)
    return session.exec(stmt).first()


def draft_plan(session: Session, commissary: Branch, day: dt.date) -> Plan:
    """The plan of day: the existing row when there is one, else a draft from plan_lines,
    written by the agent alone (event `<agent>.plan_drafted`)."""
    existing = plan_for(session, commissary.id, day)
    if existing is not None:
        return existing
    row = Plan(
        branch_id=commissary.id,
        production_date=day,
        lines=[_line_json(x) for x in plan_lines(session, commissary, day)],
    )
    return store.insert(
        session, row, agent_actor(commissary.id), action=f"{MANIFEST.id}.plan_drafted"
    )


def set_batches(
    session: Session, plan: Plan, item_id: str, batches: int, actor: Actor, note: str = ""
) -> Plan:
    """The plan with the item at `batches` whole batches, split again over the kiosks from the
    line's numbers (forecast.plan_line), changed_by the actor's person (event
    `<agent>.plan_changed`). Raises LookupError("not_planned") for an item not in the plan,
    LookupError("no_recipe") without its active recipe."""
    lines = copy.deepcopy(plan.lines)
    index = next((i for i, x in enumerate(lines) if x["item_id"] == item_id), None)
    if index is None:
        raise LookupError("not_planned")
    old = lines[index]
    kiosks = [
        forecast.Kiosk(k["branch_id"], k["forecast"], k["orders"], k["leftover"])
        for k in old["kiosks"]
    ]
    batch_yield = _recipe(session, plan.branch_id, item_id).batch_yield
    line = forecast.plan_line(item_id, kiosks, batch_yield, old["more"], batches=batches)
    lines[index] = _line_json(line, actor.person_id, note)
    return store.update(
        session, plan, {"lines": lines}, actor, action=f"{MANIFEST.id}.plan_changed"
    )


def confirm(session: Session, plan: Plan, person: Person, actor: Actor) -> Plan:
    """The plan confirmed by the person (event `<agent>.plan_confirmed`)."""
    changes = {"status": "confirmed", "confirmed_by": person.id}
    return store.update(session, plan, changes, actor, action=f"{MANIFEST.id}.plan_confirmed")


class BatchInput(BaseModel):
    item_id: str
    batch_no: int = Field(ge=1)
    good: int = Field(ge=0)
    waste: int = Field(0, ge=0)
    reason: Literal["burnt", "undercooked", "dropped", "other"] | None = None


def save_batch(
    session: Session,
    plan: Plan,
    args: BatchInput,
    person: Person,
    actor: Actor,
    *,
    at: dt.datetime | None = None,
) -> Batch:
    """One batch of the plan recorded by the person at `at` (default now), its planned yield
    the recipe's; a repeated batch number updates its row (a correction). Event
    `<agent>.batch_recorded`. Raises LookupError("not_planned") for an item not in the plan."""
    if all(x["item_id"] != args.item_id for x in plan.lines):
        raise LookupError("not_planned")
    values: dict[str, Any] = {
        "planned_yield": _recipe(session, plan.branch_id, args.item_id).batch_yield,
        "good": args.good,
        "waste": args.waste,
        "reason": args.reason,
        "recorded_by": person.id,
        "at": at or utcnow(),
    }
    action = f"{MANIFEST.id}.batch_recorded"
    existing = session.exec(
        select(Batch)
        .where(Batch.plan_id == plan.id)
        .where(Batch.item_id == args.item_id)
        .where(Batch.batch_no == args.batch_no)
    ).first()
    if existing is not None:
        return store.update(session, existing, values, actor, action=action)
    row = Batch(
        branch_id=plan.branch_id,
        plan_id=plan.id,
        item_id=args.item_id,
        batch_no=args.batch_no,
        **values,
    )
    return store.insert(session, row, actor, action=action)


def good_pieces(session: Session, plan: Plan) -> dict[str, int]:
    """Per item of the plan the pieces out of the ovens: a recorded batch its good, a planned
    batch not yet recorded its planned yield."""
    rows = session.exec(select(Batch).where(Batch.plan_id == plan.id)).all()
    out = {}
    for line in plan.lines:
        done = {b.batch_no: b.good for b in rows if b.item_id == line["item_id"]}
        per = line["pieces"] // line["batches"] if line["batches"] else 0
        planned = sum(per for n in range(1, line["batches"] + 1) if n not in done)
        out[line["item_id"]] = sum(done.values()) + planned
    return out


def pack(session: Session, plan: Plan, actor: Actor) -> list[Dispatch]:
    """One dispatch per kiosk of the plan (event `<agent>.dispatch_packed`), its lines the
    good pieces split by forecast.dispatch_split over the planned pieces, lines of 0 left out;
    the existing rows when the plan is packed."""
    existing = session.exec(select(Dispatch).where(Dispatch.plan_id == plan.id)).all()
    if existing:
        return list(existing)
    good = good_pieces(session, plan)
    kiosks: dict[str, list[dict[str, Any]]] = {}
    for line in plan.lines:
        planned = {k["branch_id"]: k["pieces"] for k in line["kiosks"]}
        for branch_id, quantity in forecast.dispatch_split(good[line["item_id"]], planned).items():
            sent = kiosks.setdefault(branch_id, [])
            if quantity:
                sent.append({"item_id": line["item_id"], "quantity": quantity})
    action = f"{MANIFEST.id}.dispatch_packed"
    return [
        store.insert(
            session,
            Dispatch(
                branch_id=branch_id,
                from_branch_id=plan.branch_id,
                plan_id=plan.id,
                business_date=plan.production_date,
                lines=lines,
            ),
            actor,
            action=action,
        )
        for branch_id, lines in kiosks.items()
    ]


def match(session: Session, dispatch: Dispatch, now: dt.datetime, actor: Actor) -> str:
    """Compare the dispatch with the kiosk's `received` stock events of its items on its
    business date up to now (read by the agent alone with read_all): `matched` when every line
    equals what was received, else `short` (no receipt at all included). Stores the status and
    the received quantities (event `<agent>.matched` or `<agent>.short`)."""
    get_rbac().require(agent_actor(dispatch.branch_id), STOCK, "read_all", session=session)
    rows = session.exec(
        select(StockEvent)
        .where(StockEvent.branch_id == dispatch.branch_id)
        .where(StockEvent.kind == "received")
        .where(StockEvent.business_date == dispatch.business_date)
        .where(col(StockEvent.item_id).is_not(None))
    ).all()
    got: dict[str, int] = {}
    for r in rows:
        if r.at <= now:
            got[str(r.item_id)] = got.get(str(r.item_id), 0) + (r.quantity or 0)
    wanted = {x["item_id"] for x in dispatch.lines}
    received = [{"item_id": i, "quantity": got.get(i, 0)} for i in wanted | set(got)]
    received.sort(key=lambda x: str(x["item_id"]))
    ok = all(got.get(x["item_id"], 0) == x["quantity"] for x in dispatch.lines)
    status = "matched" if ok else "short"
    changes = {"status": status, "received": received}
    store.update(session, dispatch, changes, actor, action=f"{MANIFEST.id}.{status}")
    return status
