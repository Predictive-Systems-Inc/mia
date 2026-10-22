"""The inventory manager's answer to one chat turn: Jev picks the action (MIA_DECIDER=jev), code
runs the tool and words the reply. The emergency script runs before this, in chat.service, for every agent."""

import asyncio
import html
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, AgentSpec, Turn, call_tool
from mia.agents.decider import THRESHOLD, Decision
from mia.agents.inventory_manager import MANIFEST, actions, calc, decider, due, replies, tools
from mia.agents.shift_supervisor.classifier import classify
from mia.chat.blocks import Block, ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import reply_text, store_reply
from mia.core import events
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Event, Message, Thread
from mia.core.rbac import Resource, get_rbac
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail.models import RetailIngredient, RetailItem

_BINDINGS = {b.tool_id: b for b in tools.BINDINGS}  # importing tools registers its handlers
_ORDER_TOOL = Resource(kind="tool", name=tools.DRAFT_ORDER)


def _last_question(session: Session, thread: Thread) -> Message | None:
    """The thread's last Mia message, questions included (chat.service._last_mia)."""
    from mia.chat.service import _last_mia  # chat.service imports the registry, so this module

    return _last_mia(session, thread, questions=True)


def _options(session: Session, deps: AgentDeps, thread: Thread) -> replies.Options:
    """The buttons of the thread's last Mia message (label to the decision a tap runs), when
    that message is a question asked today in the branch's time zone; else none."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = _last_question(session, thread)
    if asked is None or last is None or (asked.after or {}).get("message_id") != last.id:
        return {}
    if asked.timestamp.astimezone(ZoneInfo(deps.branch.timezone)).date() != deps.today:
        return {}
    return dict((asked.after or {}).get("options") or {})


def _tapped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Decision | None:
    """The decision behind a tapped button of the thread's last Mia message, asked today."""
    chosen = _options(session, deps, thread).get(text.strip())
    return Decision.model_validate(chosen) if chosen else None


def _query(
    session: Session, deps: AgentDeps, thread: Thread, text: str
) -> tuple[Decision | None, actions.Query | None]:
    """A decision already made (a tapped button, an injection), or the query for Jev."""
    tapped = _tapped(session, deps, thread, text)
    if tapped is not None:
        return tapped, None
    if classify(html.unescape(text), deps.today, deps.lang).injection:
        return Decision(action="reply_only", args={"kind": "injection"}, confidence=1), None
    last = _last_question(session, thread)
    said = session.exec(
        select(Message.id)
        .where(Message.thread_id == thread.id)
        .where(Message.role == "user")
        .order_by(col(Message.id).desc())
    ).first()
    query = actions.build_query(deps, text, last.text if last else "", message_id=said)
    return None, query


def _ask(
    session: Session, deps: AgentDeps, thread: Thread, blocks: list[Block], options: replies.Options
) -> ChatReply:
    """Store a question with buttons and remember what each button runs."""
    reply = store_reply(session, deps, thread, blocks)
    after = {"options": options, "message_id": reply.message_id}
    events.emit(session, "decision.clarify_asked", ("thread", thread.id), None, after, deps.actor)
    return reply


