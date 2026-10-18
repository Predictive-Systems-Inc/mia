"""Ask Jev which sales action a message wants and with which inputs (see mia.agents.decider).

Code does the arithmetic and the dates (rule 7); Jev's picks are item ids, period ids and a
branch. decide() runs no tool.
"""

import calendar
import datetime as dt
from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.decider import Decision, Reader
from mia.agents.sales_supervisor.actions import (
    ACTIONS,
    NONE,
    WEEKDAYS,
    Query,
    build_request,
)

THIS_MONTH = "this_month"


def _month(first: dt.date) -> tuple[dt.date, dt.date]:
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def _period(value: str | None, today: dt.date) -> tuple[dt.date, dt.date]:
    """The (start, end) dates of a period id; a weekday id is its most recent day (today if
    it is that weekday); not stated is this month."""
    monday = today - dt.timedelta(days=today.weekday())
    if value == "today":
        return today, today
    if value == "yesterday":
        return today - dt.timedelta(days=1), today - dt.timedelta(days=1)
    if value == "this_week":
        return monday, monday + dt.timedelta(days=6)
    if value == "last_week":
        return monday - dt.timedelta(days=7), monday - dt.timedelta(days=1)
    if value == "last_month":
        return _month((today.replace(day=1) - dt.timedelta(days=1)).replace(day=1))
    if value in WEEKDAYS:
        day = today - dt.timedelta(days=(today.weekday() - WEEKDAYS.index(value)) % 7)
        return day, day
    return _month(today.replace(day=1))


def _branch(r: Reader) -> str | None:
    return r.pick("branch", {*r.q.branches, "all"})


def _item(r: Reader, i: int) -> str | None:
    """The item picked for group i, or None for none (the caller reports it missing)."""
    pick = r.pick(f"item_{i}", {*r.q.items, NONE})
    return None if pick == NONE else pick


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required input that is missing, if any."""
    q: Query = r.q
    if action == "report_sales":
        items: list[dict[str, Any]] = []
        for i, g in enumerate(q.groups):
            item = _item(r, i)
            if item is None or g.quantity is None:
                return {}, f"item_{i}"
            items.append({"item_id": item, "quantity": g.quantity})
        args: dict[str, Any] = {
            "items": items,
            "total": q.total,
            "business_date": None,
            "source_message_id": None,
        }
        return args, None if items or q.total is not None else "items"
    if action == "correct_sales":
        item = _item(r, 0) if q.groups else None
        if item is None or q.groups[0].quantity is None:
            return {}, "item_0"
        return {"item_id": item, "quantity": q.groups[0].quantity}, None
    if action == "sales_today":
        return {"branch_id": _branch(r)}, None
    if action == "sales_period":
        start, end = _period(r.pick("period", set(WEEKDAYS) | set(q.periods)), q.today)
        item = _item(r, 0) if q.groups else None
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "branch_id": _branch(r),
            "item_id": item,
        }, None
    if action == "set_target":
        period = r.pick("target_period", {"day", "month"}, count_unstated=True) or "month"
        starts = q.today if period == "day" else q.today.replace(day=1)
        single = q.groups[0].quantity if len(q.groups) == 1 else None
        amount = q.total if q.total is not None else single
        args = {
            "period": period,
            "starts_on": starts.isoformat(),
            "amount": amount,
            "branch_id": _branch(r),
        }
        return args, None if amount is not None else "amount"
    if action == "why_answer":
        args = {"text": q.message[:500], "asked_message_id": None}
        return args, None if q.why_asked else "why"
    if action == "reply_only":
        kinds = {"greeting", "thanks", "goodbye", "capabilities", "other"}
        return {"kind": r.pick("conversation", kinds) or "other"}, None
    return {}, None  # clarify


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for an answer outside the options) when no usable answer came."""
    return await shared.decide(
        q,
        build_request=build_request,
        parse=partial(shared.parse, q=q, actions=ACTIONS, args=_args),
    )
