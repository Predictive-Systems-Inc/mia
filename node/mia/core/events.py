"""Append-only events log with a SHA-256 hash chain.

Guarantees: rows are only ever inserted; the ORM refuses to flush updates or deletes of Event
rows and SQLite triggers abort UPDATE and DELETE statements on the table. Each hash covers the
previous hash plus the canonical JSON of the row, so any edit breaks verify_chain().
"""

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import DDL, event, text
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Session, SQLModel, col, select

from mia.core.models import Actor, Event

GENESIS_HASH = "0" * 64

TRIGGER_SQL = (
    (
        "CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events "
        "BEGIN SELECT RAISE(ABORT, 'events are append-only'); END"
    ),
    (
        "CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events "
        "BEGIN SELECT RAISE(ABORT, 'events are append-only'); END"
    ),
)

for _sql in TRIGGER_SQL:
    event.listen(Event.metadata.tables["events"], "after_create", DDL(_sql))  # type: ignore[no-untyped-call]


class AppendOnlyViolation(RuntimeError):
    """Raised when code tries to update or delete an event row."""


@event.listens_for(OrmSession, "before_flush")
def _refuse_event_changes(session: OrmSession, _ctx: Any, _instances: Any) -> None:
    for obj in list(session.dirty) + list(session.deleted):
        if isinstance(obj, Event):
            raise AppendOnlyViolation("events are append-only; never update or delete them")


def _payload(ev: Event) -> str:
    data = ev.model_dump(mode="json", exclude={"hash", "prev_hash"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, ev: Event) -> str:
    """sha256(prev_hash + canonical payload)."""
    return hashlib.sha256((prev_hash + _payload(ev)).encode()).hexdigest()


def write_lock(session: Session) -> None:
    """Take SQLite's write lock now (rule 11). pysqlite runs SELECTs outside a transaction
    until the first write, so code that reads a value and writes based on it must lock first.
    A zero-row UPDATE starts the write transaction (waiting up to busy_timeout), changes
    nothing, and keeps the events table append-only."""
    session.execute(text("UPDATE events SET id = id WHERE 0"))


def _last_hash(session: Session) -> str:
    write_lock(session)  # two writers could otherwise read the same hash and fork the chain
    last = session.exec(select(Event.hash).order_by(col(Event.id).desc()).limit(1)).first()
    return last or GENESIS_HASH


REDACTED = "<redacted>"

PH_MOBILE = re.compile(r"639\d{9}")  # E.164 digits without the plus
DIGIT_RUN = re.compile(r"\d+")
PHONE_GAP = re.compile(r"[\s().-]+")  # what may stand between the digit groups of a number
MAX_GROUPS = 12  # a mobile has at most 12 digits, so at most 12 digit groups


def ph_mobile(text: str) -> str | None:
    """A Philippine mobile number as E.164 digits without the plus (639171234567) from
    09171234567, +63 917 123 4567, 639171234567 or 9171234567; None for any other shape or a
    character other than digits, spaces, + . - ( ). The one normaliser of the node."""
    if re.search(r"[^\d\s+().-]", text):
        return None
    digits = re.sub(r"\D", "", text)
    if digits.startswith("09"):
        digits = "63" + digits[1:]
    elif digits.startswith("9"):
        digits = "63" + digits
    return digits if PH_MOBILE.fullmatch(digits) else None


def _wordy(text: str, i: int) -> bool:
    return 0 <= i < len(text) and (text[i].isalpha() or text[i] == "_")


def phone_candidates(text: str) -> list[tuple[int, int]]:
    """The (start, end) spans of every Philippine mobile number in the text: runs of digit
    groups with only spaces . - ( ) between them (a group touching a letter, as in an id, is
    no part of one), cut from the left to the longest stretch ph_mobile accepts, a leading + or
    ( included. Whatever ph_mobile accepts is found; amounts, dates and landlines are not."""
    runs: list[list[tuple[int, int]]] = []
    for m in DIGIT_RUN.finditer(text):
        if _wordy(text, m.start() - 1) or _wordy(text, m.end()):
            continue
        if runs and PHONE_GAP.fullmatch(text[runs[-1][-1][1] : m.start()]):
            runs[-1].append(m.span())
        else:
            runs.append([m.span()])
    spans: list[tuple[int, int]] = []
    for run in runs:
        i = 0
        while i < len(run):
            for j in range(min(len(run), i + MAX_GROUPS) - 1, i - 1, -1):
                start, end = run[i][0], run[j][1]
                while start > 0 and text[start - 1] in "+(":
                    start -= 1
                if ph_mobile(text[start:end]):
                    spans.append((start, end))
                    i = j
                    break
            i += 1
    return spans


def mask_phones(text: str, keep_last: int = 4) -> str:
    """The text with every phone_candidates span replaced by "<number ...4567>" (its last
    `keep_last` digits), or by "<number>" with keep_last=0; without one it is unchanged."""
    for start, end in reversed(phone_candidates(text)):
        last = re.sub(r"\D", "", text[start:end])[-keep_last:] if keep_last > 0 else ""
        shown = f"<number ...{last}>" if last else "<number>"
        text = text[:start] + shown + text[end:]
    return text


def _masked(value: Any) -> Any:
    if isinstance(value, str):
        return mask_phones(value)
    if isinstance(value, list):
        return [_masked(v) for v in value]
    if isinstance(value, dict):
        return {k: _masked(v) for k, v in value.items()}
    return value


def snapshot(row: SQLModel | None, redact: Iterable[str] = ()) -> dict[str, Any] | None:
    """JSON-safe copy of a row for before/after values. Fields named in the model's
    `__redact__` and in `redact` are replaced by "<redacted>" so secrets never enter events,
    and a mobile number in any text is masked (mask_phones): the chain is never rewritable."""
    if row is None:
        return None
    data = row.model_dump(mode="json")
    hidden = set(getattr(row, "__redact__", ())) | set(redact)
    return {k: (REDACTED if k in hidden and v is not None else _masked(v)) for k, v in data.items()}


def emit(
    session: Session,
    action: str,
    entity: SQLModel | tuple[str, str],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: Actor,
    *,
    tool_call_id: str | None = None,
    approval_id: str | None = None,
) -> Event:
    """Append one event, chained to the previous one, in the caller's transaction."""
    if isinstance(entity, tuple):
        entity_type, entity_id = entity
    else:
        entity_type = str(getattr(entity, "__tablename__", type(entity).__name__.lower()))
        entity_id = str(getattr(entity, "id", ""))
    ev = Event(
        branch_id=actor.branch_id,
        actor_type=actor.principal.type,
        actor_id=actor.principal.id,
        on_behalf_of=actor.on_behalf_of.id if actor.on_behalf_of else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        tool_call_id=tool_call_id,
        approval_id=approval_id,
        prev_hash="",
        hash="",
    )
    ev.prev_hash = _last_hash(session)
    ev.hash = compute_hash(ev.prev_hash, ev)
    session.add(ev)
    session.flush()
    return ev


def verify_chain(session: Session) -> bool:
    """True when every event links to its predecessor and its hash matches its content."""
    prev = GENESIS_HASH
    for ev in session.exec(select(Event).order_by(col(Event.id))):
        if ev.prev_hash != prev or compute_hash(prev, ev) != ev.hash:
            return False
        prev = ev.hash
    return True
