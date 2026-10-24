"""Ask Jev which hr officer action a message wants and with which inputs (see
mia.agents.decider). decide() runs no tool."""

import datetime as dt
from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.decider import Decision, Reader
from mia.agents.hr_officer.actions import (
    ACTIONS,
    CONVERSATION,
    LEAVE_KINDS,
    PERIODS,
    WHICH,
    Query,
    build_request,
)
from mia.agents.hr_officer.calendar import cutoff, previous_cutoff


def _month(day: dt.date) -> tuple[dt.date, dt.date]:
    first = day.replace(day=1)
    return first, (first + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)


def _span(period: str | None, today: dt.date) -> tuple[dt.date, dt.date]:
    """The first and last day of the period id; the cutoff now running when not stated."""
    if period == "last_cutoff":
        return previous_cutoff(today)
    if period == "this_month":
        return _month(today)
    if period == "last_month":
        return _month(today.replace(day=1) - dt.timedelta(days=1))
    return cutoff(today)


def _date(r: Reader, slot: str) -> str | None:
    """The ISO date of the picked candidate id, or None when not stated."""
    pick = r.pick(slot, set(r.q.dates))
    return None if pick is None else str(r.q.dates[pick])


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required input that is missing, if any."""
    q: Query = r.q
    if action == "my_hours":
        start, end = _span(r.pick("period", set(PERIODS)), q.today)
        return {"start": start.isoformat(), "end": end.isoformat(), "person_id": None}, None
    if action == "contributions":
        return {"which": r.pick("which", set(WHICH)) or "all"}, None
    if action == "file_leave":
        first = _date(r, "leave_start")
        kind = r.pick("leave_kind", set(LEAVE_KINDS)) or "vacation"
        args = {"kind": kind, "start": first, "end": _date(r, "leave_end") or first}
        return args, None if first else "leave_start"
    if action == "holiday_pay":
        pick = r.pick("day", set(q.days))
        day = None if pick is None else q.days[pick].split(" ")[0]
        return {"day": day}, None if day else "day"
    if action == "certificate":
        person = r.pick("person", set(q.people)) if q.people else None
        return {"person_id": person}, None if person else "person"
    if action == "reply_only":
        return {"kind": r.pick("conversation", set(CONVERSATION)) or "other"}, None
    return {}, None  # payday, thirteenth, leave_balance, my_payslip, clarify


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for an answer outside the options) when no usable answer came."""
    parse = partial(shared.parse, q=q, actions=ACTIONS, args=_args)
    return await shared.decide(q, build_request=build_request, parse=parse)
