"""Turns that wait while Jev is unreachable (spec 2026-10-18, Jev unreachable).

A deferred turn is an event, not a row: `turn.deferred` opens it, `turn.resumed` closes it;
a worker holds it between `turn.claimed` and the close (or `turn.released`).
Each tick retries open turns oldest first, one at a time, and stops the round at the first
that still cannot reach Jev. After MAX_WAIT a turn expires to a question. The developer hears
when an outage starts and ends, never what anyone wrote.
ponytail: open turns are found by scanning events; an index table if the queue ever grows.
"""

import asyncio
import datetime as dt
import logging
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.chat.blocks import ChatReply, TextBlock
from mia.chat.channels import notify
from mia.chat.replies import reply_text
from mia.core import events
from mia.core.db import get_engine, utcnow
from mia.core.models import Actor, Branch, Event, Message, Person, Thread
from mia.i18n import t
from mia.settings import get_settings

log = logging.getLogger(__name__)
MAX_WAIT = dt.timedelta(hours=2)
DEFERRED, RESUMED = "turn.deferred", "turn.resumed"
CLAIMED, RELEASED = "turn.claimed", "turn.released"
STARTED, ENDED = "jev.outage_started", "jev.outage_ended"
Stage = Literal["route", "agent"]


def open_turns(session: Session, thread: Thread | None = None) -> list[Event]:
    """Deferred turns with no turn.resumed, oldest first (of one thread, or all)."""
    stmt = select(Event).where(Event.action == DEFERRED).order_by(col(Event.id))
    if thread is not None:
        stmt = stmt.where(Event.entity_id == thread.id)
    closed = {
        (e.after or {}).get("message_id")
        for e in session.exec(select(Event).where(Event.action == RESUMED))
    }
    return [e for e in session.exec(stmt) if (e.after or {}).get("message_id") not in closed]


def waiting(session: Session, thread: Thread) -> bool:
    """The thread has an open deferral: its new messages queue behind it."""
    return bool(open_turns(session, thread))


def _outage_open(session: Session) -> Event | None:
    last = session.exec(
        select(Event).where(col(Event.action).in_([STARTED, ENDED])).order_by(col(Event.id).desc())
    ).first()
    return last if last is not None and last.action == STARTED else None


def _tell_developer(session: Session, key: str, agent_id: str, **params: object) -> None:
    """One urgent notice to MIA_DEVELOPER_PERSON_ID (the log only when unset or unknown).
    `{time}` in the text is now, in the developer's branch time zone."""
    person_id = get_settings().MIA_DEVELOPER_PERSON_ID
    dev = session.get(Person, person_id) if person_id else None
    if dev is None:
        log.warning("jev outage notice %s (no MIA_DEVELOPER_PERSON_ID): %s", key, params)
        return
    branch = session.get(Branch, dev.branch_id)
    now = utcnow().astimezone(ZoneInfo(branch.timezone if branch else "UTC"))
    text = t(key, dev.language, time=f"{now:%H:%M}", **params)
    notify(session, dev, [TextBlock(text=text)], Actor.system(dev.branch_id), agent_id, urgent=True)


def defer(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    message_id: str,
    stage: Stage,
    agent_id: str,
) -> ChatReply:
    """Record the deferral (the caller commits) with `answer_id`, the message whose text the
    turn answers (deps.answer_id after a tap, else message_id); the busy reply once per waiting
    stretch of the thread (its id in the event, so it never counts as Mia's last message),
    otherwise an empty reply (nothing stored). The first deferral after a success starts an
    outage and tells the developer; an outage drained by expiry alone is closed silently
    first."""
    waiting_now = open_turns(session)
    first_in_thread = not any(e.entity_id == thread.id for e in waiting_now)
    started = _outage_open(session)
    if started is not None and not waiting_now and not _answered_since(session, started):
        closed = _closed_since(session, started)
        after = {"count": len(closed), "expired_only": True}
        events.emit(session, ENDED, ("jev", "typesafe"), None, after, deps.actor)
        started = None
    busy = (
        reply_text(session, deps, thread, t("reply.busy", deps.lang)) if first_in_thread else None
    )
    events.emit(
        session,
        DEFERRED,
        ("thread", thread.id),
        None,
        {
            "message_id": message_id,
            "answer_id": deps.answer_id or message_id,
            "person_id": deps.person.id,
            "stage": stage,
            "agent_id": agent_id,
            "busy_message_id": busy.message_id if busy else None,
        },
        deps.actor,
    )
    if started is None:
        events.emit(session, STARTED, ("jev", "typesafe"), None, {}, deps.actor)
        _tell_developer(session, "dev.jev_down", agent_id)
    return busy or ChatReply(
        thread_id=thread.id, message_id=message_id, agent_id=agent_id, blocks=[]
    )


