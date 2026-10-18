"""Pure inventory rules: the bake plan, low stock and an order's total. No database, no clock."""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

Plan = Literal["more", "same", "fewer"]
WEEKS = 4  # the last four same weekdays with any record
MIN_DAYS = 2  # sell-outs or leftovers on at least two of them
EARLY = dt.timedelta(hours=2)  # a sell-out counts when before closing minus two hours


@dataclass(frozen=True)
class Record:
    """One stock event as the plan sees it. `at` is aware, in the branch's zone."""

    kind: str
    item_id: str | None
    at: dt.datetime
    business_date: dt.date


def plan(
    records: Sequence[Record], items: Sequence[str], today: dt.date, closes: dt.time
) -> dict[str, Plan]:
    """For each item, the plan for tomorrow (today plus one day) over the last four business
    dates before it with tomorrow's weekday that have any record: `more` when the item sold out
    before `closes` minus two hours on at least two of them, else `fewer` when it had a leftover
    on at least two, else `same` (also with no record). ponytail: a heuristic on this agent's
    own records until the sales counts are readable (data standard 1.5, Q54)."""
    weekday = (today + dt.timedelta(days=1)).weekday()
    dates = {r.business_date for r in records if r.business_date <= today}
    window = set(sorted(d for d in dates if d.weekday() == weekday)[-WEEKS:])
    early: dict[str, set[dt.date]] = {}
    leftover: dict[str, set[dt.date]] = {}
    for r in records:
        if r.item_id is None or r.business_date not in window:
            continue
        cutoff = dt.datetime.combine(r.business_date, closes, r.at.tzinfo) - EARLY
        if r.kind == "sold_out" and r.at < cutoff:
            early.setdefault(r.item_id, set()).add(r.business_date)
        elif r.kind == "leftover":
            leftover.setdefault(r.item_id, set()).add(r.business_date)
    out: dict[str, Plan] = {}
    for item in items:
        if len(early.get(item, ())) >= MIN_DAYS:
            out[item] = "more"
        elif len(leftover.get(item, ())) >= MIN_DAYS:
            out[item] = "fewer"
        else:
            out[item] = "same"
    return out


def low(
    latest_counts: Mapping[str, int], reorder: Mapping[str, int], low_today: set[str]
) -> list[str]:
    """The ingredients of `reorder` (in its order) whose latest count is at or under their
    reorder point, or that were reported low today."""
    return [
        i
        for i, point in reorder.items()
        if i in low_today or (i in latest_counts and latest_counts[i] <= point)
    ]


def order_total(lines: Sequence[tuple[str, int]], prices: Mapping[str, int | None]) -> int | None:
    """The sum of quantity times unit price over (ingredient_id, quantity) lines, in minor
    units; None when any line has no known price."""
    total = 0
    for ingredient_id, quantity in lines:
        price = prices.get(ingredient_id)
        if price is None:
            return None
        total += quantity * price
    return total
