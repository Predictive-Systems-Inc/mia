"""The customer side: a member of the public writing to the shop's number (not a Person).

Guarantees: the sender becomes a customer principal (the customer row's ULID, never the
address) that the agent acts for, and rbac checks both (rule 4); the turn never reaches the
router, run_turn, a Thread or a staff agent; every event this module writes for a customer
carries the agent on behalf of the customer, and no customer_service.* event carries a name or
address (rule 5, `__redact__`); a reply staff cause (mark_ready, an order decision) is queued
by the staff tool or the approval handler, with that actor; the throttle key is an HMAC of
`channel:address`; a node-wide budget caps public turns (Jev requests) per hour; replies are
out rows sent by send_pending, leased and committed before the network, and never sent
outside the 24-hour window (Q68); DB work runs in worker threads and nothing holds the write
lock across an await (rules 11, 12). A held message writes no customer event: only its
inbound row's channel.received, channel.inbound_processing and channel.inbound_done.
"""

import asyncio
import datetime as dt
import logging
import re
import threading
import weakref
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import text as sql
from sqlmodel import Session, col, func, select

from mia.agents.base import Manifest, ToolLogEntry, call_tool
from mia.agents.customer_service import MANIFEST, actions, calc, decider, replies
from mia.agents.customer_service.models import Customer, CustomerMessage
from mia.agents.decider import Decision
from mia.channels import outbox
from mia.channels.base import DeliveryResult, InboundMessage
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.core import auth, events, keys, orgconfig, store
from mia.core.db import session_scope, utcnow
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError
from mia.core.models import Actor, Branch, ChannelInbound, Organisation, Principal
from mia.core.rbac import Rbac, get_rbac
from mia.i18n import SUPPORTED, t
from mia.settings import get_settings
from mia.templates.retail import hours as shop_hours

THROTTLE = "customer_message"
WINDOW = dt.timedelta(hours=24)
SEEN = f"{MANIFEST.id}.customer_seen"
HELD = f"{MANIFEST.id}.held"
MESSAGE_IN = f"{MANIFEST.id}.message_in"
MESSAGE_OUT = f"{MANIFEST.id}.message_out"
# Two markers share this action: _lease writes it on every out row found outside the window
# (the row's status `skipped`), and due.pickup_reminders on the order whose reminder was due
# with the window closed (its pickup time). The entity (a message or an order) tells them apart.
SKIPPED = f"{MANIFEST.id}.reminder_skipped"
ATTEMPT = f"{MANIFEST.id}.attempt"
LANGUAGE = f"{MANIFEST.id}.language_set"
TURN_FAILED = f"{MANIFEST.id}.turn_failed"
BUDGET_HELD = f"{MANIFEST.id}.budget_held"
log = logging.getLogger(__name__)
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


def _public_calls(session: Session, now: dt.datetime) -> int:
    """Public turns in the hour before `now`, node-wide: each recorded inbound message is one
    Jev request (a held or budget-held message records none)."""
    since = (now - auth.H1).astimezone(dt.UTC)  # stored times are UTC; SQL compares strings
    stmt = (
        select(func.count())
        .select_from(CustomerMessage)
        .where(CustomerMessage.direction == "in")
        .where(col(CustomerMessage.at) > since)
    )
    return session.exec(stmt).one()


def _arrive(
    session: Session, inbound_id: str, msg: InboundMessage, text: str, now: dt.datetime
) -> Customer | None:
    """Record the message. None when the turn stops here: the customer is held (ignored, no
    customer write or event), is over the hourly limit (held now, one hold reply queued), or
    the node is over its public budget (cs.held queued, `customer_service.budget_held`).
    The write lock comes first, so two first messages from one number (two webhook posts)
    never both read no row and insert (rule 11, the `_lease` pattern)."""
    session.execute(sql("UPDATE customer_service_customers SET id = id WHERE 0"))
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
    if _public_calls(session, now) >= orgconfig.load().customer_service.public_calls_per_hour:
        events.emit(session, BUDGET_HELD, (Customer.__tablename__, customer.id), None, {}, actor)
        queue(session, customer, [TextBlock(text=t("cs.held", customer.language))], actor)
        return None
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


def _last(session: Session, customer: Customer, direction: str, skip: int = 0) -> str | None:
    """The text of the customer's latest message in that direction (skipping `skip`)."""
    row = session.exec(
        select(CustomerMessage)
        .where(CustomerMessage.customer_id == customer.id)
        .where(CustomerMessage.direction == direction)
        .order_by(col(CustomerMessage.id).desc())
        .offset(skip)
    ).first()
    return row.text if row else None


