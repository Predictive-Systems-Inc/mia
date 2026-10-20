"""Ask Jev which production planner action a message wants and with which inputs (see
mia.agents.decider). Every value comes from the query's candidates: a number code read and Jev
picked by id, an item, kiosk or date a candidate id; the batches of a change are worked out here
(rule 7). decide() runs no tool."""

import datetime as dt
import math
from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.decider import Decision, Reader
from mia.agents.production_planner.actions import (
    ACTIONS,
    CONVERSATION,
    DIRECTIONS,
    UNITS,
    Query,
    build_request,
)

Args = tuple[dict[str, Any], str | None]


def _date(r: Reader) -> dt.date | None:
    q: Query = r.q
    picked = r.pick("date", set(q.dates))
    return dt.date.fromisoformat(q.dates[picked]) if picked else None


def _number(r: Reader) -> int | None:
    q: Query = r.q
    picked = r.pick("number", set(q.numbers)) if q.numbers else None
    return q.numbers[picked] if picked else None


def _change(r: Reader) -> Args:
    """The new whole batches of the item: the plan's current batches plus, minus (never below
    0) or set to the number; pieces become ceil(pieces / batch yield) batches. Missing:
    negated (a no), item, number, recipe (pieces without a yield), or plan when an add or
    remove has no planned line to start from (or names another date than the plan's)."""
    q: Query = r.q
    item, n = r.pick("item", set(q.items)), _number(r)
    direction = r.pick("direction", set(DIRECTIONS)) or "set"
    unit = r.pick("unit", set(UNITS)) or "batches"
    args: dict[str, Any] = {"item_id": item, "batches": None, "production_date": _date(r)}
    if q.negated:
        return args, "negated"
    if item is None:
        return args, "item"
    if n is None:
        return args, "number"
    if unit == "pieces":
        if item not in q.batch_yields:
            return args, "recipe"
        n = math.ceil(n / q.batch_yields[item])
    if direction == "set":
        return {**args, "batches": n}, None
    day = args["production_date"]
    if item not in q.plan_batches or (day is not None and day != q.plan_date):
        return args, "plan"  # the current batches are of q.plan_date's plan only
    current = q.plan_batches[item]
    return {**args, "batches": current + n if direction == "add" else max(0, current - n)}, None


def _recipe(r: Reader) -> Args:
    """The recipe code read; missing recipe when none was read, a part was not understood, or
    the yield, the oven minutes or every line is missing, else item when none is picked."""
    q: Query = r.q
    item, p = r.pick("item", set(q.items)), q.recipe
    if p is None:
        return {"item_id": item}, "recipe"
    lines = [{"ingredient_id": k, "quantity_milli": v} for k, v in p.lines.items()]
    args = {
        "item_id": item,
        "batch_yield": p.batch_yield,
        "oven_minutes": p.oven_minutes,
        "lines": lines,
    }
    if p.unknown or not lines or not p.batch_yield or not p.oven_minutes:
        return args, "recipe"
    return args, None if item else "item"


def _batch(r: Reader) -> Args:
    q: Query = r.q
    item, b = r.pick("item", set(q.items)), q.batch
    if b is None:
        return {"item_id": item}, "batch"
    args = {"item_id": item, "batch_no": b.batch_no, "good": b.good, "waste": b.waste}
    return {**args, "reason": b.reason}, None if item else "item"


def _capacity(r: Reader) -> Args:
    """The day (default tomorrow), the item and the pieces asked about (batches times the
    recipe's yield; None without a number or a yield)."""
    q: Query = r.q
    item, n = r.pick("item", set(q.items)), _number(r)
    if n is not None and r.pick("unit", set(UNITS)) == "batches":
        n = n * q.batch_yields[item] if item in q.batch_yields else None
    day = _date(r) or q.today + dt.timedelta(days=1)
    return {"day": day, "item_id": item, "pieces": n or None}, None


def _args(action: str, r: Reader) -> Args:
    """The tool input for one action and the required input that is missing, if any."""
    q: Query = r.q
    if action == "change_plan":
        return _change(r)
    if action == "set_recipe":
        return _recipe(r)
    if action == "record_batch":
        return _batch(r)
    if action == "capacity":
        return _capacity(r)
    if action in ("plan", "confirm_plan"):
        return {"production_date": _date(r)}, None
    if action == "batch_sheet":
        item = r.pick("item", set(q.items))
        return {"item_id": item, "production_date": _date(r)}, None if item else "item"
    if action in ("dispatch", "delivered"):
        kiosk = r.pick("kiosk", set(q.kiosks))
        args = {"kiosk_id": kiosk, "business_date": _date(r)}
        return args, "kiosk" if action == "delivered" and kiosk is None else None
    if action == "reply_only":
        return {"kind": r.pick("conversation", set(CONVERSATION)) or "other"}, None
    return {}, None  # clarify


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for an answer outside the options) when no usable answer came."""
    parse = partial(shared.parse, q=q, actions=ACTIONS, args=_args)
    return await shared.decide(q, build_request=build_request, parse=parse)
