"""Turn clarification choices into pending candidate records on the node (spec section 8).

Reads the database and writes only to the local learning dir (D18); emits no event."""

import datetime as dt
import os
from pathlib import Path

from sqlmodel import Session, col, select

from mia.core.egress import Pseudonymiser
from mia.core.models import Event, Message
from mia.learning.schema import OTHER, Record, Review, load_records
from mia.settings import get_settings

UNDO = ("absence.cancelled", "cover.cancelled")
SENSITIVE_PREFIXES = ("conversation.privacy_", "conversation.health_")
UNDO_WINDOW = dt.timedelta(hours=1)


def _corrected(session: Session, ev: Event, original_id: str) -> bool:
    """True when the same original message was clarified again later in the thread."""
    later = session.exec(
        select(Event)
        .where(Event.action == "intent.clarified")
        .where(Event.entity_id == ev.entity_id)
        .where(col(Event.id) > ev.id)
    ).all()
    return any((e.after or {}).get("original_message_id") == original_id for e in later)


def _undone(session: Session, ev: Event) -> bool:
    """True when the same actor cancelled something within one hour of the choice.

    Events carry no thread id, so "in that thread" is approximated by the clarifying actor.
    ponytail: a cancel by a different actor (system escalation) is not seen."""
    rows = session.exec(
        select(Event)
        .where(Event.branch_id == ev.branch_id)
        .where(col(Event.action).in_(UNDO))
        .where(Event.actor_id == ev.actor_id)
        .where(Event.on_behalf_of == ev.on_behalf_of)
        .where(col(Event.id) > ev.id)
    ).all()
    return any(r.timestamp - ev.timestamp <= UNDO_WINDOW for r in rows)


def _previous_assistant_text(session: Session, message: Message) -> str:
    previous = session.exec(
        select(Message)
        .where(Message.thread_id == message.thread_id)
        .where(Message.role == "assistant")
        .where(col(Message.id) < message.id)
        .order_by(col(Message.id).desc())
    ).first()
    return previous.text if previous else ""


def _append(path: Path, records: list[Record]) -> None:
    """Appends one JSON line per record (as write_records serialises) and syncs to disk, so
    existing, possibly reviewed, lines are never rewritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write("".join(r.model_dump_json() + "\n" for r in records))
        f.flush()
        os.fsync(f.fileno())


def _route_undone(session: Session, ev: Event) -> bool:
    """True when the thread switched away from the tapped agent within UNDO_WINDOW of the tap."""
    rows = session.exec(
        select(Event)
        .where(Event.action == "chat.agent_switched")
        .where(Event.entity_id == ev.entity_id)
        .where(col(Event.id) > ev.id)
    ).all()
    agent = (ev.after or {}).get("agent_id")
    return any(
        (r.after or {}).get("from") == agent and r.timestamp - ev.timestamp <= UNDO_WINDOW
        for r in rows
    )


def _route_forgotten(session: Session, ev: Event) -> bool:
    """True when the branch forgot this message key after the tap."""
    key = (ev.after or {}).get("key")
    later = session.exec(
        select(Event)
        .where(Event.action == "chat.route_forgotten")
        .where(Event.branch_id == ev.branch_id)
        .where(col(Event.id) > ev.id)
    ).all()
    return any((e.after or {}).get("key") == key for e in later)


def _candidates(session: Session, role: str, ev: Event) -> tuple[str, str] | None:
    """(intent, original message id) when this event may become a candidate, else None."""
    after = ev.after or {}
    original_id = after.get("original_message_id")
    if role == "router":
        intent = after.get("agent_id")
        dropped = _route_undone(session, ev) or _route_forgotten(session, ev)
        return (intent, original_id) if intent and original_id and not dropped else None
    intent = after.get("intent")
    if not intent or not original_id or intent == OTHER or intent.startswith(SENSITIVE_PREFIXES):
        return None
    if _corrected(session, ev, original_id) or _undone(session, ev):
        return None
    return intent, original_id


def harvest(session: Session, role: str, branch_id: str) -> list[Record]:
    """Returns the new candidates (pending review) and appends them to candidates.jsonl.

    Guarantees: ids already in the file are not duplicated; text and context are
    pseudonymised; `other`, corrected, undone and privacy or health choices are never written.
    Role `router` reads route taps (chat.route_chosen) instead of clarifications, and drops
    taps switched away from within the hour or forgotten."""
    path = get_settings().MIA_LEARNING_DIR / role / "candidates.jsonl"
    existing = load_records(path) if path.exists() else []
    seen = {r.id for r in existing}
    pseudo = Pseudonymiser.for_branch(session, branch_id)
    found: list[Record] = []
    action, source = (
        ("chat.route_chosen", "real-route-choice")
        if role == "router"
        else ("intent.clarified", "real-clarification")
    )
    # ponytail: every event of the branch is rescanned per run (ids in the file short-circuit
    # before any query); keep a last-event cursor if a branch grows past thousands.
    for ev in session.exec(
        select(Event)
        .where(Event.action == action)
        .where(Event.branch_id == branch_id)
        .order_by(col(Event.id))
    ):
        rid = f"{role}/real/{(ev.after or {}).get('original_message_id')}"
        if rid in seen or (picked := _candidates(session, role, ev)) is None:
            continue
        intent, original_id = picked
        message = session.get(Message, original_id)
        if message is None:
            continue
        seen.add(rid)
        found.append(
            Record(
                id=rid,
                role=role,
                intent=intent,
                lang="mixed",  # placeholder: the reviewer sets the real language before approval
                text=pseudo.apply(message.text),
                context=pseudo.apply(_previous_assistant_text(session, message)),
                counterpart="unknown",
                style="informal",
                split="train",
                source=source,
                review=Review(status="pending", note=f"harvested {dt.datetime.now(dt.UTC).date()}"),
            )
        )
    if found:
        _append(path, found)
    return found