def _last_out(session: Session, customer: Customer) -> tuple[str, list[str], dt.datetime | None]:
    """The latest reply's text, its quick-reply options and when it was queued."""
    row = session.exec(
        select(CustomerMessage)
        .where(CustomerMessage.customer_id == customer.id)
        .where(CustomerMessage.direction == "out")
        .order_by(col(CustomerMessage.id).desc())
    ).first()
    if row is None:
        return "", [], None
    quick = [b for b in _BLOCKS.validate_python(row.blocks) if isinstance(b, QuickRepliesBlock)]
    return row.text, [o for b in quick for o in b.options], row.at


def _scrubbed(customer: Customer, text: str) -> str:
    """The text with the customer's own stored name (and each part of it) replaced as whole
    words, so it never reaches Jev (rule 8) while "market" from Mark stays a word. Unlike the
    staff pseudonymiser, no inflected form is taken."""
    parts = sorted({*(customer.name or "").split()}, key=len, reverse=True)
    if not parts:
        return text
    pattern = r"\b(?:" + "|".join(map(re.escape, parts)) + r")\b"
    return re.sub(pattern, "Customer", text, flags=re.IGNORECASE)


def _query(session: Session, customer: Customer, text: str, now: dt.datetime) -> actions.Query:
    """The Jev query for the message (reads only). A tapped pickup time answers the time
    question, so the order message before it is asked again with the time added."""
    branch = session.get(Branch, customer.branch_id)
    if branch is None:
        raise LookupError(f"branch {customer.branch_id} not found")
    lang, tz = customer.language, ZoneInfo(branch.timezone)
    today = now.astimezone(tz).date()
    previous, options, asked = _last_out(session, customer)
    same_day = asked is not None and asked.astimezone(tz).date() == today
    if previous == t("cs.ask_time", lang) and text in options and same_day:
        text = f"{_last(session, customer, 'in', skip=1) or ''} {text}"
    message = _scrubbed(customer, text)
    return actions.build_query(session, branch, "customer", message, previous, today, lang)


def _context(session: Session, customer: Customer) -> EgressContext:
    branch = session.get(Branch, customer.branch_id)
    org = branch.organisation_id if branch else ""
    level = get_settings().MIA_EGRESS_LEVEL
    purpose = f"{MANIFEST.id}.decide"
    actor = customer_actor(customer)
    return EgressContext(session, actor, org, MANIFEST.id, purpose, level, provider="typesafe")


async def _decide(session: Session, customer: Customer, text: str, now: dt.datetime) -> Decision:
    """Jev's decision for the message: the query is read in a worker thread, then the request
    goes out with nothing uncommitted (rule 11). Raises JevError (JevUnreachable included)."""
    query = await asyncio.to_thread(_query, session, customer, text, now)
    await asyncio.to_thread(session.commit)
    with egress_context(_context(session, customer)):
        return await decider.decide(query)


def _call(deps: CustomerDeps, tool: str, args: BaseModel) -> dict[str, Any]:
    """Run one customer tool through the guard (call_tool commits after it)."""
    tool_id = f"{MANIFEST.id}.{tool}"
    binding = next((b for b in tools.BINDINGS if b.tool_id == tool_id), None)
    if binding is None:
        raise LookupError(f"no binding for {tool_id}")
    return call_tool(deps, binding, args, new_id())


def _open_times(deps: CustomerDeps, day: dt.date, now: dt.datetime) -> list[str]:
    """Up to three whole hours of `day` the shop is open, after now: the time question's
    quick replies (WhatsApp shows at most three buttons)."""
    rows = shop_hours.load(deps.session, deps.branch.id)
    if not shop_hours.open_days(rows)(day):
        return []
    at, end = calc.hours_span(deps.branch, rows, day)
    times: list[str] = []
    while at < end and len(times) < 3:
        if at > now:
            times.append(f"{at:%H:%M}")
        at += dt.timedelta(hours=1)
    return times