def _closed_since(session: Session, started: Event) -> list[Event]:
    """turn.resumed events after the outage started, oldest first."""
    stmt = select(Event).where(Event.action == RESUMED).order_by(col(Event.id))
    return [e for e in session.exec(stmt) if e.id > started.id]


def _answered_since(session: Session, started: Event) -> bool:
    """A turn resumed with an answer since the outage started (Jev is back, not just expired)."""
    return any(
        not (e.after or {}).get("expired") and not (e.after or {}).get("failed")
        for e in _closed_since(session, started)
    )


def _end_outage(session: Session) -> None:
    """When no turn waits and one was answered since the outage started: close it (the event
    and one notice with the count and the longest single turn's wait), and commit."""
    started = _outage_open(session)
    if started is None or open_turns(session) or not _answered_since(session, started):
        return
    closed = _closed_since(session, started)
    waits = []
    for e in closed:
        opened = session.get(Event, (e.after or {}).get("deferred_event_id"))
        waits.append(e.timestamp - opened.timestamp if opened else dt.timedelta())
    longest = max(waits, default=dt.timedelta())
    events.emit(
        session,
        ENDED,
        ("jev", "typesafe"),
        None,
        {"count": len(closed), "longest_wait_seconds": int(longest.total_seconds())},
        Actor.system(started.branch_id),
    )
    last = session.get(Event, (closed[-1].after or {})["deferred_event_id"])
    agent_id = str((last.after or {}).get("agent_id", "")) if last else ""
    minutes = int(longest.total_seconds() // 60)
    _tell_developer(session, "dev.jev_back", agent_id, count=len(closed), minutes=minutes)
    session.commit()


def _due(session: Session) -> list[dict[str, Any]]:
    """The open turns as plain values (event id, thread, branch, time and its `after`), oldest
    first; ends the read so no transaction stays open."""
    rows = [
        {"id": e.id, "thread_id": e.entity_id, "branch_id": e.branch_id, "at": e.timestamp}
        | {"after": dict(e.after or {})}
        for e in open_turns(session)
    ]
    session.commit()
    return rows


def _load(
    session: Session, due: dict[str, Any]
) -> tuple[Message | None, Thread | None, Person | None]:
    """The message to answer (answer_id), its thread and the person; None for what is gone."""
    after = due["after"]
    message = session.get(Message, after.get("answer_id") or after["message_id"])
    thread = session.get(Thread, due["thread_id"])
    person = session.get(Person, after["person_id"])
    return message, thread, person


def _fail(session: Session, due: dict[str, Any], person: Person, thread: Thread) -> None:
    """Roll back a resumed turn that failed; tell the person it is unavailable (as a
    notification), never failing the close itself."""
    from mia.chat import service  # service imports this module

    session.rollback()
    try:
        service.resumed_reply(session, person, thread, due["after"]["agent_id"])
    except Exception as exc:  # noqa: BLE001 - the turn closes as failed whatever happens
        session.rollback()
        log.error("the unavailable reply for turn %s failed: %s", due["id"], type(exc).__name__)


def _claim(
    session: Session, due: dict[str, Any], now: dt.datetime
) -> Literal["ok", "closed", "busy"]:
    """Claim the turn for this worker under the write lock and commit: "closed" when it was
    resumed meanwhile, "busy" while another worker's claim holds (a claim older than MAX_WAIT
    is stale and taken over), else "ok" with a turn.claimed event."""
    events.write_lock(session)
    rows = session.exec(
        select(Event)
        .where(Event.entity_id == due["thread_id"])
        .where(col(Event.action).in_([RESUMED, CLAIMED, RELEASED]))
        .order_by(col(Event.id))
    ).all()
    message_id = due["after"]["message_id"]
    if any(e.action == RESUMED and (e.after or {}).get("message_id") == message_id for e in rows):
        session.rollback()
        return "closed"
    mine = [e for e in rows if (e.after or {}).get("deferred_event_id") == due["id"]]
    if mine and mine[-1].action == CLAIMED and now - mine[-1].timestamp <= MAX_WAIT:
        session.rollback()
        return "busy"
    after = {"message_id": message_id, "deferred_event_id": due["id"]}
    events.emit(
        session, CLAIMED, ("thread", due["thread_id"]), None, after, Actor.system(due["branch_id"])
    )
    session.commit()
    return "ok"


def _release(session: Session, due: dict[str, Any]) -> None:
    """Give the claim back (Jev still unreachable) so the next tick retries the turn."""
    session.rollback()
    after = {"message_id": due["after"]["message_id"], "deferred_event_id": due["id"]}
    actor = Actor.system(due["branch_id"])
    events.emit(session, RELEASED, ("thread", due["thread_id"]), None, after, actor)
    session.commit()


def _close(session: Session, due: dict[str, Any], closing: dict[str, Any]) -> None:
    """turn.resumed for the deferral, committed with the turn's reply."""
    actor = Actor.system(due["branch_id"])
    events.emit(session, RESUMED, ("thread", due["thread_id"]), None, closing, actor)
    session.commit()


async def retry_due(now: dt.datetime) -> int:
    """Resume or expire open turns oldest first; stop at the first that still cannot reach
    Jev. Each closed turn commits with its reply, so a resumed turn never runs again; an
    expired turn asks only when it is its thread's latest open one (older ones close with no
    reply, so the thread gets one question); a turn that fails otherwise is closed as failed
    with the unavailable reply. Closes the outage when none are left and at least one was
    answered since it started. Returns how many turns were closed. DB work runs in worker threads (rule 12); no transaction is open across a Jev call.
    Each turn is claimed under the write lock first (turn.claimed, committed before Jev), so
    two workers (`mia serve` and `mia tick`) never answer one turn twice; a worker that meets
    another's claim stops its round."""
    from mia.chat import service  # service imports this module
    from mia.core.jev import JevUnreachable

    done = 0
    session = Session(get_engine(), expire_on_commit=False)
    try:
        dues = await asyncio.to_thread(_due, session)
        for i, due in enumerate(dues):
            claim = await asyncio.to_thread(_claim, session, due, now)
            if claim == "busy":
                break  # another worker is running the queue, in order
            if claim == "closed":
                continue
            after = due["after"]
            message, thread, person = await asyncio.to_thread(_load, session, due)
            gone = message is None or thread is None or person is None or person.status != "active"
            expired = gone or now - due["at"] > MAX_WAIT
            # one question per thread: an expired turn with a later open one closes silently
            gone = gone or (
                expired and any(d["thread_id"] == due["thread_id"] for d in dues[i + 1 :])
            )
            closing: dict[str, Any] = {
                "message_id": after["message_id"],
                "deferred_event_id": due["id"],
                "expired": expired,
            }
            try:
                if message and thread and person and not gone:
                    await service.respond(
                        session,
                        person,
                        thread,
                        message,
                        resumed=True,
                        expire=expired,
                        stage=after["stage"],
                        agent_id=after["agent_id"],
                    )
            except JevUnreachable:
                await asyncio.to_thread(_release, session, due)
                break
            except Exception as exc:  # noqa: BLE001 - one broken turn must not hold the queue
                log.error("resuming deferred turn %s failed: %s", due["id"], type(exc).__name__)
                closing |= {"failed": True, "error": type(exc).__name__}
                assert thread is not None and person is not None  # respond ran, so they exist
                await asyncio.to_thread(_fail, session, due, person, thread)
            await asyncio.to_thread(_close, session, due, closing)
            done += 1
        await asyncio.to_thread(_end_outage, session)
    finally:
        await asyncio.to_thread(session.close)
    return done
