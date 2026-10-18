"""Ask Jev which sales action a message wants and with which inputs (see mia.agents.decider).

Code does the arithmetic and the dates (rule 7); Jev's picks are item ids, period ids and a
branch. decide() runs no tool.
"""

from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.decider import Decision, Reader
from mia.agents.sales_supervisor.actions import (
    ACTIONS,
    NONE,
    THEMES,
    WEEKDAYS,
    Query,
    _month,
    _period,
    _target_start,
    _target_starts,
    build_request,
)


def _minor(value: int) -> int:
    """Major units as typed to minor units."""
    # ponytail: exponent 2 (PHP, EUR); a currency table when a zero-decimal currency appears
    return value * 100


def _target_amount(r: Reader) -> int | None:
    """The stated total, else the one number of at least 100 in the message that is not the
    count of a menu item (a group whose item pick is confident and real); never a small count."""
    q: Query = r.q
    if q.total is not None:
        return q.total
    big = []
    for i, g in enumerate(q.groups):
        counted = r.pick(f"item_{i}", {*q.items, NONE}, fallback=True) not in (None, NONE)
        if g.quantity is not None and g.quantity >= 100 and not counted:
            big.append(g.quantity)
    return big[0] if len(big) == 1 else None


def _branch(r: Reader) -> str | None:
    """The branch named, "all", or None (the tool's default) when unstated or uncertain."""
    return r.pick("branch", {*r.q.branches, "all"}, fallback=True)


def _item(r: Reader, i: int, fallback: bool = False) -> str | None:
    """The item picked for group i, or None for none (the caller reports it missing); with
    fallback=True an uncertain pick is None too (the turn asks which item)."""
    pick = r.pick(f"item_{i}", {*r.q.items, NONE}, fallback=fallback)
    return None if pick == NONE else pick


def _count(r: Reader, i: int, quantity: int) -> dict[str, Any]:
    """Group i's count; with no confident item, item_id is None, words are the group's words
    and candidates the three most probable menu items (Jev's probabilities, else the first
    three of the menu), for the turn's which-item question."""
    item = _item(r, i, fallback=True)
    if item is not None:
        return {"item_id": item, "quantity": quantity}
    probabilities = r.answers[f"item_{i}"].get("probabilities") or {}
    ranked = sorted((k for k in probabilities if k in r.q.items), key=lambda k: -probabilities[k])
    candidates = (ranked or list(r.q.items))[:3]
    words = r.q.groups[i].words
    return {"item_id": None, "quantity": quantity, "candidates": candidates, "words": words}


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required input that is missing, if any."""
    q: Query = r.q
    if action == "report_sales":
        items: list[dict[str, Any]] = []
        for i, g in enumerate(q.groups):
            if g.quantity is None:
                return {}, f"item_{i}"
            items.append(_count(r, i, g.quantity))
        unknown = next((f"item_{i}" for i, c in enumerate(items) if c["item_id"] is None), None)
        args: dict[str, Any] = {
            "items": items,
            "total": None if q.total is None else _minor(q.total),
            "business_date": None,
            "source_message_id": q.message_id,
        }
        return args, unknown or (None if items or q.total is not None else "items")
    if action == "correct_sales":
        quantity = q.groups[0].quantity if q.groups else None
        if quantity is None:
            return {}, "item_0"
        count = {**_count(r, 0, quantity), "source_message_id": q.message_id}
        return count, None if count["item_id"] else "item_0"
    if action == "sales_today":
        return {"branch_id": _branch(r)}, None
    if action == "sales_period":
        picked = r.pick("period", set(WEEKDAYS) | set(q.periods))
        start, end = _period(picked, q.today, q.lang) or _month(q.today.replace(day=1))
        item = _item(r, 0, fallback=True) if q.groups else r.pick("item", set(q.items), True)
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "branch_id": _branch(r),
            "item_id": item,
        }, None
    if action == "set_target":
        when = r.pick("target_start", set(_target_starts()))
        stated = r.pick("target_period", {"day", "month"}, count_unstated=True)
        period = stated or ("day" if when in ("today", "tomorrow") else "month")
        starts = _target_start(when, q.today, period)
        amount = _target_amount(r)
        args = {
            "period": period,
            "starts_on": starts.isoformat(),
            "amount": None if amount is None else _minor(amount),
            "branch_id": _branch(r),
        }
        return args, None if amount is not None else "amount"
    if action == "why_answer":
        theme = r.pick("theme", set(THEMES), fallback=True) if q.why_asked else None
        args = {
            "text": q.message[:500],
            "asked_message_id": q.previous_id,
            "themes": [theme or "other"],
        }
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
