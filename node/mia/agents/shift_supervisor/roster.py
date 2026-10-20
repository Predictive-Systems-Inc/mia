"""The retail roster as pure code (rule 7, D39): the owner's pattern to clauses, shift ranges read
inside the branch's hours, weekdays, job names, the roster week and swap checks.

Guarantees: no database, no model and no clock (dates and times come in); every hour, day and
minute is read by code, the model only words the reply.
"""

import datetime as dt
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from zoneinfo import ZoneInfo

from mia.agents.parsing import ALAS, DAY_NAMES, NEGATIONS
from mia.agents.shift_supervisor import scoring
from mia.core.scheduling import WEEKDAYS
from mia.templates.retail import hours as retail_hours

# Each scoring reason (the English literal) to its retail reply key.
REASON_KEYS = {
    "absent that day": "shift.reason.absent",
    "outside availability": "shift.reason.unavailable",
    "already booked at that time": "shift.reason.booked",
    "over the daily hour limit": "shift.reason.daily",
    "over the weekly hour limit": "shift.reason.weekly",
}


@dataclass(frozen=True)
class Range:
    start: dt.time
    end: dt.time


@dataclass(frozen=True)
class Days:
    byday: list[str]
    corrected: bool


@dataclass(frozen=True)
class Clause:
    person_id: str
    byday: list[str]
    start: dt.time
    end: dt.time


@dataclass(frozen=True)
class Pattern:
    clauses: list[Clause]
    unclear: list[str]


# ---- ranges ------------------------------------------------------------------------------


def _time(tag: str) -> str:
    words = "|".join(ALAS)
    return (
        rf"(?:alas\s+(?P<w{tag}>{words})\b|(?:alas\s+)?(?P<h{tag}>\d{{1,2}}))"
        rf"(?::(?P<m{tag}>[0-5]\d))?\s*(?P<ap{tag}>am|pm)?"
    )


_RANGE = re.compile(
    rf"(?<![\d:]){_time('a')}\s*(?:-|\bto\b|\bhanggang\b|\bhangtod\b|\buntil\b)\s*{_time('b')}\b",
    re.IGNORECASE,
)


def _readings(m: re.Match[str], tag: str) -> list[dt.time]:
    """The 24-hour readings of one end of a range: one with am/pm or above 12, else am then pm."""
    word, minute, ap = m[f"w{tag}"], int(m[f"m{tag}"] or 0), m[f"ap{tag}"]
    hour = ALAS[word.lower()] if word else int(m[f"h{tag}"])
    if hour > 23 or (ap and not 1 <= hour <= 12):
        return []
    if ap:
        return [dt.time(hour % 12 + (12 if ap.lower() == "pm" else 0), minute)]
    if hour > 12 or hour == 0:
        return [dt.time(hour, minute)]
    return [dt.time(hour % 12, minute), dt.time(hour % 12 + 12, minute)]


def find_ranges(text: str, opens: dt.time, closes: dt.time) -> list[tuple[str, Range]]:
    """Shift ranges in text order as (id "r0", "r1", ..., Range): "9 to 5", "1-9pm", "9am-5pm",
    "9 hanggang 5", "alas 9 hanggang alas 5". A bare start takes its reading inside the branch's
    hours (opens to closes), the end its first reading after the start. A bare number outside a
    range is no time. Pure."""
    found: list[Range] = []
    for m in _RANGE.finditer(text):
        starts, ends = _readings(m, "a"), _readings(m, "b")
        start = next((t for t in starts if opens <= t < closes), starts[0] if starts else None)
        end = next((t for t in ends if start is not None and t > start), None)
        if start is not None and end is not None:
            found.append(Range(start, end))
    return [(f"r{i}", r) for i, r in enumerate(found)]


# ---- days --------------------------------------------------------------------------------

_DAY_INDEX = {name: i for names in DAY_NAMES.values() for i, name in enumerate(names)}
_DAY = re.compile(
    r"\b(" + "|".join(sorted(_DAY_INDEX, key=len, reverse=True)) + r")\b", re.IGNORECASE
)
_THROUGH = re.compile(r"^\s*(?:-|to|hanggang|hangtod|until|through)\s*$", re.IGNORECASE)
_WORD = re.compile(r"\w+")


