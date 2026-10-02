"""The outbound queue: send due rows, retry at 1, 5 and 30 minutes, then fail.

Guarantees: each row is leased (attempts and next try written and committed) before the network
call, so a crash never double-sends quickly and never holds the write lock across the network
(rule 11); DB work runs in worker threads (rule 12); every send emits `channel.sent` with a
payload hash, never content; Meta's outside-window error (131047) re-sends once as the
`mia_new_message` template and holds the original until the person replies.
"""

import asyncio
import datetime as dt
import hashlib
import json

from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, col, or_, select

from mia.channels import registry
from mia.channels.base import ChannelPayload, DeliveryResult, TemplateCall
from mia.channels.render import to_parts
from mia.channels.service import TEMPLATE_KIND
from mia.channels.transport import sending
from mia.chat.blocks import TextBlock
from mia.core import events, store
from mia.core.db import session_scope, utcnow
from mia.core.models import Actor, ChannelIdentity, ChannelOutbox, Person, Principal

BACKOFF_MINUTES = (1, 5, 30)
MAX_ATTEMPTS = len(BACKOFF_MINUTES) + 1
OUTSIDE_WINDOW = "131047"


class _Lease(BaseModel):
    id: str
    channel: str
    address: str
    body: dict[str, object]


def outbox_actor(branch_id: str) -> Actor:
    """The system actor that sends queued channel messages."""
    return Actor(principal=Principal(type="system", id="channels.outbox"), branch_id=branch_id)


def _lease(now: dt.datetime, skip: frozenset[str]) -> list[_Lease]:
    now = now.astimezone(dt.UTC)  # stored times are UTC; SQL compares them as strings
    with session_scope() as session:
        # Take the write lock before reading due rows, so two overlapping senders (ticker,
        # background tasks, `mia tick`) never lease the same row (see events._last_hash).
        session.execute(text("UPDATE channel_outbox SET id = id WHERE 0"))
        rows = session.exec(
            select(ChannelOutbox)
            .where(ChannelOutbox.status == "queued")
            .where(col(ChannelOutbox.channel).not_in(skip))
            .where(
                or_(col(ChannelOutbox.send_after).is_(None), col(ChannelOutbox.send_after) <= now)
            )
            .order_by(col(ChannelOutbox.id))
        ).all()
        leases = []
        for row in rows:
            attempts = row.attempts + 1
            wait = BACKOFF_MINUTES[min(attempts, len(BACKOFF_MINUTES)) - 1]
            store.update(
                session,
                row,
                {"attempts": attempts, "send_after": now + dt.timedelta(minutes=wait)},
                outbox_actor(row.branch_id),
                action="channel.sending",
            )
            leases.append(
                _Lease(id=row.id, channel=row.channel, address=row.address, body=row.payload)
            )
        return leases


def _record(lease: _Lease, result: DeliveryResult) -> None:
    with session_scope() as session:
        row = session.get(ChannelOutbox, lease.id)
        if row is None:
            return
        actor = outbox_actor(row.branch_id)
        if result.ok:
            store.update(
                session,
                row,
                {
                    "status": "sent",
                    "channel_message_id": result.channel_message_id,
                    "error_code": None,
                },
                actor,
                action="channel.status",
            )
            digest = hashlib.sha256(json.dumps(lease.body, sort_keys=True).encode()).hexdigest()
            after = {
                "channel": row.channel,
                "person_id": row.person_id,
                "payload_hash": digest,
                "channel_message_id": result.channel_message_id,
            }
            events.emit(session, "channel.sent", row, None, after, actor)
        elif result.error_code == OUTSIDE_WINDOW and row.kind != TEMPLATE_KIND:
            _fall_back_to_notice(session, row, actor)
        elif row.attempts >= MAX_ATTEMPTS:
            store.update(
                session,
                row,
                {"status": "failed", "error_code": result.error_code},
                actor,
                action="channel.failed",
            )
        else:
            store.update(
                session, row, {"error_code": result.error_code}, actor, action="channel.retry"
            )


