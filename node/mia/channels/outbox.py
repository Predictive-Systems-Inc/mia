"""The outbound queue: send due rows, retry at 1, 5 and 30 minutes, then fail.

Guarantees: each row is leased (attempts and next try written and committed) before the network
call, so a crash never double-sends quickly and never holds the write lock across the network
(rule 11); DB work runs in worker threads (rule 12); every send emits `channel.sent` with a
payload HMAC, never content; Meta's outside-window error (131047) re-sends once as the
`mia_new_message` template and holds the original until the person replies.
"""

import asyncio
import datetime as dt
import json

from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, col, or_, select

from mia.channels import registry
from mia.channels.base import ChannelPayload, DeliveryResult, TemplateCall
from mia.channels.render import to_parts
from mia.channels.service import TEMPLATE_KIND
from mia.channels.transport import sending
from mia.chat.blocks import ApprovalCardBlock, Block, FileBlock, FormBlock
from mia.core import events, keys, store
from mia.core.db import session_scope, utcnow
from mia.core.models import Actor, ChannelIdentity, ChannelOutbox, Person, Principal

BACKOFF_MINUTES = (1, 5, 30)
MAX_ATTEMPTS = len(BACKOFF_MINUTES) + 1
OUTSIDE_WINDOW = "131047"
HELD_FOR = dt.timedelta(hours=24)  # held and on-demand messages are stale after this


class _Lease(BaseModel):
    id: str
    channel: str
    address: str
    body: dict[str, object]


def outbox_actor(branch_id: str) -> Actor:
    """The system actor that sends queued channel messages."""
    return Actor(principal=Principal(type="system", id="channels.outbox"), branch_id=branch_id)


def _on_demand_channels() -> list[str]:
    return [cid for cid, a in registry._adapters.items() if getattr(a, "on_demand", False)]


def _lease(now: dt.datetime, on_demand_for: str | None) -> list[_Lease]:
    now = now.astimezone(dt.UTC)  # stored times are UTC; SQL compares them as strings
    on_demand = _on_demand_channels()
    with session_scope() as session:
        # Take the write lock before reading due rows, so two overlapping senders (ticker,
        # background tasks, `mia tick`) never lease the same row (see events._last_hash).
        session.execute(text("UPDATE channel_outbox SET id = id WHERE 0"))
        rows = session.exec(
            select(ChannelOutbox)
            .where(ChannelOutbox.status == "queued")
            .where(
                or_(
                    col(ChannelOutbox.channel).not_in(on_demand),
                    col(ChannelOutbox.address) == on_demand_for,
                )
            )
            .where(
                or_(col(ChannelOutbox.send_after).is_(None), col(ChannelOutbox.send_after) <= now)
            )
            .order_by(col(ChannelOutbox.id))
        ).all()
        leases = []
        for row in rows:
            if row.channel in on_demand and row.created_at < now - HELD_FOR:
                actor = outbox_actor(row.branch_id)
                store.update(session, row, {"status": "expired"}, actor, action="channel.expired")
                continue
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
            digest = _digest(lease.body)
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


async def send_due(now: dt.datetime, on_demand_for: str | None = None) -> int:
    """Send every due queued row once. Rows of on-demand channels (the simulator) are sent only
    for the address `on_demand_for`, and expire after a day. Returns how many were sent."""
    sent = 0
    for lease in await asyncio.to_thread(_lease, now, on_demand_for):
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


async def send_direct(
    channel: str, address: str, blocks: list[Block], lang: str
) -> list[DeliveryResult]:
    """Reply to an address that is not linked to anyone (no person, so no outbox row): text,
    cards and quick replies only. Blocks that only open the app (approval cards, forms, files)
    are dropped, and nothing is rendered sensitive, so the reply never carries an app link.

    The caller keeps to the channel's window (an answer to a message the address just sent, or
    a customer reply inside the window). Logged as `channel.sent` with a payload HMAC, like
    outbox sends. Returns one result per payload sent.
    """
    adapter = registry.get(channel)
    shown: list[Block] = [
        b for b in blocks if not isinstance(b, ApprovalCardBlock | FormBlock | FileBlock)
    ]
    results = []
    for payload in adapter.render(address, to_parts(shown, adapter.capabilities, lang)):
        with sending(f"direct:{address}"):
            result = await adapter.send(payload)
        results.append(result)
        await asyncio.to_thread(_log_direct, channel, payload.body, result)
    return results


def _digest(body: dict[str, object]) -> str:
    """The payload's keyed hash (HMAC): the body holds the address, and a plain hash of a fixed
    reply text could be tried against every number of the country's form."""
    return keys.code_hmac(json.dumps(body, sort_keys=True))


def _log_direct(channel: str, body: dict[str, object], result: DeliveryResult) -> None:
    digest = _digest(body)
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
