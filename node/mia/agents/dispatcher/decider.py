"""Ask Jev which action a message wants and with which inputs (spec 2026-10-17-jev-decider).

decide() runs no tool. The request leaves only through the egress transport (rule 6), which
pseudonymises it and writes egress_log and usage; the caller sets the egress context and holds
no write lock (rule 11). parse() is pure: answers in, a Decision out.
"""

import asyncio
import datetime as dt
from typing import Any

import httpx
from pydantic import BaseModel, Field

from mia.agents.dispatcher.actions import ACTIONS, NOT_STATED, THRESHOLD, Query, build_request
from mia.core.egress import EgressBlocked, EgressTransport
from mia.settings import get_settings

RETRY_STATUS = {429, 529}
RETRIES = 2
BACKOFF = 0.5  # seconds, doubled per retry
TIMEOUT = 10.0


class DecideError(Exception):
    """Jev gave no usable answer: no key, blocked egress, an error status, a timeout, or an
    answer outside the request's options."""


class Alternative(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    probability: float
    missing: str | None = None


class Decision(BaseModel):
    action: str  # what code does: an action id, clarify after a low confidence
    args: dict[str, Any] = Field(default_factory=dict)  # the tool input; reply_only: {"kind"}
    confidence: float
    raw_action: str = ""  # Jev's own pick, before the threshold
    alternatives: list[Alternative] = Field(default_factory=list)
    missing: str | None = None  # a required input that was not found


def _inner() -> httpx.AsyncBaseTransport | None:
    """The network below egress; tests replace this with an httpx.MockTransport."""
    return None


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


class _Reader:
    """Reads the slot answers one action uses, checking each against the request's options."""

    def __init__(self, answers: dict[str, Any], q: Query) -> None:
        self.answers, self.q = answers, q
        self.confidences: list[float] = []

    def pick(self, slot: str, options: dict[str, str] | set[str]) -> str | None:
        answer = self.answers[slot]
        value = str(answer["choice"])
        if value != NOT_STATED and value not in options:
            raise DecideError(f"{slot}: {value!r} is not an option")
        self.confidences.append(float(answer["confidence"]))
        return None if value == NOT_STATED else value

    def yes(self, slot: str) -> bool:
        p = float(self.answers[slot]["noul"])
        self.confidences.append(max(p, 1 - p))
        return p >= 0.5


def _args(action: str, r: _Reader) -> tuple[dict[str, Any], str | None]:
    """The tool input for one action and the required slot that is missing, if any."""
    q = r.q
    if action == "get_my_visits":
        period = r.pick("period", {"today", "tomorrow", "this_week", "next_week"})
        start, end = _period(period, q.today)
        person = r.pick("person", q.people)
        return {"start": start, "end": end, "person_name": q.people.get(person or "")}, None
    if action == "record_absence":
        date = r.pick("date", q.dates) or q.today.isoformat()
        reason = r.pick("reason", {"sick", "late", "leaving_early", "other"})
        part = r.pick("partial_day", {"morning", "afternoon", "whole_day"})
        person = r.pick("person", q.people)
        return {
            "date": date,
            "reason": reason or "other",
            "partial_day": None if part in (None, "whole_day") else part,
            "person_name": q.people.get(person or ""),
        }, None
    if action == "find_replacements":
        visit = r.pick("visit", q.visits)
        if visit is not None:
            return {"visit_id": visit}, None
        site, day = r.pick("site", q.sites), r.pick("date", q.dates)
        if site is None:
            return {}, "visit"
        return {"location_name": q.sites[site], "date": day}, None
    if action == "assign_cover":
        person = r.pick("person", q.people)
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
    """Turn Jev's answers into a Decision. The confidence is the least certain judgment the
    chosen action used; below THRESHOLD, or with a required input missing, the decision is
    clarify with up to three alternatives (the top pick first). Raises DecideError for an
    answer outside the options."""
    try:
        top = answers["action"]
        raw = str(top["choice"])
        if raw not in ACTIONS:
            raise DecideError(f"action: {raw!r} is not an option")
        probabilities = {str(k): float(v) for k, v in top["probabilities"].items()}
        reader = _Reader(answers, q)
        args, missing = _args(raw, reader)
        confidence = min([float(top["confidence"]), *reader.confidences])
        ranked = sorted(probabilities.items(), key=lambda kv: -kv[1])
        alternatives: list[Alternative] = []
        for action, p in ranked:
            if action == "clarify" or action not in ACTIONS or p < 0.05:
                continue
            alt_args, alt_missing = _args(action, _Reader(answers, q))
            alternatives.append(
                Alternative(action=action, args=alt_args, probability=p, missing=alt_missing)
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise DecideError(f"unexpected answer: {exc!r}") from exc
    if raw == "clarify" or missing is not None or confidence < THRESHOLD:
        return Decision(
            action="clarify",
            confidence=confidence,
            raw_action=raw,
            alternatives=alternatives[:3],
            missing=missing,
        )
    others = [a for a in alternatives if a.action != raw][:3]
    return Decision(
        action=raw, args=args, confidence=confidence, raw_action=raw, alternatives=others
    )


async def decide(q: Query) -> Decision:
    """One Jev request for the query. Raises DecideError when no usable answer came back."""
    settings = get_settings()
    if not settings.MIA_TYPESAFE_KEY:
        raise DecideError("MIA_TYPESAFE_KEY is not set")
    body = build_request(q, settings.MIA_JEV_MODEL)
    headers = {"Authorization": f"Bearer {settings.MIA_TYPESAFE_KEY}"}
    async with httpx.AsyncClient(transport=EgressTransport(_inner()), timeout=TIMEOUT) as client:
        for attempt in range(RETRIES + 1):
            try:
                response = await client.post(settings.MIA_TYPESAFE_URL, json=body, headers=headers)
            except EgressBlocked as exc:
                raise DecideError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise DecideError(type(exc).__name__) from exc
            if response.status_code in RETRY_STATUS and attempt < RETRIES:
                await asyncio.sleep(BACKOFF * 2**attempt)
                continue
            if response.status_code != 200:
                raise DecideError(f"status {response.status_code}: {response.text[:300]}")
            try:
                return parse(response.json()["answers"], q)
            except (KeyError, ValueError) as exc:
                raise DecideError(f"unexpected answer: {exc!r}") from exc
    raise DecideError("no answer")  # not reached: the loop returns or raises
