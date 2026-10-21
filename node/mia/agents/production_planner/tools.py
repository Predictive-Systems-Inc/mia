"""The production planner's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store. The read and write helpers come first (the seed calls them too, so
the seeded day comes from the same code), the nine tools after them.

Every number is forecast.py or capacity.py; the model never computes one. The served kiosks'
counts, stock and confirmed orders are read by the agent alone (agent_actor, no on_behalf_of)
with read_all, after the kiosk is checked against the settings' `serves` (D39, Q96). Of an
order only its lines and pickup time are read, never its note or customer. Each write helper
takes the actor it logs; the caller has checked that actor's rights.

Scope of the tools: plans, recipes and batches are rows of the commissary. Its people work on
them with read or write; anyone elsewhere needs read_all or write_all (owner and admin), except
that a served kiosk's supervisor reads the plan lines of their own kiosk. A dispatch is a row of
the kiosk it goes to: the commissary's people (the driver with read_own, Q94) see the ones sent
from their branch, a kiosk supervisor their own kiosk's. Only the driver (skill `driver`) and
the commissary's supervisor confirm a delivery. No tool is money, external or delete, so none
asks for an approval."""

import copy
import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.inventory_manager import tools as inventory_tools
from mia.agents.production_planner import MANIFEST, forecast
from mia.agents.production_planner import capacity as oven
from mia.agents.production_planner.models import Batch, Dispatch, Plan, Recipe
from mia.agents.sales_supervisor.tools import (
    ITEMS,
    _as_reporter,
    _check,
    _currency,
    _is_lead,
    _live_counts,
)
from mia.agents.shift_supervisor import alerts
from mia.chat.channels import notify
from mia.core import events, store
from mia.core.db import utcnow
from mia.core.models import (
    Actor,
    Branch,
    CustomerOrder,
    Message,
    Person,
    Principal,
    SalesCount,
    StockEvent,
)
from mia.core.orgconfig import ProductionPlannerSettings
from mia.core.orgconfig import load as load_settings
from mia.core.rbac import PermissionDenied, Resource, get_rbac
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailIngredient, RetailItem

COUNTS = Resource(kind="data", name=SalesCount.__tablename__)
STOCK = Resource(kind="data", name=StockEvent.__tablename__)
ORDERS = Resource(kind="data", name=CustomerOrder.__tablename__)
INGREDIENTS = Resource(kind="data", name=RetailIngredient.__tablename__)
RECIPES = Resource(kind="data", name=Recipe.__tablename__)
PLANS = Resource(kind="data", name=Plan.__tablename__)
BATCHES = Resource(kind="data", name=Batch.__tablename__)
DISPATCHES = Resource(kind="data", name=Dispatch.__tablename__)
PEOPLE = Resource(kind="data", name="core.person")
BRANCHES = Resource(kind="data", name="core.branch")
DRIVER = "driver"
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


def batch_day(commissary: Branch, s: ProductionPlannerSettings, now: dt.datetime) -> dt.date:
    """The production date a batch recorded at now belongs to: the latest one whose
    hours.start has passed (the local date from hours.start on, else the day before), so a
    correction after the end of production stays on that day's plan."""
    local = now.astimezone(ZoneInfo(commissary.timezone))
    return local.date() if local.time() >= s.hours.start else local.date() - ONE_DAY


