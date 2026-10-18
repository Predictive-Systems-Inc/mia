"""Ask Jev which action a message wants and with which inputs (spec 2026-10-17-jev-decider).

decide() runs no tool. The request leaves only through the egress transport (rule 6), which
pseudonymises it and writes egress_log and usage; the caller sets the egress context and holds
no write lock (rule 11). The generic half lives in mia.agents.decider; this module keeps the
shift supervisor's argument mapping.
"""

import datetime as dt
from functools import partial
from typing import Any

from mia.agents import decider as shared
from mia.agents.decider import Alternative, DecideError, Decision, Reader
from mia.agents.shift_supervisor.actions import ACTIONS, ANOTHER_DAY, Query, build_request

__all__ = ["Alternative", "DecideError", "Decision", "decide", "parse"]


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
        if day == ANOTHER_DAY:
            return {}, "date"
        if _ambiguous(person, q):
            return {}, "person"
        date = day or q.today.isoformat()
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
        return {"location_name": q.sites.get(site or "")}, None
    if action == "report_site_problem":
        kind = r.pick("problem_kind", {"cannot_access", "site_problem"})
        site = r.pick("site", q.sites)
        location = q.sites.get(site or "")
        return {"kind": kind, "text": q.message[:500], "location_name": location}, None
    if action == "checklist":
        item = r.pick("checklist_item", q.checklist_items)
        site = r.pick("site", q.sites)
        return {
            "item": q.checklist_items.get(item or ""),
            "location_name": q.sites.get(site or ""),
        }, None
    if action == "reply_only":
        kinds = {"greeting", "thanks", "goodbye", "capabilities", "send_photos", "other"}
        return {"kind": r.pick("conversation", kinds) or "other"}, None
    return {}, None  # clarify


def parse(answers: dict[str, Any], q: Query) -> Decision:
    """The shared parse over the shift supervisor's ACTIONS and argument mapping."""
    return shared.parse(answers, q, actions=ACTIONS, args=_args)


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for an answer outside the options) when no usable answer came."""
    return await shared.decide(
        q,
        build_request=build_request,
        parse=partial(shared.parse, q=q, actions=ACTIONS, args=_args),
    )