def _order(deps: CustomerDeps, decision: Decision, now: dt.datetime) -> list[Block]:
    """Place the order the decision reads. The order_id is made here, never taken from the
    decision; the guard asks staff and the order is recorded waiting for that approval."""
    a, tz = decision.args, deps.branch.timezone
    day = dt.date.fromisoformat(str(a["day"]))
    if not a.get("time"):
        return replies.ask_time(deps.lang, _open_times(deps, day, now))
    args = tools.PlaceOrderInput(
        order_id=new_id(),
        lines=[tools.LineIn(item_id=ln["item_id"], quantity=ln["quantity"]) for ln in a["lines"]],
        fulfilment=a["fulfilment"],
        pickup_at=calc.pickup_at(day, dt.time.fromisoformat(str(a["time"])), tz),
        delivery_area=a.get("area"),
    )
    out = _call(deps, "place_order", args)
    if out["status"] == "approval_required":
        tools.record_waiting(deps, args, str(out["approval_id"]))
        out = {"time": replies.hhmm(args.pickup_at, tz)}
    return replies.customer_reply("place_order", out, deps.lang, tz)


def _act(deps: CustomerDeps, decision: Decision, text: str, now: dt.datetime) -> list[Block]:
    """The reply blocks for one decision: each CUSTOMER action through its tool; a missing
    pickup time asks for one; any other action (greeting, clarify) words the menu."""
    action, a, tz = decision.action, decision.args, deps.branch.timezone
    if action == "clarify" and decision.missing == "pickup_time":
        day = dt.date.fromisoformat(str(a.get("day") or deps.today.isoformat()))
        return replies.ask_time(deps.lang, _open_times(deps, day, now))
    if action == "language_switch" and a.get("language") in SUPPORTED:
        _call(deps, "set_language", tools.LanguageInput(language=str(a["language"])))
        deps.lang = deps.customer.language  # the row the tool wrote (or left, on a refusal)
        return replies.customer_reply("greeting", {}, deps.lang, tz)
    inputs: dict[str, BaseModel] = {
        "hours": tools.EmptyInput(),
        "prices": tools.PricesInput(item_ids=a.get("item_ids") or []),
        "delivery_area": tools.AreaInput(name=a.get("area")),
        "order_status": tools.EmptyInput(),
        "cancel_order": tools.EmptyInput(),
        "complaint": tools.ComplainInput(text=text[:2000]),
    }
    if action == "place_order":
        return _order(deps, decision, now)
    if action not in inputs:
        return replies.customer_reply("greeting", {}, deps.lang, tz)
    spec = actions.ACTIONS[action]
    out = _call(deps, str(spec.tool), inputs[action])
    if action == "delivery_area" and a.get("area") is None and out.get("pickup_branch"):
        areas = orgconfig.load().delivery_areas  # no area named: the configured ones
        return replies.delivery_areas(areas, out["pickup_branch"], deps.lang)
    return replies.customer_reply(action, out, deps.lang, tz)


def _answer(
    session: Session, customer: Customer, decision: Decision, text: str, now: dt.datetime
) -> None:
    deps = _deps(session, customer, now)
    queue(session, customer, _act(deps, decision, text, now), deps.actor)


def _unavailable(session: Session, customer_id: str, error: str) -> None:
    """After a failed turn: roll back what it left, write customer_service.turn_failed with
    the exception class only (no message text), then queue cs.unavailable."""
    session.rollback()
    customer = session.get(Customer, customer_id)
    if customer is not None:
        actor = customer_actor(customer)
        entity = (Customer.__tablename__, customer.id)
        events.emit(session, TURN_FAILED, entity, None, {"error": error}, actor)
        blocks: list[Block] = [TextBlock(text=t("cs.unavailable", customer.language))]
        queue(session, customer, blocks, actor)
    session.commit()


async def _turn(session: Session, customer: Customer, text: str, now: dt.datetime) -> None:
    """Decide and answer; any failure (Jev unreachable, egress off, a bug) is cs.unavailable
    in the customer's language, never silence. Ceiling (ponytail): a tool that committed (call_tool
    commits after each tool, a cancel done) followed by a failed step still reads
    "unavailable" to the customer, though the action stands; the staff notice it sent tells
    the shop. Say what was done instead if this confuses customers."""
    customer_id = customer.id
    try:
        if get_settings().MIA_DECIDER != "jev":
            raise JevError("the Jev decider is off")
        decision = await _decide(session, customer, text, now)
        await asyncio.to_thread(_answer, session, customer, decision, text, now)
        await asyncio.to_thread(session.commit)
    except Exception as exc:
        log.exception("customer turn failed")  # the traceback stays on the node
        await asyncio.to_thread(_unavailable, session, customer_id, type(exc).__name__)


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
        await _turn(session, customer, text, now)
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


# tools imports this module (CustomerDeps, queue); imported last so either loads first, and the
# order approval handlers register wherever the public turn runs.
from mia.agents.customer_service import tools
