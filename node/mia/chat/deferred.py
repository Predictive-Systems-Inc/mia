"""Turns that wait while Jev is unreachable (spec 2026-10-18, Jev unreachable).

A deferred turn is an event, not a row: `turn.deferred` opens it, `turn.resumed` closes it.
Each tick retries open turns oldest first, one at a time, and stops the round at the first
that still cannot reach Jev. After MAX_WAIT a turn expires to a question. The developer hears
when an outage starts and ends, never what anyone wrote.
ponytail: open turns are found by scanning events; an index table if the queue ever grows.
"""

import asyncio
import datetime as dt
import logging
from typing import Literal
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.chat.blocks import ChatReply, TextBlock
from mia.chat.channels import notify
from mia.chat.replies import reply_text
from mia.core import events
from mia.core.db import session_scope, utcnow
from mia.core.models import Actor, Branch, Event, Message, Person, Thread
from mia.i18n import t
from mia.settings import get_settings

log = logging.getLogger(__name__)
MAX_WAIT = dt.timedelta(hours=2)
DEFERRED, RESUMED = "turn.deferred", "turn.resumed"
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
    """Record the deferral (the caller commits); the busy reply once per waiting stretch of the
    thread, otherwise an empty reply (nothing stored). The first deferral after a success
    starts an outage and tells the developer."""
    first_in_thread = not waiting(session, thread)
    events.emit(
        session,
        DEFERRED,
        ("thread", thread.id),
        None,
        {
            "message_id": message_id,
            "person_id": deps.person.id,
            "stage": stage,
            "agent_id": agent_id,
        },
        deps.actor,
    )
    if _outage_open(session) is None:
        events.emit(session, STARTED, ("jev", "typesafe"), None, {}, deps.actor)
        _tell_developer(session, "dev.jev_down", agent_id)
    if first_in_thread:
        return reply_text(session, deps, thread, t("reply.busy", deps.lang))
    return ChatReply(thread_id=thread.id, message_id=message_id, agent_id=agent_id, blocks=[])


def _answered_since(session: Session, started: Event) -> bool:
    """A turn resumed with an answer since the outage started (Jev is back, not just expired)."""
    return any(
        e.id > started.id
        and not (e.after or {}).get("expired")
        and not (e.after or {}).get("failed")
        for e in session.exec(select(Event).where(Event.action == RESUMED))
    )


def _end_outage(session: Session, started: Event) -> None:
    """Close the outage: the event and one notice with the count and the longest wait."""
    closed = [
        e for e in session.exec(select(Event).where(Event.action == RESUMED)) if e.id > started.id
    ]
    longest = max((e.timestamp - started.timestamp for e in closed), default=dt.timedelta())
    events.emit(
        session,
        ENDED,
        ("jev", "typesafe"),
        None,
        {"count": len(closed), "longest_wait_seconds": int(longest.total_seconds())},
        Actor.system(started.branch_id),
    )
    last = session.get(Event, (closed[-1].after or {})["deferred_event_id"]) if closed else None
    agent_id = str((last.after or {}).get("agent_id", "")) if last else ""
    minutes = int(longest.total_seconds() // 60)
    _tell_developer(session, "dev.jev_back", agent_id, count=len(closed), minutes=minutes)


async def retry_due(now: dt.datetime) -> int:
    """Resume or expire open turns oldest first; stop at the first that still cannot reach
    Jev. Each closed turn commits with its reply, so a resumed turn never runs again; a turn
    that fails otherwise is closed as failed with the unavailable reply. Closes the outage when
    none are left and at least one was answered since it started. Returns how many turns were
    closed.
    ponytail: one tick worker per node, so no lock is held across the Jev call (rule 11); two
    workers would need a claim event first."""
    from mia.chat import service  # service imports this module
    from mia.core.jev import JevUnreachable

    done = 0
    with session_scope() as session:
        for ev in open_turns(session):
            after = ev.after or {}
            message = session.get(Message, after["message_id"])
            thread = session.get(Thread, ev.entity_id)
            person = session.get(Person, after["person_id"])
            gone = message is None or thread is None or person is None or person.status != "active"
            expired = gone or now - ev.timestamp > MAX_WAIT
            closing = {"message_id": after["message_id"], "deferred_event_id": ev.id}
            closing["expired"] = expired
            try:
                if message is not None and thread is not None and person is not None and not gone:
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
                session.rollback()
                break
            except Exception as exc:  # noqa: BLE001 - one broken turn must not hold the queue
                session.rollback()
                log.error("resuming deferred turn %s failed: %s", ev.id, type(exc).__name__)
                closing |= {"failed": True, "error": type(exc).__name__}
                assert person is not None and thread is not None  # respond ran, so they exist
                await asyncio.to_thread(
                    service.resumed_reply, session, person, thread, after["agent_id"]
                )
            events.emit(
                session,
                RESUMED,
                ("thread", ev.entity_id),
                None,
                closing,
                Actor.system(ev.branch_id),
            )
            session.commit()
            done += 1
        started = _outage_open(session)
        if started is not None and not open_turns(session) and _answered_since(session, started):
            _end_outage(session, started)
            session.commit()
    return done
