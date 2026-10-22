"""The sales supervisor's answer to one chat turn. Jev picks the action (MIA_DECIDER=jev), code
runs the tool and words the reply; there is no LLM agent and no classifier route. The
emergency script runs before this, in chat.service, for every agent."""

import asyncio
import html
import logging
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, AgentSpec, Turn, call_tool
from mia.agents.decider import THRESHOLD, Decision
from mia.agents.sales_supervisor import MANIFEST, actions, decider, due, replies
from mia.agents.sales_supervisor.tools import BINDINGS, RecordReceiptOutput, receipt_out
from mia.agents.shift_supervisor.classifier import classify
from mia.chat.blocks import Block, ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import reply_text, store_reply
from mia.core import events, sales
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Approval, Event, Message, SalesReceipt, Thread
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail.models import RetailItem

log = logging.getLogger(__name__)
_BINDINGS = {b.tool_id: b for b in BINDINGS}
_warned = False  # the no-Jev warning is logged once per process
RECEIPT_TOOLS = ("void_receipt", "refund_receipt")
# a void's or refund's refusal code -> its reply (each takes the receipt number as no)
RECEIPT_REFUSALS = {
    "receipt": "sales.void.no_receipt",
    "status": "sales.void.already",
    "kind": "sales.void.refund_kind",
    "refunded": "sales.void.refunded",
    "session_closed": "sales.void.closed",
    "quantity": "sales.refund.too_much",
    "refunded_line": "sales.refund.too_much",
    "approved_amount": "sales.refund.too_much",
    "counts_kiosk": "sales.receipts.counts_kiosk",
}


def _last_question(session: Session, thread: Thread) -> Message | None:
    """The thread's last Mia message, questions included (chat.service._last_mia)."""
    from mia.chat.service import _last_mia  # chat.service imports the registry, so this module

    return _last_mia(session, thread, questions=True)


