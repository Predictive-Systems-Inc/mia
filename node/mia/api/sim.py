"""Phones on screen: the dev page /sim shows one simulated phone per person on the sim channel.

Every route is 404 unless the node runs in dev mode and the request comes straight from
loopback (the sim channel's own guard, ADR 021). A person's phone number on the page is
63900 followed by their 1-based position among all people ordered by id, zero-padded to seven
digits (639000000001, 639000000002, ...): twelve digits like a WhatsApp address, under the
unallocated 0900 prefix, so it never collides with a real mobile. Nothing leaves the node:
the sim adapter keeps every payload in memory until a phone fetches it.
"""

import asyncio
import datetime as dt
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from mia import i18n
from mia.agents.customer_service import public
from mia.api.deps import DbSession, direct_loopback
from mia.channels import linking, outbox, registry
from mia.channels.base import InboundMessage
from mia.channels.inbound import handle_inbound
from mia.channels.simulator import SimAdapter
from mia.chat import features, phrases
from mia.chat.access import agents_for
from mia.core import db, people, store  # db.utcnow: the clock tests pin
from mia.core.ids import new_id
from mia.core.models import (
    Actor,
    Branch,
    ChannelIdentity,
    ChannelInbound,
    ChannelOutbox,
    Person,
    Principal,
)
from mia.settings import get_settings

STATIC = Path(__file__).resolve().parent.parent / "static"
PREFIX = "63900"


def dev_loopback(request: Request) -> None:
    """404 unless dev mode and a direct loopback peer (no Cloudflare headers)."""
    if get_settings().MIA_AUTH_MODE != "dev" or not direct_loopback(request):
        raise HTTPException(404, "not found")


router = APIRouter(prefix="/sim", tags=["sim"], dependencies=[Depends(dev_loopback)])


def _sim() -> SimAdapter:
    try:
        adapter = registry.get("sim")
    except KeyError:
        adapter = None
    if not isinstance(adapter, SimAdapter) or adapter not in registry.enabled():
        raise HTTPException(409, "the sim channel is off: set channels.sim.enabled")
    return adapter


def _actor(branch_id: str = "") -> Actor:
    return Actor(principal=Principal(type="system", id="channel:sim"), branch_id=branch_id)


def address_for(session: Session, person: Person) -> str:
    """The person's page number: 63900 plus their position by id, seven digits."""
    before = session.exec(select(func.count()).where(col(Person.id) < person.id)).one()
    return f"{PREFIX}{before + 1:07d}"


def _drain(sim: SimAdapter, address: str) -> list[dict[str, Any]]:
    """The payloads sent to the address, removed from `sent`; other addresses' stay. A sent
    payload carries its message id (`id`), which a button tap sends back as its context."""
    mine = [
        p.body | ({"id": p.message_id} if p.message_id else {})
        for p in sim.sent
        if p.address == address
    ]
    sim.sent[:] = [p for p in sim.sent if p.address != address]
    return mine


@router.get("", include_in_schema=False)
def page() -> FileResponse:
    return FileResponse(STATIC / "sim.html")


class PhoneOut(BaseModel):
    person_id: str
    name: str
    roles: list[str]
    language: str
    branch: str
    address: str | None


@router.get("/phones", response_model=list[PhoneOut])
def phones(session: DbSession) -> list[PhoneOut]:
    """Every active person with their sim number when they have one."""
    branches = {b.id: b.name for b in session.exec(select(Branch))}
    linked = {
        i.person_id: i.address
        for i in session.exec(
            select(ChannelIdentity)
            .where(ChannelIdentity.channel == "sim")
            .where(ChannelIdentity.status == "active")
        )
    }
    rows = session.exec(
        select(Person).where(Person.status == "active").order_by(col(Person.id))
    ).all()
    return [
        PhoneOut(
            person_id=p.id,
            name=p.name,
            roles=p.roles,
            language=p.language,
            branch=branches.get(p.branch_id, ""),
            address=linked.get(p.id),
        )
        for p in rows
    ]


class AddPhone(BaseModel):
    person_id: str


@router.post("/phones", response_model=PhoneOut)
def add_phone(session: DbSession, body: AddPhone) -> PhoneOut:
    """Give the person a sim phone (idempotent: an existing link is returned)."""
    person = session.get(Person, body.person_id)
    if person is None or person.status != "active":
        raise HTTPException(404, "no such person")
    try:
        identity = linking.link_sim(
            session, _actor(person.branch_id), person, address_for(session, person)
        )
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _phone(session, person, identity.address)


def _phone(session: Session, person: Person, address: str | None = None) -> PhoneOut:
    if address is None:
        address = session.exec(
            select(ChannelIdentity.address)
            .where(ChannelIdentity.person_id == person.id)
            .where(ChannelIdentity.channel == "sim")
            .where(ChannelIdentity.status == "active")
        ).first()
    branch = session.get(Branch, person.branch_id)
    return PhoneOut(
        person_id=person.id,
        name=person.name,
        roles=person.roles,
        language=person.language,
        branch=branch.name if branch else "",
        address=address,
    )