def find_days(text: str) -> Days:
    """The weekdays named in the text as BYDAY codes in WEEKDAYS order (en, fil, ceb and the
    other DAY_NAMES): "Martes hanggang Linggo" is a range (wrapping past Sunday), "Sabado at
    Linggo" a list. A day right after a NEGATIONS word is dropped and `corrected` set. Pure."""
    days: set[int] = set()
    corrected, prev, prev_end = False, None, 0
    for m in _DAY.finditer(text):
        day, gap = _DAY_INDEX[m[1].lower()], text[prev_end : m.start()]
        words = _WORD.findall(gap.lower())
        if words and words[-1] in NEGATIONS:
            corrected = True
        elif prev is not None and _THROUGH.match(gap):
            days |= {(prev + k) % 7 for k in range((day - prev) % 7 + 1)}
        else:
            days.add(day)
        prev, prev_end = day, m.end()
    return Days([code for i, code in enumerate(WEEKDAYS) if i in days], corrected)


# ---- the pattern -------------------------------------------------------------------------

_CLAUSE = re.compile(r"[,;]|\btapos\b|\bthen\b", re.IGNORECASE)


def parse_pattern(text: str, people: Mapping[str, str], opens: dt.time, closes: dt.time) -> Pattern:
    """The owner's pattern as clauses: split on commas, semicolons, "tapos" and "then"; each
    names exactly one of `people` (person id to first name) by word, its days (else the previous
    clause's) and one shift range per Clause (two ranges are a split shift, two Clauses). A
    clause with no days and none before it, no single name or no range goes to `unclear`."""
    by_name = {name.casefold(): pid for pid, name in people.items()}
    clauses: list[Clause] = []
    unclear: list[str] = []
    last_days: list[str] = []
    for part in (p.strip() for p in _CLAUSE.split(text)):
        if not part:
            continue
        named = {by_name[w] for w in _WORD.findall(part.casefold()) if w in by_name}
        byday = find_days(part).byday or last_days
        last_days = byday
        ranges = find_ranges(part, opens, closes)
        if len(named) != 1 or not byday or not ranges:
            unclear.append(part)
            continue
        pid = named.pop()
        clauses += [Clause(pid, byday, r.start, r.end) for _, r in ranges]
    return Pattern(clauses, unclear)


def rrule(byday: Sequence[str]) -> str:
    """The weekly recurrence of the days, BYDAY in WEEKDAYS order."""
    return "FREQ=WEEKLY;BYDAY=" + ",".join(d for d in WEEKDAYS if d in byday)


def job_name(
    start: dt.time,
    end: dt.time,
    byday: Sequence[str],
    opens: dt.time,
    closes: dt.time,
    first_name: str,
) -> str:
    """ "Opening" when the shift starts at opening, "Closing" when it ends at closing, else
    "Mid"; "Weekend opening" (and so on) for Saturday and Sunday only; then the first name."""
    label = "Opening" if start == opens else "Closing" if end == closes else "Mid"
    if set(byday) == {"SA", "SU"}:
        label = f"Weekend {label.lower()}"
    return f"{label} {first_name}"


def outside_hours(clause: Clause, hours: retail_hours.Hours) -> list[str]:
    """The clause's BYDAY codes whose hours it leaves: a weekday the branch has no hours for
    (when it has any) or one it starts before opening or ends after closing."""
    open_weekdays = {h.weekday for h in hours} or set(range(7))
    out = []
    for code in clause.byday:
        wd = WEEKDAYS.index(code)
        if wd not in open_weekdays or not (
            retail_hours.opens(hours, wd) <= clause.start
            and clause.end <= retail_hours.closes(hours, wd)
        ):
            out.append(code)
    return out


def week_of(now: dt.datetime, tz: str) -> dt.date:
    """The Monday of the local week at `now` in `tz` (never the UTC date)."""
    local = now.astimezone(ZoneInfo(tz)).date()
    return local - dt.timedelta(days=local.weekday())


def swap_breaks(
    a: scoring.CandidateData, a_slot: scoring.Slot, b: scoring.CandidateData, b_slot: scoring.Slot
) -> list[str]:
    """Every rule a swap breaks: each clerk checked in the other's slot with their own slot taken
    off their bookings, each reason prefixed "Name: " (empty means the swap is fine)."""
    out = []
    for who, own, other in ((a, a_slot, b_slot), (b, b_slot, a_slot)):
        freed = replace(who, booked=[s for s in who.booked if s != own])
        out += [f"{who.name}: {r}" for r in scoring.ineligibility(freed, other)]
    return out
