"""Inbound channel messages: link unknown addresses, run chat turns for linked people.

Guarantees: an unlinked address never reaches an agent and gets only the public reply; a
linked person's message runs the same chat turn as the app (RBAC, approvals, egress); a failed
turn is never retried (it could act twice) and the person gets one apology; DB work runs in
worker threads and nothing holds the write lock across the model call.
"""

import asyncio
import datetime as dt
import logging

from pydantic import BaseModel
from sqlalchemy import text as sql
from sqlmodel import Session, col, select

from mia.agents.dispatcher.agent import MANIFEST, get_agent
from mia.channels import linking, outbox
from mia.channels.base import InboundMessage
from mia.channels.service import deliver
from mia.chat.blocks import ChatReply, TextBlock
from mia.chat.service import run_turn
from mia.core import store
from mia.core.db import get_engine, session_scope, utcnow
from mia.core.models import (
    Actor,
    ChannelIdentity,
    ChannelInbound,
    Person,
    Principal,
    Thread,
)
from mia.i18n import SUPPORTED, t

log = logging.getLogger(__name__)


class _Step(BaseModel):
    """What to do after the sync part of handling one inbound message."""

    model_config = {"arbitrary_types_allowed": True}

    direct: list[str] = []  # texts to send straight to an unlinked address
    person: Person | None = None
    text: str | None = None  # run a chat turn with this text
    thread_id: str | None = None


SHOW_LABELS = {t("channel.show", lang).casefold() for lang in SUPPORTED}


def _both(key: str, **params: str) -> str:
    return t(key, "fi", **params) + "\n\n" + t(key, "en", **params)


def _begin(session: Session, inbound_id: str, now: dt.datetime) -> _Step | None:
    # Claim the row under the write lock, so two handlers (a webhook background task and the
    # ticker's retry) never both run it: only `pending` rows are claimed, and only once.
    session.execute(sql("UPDATE channel_inbound SET id = id WHERE 0"))
    row = session.get(ChannelInbound, inbound_id)
    if row is None or row.status != "pending":
        return None
    _finish(session, row, "processing")
    msg = InboundMessage.model_validate(row.body)
    identity = linking.identity_for(session, row.channel, row.address)
    if identity is None:
        code = linking.parse_link_text(msg.text)
        if code is None:
            _finish(session, row, "ignored")
            return _Step(direct=[_both("channel.not_linked")])
        result = linking.redeem(session, row.channel, row.address, code, now)
        if result.status != "linked" or result.person is None:
            _finish(session, row, "done")
            return _Step(direct=[_both(f"channel.code_{result.status}")])
        person = result.person
        identity = linking.identity_for(session, row.channel, row.address)
        assert identity is not None
        _touch(session, row, identity, person, now)
        welcome = t("channel.linked", person.language, name=person.name.split()[0])
        deliver(
            session, person, [TextBlock(text=welcome)], Actor.person(person), urgent=True, now=now
        )
        _finish(session, row, "done")
        return _Step(person=person)
    linked = session.get(Person, identity.person_id)
    if linked is None or linked.status != "active":
        _finish(session, row, "ignored")
        return _Step(direct=[_both("channel.not_linked")])
    person = linked
    _touch(session, row, identity, person, now)
    outbox.release_held(session, identity)
    if msg.button and msg.button.strip().casefold() in SHOW_LABELS:
        _finish(session, row, "done")  # the new-message notice's button only releases held
        return _Step(person=person)
    text = (msg.button or msg.text).strip()
    if not text:
        reply = t("channel.text_only", person.language)
        deliver(
            session, person, [TextBlock(text=reply)], Actor.person(person), urgent=True, now=now
        )
        _finish(session, row, "done")
        return _Step(person=person)
    thread = session.exec(
        select(Thread)
        .where(Thread.person_id == person.id)
        .where(Thread.agent_id == MANIFEST.id)
        .order_by(col(Thread.id).desc())
    ).first()
    return _Step(person=person, text=text, thread_id=thread.id if thread else None)


def _touch(
    session: Session,
    row: ChannelInbound,
    identity: ChannelIdentity,
    person: Person,
    now: dt.datetime,
) -> None:
    actor = Actor.person(person)
    store.update(session, identity, {"last_inbound_at": now}, actor, action="channel.inbound")
    store.update(
        session,
        row,
        {"person_id": person.id, "branch_id": person.branch_id},
        actor,
        action="channel.matched",
    )


def _finish(session: Session, row: ChannelInbound, status: str, error: str | None = None) -> None:
    actor = Actor(
        principal=Principal(type="system", id=f"channel:{row.channel}"),
        branch_id=row.branch_id or "",
    )
    store.update(
        session, row, {"status": status, "error": error}, actor, action=f"channel.inbound_{status}"
    )


def _after_turn(session: Session, inbound_id: str, person: Person, reply: ChatReply) -> None:
    deliver(
        session,
        person,
        list(reply.blocks),
        Actor.person(person),
        urgent=True,
        source_id=reply.message_id,
    )
    row = session.get(ChannelInbound, inbound_id)
    if row is not None:
        _finish(session, row, "done")


def _fail(inbound_id: str, error: str) -> tuple[str, str, str | None]:
    """Mark the row failed and queue one apology. Returns (channel, address, direct text)."""
    with session_scope() as session:
        row = session.get(ChannelInbound, inbound_id)
        if row is None:
            return "", "", None
        _finish(session, row, "failed", error[:500])
        person = session.get(Person, row.person_id) if row.person_id else None
        if person is None:
            return row.channel, row.address, _both("channel.error")
        sorry = t("channel.error", person.language)
        deliver(session, person, [TextBlock(text=sorry)], Actor.person(person), urgent=True)
        return row.channel, row.address, None


async def handle_inbound(inbound_id: str) -> None:
    """Handle one stored inbound message: link, reply, or run a chat turn. Never retried after
    an error (an agent turn could act twice); the person gets one apology instead."""
    session = Session(get_engine(), expire_on_commit=False)
    try:
        step = await asyncio.to_thread(_begin, session, inbound_id, utcnow())
        await asyncio.to_thread(session.commit)
        if step is not None and step.text is not None and step.person is not None:
            agent = get_agent()
            reply = await run_turn(session, agent, step.person, step.text, step.thread_id)
            await asyncio.to_thread(_after_turn, session, inbound_id, step.person, reply)
            await asyncio.to_thread(session.commit)
        if step is not None:
            row = await asyncio.to_thread(session.get, ChannelInbound, inbound_id)
            for text in step.direct:
                if row is not None:
                    await outbox.send_direct(row.channel, row.address, text)
    except Exception as exc:  # noqa: BLE001 - every failure must reach the person once
        await asyncio.to_thread(session.rollback)
        channel, address, direct = await asyncio.to_thread(
            _fail, inbound_id, f"{type(exc).__name__}: {exc}"
        )
        if direct and channel:
            await outbox.send_direct(channel, address, direct)
    finally:
        await asyncio.to_thread(session.close)
    try:
        await outbox.send_due(utcnow())
    except Exception:
        log.exception("sending the outbox after an inbound message failed")


def pending_inbound(older_than: dt.datetime) -> list[str]:
    """Ids of inbound rows still pending since before `older_than` (lost to a restart)."""
    older_than = older_than.astimezone(dt.UTC)  # stored times are UTC; SQL compares strings
    with session_scope() as session:
        rows = session.exec(
            select(ChannelInbound)
            .where(ChannelInbound.status == "pending")
            .where(col(ChannelInbound.created_at) < older_than)
            .order_by(col(ChannelInbound.id))
        ).all()
        return [r.id for r in rows]
