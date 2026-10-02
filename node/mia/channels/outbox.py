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
from sqlmodel import Session, col, or_, select

from mia.channels import registry
from mia.channels.base import ChannelPayload, DeliveryResult, TemplateCall
from mia.channels.transport import sending
from mia.core import events, store
from mia.core.db import session_scope
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


def _lease(now: dt.datetime) -> list[_Lease]:
    with session_scope() as session:
        rows = session.exec(
            select(ChannelOutbox)
            .where(ChannelOutbox.status == "queued")
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
        elif result.error_code == OUTSIDE_WINDOW and row.payload.get("kind") != "template":
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
            kind=row.kind,
            payload=notice.body,
            idempotency_key=f"{row.idempotency_key}:notice",
        ),
        actor,
        action="channel.queued",
    )


async def send_due(now: dt.datetime) -> int:
    """Send every due queued row once. Returns how many were sent successfully."""
    sent = 0
    for lease in await asyncio.to_thread(_lease, now):
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


def release_held(session: Session, identity: ChannelIdentity) -> int:
    """Queue the messages held for this identity (the person wrote, so the window is open)."""
    rows = session.exec(
        select(ChannelOutbox)
        .where(ChannelOutbox.person_id == identity.person_id)
        .where(ChannelOutbox.channel == identity.channel)
        .where(ChannelOutbox.status == "held")
        .order_by(col(ChannelOutbox.id))
    ).all()
    for row in rows:
        store.update(
            session,
            row,
            {"status": "queued", "send_after": None},
            outbox_actor(row.branch_id),
            action="channel.released",
        )
    return len(rows)
