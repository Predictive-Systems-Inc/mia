"""The customer service's arithmetic and matching, by code (rule 7): order totals, pickup times
on the branch clock, opening hours, delivery areas and menu items named in a message. Pure: no
session, no clock (the caller passes `now`)."""

import datetime as dt
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from mia.core.models import Branch
from mia.core.orgconfig import DeliveryArea
from mia.templates.retail import hours as shop_hours


@dataclass(frozen=True)
class OpenState:
    is_open: bool
    closes_at: dt.datetime | None  # today's closing while open, else None
    next_open: dt.datetime  # the next opening after now (tomorrow's while open today)


def fold(text: str) -> str:
    """The text casefolded, accents stripped (NFKD) and cut to its words, joined by one space."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", plain.casefold()))


def _names(text: str, name: str) -> bool:
    """True when `name` (folded) appears in `text` as whole words."""
    return f" {fold(name)} " in f" {fold(text)} "


def order_total(lines: Sequence[tuple[int, int]], fee: int = 0) -> int:
    """The sum of quantity times unit price (minor units) over the lines, plus the fee."""
    return sum(quantity * price for quantity, price in lines) + fee


def pickup_at(day: dt.date, at: dt.time, tz: str) -> dt.datetime:
    """The aware local datetime of `at` on `day` in the zone `tz`."""
    return dt.datetime.combine(day, at, ZoneInfo(tz))


def hours_span(
    branch: Branch, hours: shop_hours.Hours, day: dt.date
) -> tuple[dt.datetime, dt.datetime]:
    """The business day `day`'s opening and closing as aware local times; a closing at or
    before the opening (16:00 to 02:00) is the next calendar day's."""
    start = shop_hours.at(branch, hours, day, closing=False)
    end = shop_hours.at(branch, hours, day, closing=True)
    return start, end if end > start else end + dt.timedelta(days=1)


def business_day(branch: Branch, hours: shop_hours.Hours, when: dt.datetime) -> dt.date | None:
    """The open business day whose hours hold `when` (from its opening up to, not at, its
    closing): the local date, or the day before for a time after midnight within a closing
    past midnight; None when the shop is closed then."""
    local = when.astimezone(ZoneInfo(branch.timezone)).date()
    is_day = shop_hours.open_days(hours)
    for day in (local, local - dt.timedelta(days=1)):
        start, end = hours_span(branch, hours, day)
        if is_day(day) and start <= when < end:
            return day
    return None


def within_hours(branch: Branch, hours: shop_hours.Hours, when: dt.datetime) -> bool:
    """True when `when` falls within an open business day's hours (business_day)."""
    return business_day(branch, hours, when) is not None


def open_state(branch: Branch, hours: shop_hours.Hours, now: dt.datetime) -> OpenState:
    """Whether the shop is open at `now`, until when, and its next opening after `now`."""
    today = now.astimezone(ZoneInfo(branch.timezone)).date()
    day = business_day(branch, hours, now)
    is_open = day is not None
    closes_at = hours_span(branch, hours, day)[1] if day is not None else None
    is_day = shop_hours.open_days(hours)
    next_open = next(
        start
        for k in range(8)
        if is_day(day := today + dt.timedelta(days=k))
        and (start := shop_hours.at(branch, hours, day, closing=False)) > now
    )
    return OpenState(is_open, closes_at, next_open)


def match_area(text: str, areas: Sequence[DeliveryArea]) -> DeliveryArea | None:
    """The first configured area whose name the text holds as whole words, ignoring case and
    accents; None when it names none."""
    return next((a for a in areas if _names(text, a.name)), None)


def match_items(text: str, items: Mapping[str, Sequence[str]]) -> list[str]:
    """The ids (in the mapping's order) of the items the text names: by the whole name or by a
    short code as a word. `items` maps an id to (name, *codes)."""
    words = set(fold(text).split())
    return [
        item_id
        for item_id, (name, *codes) in items.items()
        if _names(text, name) or words & {fold(c) for c in codes}
    ]


def match_item(words: str, items: Mapping[str, Sequence[str]]) -> str | None:
    """The one item a count group's words name: the only match, else the only one named by its
    whole name ("box of 4 bibingka" is the Box, bibingka only describing it); None otherwise."""
    hits = match_items(words, items)
    if len(hits) > 1:
        hits = [i for i in hits if _names(words, items[i][0])]
    return hits[0] if len(hits) == 1 else None


def last_four(address: str) -> str:
    """The last four digits of a channel address (the last four characters when it has none)."""
    digits = "".join(c for c in address if c.isdigit())
    return (digits or address)[-4:]
