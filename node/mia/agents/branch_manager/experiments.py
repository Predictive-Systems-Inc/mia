"""Price and promo experiments as pure functions (rule 7): the baseline, the score, the seasonal
suggestion, the strategy engine (spec section 13) and its guard rails. No Session and no clock:
the tools load the branch's numbers and pass them and the local date in. Money is integer minor
units (PHP centavos); a "whole peso" is a multiple of 100.
"""

import datetime as dt
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from mia.agents.branch_manager import calc
from mia.agents.branch_manager.models import Strategy
from mia.templates.retail.models import RetailItem

Day = tuple[int, int]  # (units, amount) of one item on one business date
BASELINE_DAYS = 28  # the baseline looks at the 28 days before the start
MIN_BASELINE_DAYS = 7  # fewer such days is "not enough data"
SUGGESTED_OFF_PERCENT = 10  # the agent's own suggestion: 10 percent below the price in force
MAX_MOVE_PERCENT = 20  # never more than 20 percent from the price in force (or the last 90 days)
ITEM_GAP_DAYS = 28  # no second experiment on the same item within 28 days
PESO = 100


@dataclass(frozen=True)
class Baseline:
    """The same weekdays as the experiment's days within the 28 days before it: how many days
    had live counts and their summed units and amount."""

    days: int
    units: int
    amount: int


@dataclass(frozen=True)
class Score:
    """The experiment's days with counts, their summed units and amount, and the per-day means
    against the baseline's in whole percent (None when there is nothing to compare)."""

    days: int
    units: int
    amount: int
    units_pct: int | None
    amount_pct: int | None


def baseline(daily: Mapping[dt.date, Day], starts_on: dt.date, days: int) -> Baseline | None:
    """Sum the days of `daily` (dates with live counts only) in the BASELINE_DAYS before
    starts_on that fall on a weekday of the experiment's `days` days. None (not enough data,
    never a guess) when fewer than MIN_BASELINE_DAYS such days have counts."""
    weekdays = {(starts_on + dt.timedelta(days=k)).weekday() for k in range(days)}
    start = starts_on - dt.timedelta(days=BASELINE_DAYS)
    picked = [v for d, v in daily.items() if start <= d < starts_on and d.weekday() in weekdays]
    if len(picked) < MIN_BASELINE_DAYS:
        return None
    return Baseline(len(picked), sum(u for u, _ in picked), sum(a for _, a in picked))


def _half_up(x: Fraction) -> int:
    return math.floor(x + Fraction(1, 2))


def _pct(total: int, days: int, base_total: int, base_days: int) -> int | None:
    if not days or not base_total:
        return None
    return _half_up(Fraction(total * base_days, days * base_total) * 100 - 100)


def score(base: Baseline, during: Mapping[dt.date, Day]) -> Score:
    """The experiment's per-day means of units and amount against the baseline's per-day
    means, in percent rounded half up (exact fractions, no float)."""
    days, units = len(during), sum(u for u, _ in during.values())
    amount = sum(a for _, a in during.values())
    return Score(
        days,
        units,
        amount,
        _pct(units, days, base.units, base.days),
        _pct(amount, days, base.amount, base.days),
    )


def suggestion(last_year: Mapping[str, int], items: Sequence[RetailItem]) -> RetailItem | None:
    """The item to suggest from the same month last year (last_year: item id to units): a
    bundle first, then the most units; the earlier item on a tie. None without any units."""
    sold = [i for i in items if last_year.get(i.id, 0) > 0]
    if not sold:
        return None
    return max(sold, key=lambda i: (bool(i.components), last_year[i.id]))


def suggested_price(price: int) -> int:
    """SUGGESTED_OFF_PERCENT below the price, rounded down to the whole peso."""
    return price * (100 - SUGGESTED_OFF_PERCENT) // 100 // PESO * PESO


def _too_far(price: int, to_price: int) -> bool:
    return abs(to_price - price) * 100 > MAX_MOVE_PERCENT * price


