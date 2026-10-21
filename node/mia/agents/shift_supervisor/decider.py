"""Ask Jev which action a message wants and with which inputs (spec 2026-10-17-jev-decider).

decide() runs no tool. The request leaves only through the egress transport (rule 6), which
pseudonymises it and writes egress_log and usage; the caller sets the egress context and holds
no write lock (rule 11). The generic half lives in mia.agents.decider; this module keeps the
shift supervisor's argument mapping.
"""

import datetime as dt
import re
from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.decider import Alternative, DecideError, Decision, Reader
from mia.agents.parsing import find_dates, has_negation
from mia.agents.shift_supervisor.actions import (
    ANOTHER_DAY,
    SUPERVISING,
    Query,
    actions_for,
    build_request,
    problem_kinds,
)
from mia.agents.shift_supervisor.rules import is_retail

__all__ = ["Alternative", "DecideError", "Decision", "decide", "parse"]

# Rule 7 guards: words code reads so a wrong pick asks instead of writing. Stock is the inventory
# manager's (Q108: "ubos na ang LPG"), never a missed delivery; a correction word with a time is
# a time correction, never a check-out now. Local forms are machine drafts (Q28 to Q35).
# Only the "ran out" words: an item noun alone ("walang dumating na LPG") is a missed delivery.
STOCK_WORDS = frozenset({
    "stock", "stocks", "ubos", "naubos", "naubusan", "maubos", "paubos", "maubusan", "hurot",
    "nahurot", "mahurot", "nahurtan", "nahutdan",
})  # fmt: skip
CORRECTION_WORDS = frozenset({
    "mali", "nagkamali", "sayop", "nasayop", "sala", "nasala", "tama", "dapat", "wrong",
    "correct", "correction",
})  # fmt: skip

# A late word with a clock time, or a negated arrive word ("indi ako kaabot sa opening, 11 na ako
# maabot"), is a late notice, never a check-in now. "ma-late" reads as "ma" and "late".
LATE_WORDS = frozenset({
    "late", "malate", "nalate", "maleleyt", "naleleyt", "maleyt", "naleyt", "atrasado",
    "maatrasado", "naatrasado", "ulahi", "maulahi", "naulahi", "mahuhuli", "mahuli", "delayed",
})  # fmt: skip
ARRIVE_WORDS = frozenset({
    "abot", "kaabot", "umabot", "maabot", "makaabot", "aabot", "makakaabot", "nakaabot",
    "naabot", "arrive", "make",
})  # fmt: skip
# A closure of the kiosk: never the sender's absence or an incident (close_day or ask). A first
# person singular word makes it the sender's own ("sarado ang daan, hindi ako makakapasok").
CLOSURE_WORDS = frozenset({
    "sarado", "sirado", "closed", "nakasara", "nakasarado", "isara", "isasara", "sasarhan",
    "sirhan", "sirad-an",
})  # fmt: skip
CLOSURE_PHRASES = (
    "no open", "not open", "won't open", "waray abri", "diri abri", "dili abli", "dili moabli",
    "indi bukas", "indi abri", "indi mabukas", "dai bukas", "dai magbukas", "hindi bukas",
    "hindi magbubukas",
)  # fmt: skip
FIRST_PERSON = frozenset({"ako", "ko", "ak", "i", "me", "my", "akon", "nako", "naku", "minä"})
CLOSURE = "closure"  # the missing input of an absence or incident that names a closure


# A check-out time this far from the branch's clock is a time correction, never a check-out now.
CHECK_OUT_NOW = dt.timedelta(minutes=5)


def _has_word(text: str, words: frozenset[str]) -> bool:
    return any(w in words for w in re.findall(r"\w+", text.casefold()))


def _minutes(at: dt.time) -> int:
    return at.hour * 60 + at.minute


def _not_now(q: Query) -> bool:
    """True when the message names a clock time away from the branch's clock (CHECK_OUT_NOW)."""
    if q.now is None:
        return False
    now = _minutes(q.now)
    limit = CHECK_OUT_NOW.total_seconds() // 60
    return any(abs(_minutes(dt.time.fromisoformat(v)) - now) > limit for v in q.times.values())


def _late(q: Query) -> bool:
    """True when the message is a late notice: a LATE_WORDS word with a clock time, or a
    negation with an ARRIVE_WORDS word."""
    late = bool(q.times) and _has_word(q.message, LATE_WORDS)
    return late or (has_negation(q.message) and _has_word(q.message, ARRIVE_WORDS))


def _named_days(q: Query) -> set[str]:
    """The ISO days the message names (parsing.find_dates; "en" so an English "May 5" counts)."""
    return {d.isoformat() for _, d in find_dates(q.message, q.today, "en")}


def _off_day(day: str | None, q: Query) -> bool:
    """True in retail when the message names days and `day` is none of them ("kasuhapon" is
    yesterday, never today): the date is asked, never written. ponytail: retail only (the D40
    rows); cleaning's tests default an unpicked "tomorrow" absence to today."""
    named = _named_days(q) if is_retail() else set()
    return bool(named) and day not in named


