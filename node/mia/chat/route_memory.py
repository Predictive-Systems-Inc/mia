"""What people chose when Mia asked "Is this about": exact repeats are routed by code before
any Jev call (spec 2026-10-18-router-follow-up, decision 4b). This module is pure; the chat
reads the events and applies the result. Only agent ids are learned, never text as a rule
(rule 8)."""

import datetime as dt
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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