class SetLanguage(BaseModel):
    language: str


@router.post("/phones/{person_id}/language", response_model=PhoneOut)
def set_language(session: DbSession, person_id: str, body: SetLanguage) -> PhoneOut:
    """Set the person's reply language as the person (people.set_language, the service the
    app's language button uses; event person.language_chosen). 422 outside i18n.SUPPORTED."""
    person = session.get(Person, person_id)
    if person is None or person.status != "active":
        raise HTTPException(404, "no such person")
    if body.language not in i18n.SUPPORTED:
        raise HTTPException(422, f"language must be one of {', '.join(i18n.SUPPORTED)}")
    try:
        people.set_language(session, Actor.person(person), person, body.language)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _phone(session, person)


class SimMessage(BaseModel):
    address: str
    text: str = ""
    button: str | None = None  # a tapped button or list row title
    context: str | None = None  # the id of the message the tapped button is on (as WhatsApp)
    name: str | None = None  # display name of an unlinked (customer) number


def _store_inbound(session: Session, msg: InboundMessage) -> str:
    row = ChannelInbound(
        channel="sim",
        channel_message_id=msg.channel_message_id,
        address=msg.address,
        body=msg.model_dump(mode="json"),
    )
    inbound_id = store.insert(session, row, _actor(), action="channel.received").id
    session.commit()  # handle_inbound reads it in its own session
    return inbound_id


@router.post("/messages")
async def send_message(session: DbSession, body: SimMessage) -> list[dict[str, Any]]:
    """One message from the phone (as `mia channels sim`): stored, handled, and Mia's payloads
    to that address returned and cleared."""
    sim = _sim()
    if not body.address.isdigit() or not (body.text.strip() or body.button):
        raise HTTPException(422, "a numeric address and a text or a button")
    msg = InboundMessage(
        channel="sim",
        address=body.address,
        channel_message_id=new_id(),
        text=body.text,
        button=body.button,
        context_id=body.context if body.button else None,
        name=body.name,
        received_at=db.utcnow(),
    )
    inbound_id = await asyncio.to_thread(_store_inbound, session, msg)
    await handle_inbound(inbound_id)
    await outbox.send_due(db.utcnow(), on_demand_for=body.address)
    return _drain(sim, body.address)


@router.get("/messages")
async def poll(address: str) -> list[dict[str, Any]]:
    """Send what waits for this address (alerts, cards, tick messages) and the queued customer
    replies (an order confirmed in the app), then return this address's payloads only."""
    sim = _sim()
    await outbox.send_due(db.utcnow(), on_demand_for=address)
    await public.send_pending(db.utcnow())  # every queued customer reply; others wait in sim.sent
    return _drain(sim, address)


def _waiting(session: Session) -> int:
    count = session.exec(
        select(func.count())
        .select_from(ChannelOutbox)
        .where(ChannelOutbox.channel == "sim")
        .where(ChannelOutbox.status == "queued")
    ).one()
    session.commit()  # end the read, so the next count sees the tick's writes
    return count


@router.post("/tick")
async def tick(session: DbSession) -> dict[str, int]:
    """One round of the tick's due work now (as `mia tick`). `queued` is how many sim messages
    the round queued for phones (they arrive on each phone's next poll)."""
    from mia.agents.registry import load_roles
    from mia.api.main import run_due_work  # main includes this router

    load_roles()
    before = await asyncio.to_thread(_waiting, session)
    advanced, sent = await run_due_work()
    after = await asyncio.to_thread(_waiting, session)
    return {"advanced": advanced, "sent": sent, "queued": max(after - before, 0)}


class ClockOut(BaseModel):
    now: dt.datetime  # the node's now in the organisation's time zone
    timezone: str
    shifted: bool  # True while the test clock is set


class SetClock(BaseModel):
    at: dt.datetime | None = None  # local date and time in the organisation's zone
    reset: bool = False


def _zone(session: Session) -> str:
    """The organisation's time zone: its first branch's (as the seeds read it)."""
    return session.exec(select(Branch.timezone).order_by(col(Branch.id))).first() or "UTC"


def _clock(session: Session) -> ClockOut:
    zone = _zone(session)
    now = db.utcnow().astimezone(ZoneInfo(zone))
    return ClockOut(now=now, timezone=zone, shifted=db.dev_clock() is not None)


@router.get("/clock", response_model=ClockOut)
def clock(session: DbSession) -> ClockOut:
    """The node's now (db.utcnow, test clock included) in the organisation's zone."""
    return _clock(session)


@router.post("/clock", response_model=ClockOut)
def set_clock(session: DbSession, body: SetClock) -> ClockOut:
    """Set the test clock to a local time (naive means the organisation's zone) or reset it.
    Runs nothing by itself; /sim/tick runs due work at the new time. Moving back is allowed,
    but then events land out of order in that database."""
    if body.reset == (body.at is not None):
        raise HTTPException(422, "either at or reset")
    at = body.at
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=ZoneInfo(_zone(session)))
    db.set_dev_clock(at)
    return _clock(session)