def _closure(q: Query) -> bool:
    """True in retail when the message names a closure (CLOSURE_WORDS or CLOSURE_PHRASES) and a
    day, with no first person singular word: the kiosk's closure, never the sender's absence or
    an incident."""
    folded = " ".join(re.findall(r"[\w'-]+", q.message.casefold()))
    said = _has_word(q.message, CLOSURE_WORDS) or any(
        re.search(rf"\b{re.escape(p)}\b", folded) for p in CLOSURE_PHRASES
    )
    first = _has_word(q.message, FIRST_PERSON)
    return is_retail() and said and not first and bool(_named_days(q))


def _period(value: str | None, today: dt.date) -> tuple[str | None, str | None]:
    if value == "today":
        return today.isoformat(), today.isoformat()
    if value == "tomorrow":
        d = today + dt.timedelta(days=1)
        return d.isoformat(), d.isoformat()
    if value == "this_week":
        return today.isoformat(), (today + dt.timedelta(days=6)).isoformat()
    if value == "next_week":
        monday = today + dt.timedelta(days=7 - today.weekday())
        return monday.isoformat(), (monday + dt.timedelta(days=6)).isoformat()
    return None, None  # the tool's default


def _ambiguous(person: str | None, q: Query) -> bool:
    """True when the picked person shares a first name with someone else in the branch and the
    message names neither their surname nor their full name: the pseudonymiser gives a shared
    first name one token, so Jev cannot see the ambiguity and code must."""
    parts = q.people[person].split() if person is not None else []
    if not parts:  # no pick, or a blank name (a half-filled import row): nothing to compare
        return False
    first, *rest = parts
    namesakes = [n for n in q.people.values() if n.lower().split()[:1] == [first.lower()]]
    message = q.message.lower()
    return len(namesakes) > 1 and not any(part.lower() in message for part in rest)


def _args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required slot that is missing, if any."""
    q: Query = r.q
    if action == "get_my_visits":
        period = r.pick("period", {"today", "tomorrow", "this_week", "next_week"})
        start, end = _period(period, q.today)
        person = r.pick("person", q.people)
        if _ambiguous(person, q):
            return {}, "person"
        return {"start": start, "end": end, "person_name": q.people.get(person or "")}, None
    if action == "record_absence":
        day = r.pick("date", {*q.dates, ANOTHER_DAY}, count_unstated=True)
        reason = r.pick("reason", {"sick", "late", "leaving_early", "other"})
        part = r.pick("partial_day", {"morning", "afternoon", "whole_day"})
        person = r.pick("person", q.people, count_unstated=True)
        if _closure(q):
            return {}, CLOSURE
        if day == ANOTHER_DAY:
            return {}, "date"
        if _ambiguous(person, q):
            return {}, "person"
        date = day or q.today.isoformat()
        if _off_day(date, q):
            return {}, "date"
        return {
            "date": date,
            "reason": reason or "other",
            "partial_day": None if part in (None, "whole_day") else part,
            "person_name": q.people.get(person or ""),
        }, None
    if action == "find_replacements":
        visit = r.pick("visit", q.visits, fallback=True)  # else site and date, resolved by code
        if visit is not None:
            return {"visit_id": visit}, None
        site, day = r.pick("site", q.sites), r.pick("date", {*q.dates, ANOTHER_DAY})
        if site is None or day == ANOTHER_DAY:
            return {}, "visit"
        if day is None and is_retail():  # never today by default at the kiosk: ask
            return {}, "date"
        return {"location_name": q.sites[site], "date": day}, None
    if action == "assign_cover":
        person = r.pick("person", q.people)
        if _ambiguous(person, q):
            return {}, "person"
        if q.last_cover_visit is None:  # never a guessed visit: the cover flow comes first
            return {}, "visit"
        if person is None:
            return {"visit_id": q.last_cover_visit}, "person"
        return {"visit_id": q.last_cover_visit, "candidate_id": person}, None
    if action == "respond_to_cover":
        return {"accept": r.yes("accept")}, None
    if action in ("check_in", "check_out", "visit_details"):
        site = r.pick("site", q.sites)
        # "sayop akong check out, 5pm" or "nag-out ako 5pm" at 18:00: a correction, never now
        timed = q.times and (_has_word(q.message, CORRECTION_WORDS) or _not_now(q))
        if action == "check_out" and timed and is_retail():
            return {}, "time"
        if action == "check_in" and is_retail() and _late(q):  # a late notice, never now
            return {}, "time"
        return {"location_name": q.sites.get(site or "")}, None
    if action == "report_site_problem":
        kind = r.pick("problem_kind", set(problem_kinds()))
        site = r.pick("site", q.sites)
        location = q.sites.get(site or "")
        if _closure(q):  # "waray abri ha Biyernes": a closure, never an incident
            return {}, CLOSURE
        if is_retail() and _has_word(q.message, STOCK_WORDS):  # stock (Q108): ask, any kind
            return {}, "problem_kind"
        return {"kind": kind, "text": q.message[:500], "location_name": location}, None
    if action == "checklist":
        item = r.pick("checklist_item", q.checklist_items)
        site = r.pick("site", q.sites)
        return {
            "item": q.checklist_items.get(item or ""),
            "location_name": q.sites.get(site or ""),
        }, None
    if action in ("set_roster", "swap", "swap_reply", "correct_time", "close_day", "week_roster"):
        return _retail_args(action, r)
    if action == "reply_only":
        kinds = {"greeting", "thanks", "goodbye", "capabilities", "send_photos", "other"}
        return {"kind": r.pick("conversation", kinds) or "other"}, None
    return {}, None  # clarify


def _retail_args(action: str, r: Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for the kiosk actions (D39). The roster pattern and the times are read by
    code in build_query; Jev only picks which of them the message means."""
    q: Query = r.q
    if action == "set_roster":
        return {"shifts": q.roster}, "pattern" if not q.roster or q.roster_unclear else None
    if action == "swap_reply":
        return {"accept": r.yes("accept")}, None
    if action == "week_roster":
        period = r.pick("period", {"today", "tomorrow", "this_week", "next_week"})
        start = _period(period, q.today)[0] if period in ("this_week", "next_week") else None
        person = r.pick("person", q.people)
        if _ambiguous(person, q):
            return {}, "person"
        return {"start": start, "person_name": q.people.get(person or "")}, None
    day = r.pick("date", {*q.dates, ANOTHER_DAY})
    # correct_time defaults to today; close_day and swap ask for a day not picked
    stated = day or (q.today.isoformat() if action == "correct_time" else None)
    if day == ANOTHER_DAY or (stated is not None and _off_day(stated, q)):
        return {}, "date"
    if action == "close_day":
        site = r.pick("site", q.sites)
        args = {"location_name": q.sites.get(site or ""), "date": day, "reason": q.message[:200]}
        return args, "date" if day is None else None
    person = r.pick("person", q.people)
    if _ambiguous(person, q):
        return {}, "person"
    name = q.people.get(person or "")
    if action == "swap":
        missing = "person" if name is None else "date" if day is None else None
        return {"person_name": name, "date": day}, missing
    time = r.pick("time", q.times)  # correct_time
    date = day or q.today.isoformat()
    end = q.times.get(time or "")
    return {"date": date, "end": end, "start": None, "person_name": name}, (
        "time" if end is None else None
    )


