"""The production planner's numbers as pure code (rule 7): the forecast per kiosk and item, the
demand, whole batches and the split per kiosk, the dispatch split of what came out of the
ovens, the yield percent and the batch sheet's costs. No Session and no clock: tools.py loads
the rows and passes plain values in. Money is integer minor units, quantities integers."""

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from mia.agents.bookkeeper.calc import half_up

FORECAST_DAYS = 28  # the forecast looks at the 28 days before the production date
MIN_FORECAST_DAYS = 2  # fewer same weekdays with counts is "not enough data"


def units(
    rows: Iterable[tuple[dt.date, str, int]], components: Mapping[str, Sequence[str]]
) -> dict[dt.date, dict[str, int]]:
    """Units per business date and single item from (date, item_id, quantity) rows: a bundle
    counts as its components (Box of 4 is four Classic). A date with any row is in the result."""
    out: dict[dt.date, dict[str, int]] = {}
    for day, item_id, quantity in rows:
        sold = out.setdefault(day, {})
        for piece in components.get(item_id) or [item_id]:
            sold[piece] = sold.get(piece, 0) + quantity
    return out


def mean_for(daily: Mapping[dt.date, Mapping[str, int]], item_id: str, day: dt.date) -> int | None:
    """The mean units of the item on the dates of `daily` with day's weekday in the
    FORECAST_DAYS before day, half up (a date without the item counts 0). None (not enough
    data, never a guess) when fewer than MIN_FORECAST_DAYS such dates."""
    start = day - dt.timedelta(days=FORECAST_DAYS)
    picked = [d for d in daily if start <= d < day and d.weekday() == day.weekday()]
    if len(picked) < MIN_FORECAST_DAYS:
        return None
    return half_up(Fraction(sum(daily[d].get(item_id, 0) for d in picked), len(picked)))


@dataclass(frozen=True)
class Kiosk:
    """One kiosk's numbers for an item: forecast (None: not enough data), confirmed order
    pieces and the expected leftover."""

    branch_id: str
    forecast: int | None
    orders: int
    leftover: int

    @property
    def demand(self) -> int:
        """forecast (0 when None) plus orders less the leftover, never below 0."""
        return max(0, (self.forecast or 0) + self.orders - self.leftover)


@dataclass(frozen=True)
class KioskLine:
    branch_id: str
    forecast: int | None
    orders: int
    leftover: int
    demand: int
    pieces: int


@dataclass(frozen=True)
class Line:
    """One item of a plan: whole batches, their pieces, the more flag and the split per kiosk."""

    item_id: str
    batches: int
    pieces: int
    more: bool
    kiosks: tuple[KioskLine, ...]


def _shares(pieces: int, kiosks: Sequence[Kiosk]) -> dict[str, int]:
    """pieces over the kiosks: each its demand, the surplus to the kiosk with the larger
    forecast (None counts 0, a tie to the first); with no forecast at any kiosk the surplus is
    shared evenly, the remainder from the first. Fewer pieces than the demand: dispatch_split."""
    demand = {k.branch_id: k.demand for k in kiosks}
    surplus = pieces - sum(demand.values())
    if surplus < 0 or not kiosks:
        return dispatch_split(pieces, demand)
    if all(k.forecast is None for k in kiosks):
        each, rest = divmod(surplus, len(kiosks))
        return {b: q + each + (i < rest) for i, (b, q) in enumerate(demand.items())}
    top = max(kiosks, key=lambda k: k.forecast or 0)  # max keeps the first on a tie
    return {b: q + (surplus if b == top.branch_id else 0) for b, q in demand.items()}


def plan_line(
    item_id: str,
    kiosks: Sequence[Kiosk],
    batch_yield: int,
    more: bool,
    batches: int | None = None,
) -> Line:
    """The item's line: batches (given, or the total demand rounded up to whole batches plus
    one when `more`), pieces = batches times batch_yield, split over the kiosks (_shares)."""
    if batches is None:
        batches = -(-sum(k.demand for k in kiosks) // batch_yield) + int(more)
    pieces = batches * batch_yield
    share = _shares(pieces, kiosks)
    lines = tuple(
        KioskLine(k.branch_id, k.forecast, k.orders, k.leftover, k.demand, share[k.branch_id])
        for k in kiosks
    )
    return Line(item_id, batches, pieces, more, lines)


def order_pieces(
    lines: Iterable[Mapping[str, Any]], components: Mapping[str, Sequence[str]]
) -> dict[str, int]:
    """Pieces per single item of order lines {"item_id", "quantity"}, bundles expanded."""
    out: dict[str, int] = {}
    for line in lines:
        for piece in components.get(line["item_id"]) or [line["item_id"]]:
            out[piece] = out.get(piece, 0) + int(line["quantity"])
    return out


def dispatch_split(good: int, planned: Mapping[str, int]) -> dict[str, int]:
    """The good pieces over the kiosks' planned pieces: a shortfall comes off the kiosk with
    the larger planned pieces first (the first on a tie), extra pieces go to it."""
    out = dict(planned)
    if not out:
        return out
    order = sorted(out, key=lambda b: -out[b])  # stable: the first on a tie
    gap = good - sum(out.values())
    if gap >= 0:
        out[order[0]] += gap
        return out
    for b in order:
        take = min(out[b], -gap)
        out[b] -= take
        gap += take
    return out


def yield_percent(good: int, planned: int) -> int | None:
    """good of planned in whole percent, half up; None for nothing planned."""
    return half_up(Fraction(good * 100, planned)) if planned else None


def line_cost(quantity_milli: int, pack_price: int | None) -> int | None:
    """quantity_milli thousandths of a unit at pack_price minor units, half up; None without
    a price."""
    return None if pack_price is None else half_up(Fraction(quantity_milli * pack_price, 1000))


@dataclass(frozen=True)
class SheetLine:
    ingredient_id: str
    quantity_milli: int
    cost: int | None


@dataclass(frozen=True)
class Sheet:
    """A batch sheet: every line times the batches; the cost per batch (one batch's lines) and
    per piece, both None when any ingredient has no price (Q55: never a partial cost)."""

    batches: int
    batch_yield: int
    lines: tuple[SheetLine, ...]
    cost_per_batch: int | None
    cost_per_piece: int | None


def sheet(
    lines: Sequence[tuple[str, int]],
    prices: Mapping[str, int | None],
    batches: int,
    batch_yield: int,
) -> Sheet:
    """The batch sheet of a recipe's (ingredient_id, quantity_milli per batch) lines."""
    out = tuple(SheetLine(i, q * batches, line_cost(q * batches, prices.get(i))) for i, q in lines)
    one = [line_cost(q, prices.get(i)) for i, q in lines]
    per_batch = None if None in one else sum(c for c in one if c is not None)
    per_piece = None if per_batch is None else half_up(Fraction(per_batch, batch_yield))
    return Sheet(batches, batch_yield, out, per_batch, per_piece)