# ---- teach Mia as you go (spec 2026-10-22-teach-mia-design, 4 and 4b) --------------------


def _active(session: Session, person_id: str) -> Person:
    person = session.get(Person, person_id)
    if person is None or person.status != "active":
        raise HTTPException(404, "no such person")
    return person


def _tester(person: Person) -> Actor:
    """The person on that phone, on behalf of the tester at the page (dev mode: the tester
    is the approver)."""
    tester = Principal(type="system", id="sim:tester")
    return Actor(
        principal=Actor.person(person).principal, on_behalf_of=tester, branch_id=person.branch_id
    )


class TeachAction(BaseModel):
    action: str
    label: str


class TeachAgent(BaseModel):
    agent_id: str
    label: str
    actions: list[TeachAction]


@router.get("/phones/{person_id}/teach", response_model=list[TeachAgent])
def teach_options(session: DbSession, person_id: str) -> list[TeachAgent]:
    """The person's agents and their teachable actions, labelled in the person's language."""
    person = _active(session, person_id)
    lang = person.language
    return [
        TeachAgent(
            agent_id=spec.id,
            label=i18n.t(spec.label_key, lang),
            actions=[
                TeachAction(action=name, label=i18n.t(str(a.label_key), lang))
                for name, a in phrases.teachable(spec.id).items()
            ],
        )
        for spec in agents_for(session, person)
    ]


class TeachIn(BaseModel):
    person_id: str
    text: str = Field(min_length=1, max_length=features.MAX_TEXT)
    agent_id: str
    action: str


@router.post("/teach")
def teach(session: DbSession, body: TeachIn) -> dict[str, Any]:
    """Teach the message's key to one of the person's agents' actions at the phone's branch
    (phrase.taught). 422 for an agent that is not the person's or an action not teachable."""
    person = _active(session, body.person_id)
    if body.agent_id not in {a.id for a in agents_for(session, person)}:
        raise HTTPException(422, "not one of this person's agents")
    try:
        ev = phrases.teach(
            session, _tester(person), person.branch_id, body.text, body.agent_id, body.action,
            lang=person.language, roles=person.roles,
        )  # fmt: skip
    except phrases.TeachError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"key": (ev.after or {})["key"], "version": phrases.version(session, person.branch_id)}


class PhraseOut(BaseModel):
    branch: str
    branch_id: str | None
    key: str
    text: str
    agent_id: str
    action: str
    taught: bool
    confidence: int
    taps: int


@router.get("/phrases")
def phrase_list(session: DbSession) -> dict[str, Any]:
    """Every branch's live phrases (taught ones for every branch once) and each branch's
    phrasebook version."""
    names = {b.id: b.name for b in session.exec(select(Branch).order_by(col(Branch.id)))}
    seen: set[tuple[str | None, str]] = set()
    rows: list[PhraseOut] = []
    for branch_id in names:
        for p in phrases.entries(session, branch_id):
            if (p.branch_id, p.key) in seen:
                continue
            seen.add((p.branch_id, p.key))
            name = names.get(p.branch_id, "") if p.branch_id else "every branch"
            rows.append(PhraseOut(branch=name, **{k: getattr(p, k) for k in PHRASE_FIELDS}))
    versions = {name: phrases.version(session, branch_id) for branch_id, name in names.items()}
    return {"versions": versions, "phrases": rows}


PHRASE_FIELDS = ("branch_id", "key", "text", "agent_id", "action", "taught", "confidence", "taps")


class RetireIn(BaseModel):
    key: str
    branch_id: str | None = None


@router.post("/phrases/retire")
def retire(session: DbSession, body: RetireIn) -> dict[str, int]:
    """Retire a phrase at its branch (None: every branch) by the sim's actor."""
    branch_id = body.branch_id or session.exec(select(Branch.id).order_by(col(Branch.id))).first()
    phrases.retire(session, _actor(branch_id or ""), body.branch_id, body.key)
    return {"version": phrases.version(session, branch_id or "")}


class RequestIn(BaseModel):
    person_id: str
    text: str = Field(min_length=1, max_length=features.MAX_TEXT)
    failed_text: str | None = None  # the message Mia could not do ("Mia can't do this yet")


@router.post("/requests")
def add_request(session: DbSession, body: RequestIn) -> dict[str, str]:
    """A feature request from the person on that phone (feature.requested)."""
    person = _active(session, body.person_id)
    ev = features.request(session, person, body.text, _tester(person), failed_text=body.failed_text)
    session.commit()
    return {"id": ev.id}


@router.get("/requests")
def request_list(session: DbSession) -> list[dict[str, Any]]:
    """The node's feature requests grouped by key, with counts and status."""
    return [
        {"id": g.id, "text": g.text, "count": g.count, "status": g.status, "failed": g.failed}
        for g in features.groups(session)
    ]
