"""Webhooks for every channel: GET for the subscription handshake, POST for messages.

POST verifies the signature on the raw body, stores each new message once (channels resend),
applies delivery statuses, commits, answers 200 at once, and handles messages afterwards.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, select

from mia.channels import outbox, registry
from mia.channels.base import ChannelAdapter, InboundMessage, StatusUpdate
from mia.channels.inbound import handle_inbound
from mia.chat.router import DbSession
from mia.core import events, store
from mia.core.models import Actor, ChannelInbound, Principal

router = APIRouter(prefix="/channels", tags=["channels"])


def get_adapter(channel_id: str) -> ChannelAdapter:
    """The registered and enabled adapter for the path's channel id, else 404."""
    if channel_id not in {a.channel_id for a in registry.enabled()}:
        raise HTTPException(404, "unknown channel")
    return registry.get(channel_id)


async def raw_body(request: Request) -> bytes:
    """The request body exactly as sent (signatures cover the raw bytes)."""
    return await request.body()


AdapterDep = Annotated[ChannelAdapter, Depends(get_adapter)]
RawBody = Annotated[bytes, Depends(raw_body)]


def _actor(channel_id: str) -> Actor:
    return Actor(principal=Principal(type="system", id=f"channel:{channel_id}"), branch_id="")


@router.get("/{channel_id}/webhook", response_class=PlainTextResponse)
def verify(adapter: AdapterDep, request: Request) -> str:
    """Echo the subscription challenge when the verify token matches."""
    challenge = adapter.verify_subscription(dict(request.query_params))
    if challenge is None:
        raise HTTPException(403, "verification failed")
    return challenge


@router.post("/{channel_id}/webhook")
def webhook(
    adapter: AdapterDep,
    request: Request,
    body: RawBody,
    session: DbSession,
    background: BackgroundTasks,
) -> dict[str, bool]:
    """Store new messages and statuses, then handle messages after the response."""
    if not adapter.verify_webhook(dict(request.headers), body):
        events.emit(
            session,
            "channel.webhook_rejected",
            ("channel", adapter.channel_id),
            None,
            None,
            _actor(adapter.channel_id),
        )
        session.commit()
        raise HTTPException(403, "bad signature")
    new_ids = []
    for item in adapter.receive(body):
        if isinstance(item, StatusUpdate):
            outbox.apply_status(
                session, item.channel, item.channel_message_id, item.status, item.error_code
            )
        elif isinstance(item, InboundMessage) and not _seen(session, item):
            row = ChannelInbound(
                channel=item.channel,
                channel_message_id=item.channel_message_id,
                address=item.address,
                body=item.model_dump(mode="json"),
            )
            new_ids.append(
                store.insert(session, row, _actor(item.channel), action="channel.received").id
            )
    session.commit()
    for inbound_id in new_ids:
        background.add_task(handle_inbound, inbound_id)
    return {"ok": True}


def _seen(session: Session, item: InboundMessage) -> bool:
    return (
        session.exec(
            select(ChannelInbound)
            .where(ChannelInbound.channel == item.channel)
            .where(ChannelInbound.channel_message_id == item.channel_message_id)
        ).first()
        is not None
    )
