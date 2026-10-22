"""Phones on screen: the dev page /sim shows one simulated phone per person on the sim channel.

Every route is 404 unless the node runs in dev mode and the request comes straight from
loopback (the sim channel's own guard, ADR 021). A person's phone number on the page is
63900 followed by their 1-based position among all people ordered by id, zero-padded to seven
digits (639000000001, 639000000002, ...): twelve digits like a WhatsApp address, under the
unallocated 0900 prefix, so it never collides with a real mobile. Nothing leaves the node:
the sim adapter keeps every payload in memory until a phone fetches it.
"""

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from mia.api.deps import DbSession, direct_loopback
from mia.channels import linking, outbox, registry
from mia.channels.base import InboundMessage
from mia.channels.inbound import handle_inbound
from mia.channels.simulator import SimAdapter
from mia.core import store
from mia.core.db import utcnow
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
    """The payloads sent to the address, removed from `sent`; other addresses' stay."""
    mine = [p.body for p in sim.sent if p.address == address]
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
    branch = session.get(Branch, person.branch_id)
    return PhoneOut(
        person_id=person.id,
        name=person.name,
        roles=person.roles,
        language=person.language,
        branch=branch.name if branch else "",
        address=identity.address,
    )


class SimMessage(BaseModel):
    address: str
    text: str = ""
    button: str | None = None  # a tapped button or list row title
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
        name=body.name,
        received_at=utcnow(),
    )
    inbound_id = await asyncio.to_thread(_store_inbound, session, msg)
    await handle_inbound(inbound_id)
    await outbox.send_due(utcnow(), on_demand_for=body.address)
    return _drain(sim, body.address)


@router.get("/messages")
async def poll(address: str) -> list[dict[str, Any]]:
    """Send what waits for this address (alerts, cards, tick messages) and return it."""
    sim = _sim()
    await outbox.send_due(utcnow(), on_demand_for=address)
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
