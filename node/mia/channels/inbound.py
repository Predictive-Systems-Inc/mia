"""Inbound channel messages: link unknown addresses, run chat turns for linked people.

Guarantees: an unlinked address never reaches an agent and gets only the public reply; a
linked person's message runs the same chat turn as the app (RBAC, approvals, egress); a failed
turn is never retried (it could act twice) and the person gets one apology; DB work runs in
worker threads and nothing holds the write lock across the model call.
"""

import asyncio
import datetime as dt
import logging
import os
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import text as sql
from sqlmodel import Session, col, select

from mia.agents.dispatcher.agent import MANIFEST, get_agent
from mia.channels import linking, outbox, registry, transport
from mia.channels.base import InboundMessage
from mia.channels.service import deliver
from mia.chat.blocks import ChatReply, TextBlock
from mia.chat.service import run_turn
from mia.core import events, store
from mia.core.db import get_engine, session_scope, utcnow
from mia.core.ids import new_id
from mia.core.models import (
    Actor,
    Branch,
    ChannelIdentity,
    ChannelInbound,
    Event,
    Location,
    Person,
    Principal,
    Thread,
    Visit,
)
from mia.core.rbac import Resource, get_rbac
from mia.i18n import SUPPORTED, t
from mia.settings import get_settings

log = logging.getLogger(__name__)


class _Step(BaseModel):
    """What to do after the sync part of handling one inbound message."""

    model_config = {"arbitrary_types_allowed": True}

    direct: list[str] = []  # texts to send straight to an unlinked address
    person: Person | None = None
    text: str | None = None  # run a chat turn with this text
    thread_id: str | None = None
    media: InboundMessage | None = None  # save the attachment as proof of the current visit


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
    if msg.has_media and msg.media_id:
        return _Step(person=person, media=msg)
    if msg.lat is not None and msg.lon is not None:
        _attend(session, person, msg, now)
        dropped = {**row.body, "lat": None, "lon": None}  # the point is used once, never kept
        _finish(session, row, "done", body=dropped)
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


DEFAULT_RADIUS_M = 100
OUTSIDE_FENCE = "visit.attendance_outside_fence"


def _attend(session: Session, person: Person, msg: InboundMessage, now: dt.datetime) -> None:
    """A shared location checks the person in to their current visit (planned, in its window)
    or out of it (in progress). Code compares the point with the site's geofence (rule 7): a
    point outside it is flagged with one event (distance only, never the coordinates) and
    named in the reply; the check-in or check-out stands. A chosen place (WhatsApp lets the
    person pick one) is flagged the same way: the point is the person's claim, never proof.
    On a two-person visit the second arrival is told it is already checked in, as the chat
    tool does. Replies to the person."""
    from mia.agents.dispatcher.scoring import distance_km
    from mia.core import scheduling  # core imports channels for linking; keep this one lazy

    actor = Actor.person(person)
    get_rbac().require(
        actor,
        Resource(kind="data", name="core.visit", owner_id=person.id),
        "write",
        session=session,
    )
    branch = session.get(Branch, person.branch_id)
    visit = scheduling.current_visit(session, branch, person, now) if branch else None
    if visit is None or branch is None:
        text = t("check_in.no_visit", person.language)
        deliver(session, person, [TextBlock(text=text)], actor, urgent=True)
        return
    loc = session.get(Location, visit.location_id)
    name = loc.name if loc else "?"
    kind = "check_out" if visit.status == "in_progress" else "check_in"
    if kind == "check_out" and _checked_in_by(session, visit) != person.id:
        text = t("check_in.already", person.language)
        deliver(session, person, [TextBlock(text=text)], actor, urgent=True)
        return
    try:
        if kind == "check_out":
            scheduling.check_out(session, actor, visit, person, now)
        else:
            scheduling.check_in(session, actor, visit, person, now)
    except scheduling.ScheduleError as exc:
        reason = "too_early" if "too early" in str(exc) else "too_late"
        deliver(
            session,
            person,
            [TextBlock(text=t(f"check_in.{reason}", person.language))],
            actor,
            urgent=True,
        )
        return
    when = now.astimezone(ZoneInfo(branch.timezone)).strftime("%H:%M")
    text = t(f"{kind}.done", person.language, location=name, time=when)
    if loc is not None and loc.lat is not None and loc.lon is not None:
        assert msg.lat is not None and msg.lon is not None
        distance_m = round(distance_km((loc.lat, loc.lon), (msg.lat, msg.lon)) * 1000)
        radius_m = _radius_m(loc)
        reason = "picked_place" if msg.picked_place else "outside"
        if distance_m > radius_m or msg.picked_place:
            data = {
                "kind": kind,
                "reason": reason,
                "person_id": person.id,
                "distance_m": distance_m,
                "radius_m": radius_m,
                "date": visit.date.isoformat(),
            }
            events.emit(session, OUTSIDE_FENCE, visit, None, data, actor)
            text += "\n" + t(
                f"attendance.{'picked_place' if msg.picked_place else 'outside_fence'}",
                person.language,
                distance=str(distance_m),
                location=name,
            )
    deliver(session, person, [TextBlock(text=text)], actor, urgent=True)