def served(session: Session, commissary: Branch) -> list[Branch]:
    """The kiosks the commissary bakes for, in the settings' `serves` order (same organisation),
    read by the agent alone after its core.branch read check."""
    get_rbac().require(agent_actor(commissary.id), BRANCHES, "read", session=session)
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
    recipe keeps overnight, counted the day before) and the items the inventory manager's plan
    says `more` for."""

    daily: dict[dt.date, dict[str, int]]
    orders: dict[str, int]
    leftovers: dict[str, int]
    more: set[str]


def kiosk_data(session: Session, commissary: Branch, kiosk: Branch, day: dt.date) -> KioskData:
    """The kiosk's numbers for production date day, read by the agent alone with read_all on
    counts, stock and orders and read on items, recipes and hours (each check logged). Raises
    LookupError("not_served") for a branch the commissary does not bake for, PermissionDenied
    without the agent role's rights."""
    if kiosk.id not in {b.id for b in served(session, commissary)}:
        raise LookupError("not_served")
    actor, rbac = agent_actor(kiosk.id), get_rbac()
    for resource in (COUNTS, STOCK, ORDERS):
        rbac.require(actor, resource, "read_all", session=session)
    for resource in (ITEMS, RECIPES, inventory_tools.HOURS):
        rbac.require(actor, resource, "read", session=session)
    components = _components(session)
    counts = _live_counts(
        session, [kiosk.id], day - dt.timedelta(days=forecast.FORECAST_DAYS), day - ONE_DAY
    )
    daily = forecast.units(((c.business_date, c.item_id, c.quantity) for c in counts), components)
    zone = ZoneInfo(kiosk.timezone)
    # ponytail: pickup_at is an ISO string with its writer's offset, so the SQL bound is the
    # day widened by one each side (any offset lands in it); the exact local date is cut below.
    lo = dt.datetime.combine(day - ONE_DAY, dt.time(), dt.UTC)
    hi = dt.datetime.combine(day + 2 * ONE_DAY, dt.time(), dt.UTC)
    picked = session.exec(
        select(CustomerOrder.lines, CustomerOrder.pickup_at)
        .where(CustomerOrder.branch_id == kiosk.id)
        .where(CustomerOrder.status == "confirmed")
        .where(col(CustomerOrder.pickup_at) >= lo)
        .where(col(CustomerOrder.pickup_at) < hi)
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
            .where(StockEvent.business_date == day - ONE_DAY)
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
    """The commissary's plan row of production date day, if any, read by the agent alone after
    its plans read check (PermissionDenied without it)."""
    get_rbac().require(agent_actor(commissary_id), PLANS, "read", session=session)
    stmt = select(Plan).where(Plan.branch_id == commissary_id).where(Plan.production_date == day)
    return session.exec(stmt).first()


def draft_plan(session: Session, commissary: Branch, day: dt.date) -> Plan:
    """The plan of day: the existing row when there is one, else a draft from plan_lines,
    written by the agent alone (event `<agent>.plan_drafted`). Raises
    LookupError("not_commissary") for a branch other than the settings' commissary."""
    if commissary.name != load_settings().production_planner.commissary:
        raise LookupError("not_commissary")
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
    the recipe's; a repeated batch number updates its row (a correction). The read of that row
    and its write run under the write lock (rule 11). Event `<agent>.batch_recorded`. Raises
    LookupError("not_planned") for an item not in the plan or a batch number above its line's
    batches."""
    line = next((x for x in plan.lines if x["item_id"] == args.item_id), None)
    if line is None or args.batch_no > line["batches"]:
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
    events.write_lock(session)
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
    good pieces split by forecast.dispatch_split over the planned pieces, lines of 0 left out
    and a kiosk with no line at all skipped; the existing rows when the plan is packed."""
    existing = session.exec(select(Dispatch).where(Dispatch.plan_id == plan.id)).all()
    if existing:
        return list(existing)
    good = good_pieces(session, plan)
    kiosks: dict[str, list[dict[str, Any]]] = {}
    for line in plan.lines:
        planned = {k["branch_id"]: k["pieces"] for k in line["kiosks"]}
        for branch_id, quantity in forecast.dispatch_split(good[line["item_id"]], planned).items():
            if quantity:
                sent = kiosks.setdefault(branch_id, [])
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


class ItemYield(BaseModel):
    item_id: str
    good: int
    planned: int
    waste: int
    percent: int | None


class YieldOut(BaseModel):
    day: dt.date
    items: list[ItemYield]


def day_yield(session: Session, commissary: Branch, day: dt.date) -> YieldOut:
    """The yield of the commissary's plan of production date day, read by the agent alone:
    per item with a recorded batch (plan line order) the good pieces, the planned yield of
    those batches, the waste and forecast.yield_percent. No plan or no batch: no items."""
    get_rbac().require(agent_actor(commissary.id), BATCHES, "read", session=session)
    plan = plan_for(session, commissary.id, day)
    rows = [] if plan is None else session.exec(select(Batch).where(Batch.plan_id == plan.id)).all()
    items = []
    for line in plan.lines if plan is not None else []:
        mine = [b for b in rows if b.item_id == line["item_id"]]
        if not mine:
            continue
        good, planned = sum(b.good for b in mine), sum(b.planned_yield for b in mine)
        items.append(
            ItemYield(
                item_id=line["item_id"],
                good=good,
                planned=planned,
                waste=sum(b.waste for b in mine),
                percent=forecast.yield_percent(good, planned),
            )
        )
    return YieldOut(day=day, items=items)


# ---- shared helpers of the tools ----------------------------------------------------------


def commissary(session: Session, organisation_id: str) -> Branch | None:
    """The organisation's commissary by the settings' name; None when the planner is off."""
    name = load_settings().production_planner.commissary
    if not name:
        return None
    stmt = select(Branch).where(Branch.organisation_id == organisation_id)
    return session.exec(stmt.where(Branch.name == name)).first()


def _commissary(deps: AgentDeps) -> Branch:
    """The person's organisation's commissary; LookupError("no_commissary") when it has none."""
    row = commissary(deps.session, deps.organisation_id)
    if row is None:
        raise LookupError("no_commissary")
    return row


def _day(commissary: Branch, given: dt.date | None) -> dt.date:
    """The given production date, or the production day; a date before the production day
    raises LookupError("past")."""
    today = _today(commissary)
    day = given or today
    if day < today:
        raise LookupError("past")
    return day


def _at_commissary(
    deps: AgentDeps, commissary: Branch, resources: list[Resource], action: str, tool_call_id: str
) -> None:
    """The action on every resource, and `<action>_all` on each when the person is not at the
    commissary (PermissionDenied otherwise)."""
    for resource in resources:
        _check(deps, resource, action, tool_call_id)
        if deps.branch.id != commissary.id:
            _check(deps, resource, f"{action}_all", tool_call_id)


def _today(commissary: Branch) -> dt.date:
    """The production date at the commissary now."""
    return production_day(commissary, load_settings().production_planner, utcnow())


def _batch_day(commissary: Branch) -> dt.date:
    """The production date a batch recorded now belongs to (batch_day)."""
    return batch_day(commissary, load_settings().production_planner, utcnow())


def _plan(deps: AgentDeps, commissary: Branch, day: dt.date) -> Plan:
    plan = plan_for(deps.session, commissary.id, day)
    if plan is None:
        raise LookupError("no_plan")
    return plan


def _line(plan: Plan, item_id: str) -> dict[str, Any]:
    line = next((x for x in plan.lines if x["item_id"] == item_id), None)
    if line is None:
        raise LookupError("not_planned")
    return line


# ---- plan, change_plan, confirm_plan ------------------------------------------------------


class PlanInput(BaseModel):
    production_date: dt.date | None = Field(None, description="Only when the user names the day")


class KioskOut(BaseModel):
    branch_id: str
    forecast: int | None
    orders: int
    leftover: int
    demand: int
    pieces: int


class LineOut(BaseModel):
    item_id: str
    batches: int
    pieces: int
    more: bool
    kiosks: list[KioskOut]


class PlanOut(BaseModel):
    plan_id: str
    production_date: dt.date
    status: str
    lines: list[LineOut]
    minutes_free: int


def plan_out(session: Session, plan: Plan, kiosk_id: str | None = None) -> PlanOut:
    """The plan with the commissary's free oven minutes of its date; with kiosk_id every line
    carries that kiosk only."""
    lines = [
        LineOut(
            item_id=x["item_id"],
            batches=x["batches"],
            pieces=x["pieces"],
            more=x["more"],
            kiosks=[
                KioskOut.model_validate(k)
                for k in x["kiosks"]
                if kiosk_id is None or k["branch_id"] == kiosk_id
            ],
        )
        for x in plan.lines
    ]
    free = oven.free(session, plan.branch_id, plan.production_date).minutes_free
    return PlanOut(
        plan_id=plan.id,
        production_date=plan.production_date,
        status=plan.status,
        lines=lines,
        minutes_free=free,
    )


def plan(deps: AgentDeps, args: PlanInput, tool_call_id: str) -> PlanOut:
    """The plan of the production date (default the commissary's production day). The
    commissary's people and anyone with read_all see every kiosk; a served kiosk's supervisor
    sees their kiosk only. Raises LookupError("no_plan") before the draft."""
    commissary = _commissary(deps)
    _check(deps, PLANS, "read", tool_call_id)
    _check(deps, RECIPES, "read", tool_call_id)
    kiosk_id = None
    if deps.branch.id != commissary.id:
        rbac = get_rbac()
        everything = all(
            rbac.check(deps.actor, r, "read_all", session=deps.session, tool_call_id=tool_call_id)
            for r in (PLANS, RECIPES)
        )
        if not everything:
            if deps.branch.id not in {b.id for b in served(deps.session, commissary)}:
                _check(deps, PLANS, "read_all", tool_call_id)  # raises PermissionDenied
            kiosk_id = deps.branch.id
    day = args.production_date or _today(commissary)
    return plan_out(deps.session, _plan(deps, commissary, day), kiosk_id)


class ChangePlanInput(BaseModel):
    item_id: str
    batches: int = Field(ge=0, le=40, description="The item's whole batches after the change")
    production_date: dt.date | None = Field(None, description="Only when the user names the day")


def check_change(deps: AgentDeps, args: ChangePlanInput, tool_call_id: str) -> None:
    """The precheck of change_plan: the rights first (write on plans, write_all away from the
    commissary), then the date (filled in place; a date before the production day is `past`),
    the plan and its line, and the ovens: added batches beyond the free oven minutes refuse
    (`capacity`)."""
    commissary = _commissary(deps)
    _at_commissary(deps, commissary, [PLANS, RECIPES], "write", tool_call_id)
    args.production_date = _day(commissary, args.production_date)
    old = _line(_plan(deps, commissary, args.production_date), args.item_id)["batches"]
    recipe = _recipe(deps.session, commissary.id, args.item_id)
    free = oven.free(deps.session, commissary.id, args.production_date).minutes_free
    if (args.batches - old) * recipe.oven_minutes > free:
        raise LookupError("capacity")


def change_plan(deps: AgentDeps, args: ChangePlanInput, tool_call_id: str) -> PlanOut:
    """The plan with the item at the given batches, split again (set_batches; event
    `<agent>.plan_changed`). check_change ran first through the guard."""
    check_change(deps, args, tool_call_id)  # a direct call skips the guard's precheck
    commissary = _commissary(deps)
    day = args.production_date or _today(commissary)
    row = set_batches(
        deps.session, _plan(deps, commissary, day), args.item_id, args.batches, deps.actor
    )
    return plan_out(deps.session, row)


class ConfirmPlanInput(BaseModel):
    production_date: dt.date | None = Field(None, description="Only when the user names the day")


def confirm_plan(deps: AgentDeps, args: ConfirmPlanInput, tool_call_id: str) -> PlanOut:
    """The plan of the production date confirmed by the person (event
    `<agent>.plan_confirmed`); a confirmed plan is returned unchanged, no second event.
    Raises LookupError("past") before the production day, LookupError("no_plan")."""
    commissary = _commissary(deps)
    _at_commissary(deps, commissary, [PLANS], "write", tool_call_id)
    _check(deps, RECIPES, "read", tool_call_id)
    row = _plan(deps, commissary, _day(commissary, args.production_date))
    if row.status != "confirmed":
        row = confirm(deps.session, row, deps.person, deps.actor)
    return plan_out(deps.session, row)


# ---- batch_sheet and set_recipe -----------------------------------------------------------


class BatchSheetInput(BaseModel):
    item_id: str
    production_date: dt.date | None = Field(None, description="Only when the user names the day")


class SheetLineOut(BaseModel):
    ingredient_id: str
    quantity_milli: int
    unit: str
    cost: int | None


class SheetOut(BaseModel):
    item_id: str
    batches: int
    batch_yield: int
    lines: list[SheetLineOut]
    cost_per_batch: int | None
    cost_per_piece: int | None
    currency: str


def batch_sheet(deps: AgentDeps, args: BatchSheetInput, tool_call_id: str) -> SheetOut:
    """The item's recipe times the batches of the day's plan (1 without a plan or line), with
    costs from the ingredients' pack prices (forecast.sheet). Raises LookupError("no_recipe")."""
    commissary = _commissary(deps)
    _at_commissary(deps, commissary, [RECIPES, PLANS], "read", tool_call_id)
    _check(deps, INGREDIENTS, "read", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    recipe = _recipe(deps.session, commissary.id, args.item_id)
    row = plan_for(deps.session, commissary.id, args.production_date or _today(commissary))
    line = next((x for x in row.lines if x["item_id"] == args.item_id), None) if row else None
    batches = line["batches"] if line else 1
    found = {i.id: i for i in deps.session.exec(select(RetailIngredient))}
    pairs = [(x["ingredient_id"], x["quantity_milli"]) for x in recipe.lines]
    prices = {i: found[i].pack_price if i in found else None for i, _ in pairs}
    s = forecast.sheet(pairs, prices, batches, recipe.batch_yield)
    return SheetOut(
        item_id=args.item_id,
        batches=s.batches,
        batch_yield=s.batch_yield,
        lines=[
            SheetLineOut(
                ingredient_id=x.ingredient_id,
                quantity_milli=x.quantity_milli,
                unit=found[x.ingredient_id].unit if x.ingredient_id in found else "",
                cost=x.cost,
            )
            for x in s.lines
        ],
        cost_per_batch=s.cost_per_batch,
        cost_per_piece=s.cost_per_piece,
        currency=_currency(deps.session, commissary.id),
    )


class RecipeLine(BaseModel):
    ingredient_id: str
    quantity_milli: int = Field(gt=0, description="Thousandths of the ingredient's unit")


class RecipeInput(BaseModel):
    item_id: str
    batch_yield: int = Field(gt=0, le=500)
    oven_minutes: int = Field(gt=0, le=600)
    lines: list[RecipeLine] = Field(min_length=1)
    keeps_overnight: bool = False


class RecipeOut(BaseModel):
    id: str
    item_id: str
    batch_yield: int
    oven_minutes: int
    lines: list[RecipeLine]
    keeps_overnight: bool


def check_recipe(deps: AgentDeps, args: RecipeInput, tool_call_id: str) -> None:
    """The precheck of set_recipe: the rights first (write on recipes, write_all away from the
    commissary), then the item exists (`item`) and is a single item, never a bundle
    (`bundle`); every ingredient exists (`ingredient`)."""
    _at_commissary(deps, _commissary(deps), [RECIPES], "write", tool_call_id)
    _check(deps, ITEMS, "read", tool_call_id)
    _check(deps, INGREDIENTS, "read", tool_call_id)
    found = deps.session.get(RetailItem, args.item_id)
    if found is None:
        raise LookupError("item")
    if found.components:
        raise LookupError("bundle")
    for x in args.lines:
        if deps.session.get(RetailIngredient, x.ingredient_id) is None:
            raise LookupError("ingredient")


def set_recipe(deps: AgentDeps, args: RecipeInput, tool_call_id: str) -> RecipeOut:
    """The item's recipe at the commissary, set by the person: the old active row made
    inactive, a new row written (both events `<agent>.recipe_set`)."""
    check_recipe(deps, args, tool_call_id)  # a direct call skips the guard's precheck
    commissary = _commissary(deps)
    _at_commissary(deps, commissary, [RECIPES], "read", tool_call_id)
    _at_commissary(deps, commissary, [RECIPES], "write", tool_call_id)
    action = f"{MANIFEST.id}.recipe_set"
    for old in recipes(deps.session, commissary.id):
        if old.item_id == args.item_id:
            store.update(deps.session, old, {"active": False}, deps.actor, action=action)
    row = store.insert(
        deps.session,
        Recipe(
            branch_id=commissary.id,
            item_id=args.item_id,
            batch_yield=args.batch_yield,
            oven_minutes=args.oven_minutes,
            lines=[x.model_dump() for x in args.lines],
            keeps_overnight=args.keeps_overnight,
            set_by=deps.person.id,
        ),
        deps.actor,
        action=action,
        tool_call_id=tool_call_id,
    )
    return RecipeOut(
        id=row.id,
        item_id=row.item_id,
        batch_yield=row.batch_yield,
        oven_minutes=row.oven_minutes,
        lines=args.lines,
        keeps_overnight=row.keeps_overnight,
    )


# ---- record_batch -------------------------------------------------------------------------


class BatchOut(BaseModel):
    id: str
    item_id: str
    batch_no: int
    planned_yield: int
    good: int
    waste: int
    reason: str | None
    day_percent: int | None
    last: bool


def check_batch(deps: AgentDeps, args: BatchInput, tool_call_id: str) -> None:
    """The precheck of record_batch: the rights first (write on batches, write_all away from
    the commissary), then the plan of the batch day (batch_day: `no_plan`), the item and batch
    number in it (`not_planned`), and good plus waste at most twice the batch yield
    (`batch_total`)."""
    commissary = _commissary(deps)
    _at_commissary(deps, commissary, [BATCHES], "write", tool_call_id)
    _at_commissary(deps, commissary, [PLANS, RECIPES], "read", tool_call_id)
    line = _line(_plan(deps, commissary, _batch_day(commissary)), args.item_id)
    if args.batch_no > line["batches"]:
        raise LookupError("not_planned")
    if args.good + args.waste > 2 * _recipe(deps.session, commissary.id, args.item_id).batch_yield:
        raise LookupError("batch_total")


def _all_recorded(session: Session, plan: Plan) -> bool:
    done = {
        (b.item_id, b.batch_no) for b in session.exec(select(Batch).where(Batch.plan_id == plan.id))
    }
    return all((x["item_id"], n) in done for x in plan.lines for n in range(1, x["batches"] + 1))


def record_batch(deps: AgentDeps, args: BatchInput, tool_call_id: str) -> BatchOut:
    """One batch of the batch day's plan recorded by the person (save_batch), with the item's
    yield percent so far. When it is the plan's last unrecorded batch the dispatches are packed
    by the agent alone and their lists sent, urgent (send_dispatch). The agent's write_all on
    dispatches is checked before the batch is saved, so a denied grant leaves no batch row."""
    check_batch(deps, args, tool_call_id)  # a direct call skips the guard's precheck
    commissary = _commissary(deps)
    plan = _plan(deps, commissary, _batch_day(commissary))
    agent = agent_actor(commissary.id)
    get_rbac().require(agent, DISPATCHES, "write_all", session=deps.session)
    row = save_batch(deps.session, plan, args, deps.person, deps.actor)
    rows = deps.session.exec(
        select(Batch).where(Batch.plan_id == plan.id).where(Batch.item_id == args.item_id)
    ).all()
    percent = forecast.yield_percent(sum(b.good for b in rows), sum(b.planned_yield for b in rows))
    last = _all_recorded(deps.session, plan)
    if last:
        packed = deps.session.exec(select(Dispatch).where(Dispatch.plan_id == plan.id)).first()
        if packed is None:
            send_dispatch(deps.session, commissary, pack(deps.session, plan, agent))
    return BatchOut(
        id=row.id,
        item_id=row.item_id,
        batch_no=row.batch_no,
        planned_yield=row.planned_yield,
        good=row.good,
        waste=row.waste,
        reason=row.reason,
        day_percent=percent,
        last=last,
    )


def send_dispatch(session: Session, commissary: Branch, rows: list[Dispatch]) -> list[Message]:
    """One card per person with every dispatch (replies.dispatch_card: the lists and a
    Delivered button per packed kiosk, the decisions stored by turn.remember) to the
    commissary's supervisors and every active person there with the driver skill, urgent.
    People and items are read by the agent alone after its read check. Returns the messages
    sent (none without a dispatch)."""
    from mia.agents.production_planner import replies, turn  # both import this module

    agent, rbac = agent_actor(commissary.id), get_rbac()
    rbac.require(agent, PEOPLE, "read", session=session)
    people = session.exec(select(Person).where(Person.branch_id == commissary.id)).all()
    heads = alerts.supervisors(session, commissary.id)
    drivers = [p for p in people if DRIVER in p.skills and p.status == "active"]
    to = list({p.id: p for p in [*heads, *drivers]}.values())
    rbac.require(agent, ITEMS, "read", session=session)
    names = {i.id: i.name for i in session.exec(select(RetailItem))}
    names |= {k.id: k.name for k in served(session, commissary)}  # the kiosks named in settings
    actor = Actor.system(commissary.id)
    outs, sent = [dispatch_out(d) for d in rows], []
    for person in to if outs else []:
        blocks, options = replies.dispatch_card(outs, names, person.language or "en")
        message = notify(session, person, blocks, actor, MANIFEST.id, urgent=True)
        turn.remember(session, message, options, actor)
        sent.append(message)
    return sent


# ---- dispatch_list and confirm_delivery ---------------------------------------------------


class DispatchInput(BaseModel):
    kiosk_id: str | None = None
    business_date: dt.date | None = Field(None, description="Only when the user names the day")


class DispatchOut(BaseModel):
    id: str
    branch_id: str
    business_date: dt.date
    lines: list[dict[str, Any]]
    status: str


class DispatchListOut(BaseModel):
    dispatches: list[DispatchOut]


def dispatch_out(row: Dispatch) -> DispatchOut:
    """The dispatch as a tool output."""
    return DispatchOut(
        id=row.id,
        branch_id=row.branch_id,
        business_date=row.business_date,
        lines=row.lines,
        status=row.status,
    )


def _dispatches(
    deps: AgentDeps, commissary: Branch, kiosk_id: str | None, action: str, tool_call_id: str
) -> list[Dispatch]:
    """The dispatches the person may see, newest date first: at the commissary those sent from
    it (to kiosk_id when named), elsewhere those to the person's kiosk; another kiosk needs
    `<action>_all`. A named kiosk_id the commissary does not serve has none. The check carries
    the person as owner, so read_own and write_own gate by role (Q94) and the query decides the
    rows."""
    _check(deps, _as_reporter(DISPATCHES, deps), action, tool_call_id)
    stmt = select(Dispatch).order_by(col(Dispatch.business_date).desc())
    if deps.branch.id == commissary.id:
        stmt = stmt.where(Dispatch.from_branch_id == commissary.id)
        if kiosk_id is not None:
            stmt = stmt.where(Dispatch.branch_id == kiosk_id)
    else:
        if kiosk_id is not None and kiosk_id != deps.branch.id:
            _check(deps, DISPATCHES, f"{action}_all", tool_call_id)
        stmt = stmt.where(Dispatch.branch_id == (kiosk_id or deps.branch.id))
    if kiosk_id is not None and kiosk_id not in {b.id for b in served(deps.session, commissary)}:
        return []
    return list(deps.session.exec(stmt))


def check_list(deps: AgentDeps, args: DispatchInput, tool_call_id: str) -> None:
    """The precheck of dispatch_list (spec section 9): staff need the driver skill; a
    supervisor, owner or admin passes (PermissionDenied otherwise)."""
    person = deps.person
    if not (_is_lead(person) or "supervisor" in person.roles or DRIVER in person.skills):
        raise PermissionDenied(deps.actor.principal.id, "skill:driver")


def dispatch_list(deps: AgentDeps, args: DispatchInput, tool_call_id: str) -> DispatchListOut:
    """The dispatches of the business date (default the person's business date, deps.today,
    so no earlier day's list shows before today's is packed), scoped by _dispatches."""
    check_list(deps, args, tool_call_id)  # a direct call skips the guard's precheck
    rows = _dispatches(deps, _commissary(deps), args.kiosk_id, "read", tool_call_id)
    day = args.business_date or deps.today
    return DispatchListOut(dispatches=[dispatch_out(d) for d in rows if d.business_date == day])


class DeliveredInput(BaseModel):
    kiosk_id: str
    business_date: dt.date | None = Field(None, description="Only when the user names the day")


def check_driver(deps: AgentDeps, args: DeliveredInput, tool_call_id: str) -> None:
    """The precheck of confirm_delivery: an owner or admin passes at any branch after the
    write_all check on dispatches (spec section 3; PermissionDenied without it); anyone else
    is at the commissary and has the driver skill or the supervisor role, else `not_driver`."""
    if _is_lead(deps.person):
        _check(deps, DISPATCHES, "write_all", tool_call_id)
        return
    at_commissary = deps.branch.id == _commissary(deps).id
    if not at_commissary or not (DRIVER in deps.person.skills or "supervisor" in deps.person.roles):
        raise LookupError("not_driver")


def confirm_delivery(deps: AgentDeps, args: DeliveredInput, tool_call_id: str) -> DispatchOut:
    """The kiosk's dispatch of the business date (default its newest) delivered by the person
    (event `<agent>.delivered`); a dispatch already past packed is returned unchanged. Raises
    LookupError("no_dispatch")."""
    check_driver(deps, args, tool_call_id)  # a direct call skips the guard's precheck
    commissary = _commissary(deps)
    _check(deps, _as_reporter(DISPATCHES, deps), "read", tool_call_id)
    rows = _dispatches(deps, commissary, args.kiosk_id, "write", tool_call_id)
    day = args.business_date or (rows[0].business_date if rows else None)
    row = next((d for d in rows if d.business_date == day), None)
    if row is None:
        raise LookupError("no_dispatch")
    if row.status == "packed":
        changes = {"status": "delivered", "delivered_by": deps.person.id, "delivered_at": utcnow()}
        row = store.update(
            deps.session,
            row,
            changes,
            deps.actor,
            action=f"{MANIFEST.id}.delivered",
            tool_call_id=tool_call_id,
        )
    return dispatch_out(row)


# ---- capacity -----------------------------------------------------------------------------


class CapacityInput(BaseModel):
    day: dt.date
    item_id: str | None = None
    pieces: int | None = Field(None, gt=0)


class CapacityOut(BaseModel):
    day: dt.date
    minutes_free: int
    per_item: dict[str, int]
    fits: bool | None


def capacity(deps: AgentDeps, args: CapacityInput, tool_call_id: str) -> CapacityOut:
    """The commissary's free oven minutes and free pieces per item on the day (capacity.free);
    with an item and pieces whether they fit. Raises LookupError("no_recipe") for an item
    without an active recipe."""
    commissary = _commissary(deps)
    _at_commissary(deps, commissary, [RECIPES, PLANS], "read", tool_call_id)
    free = oven.free(deps.session, commissary.id, args.day)
    fits = None
    if args.item_id is not None:
        if args.item_id not in free.per_item:
            raise LookupError("no_recipe")
        fits = None if args.pieces is None else args.pieces <= free.per_item[args.item_id]
    return CapacityOut(
        day=args.day, minutes_free=free.minutes_free, per_item=free.per_item, fits=fits
    )


# ---- bindings -----------------------------------------------------------------------------


BINDINGS = [
    ToolBinding(
        f"{MANIFEST.id}.plan",
        plan,
        PlanInput,
        "The production plan of a date: batches and pieces per item, the split per kiosk.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.change_plan",
        change_plan,
        ChangePlanInput,
        "Set an item's batches in the plan when the ovens have room.",
        precheck=check_change,
    ),
    ToolBinding(
        f"{MANIFEST.id}.confirm_plan",
        confirm_plan,
        ConfirmPlanInput,
        "Confirm the production plan of a date.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.batch_sheet",
        batch_sheet,
        BatchSheetInput,
        "An item's batch sheet: ingredients times the batches, cost per batch and piece.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.set_recipe",
        set_recipe,
        RecipeInput,
        "Set an item's recipe: pieces and oven minutes per batch, ingredient lines.",
        precheck=check_recipe,
    ),
    ToolBinding(
        f"{MANIFEST.id}.record_batch",
        record_batch,
        BatchInput,
        "Record one batch's good pieces and waste with its reason.",
        precheck=check_batch,
    ),
    ToolBinding(
        f"{MANIFEST.id}.dispatch_list",
        dispatch_list,
        DispatchInput,
        "What goes to each kiosk on a date.",
        precheck=check_list,
    ),
    ToolBinding(
        f"{MANIFEST.id}.confirm_delivery",
        confirm_delivery,
        DeliveredInput,
        "Confirm a kiosk's dispatch was delivered.",
        precheck=check_driver,
    ),
    ToolBinding(
        f"{MANIFEST.id}.capacity",
        capacity,
        CapacityInput,
        "Free oven minutes and pieces per item on a date.",
    ),
]