def _fall_back_to_notice(session: Session, row: ChannelOutbox, actor: Actor) -> None:
    person = session.get(Person, row.person_id)
    adapter = registry.get(row.channel)
    call = TemplateCall(name="mia_new_message", lang=person.language if person else "fi")
    notice = adapter.render_template(row.address, call)
    store.update(
        session,
        row,
        {"status": "held", "attempts": 0, "send_after": None},
        actor,
        action="channel.held",
    )
    store.insert(
        session,
        ChannelOutbox(
            branch_id=row.branch_id,
            person_id=row.person_id,
            channel=row.channel,
            address=row.address,
            kind=TEMPLATE_KIND,
            payload=notice.body,
            idempotency_key=f"{row.idempotency_key}:notice",
        ),
        actor,
        action="channel.queued",
    )


async def send_due(now: dt.datetime, skip: frozenset[str] = frozenset()) -> int:
    """Send every due queued row once, except on channels in `skip`. Returns how many were sent."""
    sent = 0
    for lease in await asyncio.to_thread(_lease, now, skip):
        try:
            adapter = registry.get(lease.channel)
        except KeyError:
            result = DeliveryResult(ok=False, error_code="no_adapter")
        else:
            payload = ChannelPayload(channel=lease.channel, address=lease.address, body=lease.body)
            with sending(lease.id):
                result = await adapter.send(payload)
        await asyncio.to_thread(_record, lease, result)
        sent += result.ok
    return sent


HELD_FOR = dt.timedelta(hours=24)


def release_held(session: Session, identity: ChannelIdentity) -> int:
    """Queue the messages held for this identity (the person wrote, so the window is open).

    Messages held longer than a day are stale (a cover ask for a past visit) and expire instead.
    Returns how many were queued.
    """
    cutoff = utcnow() - HELD_FOR
    rows = session.exec(
        select(ChannelOutbox)
        .where(ChannelOutbox.person_id == identity.person_id)
        .where(ChannelOutbox.channel == identity.channel)
        .where(ChannelOutbox.status == "held")
        .order_by(col(ChannelOutbox.id))
    ).all()
    queued = 0
    for row in rows:
        actor = outbox_actor(row.branch_id)
        if row.created_at < cutoff:
            store.update(session, row, {"status": "expired"}, actor, action="channel.expired")
            continue
        changes = {"status": "queued", "send_after": None}
        store.update(session, row, changes, actor, action="channel.released")
        queued += 1
    return queued


async def send_direct(channel: str, address: str, text: str) -> bool:
    """Reply to an address that is not linked to anyone (no person, so no outbox row).

    Used only for answers to a message the address just sent, so the channel's window is open.
    Logged as `channel.sent` with a payload hash, like outbox sends.
    """
    adapter = registry.get(channel)
    parts = to_parts([TextBlock(text=text)], adapter.capabilities, "fi")
    ok = True
    for payload in adapter.render(address, parts):
        with sending(f"direct:{address}"):
            result = await adapter.send(payload)
        ok = ok and result.ok
        await asyncio.to_thread(_log_direct, channel, payload.body, result)
    return ok


def _log_direct(channel: str, body: dict[str, object], result: DeliveryResult) -> None:
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    actor = Actor(principal=Principal(type="system", id=f"channel:{channel}"), branch_id="")
    after = {"channel": channel, "payload_hash": digest, "ok": result.ok}
    with session_scope() as session:
        events.emit(session, "channel.sent", ("channel", channel), None, after, actor)


def apply_status(
    session: Session, channel: str, message_id: str, status: str, error: str | None
) -> None:
    """Record a delivery status reported by the channel for one sent row."""
    row = session.exec(
        select(ChannelOutbox)
        .where(ChannelOutbox.channel == channel)
        .where(ChannelOutbox.channel_message_id == message_id)
    ).first()
    if row is None:
        return
    if row.status in ("held", "expired"):
        return  # already handled; Meta redelivers status webhooks
    actor = outbox_actor(row.branch_id)
    if status == "failed" and error == OUTSIDE_WINDOW and row.kind != TEMPLATE_KIND:
        _fall_back_to_notice(session, row, actor)
        return
    changes: dict[str, object] = {"status": status}
    if error:
        changes["error_code"] = error
    store.update(session, row, changes, actor, action="channel.status")
