"""Ask Jev which customer service action a message wants and with which inputs (see
mia.agents.decider). Code reads the order lines, the items asked about and the area (calc);
Jev's picks are checked against the request's options. decide() runs no tool."""

from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.customer_service import calc
from mia.agents.customer_service.actions import (
    ACTIONS,
    CONVERSATION,
    FULFILMENT,
    SIDES,
    Query,
    build_request,
)
from mia.agents.decider import NOT_STATED, Decision, Reader
from mia.i18n import SUPPORTED


def _lines(q: Query) -> list[dict[str, Any]] | None:
    """One line per count group whose words name one item (calc.match_item); None when a
    group names none or several, or there is no group."""
    lines = []
    for g in q.groups:
        item = calc.match_item(g.words, q.items)
        if item is None or g.quantity is None:
            return None
        lines.append({"item_id": item, "quantity": g.quantity})
    return lines or None


def _order(r: Reader) -> tuple[dict[str, Any], str | None]:
    """The staff order: the only candidate, or Jev's pick among several."""
    q: Query = r.q
    order = next(iter(q.orders)) if len(q.orders) == 1 else None
    if len(q.orders) > 1:
        order = r.pick("order", set(q.orders))
    return {"order_id": order}, None if order else "order"


def _complaint(r: Reader) -> tuple[dict[str, Any], str | None]:
    """The open complaint: the only one, or Jev's pick among several."""
    q: Query = r.q
    complaint = next(iter(q.complaints)) if len(q.complaints) == 1 else None
    if len(q.complaints) > 1:
        complaint = r.pick("complaint", set(q.complaints))
    return {"complaint_id": complaint}, None if complaint else "complaint"


def _place_order(r: Reader) -> tuple[dict[str, Any], str | None]:
    """The order input; the day is today when not stated, the fulfilment pickup."""
    q: Query = r.q
    lines = _lines(q)
    fulfilment = r.pick("fulfilment", set(FULFILMENT) - {NOT_STATED}) or "pickup"
    day = r.pick("day", set(q.dates))
    time = r.pick("time", set(q.times))
    area = calc.match_area(q.message, q.areas) if fulfilment == "delivery" else None
    args = {
        "lines": lines or [],
        "fulfilment": fulfilment,
        "day": q.dates[day] if day else q.today.isoformat(),
        "time": q.times[time] if time else None,
        "area": area.name if area else None,
    }
    return args, "items" if lines is None else None if time else "pickup_time"


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required input that is missing, if any."""
    q: Query = r.q
    if action == "place_order":
        return _place_order(r)
    if action == "prices":
        return {"item_ids": calc.match_items(q.message, q.items)}, None
    if action == "delivery_area":
        area = calc.match_area(q.message, q.areas)
        return {"area": area.name if area else None}, None
    if action == "language_switch":
        language = r.pick("language", set(SUPPORTED))
        return {"language": language}, None if language else "language"
    if action in ("staff_mark_ready", "staff_mark_picked_up"):
        return _order(r)
    if action == "staff_resolve_complaint":
        return _complaint(r)
    if action == "greeting":
        return {"kind": r.pick("conversation", set(CONVERSATION)) or "other"}, None
    return {}, None  # hours, order_status, complaint, cancel_order, staff_orders_today, clarify


def parse(answers: dict[str, Any], q: Query) -> Decision:
    """shared.parse over the side's actions only: an action of the other side (or unknown)
    becomes clarify, keeping Jev's pick as raw_action."""
    allowed = {name: a for name, a in ACTIONS.items() if name in SIDES[q.side]}
    top = answers.get("action")
    raw = str(top.get("choice")) if isinstance(top, dict) else ""
    if isinstance(top, dict) and raw not in allowed:
        answers = {**answers, "action": {**top, "choice": "clarify"}}
    d = shared.parse(answers, q, actions=allowed, args=_args)
    return (
        d
        if raw in allowed or not isinstance(top, dict)
        else d.model_copy(update={"raw_action": raw})
    )


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for a malformed answer) when no usable answer came."""
    return await shared.decide(q, build_request=build_request, parse=partial(parse, q=q))
