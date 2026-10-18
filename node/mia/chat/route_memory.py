"""What people chose when Mia asked "Is this about": exact repeats are routed by code before
any Jev call (spec 2026-10-18-router-follow-up, decision 4b). The rules (`learned`) are pure;
`remember` writes the tap event and `recall` reads the branch's events, both in the caller's
session. Only agent ids are learned, never text as a rule (rule 8)."""

import datetime as dt
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.core import events
from mia.core.models import Event, Message, Thread

CHOSEN = "chat.route_chosen"
FORGOTTEN = "chat.route_forgotten"
WINDOW = dt.timedelta(days=90)
UNDO_WINDOW = dt.timedelta(hours=1)
MIN_TAPS = 2

_SPACES = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")


def key_of(text: str) -> str:
    """The memory key of a message: casefolded, one space between words, trailing punctuation
    dropped, every number replaced by # (so each day's counts share one key)."""
    key = _SPACES.sub(" ", text.casefold()).strip().rstrip(".!?,;:").strip()
    return _DIGITS.sub("#", key)


@dataclass(frozen=True)
class Tap:
    """One chat.route_chosen event: a person tapped agent_id for this key."""

    key: str
    agent_id: str
    at: dt.datetime
    thread_id: str
    event_id: str


@dataclass(frozen=True)
class Switch:
    """A person moved away from from_agent on this key in this thread."""

    key: str
    from_agent: str
    at: dt.datetime
    thread_id: str


def _undone(tap: Tap, switches: Sequence[Switch]) -> bool:
    """True when a switch away from the tapped agent follows it within UNDO_WINDOW in the
    same thread for the same key."""
    return any(
        s.key == tap.key
        and s.thread_id == tap.thread_id
        and s.from_agent == tap.agent_id
        and dt.timedelta(0) <= s.at - tap.at <= UNDO_WINDOW
        for s in switches
    )


def _counts(tap: Tap, now: dt.datetime, forgotten: Mapping[str, dt.datetime]) -> bool:
    """True when a tap is inside WINDOW and was not forgotten after it happened."""
    if now - tap.at > WINDOW:
        return False
    forgot_at = forgotten.get(tap.key)
    return forgot_at is None or forgot_at <= tap.at


def learned(
    taps: Sequence[Tap],
    switches: Sequence[Switch],
    forgotten: Mapping[str, dt.datetime],
    now: dt.datetime,
) -> dict[str, str]:
    """Key to agent id for every key with at least MIN_TAPS taps for one agent and none for
    another, counting only taps inside WINDOW, not forgotten after they happened, and not
    undone by a switch away within UNDO_WINDOW in the same thread."""
    votes: dict[str, Counter[str]] = {}
    for tap in taps:
        if not _counts(tap, now, forgotten) or _undone(tap, switches):
            continue
        votes.setdefault(tap.key, Counter())[tap.agent_id] += 1
    return {
        key: next(iter(c))
        for key, c in votes.items()
        if len(c) == 1 and next(iter(c.values())) >= MIN_TAPS
    }


def remember(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    original_message_id: str | None,
    agent_id: str,
    picked: str | None,
    confidence: float | None,
    options: list[str],
) -> None:
    """Emits chat.route_chosen for a tap in the caller's transaction (it commits nothing). The
    event carries the message's key, not its text. No event when the original message is
    unknown: there is nothing to learn from."""
    message = session.get(Message, original_message_id) if original_message_id else None
    if message is None:
        return
    after = {
        "original_message_id": message.id,
        "agent_id": agent_id,
        "picked": picked,
        "confidence": confidence,
        "options": options,
        "lang": deps.lang,
        "key": key_of(message.text),
    }
    events.emit(session, CHOSEN, ("thread", thread.id), None, after, deps.actor)


def _branch_events(session: Session, branch_id: str, action: str) -> Sequence[Event]:
    return session.exec(
        select(Event).where(Event.action == action).where(Event.branch_id == branch_id)
    ).all()


def _switches(session: Session, branch_id: str) -> list[Switch]:
    """The branch's chat.agent_switched events as Switch rows, keyed by the thread's latest
    user message before the switch (the message that was switched on)."""
    out: list[Switch] = []
    for ev in _branch_events(session, branch_id, "chat.agent_switched"):
        from_agent = (ev.after or {}).get("from")
        message = session.exec(
            select(Message)
            .where(Message.thread_id == ev.entity_id)
            .where(Message.role == "user")
            .where(col(Message.id) < ev.id)  # ULIDs are ordered (core/ids.new_id)
            .order_by(col(Message.id).desc())
        ).first()
        if message is not None and from_agent:
            out.append(Switch(key_of(message.text), str(from_agent), ev.timestamp, ev.entity_id))
    return out


def recall(session: Session, branch_id: str, now: dt.datetime) -> dict[str, str]:
    """The branch's learned keys (key to agent id) by the rules of `learned`. Reads only;
    sync, so call it through asyncio.to_thread (rule 12)."""
    # ponytail: a scan of the branch's route events per message; cache or index when a branch
    # passes thousands of taps.
    taps = [
        Tap(str(a["key"]), str(a["agent_id"]), ev.timestamp, ev.entity_id, ev.id)
        for ev in _branch_events(session, branch_id, CHOSEN)
        if (a := ev.after or {}).get("key") and a.get("agent_id")
    ]
    forgotten: dict[str, dt.datetime] = {}
    for ev in _branch_events(session, branch_id, FORGOTTEN):
        key = str((ev.after or {}).get("key"))
        forgotten[key] = max(forgotten.get(key, ev.timestamp), ev.timestamp)
    return learned(taps, _switches(session, branch_id), forgotten, now)
