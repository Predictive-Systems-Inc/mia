"""The customer side: a member of the public writing to the shop's number (not a Person).

Guarantees: the sender becomes a customer principal (the customer row's ULID, never the
address) that the agent acts for, and rbac checks both (rule 4); the turn never reaches the
router, run_turn, a Thread or a staff agent; every customer_service.* event carries the agent
on behalf of the customer and no name or address (rule 5, `__redact__`); the throttle key is an HMAC of
`channel:address`; replies are out rows sent by send_pending, leased and committed before the
network, and never sent outside the 24-hour window (Q68); DB work runs in worker threads and
nothing holds the write lock across an await (rules 11, 12).
"""

import asyncio
import datetime as dt
import threading
import weakref
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import text as sql
from sqlmodel import Session, col, select

from mia.agents.base import Manifest, ToolLogEntry
from mia.agents.customer_service import MANIFEST
from mia.agents.customer_service.models import Customer, CustomerMessage
from mia.channels import outbox
from mia.channels.base import DeliveryResult, InboundMessage
from mia.chat.blocks import Block, TextBlock
from mia.core import auth, keys, orgconfig, store
from mia.core.db import session_scope, utcnow
from mia.core.models import Actor, Branch, ChannelInbound, Organisation, Principal
from mia.core.rbac import Rbac, get_rbac
from mia.i18n import t

THROTTLE = "customer_message"
WINDOW = dt.timedelta(hours=24)
SEEN = f"{MANIFEST.id}.customer_seen"
HELD = f"{MANIFEST.id}.held"
MESSAGE_IN = f"{MANIFEST.id}.message_in"
MESSAGE_OUT = f"{MANIFEST.id}.message_out"
SKIPPED = f"{MANIFEST.id}.reminder_skipped"
ATTEMPT = f"{MANIFEST.id}.attempt"
_BLOCKS: TypeAdapter[list[Block]] = TypeAdapter(list[Block])


_roles_loaded: "weakref.WeakSet[Rbac]" = weakref.WeakSet()
_roles_lock = threading.Lock()


def ensure_role() -> None:
    """Load the agent role's manifest grants into the node's enforcer, once per enforcer
    (build_agent does this for the LLM agents; the customer side builds none). Idempotent and
    safe from several threads; the public turn and the approval handlers call it first."""
    rbac = get_rbac()
    with _roles_lock:
        if rbac in _roles_loaded:
            return
        roles = MANIFEST.roles
        rbac.load_agent_role(roles.agent_role, roles.grants, roles.denies)
        _roles_loaded.add(rbac)


def runs() -> bool:
    """True when this organisation runs the customer service."""
    return MANIFEST.id in orgconfig.load().agents


def customer_actor(customer: Customer) -> Actor:
    """The agent acting on behalf of the customer. The customer principal's id is the row's
    ULID and its only role is `customer` (inherits nothing, no agent use)."""
    return Actor(
        principal=agent_principal(),
        on_behalf_of=Principal(type="customer", id=customer.id, roles=["customer"]),
        branch_id=customer.branch_id,
    )


def agent_principal() -> Principal:
    """The customer service's agent principal."""
    role = MANIFEST.roles.agent_role
    return Principal(type="agent", id=role, roles=[role])


def _agent_only(branch_id: str) -> Actor:
    """The agent alone, for an out row whose customer row is gone."""
    return Actor(principal=agent_principal(), branch_id=branch_id)


def window_open(last_inbound_at: dt.datetime | None, now: dt.datetime) -> bool:
    """True when the customer wrote less than 24 hours before now (strictly under)."""
    return last_inbound_at is not None and now - last_inbound_at < WINDOW


def throttle_key(channel: str, address: str) -> str:
    """The attempt key for the message throttle: an HMAC, so no address lands in a row."""
    return keys.code_hmac(f"{channel}:{address}")[:32] + "@-"


@dataclass
class CustomerDeps:
    """Per-turn dependencies of a customer's turn (a ToolDeps for guard and call_tool).
    `actor` is the agent on behalf of `customer`; there is no Person."""

    session: Session
    actor: Actor
    branch: Branch
    organisation_id: str
    today: dt.date
    lang: str
    manifest: Manifest
    customer: Customer
    tool_log: list[ToolLogEntry] = field(default_factory=list)
    approved: set[str] = field(default_factory=set)


