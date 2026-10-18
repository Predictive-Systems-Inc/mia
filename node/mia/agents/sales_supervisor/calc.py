"""Sales calculations as pure functions (rule 7): business date, target share, totals.

No Session here: the tools load rows and pass plain values in.
"""

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from zoneinfo import ZoneInfo

AFTER_CLOSING = dt.timedelta(hours=2)


@dataclass(frozen=True)
class Target:
    """What day_share needs of a sales target."""

    period: str  # day or month
    starts_on: dt.date
    amount: int


@dataclass(frozen=True)
class Count:
    """What totals needs of a sales count row."""

    item_id: str
    quantity: int
    amount: int
    superseded_by: str | None = None


def business_date(
    reported_at: dt.datetime, tz: str, opens: dt.time, closed_yesterday: dt.time
) -> dt.date:
    """The business date a count reported at `reported_at` belongs to: the day before the local
    date in `tz` when it is before today's opening `opens` and within two hours after the day
    before's closing `closed_yesterday` (a late closing, counted after midnight); else the
    local date. Never asks."""
    local = reported_at.astimezone(ZoneInfo(tz))
    day = local.date()
    yesterday = day - dt.timedelta(days=1)
    closed_at = dt.datetime.combine(yesterday, closed_yesterday, local.tzinfo)
    opened_at = dt.datetime.combine(day, opens, local.tzinfo)
    return yesterday if local < opened_at and local < closed_at + AFTER_CLOSING else day


def _month_days(start: dt.date) -> list[dt.date]:
    first = start.replace(day=1)
    days = []
    day = first
    while day.month == first.month:
        days.append(day)
        day += dt.timedelta(days=1)
    return days


def day_share(target: Target, day: dt.date, open_days: Callable[[dt.date], bool]) -> int | None:
    """The part of `target` that falls on `day`: a day target's amount on its own date; a month
    target's amount divided by the open days of its month (rounded half up to the minor unit)
    for a day in that month on or after starts_on; None when the target does not cover the
    day."""
    if target.period == "day":
        return target.amount if day == target.starts_on else None
    same_month = (day.year, day.month) == (target.starts_on.year, target.starts_on.month)
    if target.period != "month" or not same_month or day < target.starts_on:
        return None
    opened = sum(1 for d in _month_days(target.starts_on) if open_days(d))
    return (target.amount + opened // 2) // opened if opened else None


def totals(counts: Sequence[Count]) -> dict[str, tuple[int, int]]:
    """(quantity, amount) per item id over the live rows (superseded rows are skipped)."""
    out: dict[str, tuple[int, int]] = {}
    for row in counts:
        if row.superseded_by is None:
            quantity, amount = out.get(row.item_id, (0, 0))
            out[row.item_id] = (quantity + row.quantity, amount + row.amount)
    return out


def compare(today_total: int, reference: int | None) -> int | None:
    """Percent difference of today_total from reference, rounded; None without a reference."""
    if not reference:
        return None
    return round((today_total - reference) * 100 / reference)
