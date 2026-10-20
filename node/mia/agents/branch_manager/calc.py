"""The branch manager's coaching numbers as pure functions (rule 7): the tip rotation, the nudge
rule, the personal best, the pairing and "improved". No Session and no clock: the tools load rows
and pass plain values and the local date in.
"""

import datetime as dt
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

TIP_DAYS = 30  # a tip or quote is never given to the same person twice within 30 days
BEST_DAYS = 90  # a personal best is the best amount in the 90 days before
NUDGE_GAP = 7  # never two nudges to one person in a week


@dataclass(frozen=True)
class TipRef:
    """What pick_tip needs of a tip row: its id, kind (tip or quote) and item (None: general)."""

    id: str
    kind: str
    item_id: str | None


def pick_tip(
    tips: Sequence[TipRef],
    given: Mapping[str, dt.date],
    today: dt.date,
    item_id: str | None = None,
) -> str | None:
    """The id of the tip to give today: among the general tips and the item's own (another
    item's tips are skipped), those not given to this person within TIP_DAYS, the item's first,
    then never given, then least recently given, then by id. None when every one was given
    within TIP_DAYS. given maps tip id to the last local date it was given to this person."""
    cutoff = today - dt.timedelta(days=TIP_DAYS)
    ready = [
        t
        for t in tips
        if t.item_id in (None, item_id) and (t.id not in given or given[t.id] <= cutoff)
    ]
    if not ready:
        return None
    best = min(ready, key=lambda t: (t.item_id is None, given.get(t.id, dt.date.min), t.id))
    return best.id


def nudge_due(
    missed: Sequence[bool], last_nudge: dt.date | None, today: dt.date, after: int
) -> bool:
    """True when the last `after` days (missed is oldest first, True a missed day target) were
    all missed and the person had no nudge in the NUDGE_GAP days before today."""
    if after < 1 or len(missed) < after or not all(missed[-after:]):
        return False
    return last_nudge is None or (today - last_nudge).days >= NUDGE_GAP


def personal_best(amounts: Mapping[dt.date, int], day: dt.date) -> bool:
    """True when the day's amount beats every amount of the BEST_DAYS days before it; False
    without the day or without one earlier day in that window."""
    if day not in amounts:
        return False
    start = day - dt.timedelta(days=BEST_DAYS)
    earlier = [a for d, a in amounts.items() if start <= d < day]
    return bool(earlier) and amounts[day] > max(earlier)


def pairing(baskets: Iterable[frozenset[str]]) -> tuple[str, str] | None:
    """The two item ids most often in one basket (one clerk's items on one business date), the
    pair sorted; ties go to the smallest sorted pair. None when no basket holds two items."""
    pairs: Counter[tuple[str, str]] = Counter()
    for basket in baskets:
        pairs.update(combinations(sorted(basket), 2))
    if not pairs:
        return None
    a, b = min(pairs, key=lambda p: (-pairs[p], p))
    return a, b


def improved(now: int, before: int) -> bool:
    """True when this period's number beats the period before."""
    return now > before
