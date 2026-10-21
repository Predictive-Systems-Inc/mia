"""Linking a channel address to a person with a one-time code (spec, Channel rules).

Guarantees (codes, limits and attempts live in core/auth.py): codes are 6 digits, stored only
as an HMAC, single use and time limited; one active address belongs to one person and is never
overwritten; 5 failed attempts from an address within an hour block it for an hour; every
attempt is an event.
"""

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel
from sqlmodel import Session, col, select

from mia.chat.blocks import TextBlock
from mia.core import auth, events, keys, store
from mia.core.db import utcnow
from mia.core.models import Actor, AuthCode, ChannelIdentity, Person, Principal
from mia.i18n import t
from mia.settings import get_settings

Purpose = Literal["invite", "self"]
Status = Literal["linked", "invalid", "expired", "used", "taken", "blocked"]
STATUS_OF: dict[str, Status] = {
    "ok": "linked",
    "invalid": "invalid",
    "expired": "expired",
    "used": "used",
    "exhausted": "invalid",
}
LINK_TEXT = re.compile(r"^\s*LINK\s+(\d{6})\s*$", re.IGNORECASE)
PHONE_CHANNELS = ("whatsapp", "sim")  # the channels whose address is the phone number


class LinkingError(RuntimeError):
    """Linking is not configured (no master key file and no MIA_NODE_SECRET)."""


class RedeemResult(BaseModel):
    status: Status
    person: Person | None = None


def create_code(session: Session, actor: Actor, person: Person, purpose: Purpose) -> str:
    """A new code for the person. The plain code is returned once and never stored."""
    try:
        return auth.create_code(session, actor, person, purpose, utcnow())
    except keys.MasterKeyError as exc:
        raise LinkingError(str(exc)) from exc


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


def ph_mobile(text: str) -> str | None:
    """A Philippine mobile number as a channel address (E.164 digits without the plus, as
    WhatsApp sends it: 639171234567) from 09171234567, +63 917 123 4567, 639171234567 or
    9171234567; None for any other shape or a character other than digits, spaces, + . - ( ).
    It is events.ph_mobile, the normaliser events.mask_phones uses: whatever is linked is masked."""
    return events.ph_mobile(text)


def link_phone(session: Session, actor: Actor, person: Person, address: str) -> None:
    """Link the address to the person on WhatsApp and on every enabled phone channel (the sim
    in dev), the row a redeemed code writes (event channel.linked, the address redacted). An
    address the person already holds is kept, and the person's open invite and self codes are
    revoked (event auth.code_revoked), so no second number can act as them through an earlier
    code. Raises LookupError("phone_taken") when another person holds it on one of those
    channels, before anything is written: never relinked."""
    from mia.channels import registry  # registry loads orgconfig; keep linking light

    enabled = [a.channel_id for a in registry.enabled() if a.channel_id in PHONE_CHANNELS]
    held = {c: identity_for(session, c, address) for c in dict.fromkeys(["whatsapp", *enabled])}
    if any(row is not None and row.person_id != person.id for row in held.values()):
        raise LookupError("phone_taken")
    now = utcnow()
    for channel in (c for c, row in held.items() if row is None):
        identity = ChannelIdentity(
            branch_id=person.branch_id,
            person_id=person.id,
            channel=channel,
            address=address,
            verified_at=now,
            consent_at=now,
        )
        store.insert(session, identity, actor, action="channel.linked", redact=("address",))
    open_codes = session.exec(
        select(AuthCode)
        .where(AuthCode.person_id == person.id)
        .where(col(AuthCode.purpose).in_(["invite", "self"]))
        .where(col(AuthCode.used_at).is_(None))
        .where(AuthCode.expires_at > now)
    ).all()
    for code in open_codes:
        revoked = {"expires_at": code.created_at}  # expired from the start, on any clock
        store.update(session, code, revoked, actor, action="auth.code_revoked")


def _channel_actor(channel: str) -> Actor:
    # Attempts from unknown addresses belong to no branch yet.
    return Actor(principal=Principal(type="system", id=f"channel:{channel}"), branch_id="")


def _key(channel: str, address: str) -> str:
    return auth.attempt_key(f"{channel}:{address}", None)


def _record(session: Session, channel: str, address: str, ok: bool, now: dt.datetime) -> None:
    auth.record_attempt(
        session,
        "link_code",
        _key(channel, address),
        ok,
        now,
        actor=_channel_actor(channel),
        action="channel.link_attempt",
    )


def redeem(
    session: Session, channel: str, address: str, code: str, now: dt.datetime
) -> RedeemResult:
    """Link the address to the code's person, or say why not. Never overwrites a link, and
    never links a second address on the channel to a person who already has one there
    (invalid, no hint; they relink through the owner)."""
    if auth.throttled(session, "link_code", _key(channel, address), now):
        _record(session, channel, address, False, now)
        return RedeemResult(status="blocked")
    result = auth.check_code(session, "invite", code, now)
    if result.status == "invalid":
        result = auth.check_code(session, "self", code, now)
    status: Status = STATUS_OF[result.status]
    row = result.row
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
    if existing is None and _holds_channel(session, person, channel):
        _record(session, channel, address, False, now)
        return RedeemResult(status="invalid")
    actor = Actor.person(person)
    auth.use_code(session, actor, row, now)
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


def _holds_channel(session: Session, person: Person, channel: str) -> bool:
    return (
        session.exec(
            select(ChannelIdentity)
            .where(ChannelIdentity.person_id == person.id)
            .where(ChannelIdentity.channel == channel)
            .where(ChannelIdentity.status == "active")
        ).first()
        is not None
    )


def _tell_inviter(session: Session, row: AuthCode, person: Person) -> None:
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