def _as_correction(d: Decision) -> Decision:
    """A check-out held back for its time (missing "time") runs as correct_time when Jev offered
    that with every input and a probability at or above the decider's THRESHOLD; else it stays
    a clarify that asks."""
    if d.action != "clarify" or d.raw_action != "check_out" or d.missing != "time":
        return d
    fix = next((a for a in d.alternatives if a.action == "correct_time"), None)
    if fix is None or fix.missing is not None or fix.probability < shared.THRESHOLD:
        return d
    return Decision(
        action="correct_time", args=fix.args, confidence=d.confidence, raw_action=d.raw_action
    )


def _as_closure(d: Decision, answers: dict[str, Any], q: Query) -> Decision:
    """An absence or incident held back for a closure (missing CLOSURE) runs close_day when the
    sender is head staff (SUPERVISING), Jev was sure, the message has no clock time and the day
    is the one it names; else it stays a clarify, close_day offered first when complete."""
    if d.missing != CLOSURE:
        return d
    reader = Reader(answers, q)
    args, missing = _retail_args("close_day", reader)
    named = _named_days(q)
    if args.get("date") is None and len(named) == 1:
        args, missing = {**args, "date": next(iter(named))}, None
    if missing is not None:
        return d
    sure = min([d.confidence, *reader.confidences]) >= shared.THRESHOLD
    if sure and not q.times and SUPERVISING & set(q.role.split(", ")):
        return Decision(
            action="close_day", args=args, confidence=d.confidence, raw_action=d.raw_action
        )
    close = Alternative(action="close_day", args=args, probability=d.confidence)
    others = [a for a in d.alternatives if a.action != "close_day"]
    return d.model_copy(update={"alternatives": [close, *others][:3]})


def parse(answers: dict[str, Any], q: Query) -> Decision:
    """The shared parse over the template's actions (actions_for) and argument mapping; a
    held-back check-out becomes correct_time (_as_correction), a held-back closure close_day
    (_as_closure)."""
    d = _as_correction(shared.parse(answers, q, actions=actions_for(), args=_args))
    return _as_closure(d, answers, q)


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for an answer outside the options) when no usable answer came."""
    return await shared.decide(q, build_request=build_request, parse=partial(parse, q=q))