def guard(
    item_price: int,
    cost: int | None,
    to_price: int,
    last_prices_90d: Sequence[int],
    last_experiment_on_item: int | None,
) -> str | None:
    """The guard rails of spec section 13, as the refusal reason or None when to_price may be
    tested: "unchanged" (to_price is the price in force), "too_far" (more than MAX_MOVE_PERCENT
    from the price in force; without a cost this is also the deepest cut), "below_cost" (under
    the item's cost), "drift" (more than MAX_MOVE_PERCENT from a price the item had in the last
    90 days, so steps cannot add up past the limit), "recent_experiment" (last_experiment_on_item,
    the days from the item's last experiment's end to this start, is under ITEM_GAP_DAYS). One
    open experiment per branch is the tool's check (it needs the approvals table)."""
    if to_price == item_price:
        return "unchanged"
    if _too_far(item_price, to_price):
        return "too_far"
    if cost is not None and to_price < cost:
        return "below_cost"
    if any(_too_far(p, to_price) for p in last_prices_90d):
        return "drift"
    if last_experiment_on_item is not None and last_experiment_on_item < ITEM_GAP_DAYS:
        return "recent_experiment"
    return None


@dataclass(frozen=True)
class BranchNumbers:
    """A branch's numbers the strategy conditions read, all by item id over the window the tool
    loads (the days before today): units sold and open_days with counts; the price in force
    today (prices; an item missing reads its default price); sold_out_days (days it sold out
    before closing); leftovers (local date to the pieces left at close); baskets (one clerk's
    items on one business date); order_pieces (pieces per customer order line); last_year (month
    number to item id to units in that month last year); last_prices_90d (the prices it had in
    the last 90 days); since_experiment (days since its last experiment ended)."""

    open_days: int
    units: Mapping[str, int] = field(default_factory=dict)
    prices: Mapping[str, int] = field(default_factory=dict)
    sold_out_days: Mapping[str, int] = field(default_factory=dict)
    leftovers: Mapping[str, Mapping[dt.date, int]] = field(default_factory=dict)
    baskets: Sequence[frozenset[str]] = ()
    order_pieces: Mapping[str, Sequence[int]] = field(default_factory=dict)
    last_year: Mapping[int, Mapping[str, int]] = field(default_factory=dict)
    last_prices_90d: Mapping[str, Sequence[int]] = field(default_factory=dict)
    since_experiment: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Proposal:
    """One experiment the engine proposes: the strategy row, the item, the kind, the reference
    price and the price to test, the branch's numbers the condition read (rationale, JSON-safe),
    the guard rails' bounds (floor and ceiling, minor units) and new_item. new_item is None when
    the item itself is repriced; else the components of a new item to create at to_price ([] for
    a premium variant of item_id, the pair for a bundle, the pieces for a decoy), never a
    repricing of item_id. For a new item from_price is what it stands against: the item's price
    (anchor), the pair's sum (bundle), two of the target box (decoy)."""

    strategy_id: str
    item_id: str
    kind: str
    from_price: int
    to_price: int
    rationale: dict[str, Any]
    floor: int
    ceiling: int
    new_item: list[str] | None = None


@dataclass(frozen=True)
class Candidate:
    """One candidate of a rule, before the guard rails."""

    item_id: str
    price: int
    to_price: int
    cost: int | None
    rationale: dict[str, Any]
    new_item: list[str] | None = None


Rule = Callable[[dict[str, Any], BranchNumbers, Sequence[RetailItem], dt.date], list[Candidate]]


def _price(n: BranchNumbers, item: RetailItem) -> int:
    return n.prices.get(item.id, item.price)


def _ranked(n: BranchNumbers, items: Sequence[RetailItem]) -> list[RetailItem]:
    """Items by units sold in the window, most first (menu order on a tie)."""
    return sorted(items, key=lambda i: -n.units.get(i.id, 0))


def _down(x: int, step: int = PESO) -> int:
    return x // step * step


def _up(x: int | Fraction, step: int = PESO) -> int:
    return math.ceil(Fraction(x) / step) * step


def _charm(
    p: dict[str, Any], n: BranchNumbers, items: Sequence[RetailItem], _: dt.date
) -> list[Candidate]:
    """A whole-peso price whose last peso digit is in endings ([0]): tested `under` (one peso)
    lower, one peso under the next ten (50 to 49)."""
    out = []
    for i in _ranked(n, items):
        price = _price(n, i)
        if price % PESO == 0 and price // PESO % 10 in p["endings"]:
            rationale = {"price": price, "units": n.units.get(i.id, 0)}
            out.append(Candidate(i.id, price, price - p["under"], i.cost, rationale))
    return out


