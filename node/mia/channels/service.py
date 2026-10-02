"""Channel delivery: the one entry point agents and services use for outside channels.

deliver() guarantees: only enabled channels with an active identity get anything; sensitive
messages carry no content; outside the messaging window only an approved template goes out and
the full message is held until the person writes; non-urgent messages wait for quiet hours to
end; the same source message is queued at most once per channel.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.channels import registry
from mia.channels.base import ChannelCapabilities, TemplateCall
from mia.channels.render import to_parts
from mia.chat.blocks import Block
from mia.core import orgconfig, store
from mia.core.db import utcnow
from mia.core.ids import new_id
from mia.core.models import Actor, Branch, ChannelIdentity, ChannelOutbox, Person

NEW_MESSAGE = "mia_new_message"
TEMPLATE_KIND = "template"  # outbox kind of template rows (adapter payload shapes differ)


def window_open(identity: ChannelIdentity, caps: ChannelCapabilities, now: dt.datetime) -> bool:
    """True when the channel lets Mia send free-form messages to this identity now."""
    if caps.session_window_hours is None:
        return True
    last = identity.last_inbound_at
    return last is not None and now - last <= dt.timedelta(hours=caps.session_window_hours)


def quiet_until(now: dt.datetime, tz: str) -> dt.datetime | None:
    """When quiet hours end (in UTC), if `now` is inside them in the branch time zone; else None."""
    quiet = orgconfig.load().quiet_hours
    local = now.astimezone(ZoneInfo(tz))
    if not quiet.contains(local.time().replace(tzinfo=None)):
        return None
    end = local.replace(hour=quiet.end.hour, minute=quiet.end.minute, second=0, microsecond=0)
    end = end if end > local else end + dt.timedelta(days=1)
    # UTC: send_after is compared in SQL as a string against UTC times, so offsets must match.
    return end.astimezone(dt.UTC)


def deliver(
    session: Session,
    person: Person,
    blocks: list[Block],
    actor: Actor,
    *,
    kind: str = "message",
    template: TemplateCall | None = None,
    sensitive: bool = False,
    urgent: bool = False,
    now: dt.datetime | None = None,
    source_id: str | None = None,
) -> list[ChannelOutbox]:
    """Queue the message for every enabled channel the person has linked. Returns new rows."""
    now = now or utcnow()
    source = source_id or new_id()
    branch = session.get(Branch, person.branch_id)
    send_after = None if urgent else quiet_until(now, branch.timezone if branch else "UTC")
    rows: list[ChannelOutbox] = []
    for adapter in registry.enabled():
        identity = session.exec(
            select(ChannelIdentity)
            .where(ChannelIdentity.person_id == person.id)
            .where(ChannelIdentity.channel == adapter.channel_id)
            .where(ChannelIdentity.status == "active")
        ).first()
        prefix = f"{source}:{adapter.channel_id}"
        if identity is None or _queued(session, f"{prefix}:0"):
            continue
        parts = to_parts(blocks, adapter.capabilities, person.language, sensitive=sensitive)
        payloads = [p.body for p in adapter.render(identity.address, parts)]
        if window_open(identity, adapter.capabilities, now):
            bodies = [(body, "queued") for body in payloads]
        else:
            call = template or TemplateCall(name=NEW_MESSAGE, lang=person.language)
            notice = adapter.render_template(identity.address, call).body
            bodies = [(notice, "queued")]
            if call.name == NEW_MESSAGE:  # a specific template already is the whole message
                bodies += [(body, "held") for body in payloads]
        for i, (body, status) in enumerate(bodies):
            is_notice = i == 0 and not window_open(identity, adapter.capabilities, now)
            row = ChannelOutbox(
                branch_id=person.branch_id,
                person_id=person.id,
                channel=adapter.channel_id,
                address=identity.address,
                kind=TEMPLATE_KIND if is_notice else kind,
                payload=body,
                idempotency_key=f"{prefix}:{i}",
                status=status,
                send_after=send_after if status == "queued" else None,
            )
            rows.append(store.insert(session, row, actor, action="channel.queued"))
    return rows


def _queued(session: Session, key: str) -> bool:
    return (
        session.exec(select(ChannelOutbox).where(ChannelOutbox.idempotency_key == key)).first()
        is not None
    )
