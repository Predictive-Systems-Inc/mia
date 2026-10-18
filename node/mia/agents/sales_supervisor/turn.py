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
from mia.agents.sales_supervisor import MANIFEST, actions, decider, replies
from mia.agents.sales_supervisor.tools import BINDINGS
from mia.agents.shift_supervisor.classifier import classify
from mia.chat.blocks import Block, ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import latest_message, reply_text, store_reply
from mia.core import events
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Event, Message, Thread
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail.models import RetailItem

log = logging.getLogger(__name__)
_BINDINGS = {b.tool_id: b for b in BINDINGS}
_warned = False  # the no-Jev warning is logged once per process


def _last_question(session: Session, thread: Thread) -> Message | None:
    """The thread's last Mia message, questions included (chat.service._last_mia)."""
    from mia.chat.service import _last_mia  # chat.service imports the registry, so this module

    return _last_mia(session, thread, questions=True)


def _tapped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Decision | None:
    """The stored decision behind a tapped button (Did you mean, which day, which item), if
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
    last = latest_message(session, thread, "assistant")
    return None, actions.build_query(deps, text, last.text if last else "")


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
    """The reply to a refused tool call: which day, no count to correct, not allowed."""
    status, message = out.get("status"), out.get("message")
    if status == "invalid" and message == "business_date":
        blocks, options = replies.ask_day(decision, deps.today, deps.lang)
        return _ask(session, deps, thread, blocks, options)
    if status == "invalid" and message == "count":
        item = session.get(RetailItem, str(decision.args.get("item_id")))
        name = item.name if item is not None else ""
        return reply_text(session, deps, thread, t("sales.no_count_today", deps.lang, item=name))
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
    if action == "clarify":
        return _did_you_mean(session, deps, thread, decision)
    tool = actions.ACTIONS[action].tool
    if tool is None:  # reply_only
        kind = str(decision.args.get("kind", "other"))
        return store_reply(session, deps, thread, replies.conversation_reply(kind, deps.lang))
    index = replies.unknown_item(decision.args)
    if index is not None:
        return _ask_item(session, deps, thread, decision, index)
    binding = _BINDINGS[f"{MANIFEST.id}.{tool}"]
    try:
        args = binding.input_type.model_validate(decision.args)
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    out = call_tool(deps, binding, args, new_id())
    if "status" in out and "message" in out:  # a ToolRefusal
        return _refusal(session, deps, thread, decision, tool, out)
    blocks = replies.tool_reply(tool, out, decision.args, deps.lang)
    return store_reply(session, deps, thread, blocks)


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
        "Sales: clerks reporting how many of each item they sold and for how much, daily and"
        " mid-day totals, sales targets, how today compares, why sales went well; not how much"
        " stock is left and not what to bake."
    ),
    handle_turn=handle_turn,
    run_due=None,  # Task 6
    stream_agent=None,
)