def _radius_m(loc: Location) -> int:
    """The site's fence radius; the default when the JSON holds nothing usable, so a bad value
    never fails the check-in."""
    try:
        return int(loc.geofence.get("radius_m", DEFAULT_RADIUS_M))
    except (TypeError, ValueError, AttributeError):
        return DEFAULT_RADIUS_M


def _checked_in_by(session: Session, visit: Visit) -> str | None:
    """The person whose check-in put the visit in progress (the latest `visit.checked_in`)."""
    row = session.exec(
        select(Event)
        .where(Event.action == "visit.checked_in")
        .where(Event.entity_id == visit.id)
        .order_by(col(Event.id).desc())
    ).first()
    return row.actor_id if row else None


EXT = {"image": "jpg", "video": "mp4", "audio": "ogg", "document": "bin"}


def _save_proof(
    session: Session,
    inbound_id: str,
    person: Person,
    msg: InboundMessage,
    data: bytes,
    now: dt.datetime,
) -> None:
    """Store the attachment under MIA_MEDIA_DIR and reference it on the person's current
    visit (event `visit.proof_added`, the reference only). Replies to the person and marks
    the inbound row done. Ownership: current_visit only returns a visit the person is assigned
    to, in their branch, today (the non-tool path's equivalent of the tools' rbac check)."""
    from mia.core import scheduling  # core imports channels for linking; keep this one lazy

    actor = Actor.person(person)
    row = session.get(ChannelInbound, inbound_id)
    branch = session.get(Branch, person.branch_id)
    visit = scheduling.current_visit(session, branch, person, now) if branch else None
    if visit is None:
        deliver(
            session,
            person,
            [TextBlock(text=t("proof.no_visit", person.language))],
            actor,
            urgent=True,
        )
        if row is not None:
            _finish(session, row, "done")
        return
    folder = get_settings().MIA_MEDIA_DIR / visit.branch_id / visit.id
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{new_id()}.{EXT.get(msg.media_kind or '', 'bin')}"
    path = folder / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    try:
        ref = f"media/{visit.branch_id}/{visit.id}/{name}"
        store.update(
            session,
            visit,
            {"proof_refs": [*visit.proof_refs, ref]},
            actor,
            action="visit.proof_added",
        )
        loc = session.get(Location, visit.location_id)
        text = t("proof.saved", person.language, location=loc.name if loc else "?")
        deliver(session, person, [TextBlock(text=text)], actor, urgent=True)
        if row is not None:
            _finish(session, row, "done")
    except Exception:
        path.unlink(missing_ok=True)  # no orphan file without its reference
        raise


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


def _finish(
    session: Session,
    row: ChannelInbound,
    status: str,
    error: str | None = None,
    body: dict[str, Any] | None = None,
) -> None:
    actor = Actor(
        principal=Principal(type="system", id=f"channel:{row.channel}"),
        branch_id=row.branch_id or "",
    )
    changes: dict[str, Any] = {"status": status, "error": error}
    if body is not None:
        changes["body"] = body
    store.update(session, row, changes, actor, action=f"channel.inbound_{status}")


def _after_turn(session: Session, inbound_id: str, person: Person, reply: ChatReply) -> None:
    deliver(
        session,
        person,
        list(reply.blocks),
        Actor.person(person),
        urgent=True,
        source_id=reply.message_id,
        sensitive=reply.sensitive,
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
        if step is not None and step.media is not None and step.person is not None:
            adapter = registry.get(step.media.channel)
            with transport.fetching(inbound_id):  # rule 6: a GET for a logged attachment only
                data = await adapter.fetch_media(step.media.media_id or "")
            if data is None:
                raise RuntimeError(f"media {step.media.media_id} could not be fetched")
            await asyncio.to_thread(
                _save_proof, session, inbound_id, step.person, step.media, data, utcnow()
            )
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