def _sizes(items: Sequence[RetailItem]) -> dict[str, list[RetailItem]]:
    """A line per single item: the item, then the bundles made only of it, smallest first."""
    lines: dict[str, list[RetailItem]] = {i.id: [i] for i in items if not i.components}
    for i in sorted(items, key=lambda i: len(i.components)):
        if i.components and len(set(i.components)) == 1 and i.components[0] in lines:
            lines[i.components[0]].append(i)
    return lines


def _anchor(
    p: dict[str, Any], n: BranchNumbers, items: Sequence[RetailItem], _: dt.date
) -> list[Candidate]:
    """A single item that comes in one size (no bundle holds it): a new premium variant at
    premium_percent above, rounded down to the whole peso."""
    held = {c for i in items for c in i.components}
    out = []
    for i in _ranked(n, items):
        if i.components or i.id in held:
            continue
        price = _price(n, i)
        to = _down(price * (100 + p["premium_percent"]) // 100)
        rationale = {"variant": "premium", "units": n.units.get(i.id, 0)}
        out.append(Candidate(i.id, price, to, i.cost, rationale, []))
    return out


def _bundle(
    p: dict[str, Any], n: BranchNumbers, items: Sequence[RetailItem], _: dt.date
) -> list[Candidate]:
    """The pair most often in one basket, when in at least min_pair_share percent of baskets:
    a new bundle of the two at off_percent below the pair's sum, rounded down to the whole
    peso."""
    pair = calc.pairing(n.baskets)
    by_id = {i.id: i for i in items}
    if pair is None or not set(pair) <= set(by_id):
        return []
    share = sum(set(pair) <= b for b in n.baskets) * 100 // len(n.baskets)
    if share < p["min_pair_share"]:
        return []
    a, b = by_id[pair[0]], by_id[pair[1]]
    total = _price(n, a) + _price(n, b)
    costs = (a.cost, b.cost)
    cost = sum(c for c in costs if c is not None) if None not in costs else None
    rationale = {"pair": list(pair), "share": share, "sum": total}
    to = _down(total * (100 - p["off_percent"]) // 100)
    return [Candidate(a.id, total, to, cost, rationale, list(pair))]


def _volume(
    p: dict[str, Any], n: BranchNumbers, items: Sequence[RetailItem], _: dt.date
) -> list[Candidate]:
    """An item whose order lines hold min_quantity pieces or more in at least min_multi_share
    percent of them: the per-piece price at off_percent below from that quantity."""
    out = []
    for i in _ranked(n, items):
        lines = n.order_pieces.get(i.id, ())
        if not lines:
            continue
        share = sum(q >= p["min_quantity"] for q in lines) * 100 // len(lines)
        if share >= p["min_multi_share"]:
            price = _price(n, i)
            rationale = {"share": share, "orders": len(lines), "min_quantity": p["min_quantity"]}
            to = _down(price * (100 - p["off_percent"]) // 100)
            out.append(Candidate(i.id, price, to, i.cost, rationale))
    return out


def _markdown(
    p: dict[str, Any], n: BranchNumbers, items: Sequence[RetailItem], today: dt.date
) -> list[Candidate]:
    """An item with leftovers on at least min_leftover_days of the last window_days: a cut of
    the leftover share of what was made (the leftover per open day over units plus leftover per
    open day), at most max_off_percent, rounded down to the whole peso and never below cost.
    ponytail: prices are dated per day, so the cut is all day (Q82), not late-day only."""
    start = today - dt.timedelta(days=p["window_days"])
    out = []
    for i in _ranked(n, items):
        left = [q for d, q in n.leftovers.get(i.id, {}).items() if start <= d < today and q > 0]
        if len(left) < p["min_leftover_days"] or not n.open_days:
            continue
        mean_left = Fraction(sum(left), n.open_days)
        mean_units = Fraction(n.units.get(i.id, 0), n.open_days)
        off = min(p["max_off_percent"], math.ceil(100 * mean_left / (mean_units + mean_left)))
        price = _price(n, i)
        to = _down(price * (100 - off) // 100)
        if i.cost is not None and to < i.cost:
            to = _up(i.cost)
        if to >= price:
            continue
        rationale = {
            "leftover_days": len(left),
            "mean_leftover": _half_up(mean_left),
            "mean_units": _half_up(mean_units),
            "off_percent": off,
        }
        out.append(Candidate(i.id, price, to, i.cost, rationale))
    return out


def _increase(
    p: dict[str, Any], n: BranchNumbers, items: Sequence[RetailItem], _: dt.date
) -> list[Candidate]:
    """An item sold out before closing on at least min_sold_out_share percent of the open days:
    up_percent_min higher rounded up to the next 5 pesos; past up_percent_max, the limit itself
    rounded down to 50 centavos (45 to 49.50; 25.49 to 28)."""
    out = []
    for i in _ranked(n, items):
        sold_out = n.sold_out_days.get(i.id, 0)
        if not n.open_days or sold_out * 100 // n.open_days < p["min_sold_out_share"]:
            continue
        price = _price(n, i)
        to = _up(Fraction(price * (100 + p["up_percent_min"]), 100), 5 * PESO)
        if (to - price) * 100 > p["up_percent_max"] * price:
            to = _down(price * (100 + p["up_percent_max"]) // 100, PESO // 2)
        rationale = {"sold_out_days": sold_out, "days": n.open_days}
        out.append(Candidate(i.id, price, to, i.cost, rationale))
    return out


def _seasonal(
    p: dict[str, Any], n: BranchNumbers, items: Sequence[RetailItem], today: dt.date
) -> list[Candidate]:
    """The suggestion for the month lead_days ahead from last year's same month, at the
    suggested price (SUGGESTED_OFF_PERCENT below, whole peso)."""
    month = (today + dt.timedelta(days=p["lead_days"])).month
    sold = n.last_year.get(month, {})
    item = suggestion(sold, items)
    if item is None:
        return []
    price = _price(n, item)
    rationale = {"month": month, "units": sold[item.id]}
    return [Candidate(item.id, price, suggested_price(price), item.cost, rationale)]


def _decoy(
    p: dict[str, Any], n: BranchNumbers, items: Sequence[RetailItem], _: dt.date
) -> list[Candidate]:
    """A line with one size short of `variants` (a single item and its box of n pieces): a new
    top size of 2n pieces at two boxes plus one piece, rounded up to the whole peso, so the box
    is the middle of three and the one to sell (good, better, best)."""
    out = []
    for single, *boxes in _sizes(items).values():
        if 1 + len(boxes) != p["variants"] - 1:  # the line's sizes, one short
            continue
        box = boxes[-1]
        two = 2 * _price(n, box)
        pieces = [single.id] * (2 * len(box.components))
        rationale = {"variant": "decoy", "pieces": len(pieces), "units": n.units.get(box.id, 0)}
        out.append(Candidate(box.id, two, _up(two + _price(n, single)), None, rationale, pieces))
    return sorted(out, key=lambda c: -c.rationale["units"])


RULES: dict[str, Rule] = {
    "bm.strategy.charm": _charm,
    "bm.strategy.anchor": _anchor,
    "bm.strategy.bundle": _bundle,
    "bm.strategy.volume": _volume,
    "bm.strategy.markdown": _markdown,
    "bm.strategy.increase": _increase,
    "bm.strategy.seasonal": _seasonal,
    "bm.strategy.decoy": _decoy,
}


def propose(
    numbers: BranchNumbers,
    items: Sequence[RetailItem],
    strategies: Sequence[Strategy],
    today: dt.date,
) -> list[Proposal]:
    """For each active strategy whose condition holds in the branch's numbers, one Proposal:
    the rule's first candidate (best seller first) that passes guard; strategies in the given
    order. A new item has no price history and no past experiment (guard gets () and None). A
    strategy with no rule in RULES (an owner's own row) proposes nothing."""
    out = []
    for s in strategies:
        rule = RULES.get(s.name_key)
        if not s.active or rule is None:
            continue
        for c in rule(s.params, numbers, items, today):
            new = c.new_item is not None
            refused = guard(
                c.price,
                c.cost,
                c.to_price,
                () if new else numbers.last_prices_90d.get(c.item_id, ()),
                None if new else numbers.since_experiment.get(c.item_id),
            )
            if refused is None:
                least = math.ceil(Fraction(c.price * (100 - MAX_MOVE_PERCENT), 100))
                floor = max(c.cost or 0, least)
                ceiling = c.price * (100 + MAX_MOVE_PERCENT) // 100
                proposal = Proposal(
                    strategy_id=s.id,
                    item_id=c.item_id,
                    kind=s.kind,
                    from_price=c.price,
                    to_price=c.to_price,
                    rationale=c.rationale,
                    floor=floor,
                    ceiling=ceiling,
                    new_item=c.new_item,
                )
                out.append(proposal)
                break
    return out