def queue(
    session: Session, customer: Customer, blocks: list[Block], actor: Actor
) -> CustomerMessage:
    """Queue one reply to the customer (an out row, status queued; send_pending sends it).
    Event `customer_service.message_out` with the text and blocks redacted."""
    row = CustomerMessage(
        branch_id=customer.branch_id,
        customer_id=customer.id,
        direction="out",
        text="\n\n".join(b.text for b in blocks if isinstance(b, TextBlock)),
        blocks=[b.model_dump(mode="json") for b in blocks],
        at=utcnow(),
        status="queued",
    )
    return store.insert(session, row, actor, action=MESSAGE_OUT)


def _first_branch(session: Session) -> Branch:
    """The branch the node's number serves: the organisation's first branch by id (Q76)."""
    branch = session.exec(select(Branch).order_by(col(Branch.id))).first()
    if branch is None:
        raise LookupError("no branch on this node")
    return branch


def _find(session: Session, msg: InboundMessage) -> Customer | None:
    return session.exec(
        select(Customer)
        .where(Customer.channel == msg.channel)
        .where(Customer.address == msg.address)
    ).first()


def _upsert(
    session: Session, row: Customer | None, msg: InboundMessage, now: dt.datetime
) -> Customer:
    if row is None:
        branch = _first_branch(session)
        org = session.get(Organisation, branch.organisation_id)
        row = Customer(
            branch_id=branch.id,
            channel=msg.channel,
            address=msg.address,
            name=msg.name,
            language=org.default_language if org else "en",
            first_seen_at=now,
            last_inbound_at=now,
        )
        return store.insert(session, row, customer_actor(row), action=SEEN)
    changes: dict[str, object] = {"last_inbound_at": now}
    if msg.name and msg.name != row.name:
        changes["name"] = msg.name
    return store.update(session, row, changes, customer_actor(row), action=SEEN)


def _arrive(
    session: Session, inbound_id: str, msg: InboundMessage, text: str, now: dt.datetime
) -> Customer | None:
    """Record the message. None when the turn stops here: the customer is held (ignored, no
    write and no event at all), or is over the hourly limit (held now, one hold reply queued)."""
    found = _find(session, msg)
    if found is not None and found.held_until is not None and found.held_until > now:
        return None
    customer = _upsert(session, found, msg, now)
    actor = customer_actor(customer)
    inbound = session.get(ChannelInbound, inbound_id)
    if inbound is not None:
        changes = {"branch_id": customer.branch_id}
        store.update(session, inbound, changes, actor, action="channel.matched")
    key = throttle_key(msg.channel, msg.address)
    per_hour = orgconfig.load().customer_service.messages_per_hour
    limit = auth.Limit(per_hour, auth.H1, auth.H1)
    if auth.throttled(session, THROTTLE, key, now, limit=limit):
        store.update(session, customer, {"held_until": now + auth.H1}, actor, action=HELD)
        queue(session, customer, [TextBlock(text=t("cs.held", customer.language))], actor)
        return None
    auth.record_attempt(session, THROTTLE, key, False, now, actor=actor, action=ATTEMPT)
    message = CustomerMessage(
        branch_id=customer.branch_id,
        customer_id=customer.id,
        direction="in",
        text=text,
        at=now,
    )
    store.insert(session, message, actor, action=MESSAGE_IN)
    return customer


def _deps(session: Session, customer: Customer, now: dt.datetime) -> CustomerDeps:
    branch = session.get(Branch, customer.branch_id)
    if branch is None:
        raise LookupError(f"branch {customer.branch_id} not found")
    return CustomerDeps(
        session=session,
        actor=customer_actor(customer),
        branch=branch,
        organisation_id=branch.organisation_id,
        today=now.astimezone(ZoneInfo(branch.timezone)).date(),
        lang=customer.language,
        manifest=MANIFEST,
        customer=customer,
    )