def _did_you_mean(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Ask "Did you mean" with a button per offerable alternative; with none, ask to rephrase."""
    options: replies.Options = {}
    for alt in decision.alternatives:
        spec = actions.ACTIONS.get(alt.action)
        if spec is None or spec.label_key is None or alt.missing is not None:
            continue
        label = t(spec.label_key, deps.lang)
        if label not in options:
            chosen = Decision(action=alt.action, args=alt.args, confidence=alt.probability)
            options[label] = chosen.model_dump(mode="json")
    if not options:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    other = t("clarify.something_else", deps.lang)
    blocks: list[Block] = [
        TextBlock(text=t("clarify.question", deps.lang)),
        QuickRepliesBlock(options=[*options, other]),
    ]
    options[other] = Decision(action="clarify", confidence=1.0).model_dump(mode="json")
    return _ask(session, deps, thread, blocks, options)


def _refusal(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    tool: str,
    out: dict[str, Any],
) -> ChatReply:
    """The reply to a refused tool call: an order by someone who may not order, else denied
    or rephrase. (No decision names another branch: draft_order's is stripped in _run.)"""
    if out["status"] == "denied":
        key = "stock.not_allowed" if tool == "draft_order" else "denied.generic"
    else:
        key = "clarify.rephrase"
    return reply_text(session, deps, thread, t(key, deps.lang))


def _order_summary(session: Session, deps: AgentDeps, order: tools.DraftOrderInput) -> str:
    """The order in words for the approval and the reply; the total is calc.order_total over
    the prices draft_order writes (a pack price only for a line in its ingredient's unit), so
    what the owner sees is what is written."""
    lines: list[tuple[int, str, str]] = []
    priced: list[tuple[int, int | None]] = []
    currency = "PHP"
    for line in order.lines:
        ing = session.get(RetailIngredient, line.ingredient_id)
        name, unit = (ing.name, line.unit or ing.unit) if ing else (line.ingredient_id, "")
        lines.append((line.quantity, unit, name))
        priced.append((line.quantity, ing.pack_price if ing and unit == ing.unit else None))
        currency = ing.currency if ing is not None else currency
    total = calc.order_total(priced)
    return replies.order_text(order.supplier, lines, total, currency, deps.lang)


def _offer(
    session: Session, deps: AgentDeps, out: dict[str, Any]
) -> tuple[list[Block], replies.Options] | None:
    """The order offer for the first ingredient reported low that has a supplier, when the
    person may order (quantity: twice the reorder point, in the ingredient's unit)."""
    if not get_rbac().check(deps.actor, _ORDER_TOOL, "request"):
        return None
    for e in tools.RecordEventsOutput.model_validate(out).recorded:
        ing = session.get(RetailIngredient, e.ingredient_id or "")
        if e.kind != "low" or ing is None or not ing.supplier:
            continue
        line = {"ingredient_id": ing.id, "quantity": ing.reorder_point * 2, "unit": ing.unit}
        return replies.ask_offer(ing.name, {"supplier": ing.supplier, "lines": [line]}, deps.lang)
    return None


def _run(
    session: Session, deps: AgentDeps, thread: Thread, tool: str, args: dict[str, Any]
) -> ChatReply:
    """Run the tool through the guard and word the reply: an order lands on the approval path
    (its words become the approval's summary); a low report offers an order."""
    binding = _BINDINGS[f"{MANIFEST.id}.{tool}"]
    if tool == "draft_order":  # ponytail: the person's own branch only; no branch from a decision
        args = {k: v for k, v in args.items() if k != "branch_id"}
    try:
        inp = binding.input_type.model_validate(args)
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    summary = _order_summary(session, deps, inp) if isinstance(inp, tools.DraftOrderInput) else ""
    out = call_tool(deps, binding, inp, new_id(), summary)
    if out.get("status") == "approval_required":
        blocks = replies.order_waiting(summary, str(out["approval_id"]), deps.lang)
        return store_reply(session, deps, thread, blocks)
    if "status" in out and "message" in out:  # a ToolRefusal
        return _refusal(session, deps, thread, tool, out)
    blocks = replies.tool_reply(tool, out, args, deps.lang, deps.branch.timezone)
    offer = _offer(session, deps, out) if tool == "record_events" else None
    if offer is None:
        return store_reply(session, deps, thread, blocks)
    return _ask(session, deps, thread, [*blocks, *offer[0]], offer[1])


def _answer_offer(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Yes drafts the offered order (a typed yes or no takes the button's order), No declines."""
    args = decision.args
    if "lines" not in args and args.get("yes"):
        offered = [Decision.model_validate(v) for v in _options(session, deps, thread).values()]
        args = next((d.args for d in offered if d.action == "answer_offer" and d.args["yes"]), {})
    if not args.get("yes"):
        key = "stock.offer_declined" if "yes" in args else "clarify.rephrase"
        return reply_text(session, deps, thread, t(key, deps.lang))
    order = {"supplier": args.get("supplier"), "lines": args.get("lines")}
    return _run(session, deps, thread, "draft_order", order)


def _names(session: Session, events: list[dict[str, Any]]) -> dict[str, str]:
    """The name of each item or ingredient the events are about, by id."""
    out: dict[str, str] = {}
    for e in events:
        if (item := session.get(RetailItem, e.get("item_id") or "")) is not None:
            out[item.id] = item.name
        if (ing := session.get(RetailIngredient, e.get("ingredient_id") or "")) is not None:
            out[ing.id] = ing.name
    return out


def _act(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """Log the decision, then ask what is missing (a waste reason asks with buttons), or run
    its tool through the guard and word the reply. Nothing is recorded before it is complete."""
    after = decision.model_dump(mode="json")
    events.emit(session, "decision.made", ("thread", thread.id), None, after, deps.actor)
    sure = decision.confidence >= THRESHOLD
    if decision.action == "clarify" and decision.missing == "reason" and sure:
        names = _names(session, decision.args.get("events") or [])
        return _ask(session, deps, thread, *replies.ask_reason(decision, names, deps.lang))
    said = decision.args.get("events") or []
    if decision.action == "clarify" and decision.missing == "kind" and sure and said:
        names = _names(session, said)  # a bare item and number: the kind buttons
        return _ask(session, deps, thread, *replies.ask_kind(decision, names, deps.lang))
    if decision.action == "clarify" and decision.missing == "quantity" and sure:
        name = next(iter(_names(session, decision.args.get("events") or []).values()), "")
        return reply_text(
            session, deps, thread, t("stock.ask.waste_quantity", deps.lang, item=name)
        )
    if decision.action == "clarify":
        return _did_you_mean(session, deps, thread, decision)
    if decision.action == "report_stock" and decision.args.get(decider.ON_HAND):
        return _run(session, deps, thread, "on_hand", decision.args)  # how many are left
    spec = actions.ACTIONS.get(decision.action)
    if spec is None:  # a tapped decision of another agent
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    if decision.action == "answer_offer":
        return _answer_offer(session, deps, thread, decision)
    if spec.tool is not None:
        return _run(session, deps, thread, spec.tool, decision.args)
    kind = str(decision.args.get("kind", "other"))
    return store_reply(session, deps, thread, replies.conversation_reply(kind, deps.lang))


def _unavailable(
    session: Session, deps: AgentDeps, thread: Thread, error: str | None = None
) -> ChatReply:
    """reply.unavailable; a Jev error is logged as decision.failed."""
    if error is not None:
        failed = {"error": error}
        events.emit(session, "decision.failed", ("thread", thread.id), None, failed, deps.actor)
    return reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


async def _jev_turn(
    session: Session, deps: AgentDeps, thread: Thread, text: str, ctx: EgressContext
) -> ChatReply:
    """DB work runs in worker threads; the Jev request runs with no write lock held."""
    decision, query = await asyncio.to_thread(_query, session, deps, thread, text)
    if decision is None and query is not None:
        await asyncio.to_thread(session.commit)
        try:
            with egress_context(replace(ctx, provider="typesafe", purpose=f"{MANIFEST.id}.decide")):
                decision = await decider.decide(query)
        except JevUnreachable:
            raise  # an outage: the chat defers the turn
        except JevError as exc:
            return await asyncio.to_thread(_unavailable, session, deps, thread, str(exc))
    assert decision is not None
    return await asyncio.to_thread(_act, session, deps, thread, decision)


async def handle_turn(turn: Turn) -> ChatReply:
    """A tapped button or Jev's decision worded by code; reply.unavailable without Jev."""
    session, deps, thread = turn.session, turn.deps, turn.thread
    if get_settings().MIA_DECIDER != "jev":
        return await asyncio.to_thread(_unavailable, session, deps, thread)
    return await _jev_turn(session, deps, thread, turn.text, turn.ctx)


SPEC = AgentSpec(
    manifest=MANIFEST,
    label_key=f"agent.{MANIFEST.id}.label",
    router_description=(
        "Kiosk stock: items sold out or running low at a kiosk, how many are left, leftovers (trays"
        " left over) and waste (items thrown away) at closing, how many of each item a kiosk needs"
        " on hand tomorrow, ingredients and packaging to buy before a day, placing supplier orders"
        " (not who approves them); not how many were sold and not the commissary's production. A"
        " sell-out message is stock."
    ),
    handle_turn=handle_turn,
    run_due=due.run_due,
    stream_agent=None,
)