def _tapped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Decision | None:
    """The stored decision behind a tapped button (Did you mean, which item), if
    text is one. A button only counts while its question is the thread's last Mia message and
    was asked today in the branch's time zone."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = _last_question(session, thread)
    if asked is None or last is None or (asked.after or {}).get("message_id") != last.id:
        return None
    if asked.timestamp.astimezone(ZoneInfo(deps.branch.timezone)).date() != deps.today:
        return None
    chosen = ((asked.after or {}).get("options") or {}).get(text.strip())
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
    last = _last_question(session, thread)  # a notification (the why question) counts
    said = session.exec(
        select(Message.id)
        .where(Message.thread_id == thread.id)
        .where(Message.role == "user")
        .order_by(col(Message.id).desc())
    ).first()
    previous, previous_id = (last.text, last.id) if last else ("", None)
    query = actions.build_query(deps, text, previous, message_id=said, previous_id=previous_id)
    return None, query


def _ask(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    blocks: list[Block],
    options: replies.Options,
) -> ChatReply:
    """Store a question with buttons and remember what each button runs."""
    reply = store_reply(session, deps, thread, blocks)
    after = {"options": options, "message_id": reply.message_id}
    events.emit(session, "decision.clarify_asked", ("thread", thread.id), None, after, deps.actor)
    return reply


def _did_you_mean(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision
) -> ChatReply:
    """Ask "Did you mean" with one button per offerable alternative plus Something else; with
    none, ask to rephrase."""
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


def _ask_item(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision, index: int
) -> ChatReply:
    """Which item a count is, from the candidates the decider kept."""
    count = decision.args["items"][index] if "items" in decision.args else decision.args
    names = {}
    for item_id in count.get("candidates") or []:
        item = session.get(RetailItem, item_id)
        if item is not None:
            names[item.id] = item.name
    if not names:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    blocks, options = replies.ask_item(decision, index, names, deps.lang)
    return _ask(session, deps, thread, blocks, options)


def _refusal(
    session: Session, deps: AgentDeps, thread: Thread, decision: Decision, tool: str, out: Any
) -> ChatReply:
    """The reply to a refused tool call: no count to correct, another branch or a target not
    allowed, else denied or rephrase (a stated day other than today or yesterday too)."""
    status, message = out.get("status"), out.get("message")
    if status == "invalid" and tool in RECEIPT_TOOLS and message in RECEIPT_REFUSALS:
        no = str(decision.args.get("receipt_no", ""))
        return reply_text(session, deps, thread, t(RECEIPT_REFUSALS[message], deps.lang, no=no))
    if status == "invalid" and message == "count":
        item = session.get(RetailItem, str(decision.args.get("item_id")))
        name = item.name if item is not None else ""
        return reply_text(session, deps, thread, t("sales.no_count_today", deps.lang, item=name))
    named = decision.args.get("branch_id")
    if status == "denied" and named is not None and named != deps.branch.id:
        branch = deps.branch.name
        return reply_text(
            session, deps, thread, t("sales.not_allowed.branch", deps.lang, branch=branch)
        )
    if status == "denied" and tool == "set_target":
        return reply_text(session, deps, thread, t("sales.not_allowed", deps.lang))
    if status == "denied":
        return reply_text(session, deps, thread, t("denied.generic", deps.lang))
    return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))


def _act(session: Session, deps: AgentDeps, thread: Thread, decision: Decision) -> ChatReply:
    """Log the decision, then ask what is missing or run its tool through the guard and word
    the reply. A count without an item asks which item; nothing is recorded until each count
    has one."""
    events.emit(
        session,
        "decision.made",
        ("thread", thread.id),
        None,
        decision.model_dump(mode="json"),
        deps.actor,
    )
    action = decision.action
    item_missing = (decision.missing or "").startswith("item_")
    if action == "clarify" and item_missing and decision.confidence >= THRESHOLD:
        action = decision.raw_action  # the action is clear, one count's item is not
    if (
        action == "clarify"
        and decision.missing == "receipt_no"
        and decision.confidence >= THRESHOLD
    ):
        action = decision.raw_action or action  # the action is clear, its receipt number is not
    if action == "clarify" and decision.missing == "tender":
        if "typed_total" not in decision.args:  # a count: two tenders are sent apart
            return reply_text(session, deps, thread, t("sales.ask.tender", deps.lang))
        if decision.confidence >= THRESHOLD:
            action = decision.raw_action  # a clear receipt: the tender buttons below
    if action == "clarify":
        return _did_you_mean(session, deps, thread, decision)
    spec = actions.ACTIONS.get(action)
    if spec is None:  # a tapped decision of another agent
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    tool = spec.tool
    if tool is None:  # reply_only
        kind = str(decision.args.get("kind", "other"))
        return store_reply(session, deps, thread, replies.conversation_reply(kind, deps.lang))
    if tool in RECEIPT_TOOLS and sales.source_of(deps.branch, deps.today) == "counts":
        return reply_text(session, deps, thread, t("sales.receipts.counts_kiosk", deps.lang))
    if tool in RECEIPT_TOOLS and not decision.args.get("receipt_no"):
        return reply_text(session, deps, thread, t("sales.receipt.which_no", deps.lang))
    index = replies.unknown_item(decision.args)
    if index is not None:
        return _ask_item(session, deps, thread, decision, index)
    if tool == "record_receipt" and decision.args.get("tender") is None:
        blocks, options = replies.ask_tender(decision, deps.lang)
        return _ask(session, deps, thread, blocks, options)
    binding = _BINDINGS[f"{MANIFEST.id}.{tool}"]
    try:
        args = binding.input_type.model_validate(decision.args)
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    out = call_tool(deps, binding, args, new_id())
    if out.get("status") == "approval_required" and tool in RECEIPT_TOOLS:
        return store_reply(session, deps, thread, _asked(session, deps, str(out["approval_id"])))
    if "status" in out and "message" in out:  # a ToolRefusal
        return _refusal(session, deps, thread, decision, tool, out)
    if tool == "record_receipt" and out["status"] == "no_session":
        return reply_text(session, deps, thread, t("sales.receipt.no_session", deps.lang))
    if tool == "record_receipt" and out["status"] == "total_differs":
        receipt = RecordReceiptOutput.model_validate(out)
        blocks, options = replies.ask_total(decision, receipt, deps.lang)
        return _ask(session, deps, thread, blocks, options)
    blocks = replies.tool_reply(tool, out, decision.args, deps.lang)
    if tool == "record_counts" and decision.args.get("as_count"):
        blocks = _as_count(session, deps, str(out["business_date"])) + blocks
    return store_reply(session, deps, thread, blocks)


def _asked(session: Session, deps: AgentDeps, approval_id: str) -> list[Block]:
    """The reply to a void or refund sent for approval, from the approval: the receipt it
    names (its lines and total) for a void, the computed amount for a refund."""
    approval = session.get(Approval, approval_id)
    receipt = session.get(SalesReceipt, approval.subject_id) if approval else None
    assert approval is not None and receipt is not None  # the binding's request wrote both
    if approval.type == sales.VOID:
        return replies.void_asked(receipt_out(session, deps.branch, receipt), deps.lang)
    amount = int(approval.evidence["amount"])
    return replies.refund_asked(receipt.receipt_no, amount, receipt.currency, deps.lang)


AS_COUNT = "sales.as_count_noted"  # marker: the counts-kiosk notice was said (person, date)


def _as_count(session: Session, deps: AgentDeps, day: str) -> list[Block]:
    """The counts-kiosk notice, once per person and business date (an AS_COUNT marker)."""
    events.write_lock(session)  # read the marker and write it in one transaction (rule 11)
    said = session.exec(
        select(Event).where(Event.action == AS_COUNT).where(Event.entity_id == deps.person.id)
    )
    if any((e.after or {}).get("date") == day for e in said):
        return []
    events.emit(session, AS_COUNT, deps.person, None, {"date": day}, deps.actor)
    return [TextBlock(text=t("sales.receipt.as_count", deps.lang))]


def _failed(session: Session, deps: AgentDeps, thread: Thread, error: str) -> ChatReply:
    events.emit(
        session, "decision.failed", ("thread", thread.id), None, {"error": error}, deps.actor
    )
    return reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


async def _jev_turn(
    session: Session, deps: AgentDeps, thread: Thread, text: str, ctx: EgressContext
) -> ChatReply:
    """DB work runs in worker threads; the Jev request runs with no write lock held (the
    query step only reads, and the user message was committed by the chat)."""
    decision, query = await asyncio.to_thread(_query, session, deps, thread, text)
    if decision is None and query is not None:
        await asyncio.to_thread(session.commit)
        try:
            with egress_context(replace(ctx, provider="typesafe", purpose=f"{MANIFEST.id}.decide")):
                decision = await decider.decide(query)
        except JevUnreachable:
            raise  # an outage: the chat defers the turn
        except JevError as exc:
            return await asyncio.to_thread(_failed, session, deps, thread, str(exc))
    assert decision is not None
    return await asyncio.to_thread(_act, session, deps, thread, decision)


def _unavailable(session: Session, deps: AgentDeps, thread: Thread) -> ChatReply:
    global _warned
    if not _warned:
        log.warning("%s answers only with MIA_DECIDER=jev", MANIFEST.id)
        _warned = True
    return reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


async def handle_turn(turn: Turn) -> ChatReply:
    """The sales supervisor's answer to one stored message: a tapped button, Jev's decision
    run through the tool guard, or reply.unavailable without Jev. The caller commits."""
    session, deps, thread = turn.session, turn.deps, turn.thread
    if get_settings().MIA_DECIDER != "jev":
        return await asyncio.to_thread(_unavailable, session, deps, thread)
    return await _jev_turn(session, deps, thread, turn.text, turn.ctx)


SPEC = AgentSpec(
    manifest=MANIFEST,
    label_key=f"agent.{MANIFEST.id}.label",
    router_description=(
        "Sales: clerks reporting how many of each item they sold and for how much, corrections to a"
        " reported count (sorry, 4 special not 3), daily, morning and mid-day sales totals, sales"
        " targets, how today compares, the best day, why sales went well; not how much stock is"
        " left, not what to bake, not how a clerk is doing and not advice on how to sell more."
    ),
    handle_turn=handle_turn,
    run_due=due.run_due,
    stream_agent=None,
)