async def _decide(customer: Customer, text: str) -> str:
    """The action the message wants."""
    return "greeting"  # ponytail: Task 5 wires the Jev decider here (after the commit)


def _act(deps: CustomerDeps, action: str) -> list[Block]:
    """The reply blocks for one decided action. Every action words the menu for now."""
    return [TextBlock(text=t("cs.menu", deps.lang))]  # ponytail: Task 5 dispatches CUSTOMER


def _answer(session: Session, customer: Customer, action: str, now: dt.datetime) -> None:
    deps = _deps(session, customer, now)
    queue(session, customer, _act(deps, action), deps.actor)


async def public_turn(
    session: Session, inbound_id: str, msg: InboundMessage, now: dt.datetime
) -> None:
    """One customer message: arrive (customer row, hold and throttle, message row), commit,
    decide, act, commit, then send what is queued. The caller marks the inbound row."""
    ensure_role()
    text = (msg.button or msg.text).strip()
    customer = await asyncio.to_thread(_arrive, session, inbound_id, msg, text, now)
    await asyncio.to_thread(session.commit)  # nothing holds the write lock across Jev
    if customer is not None:
        action = await _decide(customer, text)
        await asyncio.to_thread(_answer, session, customer, action, now)
        await asyncio.to_thread(session.commit)
    await send_pending(utcnow())


class _Lease(BaseModel):
    id: str
    channel: str
    address: str
    lang: str
    blocks: list[Block]


def _lease(now: dt.datetime) -> list[_Lease]:
    """Mark due out rows `sending` (inside the window) or `skipped` (outside it, with
    `customer_service.reminder_skipped`), committed before any send."""
    leases = []
    with session_scope() as session:
        # The write lock first, so two senders never lease the same row (see events._last_hash).
        session.execute(sql("UPDATE customer_service_messages SET id = id WHERE 0"))
        rows = session.exec(
            select(CustomerMessage)
            .where(CustomerMessage.direction == "out")
            .where(CustomerMessage.status == "queued")
            .order_by(col(CustomerMessage.id))
        ).all()
        for row in rows:
            customer = session.get(Customer, row.customer_id)
            if customer is None:  # nobody to send to: never left queued
                failed = f"{MANIFEST.id}.message_failed"
                agent = _agent_only(row.branch_id)
                store.update(session, row, {"status": "failed"}, agent, action=failed)
                continue
            actor = customer_actor(customer)
            if not window_open(customer.last_inbound_at, now):
                store.update(session, row, {"status": "skipped"}, actor, action=SKIPPED)
                continue
            store.update(
                session, row, {"status": "sending"}, actor, action=f"{MANIFEST.id}.message_sending"
            )
            leases.append(
                _Lease(
                    id=row.id,
                    channel=customer.channel,
                    address=customer.address,
                    lang=customer.language,
                    blocks=_BLOCKS.validate_python(row.blocks),
                )
            )
    return leases


def _record(lease: _Lease, results: list[DeliveryResult]) -> bool:
    """`sent` with the channel's message id, or `failed` (never resent: a part may be out)."""
    ok = all(r.ok for r in results)
    with session_scope() as session:
        row = session.get(CustomerMessage, lease.id)
        if row is None:
            return ok
        customer = session.get(Customer, row.customer_id)
        actor = customer_actor(customer) if customer else _agent_only(row.branch_id)
        changes: dict[str, object] = {"status": "sent" if ok else "failed"}
        if ok and results:
            changes["channel_message_id"] = results[-1].channel_message_id
        action = f"{MANIFEST.id}.message_{changes['status']}"
        store.update(session, row, changes, actor, action=action)
    return ok


async def send_pending(now: dt.datetime) -> int:
    """Send every queued reply once, each leased and committed before the network. Returns how
    many were sent."""
    sent = 0
    for lease in await asyncio.to_thread(_lease, now):
        try:
            results = await outbox.send_direct(
                lease.channel, lease.address, lease.blocks, lease.lang
            )
        except KeyError:  # the channel's adapter is not registered
            results = [DeliveryResult(ok=False, error_code="no_adapter")]
        sent += await asyncio.to_thread(_record, lease, results)
    return sent
