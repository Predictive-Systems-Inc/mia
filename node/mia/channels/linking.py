"""Linking a channel address to a person with a one-time code (spec, Channel rules).

Guarantees: codes are 6 digits, stored only as an HMAC keyed by MIA_NODE_SECRET, single use and
time limited; one active address belongs to one person and is never overwritten; 5 failed
attempts from an address within an hour block it for an hour; every attempt is an event.
"""

import datetime as dt
import hashlib
import hmac
import re
import secrets
from typing import Literal

from pydantic import BaseModel
from sqlmodel import Session, col, select

from mia.chat.blocks import TextBlock
from mia.core import store
from mia.core.db import utcnow
from mia.core.models import (
    Actor,
    ChannelIdentity,
    ChannelLinkAttempt,
    ChannelLinkCode,
    Person,
    Principal,
)
from mia.i18n import t
from mia.settings import get_settings

Purpose = Literal["invite", "self"]
Status = Literal["linked", "invalid", "expired", "used", "taken", "blocked"]
VALID_FOR = {"invite": dt.timedelta(days=7), "self": dt.timedelta(minutes=10)}
MAX_FAILURES = 5
LOCKOUT = dt.timedelta(hours=1)
LINK_TEXT = re.compile(r"^\s*LINK\s+(\d{6})\s*$", re.IGNORECASE)


class LinkingError(RuntimeError):
    """Linking is not configured (no MIA_NODE_SECRET)."""


class RedeemResult(BaseModel):
    status: Status
    person: Person | None = None


def _hmac(code: str) -> str:
    secret = get_settings().MIA_NODE_SECRET
    if not secret:
        raise LinkingError("set MIA_NODE_SECRET before creating or redeeming link codes")
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def create_code(session: Session, actor: Actor, person: Person, purpose: Purpose) -> str:
    """A new code for the person. The plain code is returned once and never stored."""
    while True:
        code = f"{secrets.randbelow(10**6):06d}"
        digest = _hmac(code)
        taken = session.exec(select(ChannelLinkCode).where(ChannelLinkCode.code_hmac == digest))
        if taken.first() is None:
            break
    store.insert(
        session,
        ChannelLinkCode(
            branch_id=person.branch_id,
            person_id=person.id,
            code_hmac=digest,
            purpose=purpose,
            expires_at=utcnow() + VALID_FOR[purpose],
            created_by=actor.principal.id,
        ),
        actor,
        action="channel.code_created",
    )
    return code


def invite_link(code: str) -> str:
    """Click-to-chat link that opens WhatsApp with `LINK <code>` typed in."""
    number = re.sub(r"\D", "", get_settings().MIA_WA_NUMBER)
    return f"https://wa.me/{number}?text=LINK%20{code}"


def parse_link_text(text: str) -> str | None:
    """The 6-digit code in a `LINK 123456` message, or None."""
    m = LINK_TEXT.match(text)
    return m[1] if m else None


def identity_for(session: Session, channel: str, address: str) -> ChannelIdentity | None:
    """The active identity for an address on a channel, if any."""
    return session.exec(
        select(ChannelIdentity)
        .where(ChannelIdentity.channel == channel)
        .where(ChannelIdentity.address == address)
        .where(ChannelIdentity.status == "active")
    ).first()


def _channel_actor(channel: str) -> Actor:
    # Attempts from unknown addresses belong to no branch yet.
    return Actor(principal=Principal(type="system", id=f"channel:{channel}"), branch_id="")


def _blocked(session: Session, channel: str, address: str, now: dt.datetime) -> bool:
    failures = session.exec(
        select(ChannelLinkAttempt)
        .where(ChannelLinkAttempt.channel == channel)
        .where(ChannelLinkAttempt.address == address)
        .where(ChannelLinkAttempt.ok == False)
        .where(col(ChannelLinkAttempt.created_at) > now - LOCKOUT)
    ).all()
    return len(failures) >= MAX_FAILURES


def _record(session: Session, channel: str, address: str, ok: bool, now: dt.datetime) -> None:
    attempt = ChannelLinkAttempt(channel=channel, address=address, ok=ok, created_at=now)
    store.insert(session, attempt, _channel_actor(channel), action="channel.link_attempt")


def redeem(
    session: Session, channel: str, address: str, code: str, now: dt.datetime
) -> RedeemResult:
    """Link the address to the code's person, or say why not. Never overwrites a link."""
    if _blocked(session, channel, address, now):
        _record(session, channel, address, False, now)
        return RedeemResult(status="blocked")
    row = session.exec(
        select(ChannelLinkCode).where(ChannelLinkCode.code_hmac == _hmac(code))
    ).first()
    status: Status
    if row is None:
        status = "invalid"
    elif row.used_at is not None:
        status = "used"
    elif row.expires_at <= now:
        status = "expired"
    else:
        status = "linked"
    if status != "linked" or row is None:
        _record(session, channel, address, False, now)
        return RedeemResult(status=status)
    person = session.get(Person, row.person_id)
    if person is None or person.status != "active":
        _record(session, channel, address, False, now)
        return RedeemResult(status="invalid")
    existing = identity_for(session, channel, address)
    if existing is not None and existing.person_id != person.id:
        _record(session, channel, address, False, now)
        _tell_inviter(session, row, person)
        return RedeemResult(status="taken", person=None)
    actor = Actor.person(person)
    store.update(session, row, {"used_at": now}, actor, action="channel.code_used")
    if existing is None:
        store.insert(
            session,
            ChannelIdentity(
                branch_id=person.branch_id,
                person_id=person.id,
                channel=channel,
                address=address,
                verified_at=now,
                consent_at=now,
            ),
            actor,
            action="channel.linked",
        )
    _record(session, channel, address, True, now)
    return RedeemResult(status="linked", person=person)


def _tell_inviter(session: Session, row: ChannelLinkCode, person: Person) -> None:
    from mia.chat.channels import notify  # chat.channels imports channels.service later

    inviter = session.get(Person, row.created_by)
    if inviter is None:
        return
    text = t("channel.link_taken", inviter.language, name=person.name)
    notify(session, inviter, [TextBlock(text=text)], Actor.system(person.branch_id), "mia")


def revoke_all(session: Session, actor: Actor, person: Person) -> int:
    """Revoke every active identity of the person. Returns how many were revoked."""
    rows = session.exec(
        select(ChannelIdentity)
        .where(ChannelIdentity.person_id == person.id)
        .where(ChannelIdentity.status == "active")
    ).all()
    for row in rows:
        store.update(session, row, {"status": "revoked"}, actor, action="channel.revoked")
    return len(rows)
