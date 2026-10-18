"""The shift supervisor's answer to one chat turn: template replies, Did you mean questions,
Jev (MIA_DECIDER=jev) or the Pydantic AI agent. The emergency script runs before this, in
chat.service, for every agent."""

import asyncio
import datetime as dt
import html
import time
from dataclasses import replace
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from pydantic_ai.exceptions import UsageLimitExceeded
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, AgentSpec, Turn, call_tool
from mia.agents.shift_supervisor import MANIFEST, actions, alerts, cover, decider, replies
from mia.agents.shift_supervisor.agent import get_agent
from mia.agents.shift_supervisor.classifier import classify
from mia.agents.shift_supervisor.tools import BINDINGS
from mia.chat.blocks import ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.replies import (
    USAGE_LIMITS,
    finish,
    latest_message,
    reply_capped,
    reply_text,
    store_reply,
    wrap_user_text,
)
from mia.core import events
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.jev import JevError
from mia.core.models import Event, Message, Thread
from mia.i18n import t
from mia.i18n.strings import STRINGS
from mia.learning import catalogue
from mia.settings import get_settings
from mia.skills import runtime
from mia.skills.roles import load_role_plan
from mia.skills.routing import Route, route


def _pending_clarification(session: Session, thread: Thread) -> Event | None:
    """The clarify question that is the thread's last assistant message, if any."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "intent.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = latest_message(session, thread, "assistant")
    if asked is None or last is None or (asked.after or {}).get("message_id") != last.id:
        return None
    return asked


@cache
def _template_conversation_ids() -> frozenset[str]:
    return frozenset(c.id for c in catalogue.conversation_intents() if c.handling == "template")


def _classify_turn(
    session: Session, deps: AgentDeps, thread: Thread, text: str
) -> tuple[Route, str]:
    """Route one turn; returns the route and the text the agent should read.

    An exact option label answers a pending question: the agent then reads the ORIGINAL message
    (not the label) with the chosen intent, or a template reply is sent for a template intent.
    Any other text is classified. Commits its events, so no write lock is held while the
    model runs."""
    pending = _pending_clarification(session, thread)
    options = (pending.after or {}).get("options") or {} if pending else {}
    chosen = options.get(text.strip())
    if pending is not None and pending.after is not None and chosen is not None:
        events.emit(
            session,
            "intent.clarified",
            ("thread", thread.id),
            None,
            {
                "intent": chosen,
                "asked_event_id": pending.id,
                "original_message_id": pending.after["original_message_id"],
            },
            deps.actor,
        )
        session.commit()
        if chosen == "other":
            return Route(kind="clarify"), text  # nothing fitted: ask to rephrase
        original = session.get(Message, pending.after["original_message_id"])
        original_text = original.text if original is not None else text
        if chosen in _template_conversation_ids():
            return Route(kind="template", intent=chosen), original_text
        return Route(kind="agent", intent=chosen), original_text
    role = load_role_plan(MANIFEST.id)
    last = latest_message(session, thread, "assistant")
    start = time.perf_counter()
    c = runtime.get_classifier(MANIFEST.id).classify(text, last.text if last else "")
    latency_ms = round((time.perf_counter() - start) * 1000)
    events.emit(
        session,
        "intent.classified",
        ("thread", thread.id),
        None,
        {
            "role": MANIFEST.id,
            "version": c.version,
            "intent": c.intent,
            "band": c.band,
            "latency_ms": latency_ms,
        },
        deps.actor,
    )
    session.commit()
    return route(c, role, safety_floor=role.targets.safety_floor if role else 0.2), text


def _template_key(intent: str) -> str:
    """The i18n key of a template intent's reply text."""
    return intent if intent.startswith("conversation.") else f"reply.{intent}"


def _option_label(intent: str, deps: AgentDeps) -> str | None:
    """Short button label for an intent, or None when it has none (then it is not offered)."""
    if intent.startswith("conversation."):
        key = f"conversation.label.{intent.split('.', 1)[1]}"
    else:
        key = f"intent.{intent}"
    return t(key, deps.lang) if key in STRINGS["en"] else None


def _unique_labels(options: list[str], deps: AgentDeps) -> dict[str, str]:
    """Button label -> intent, one-to-one (a repeated label gets a numeric suffix)."""
    labels: dict[str, str] = {}
    for intent in options:
        label = _option_label(intent, deps)
        if label is None:
            continue
        base, n = label, 1
        while label in labels:
            n += 1
            label = f"{base} {n}"
        labels[label] = intent
    return labels


def _reply_clarify(
    session: Session, deps: AgentDeps, thread: Thread, options: list[str]
) -> ChatReply:
    """Ask "Did you mean" with one button per option plus "Something else"; with no usable
    option, ask the user to rephrase."""
    labels = _unique_labels(options, deps)
    if not labels:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    other = t("clarify.something_else", deps.lang)
    reply = store_reply(
        session,
        deps,
        thread,
        [
            TextBlock(text=t("clarify.question", deps.lang)),
            QuickRepliesBlock(options=[*labels, other]),
        ],
    )
    user = latest_message(session, thread, "user")
    events.emit(
        session,
        "intent.clarify_asked",
        ("thread", thread.id),
        None,
        {
            "options": {**labels, other: "other"},
            "message_id": reply.message_id,
            "original_message_id": user.id if user else None,
        },
        deps.actor,
    )
    return reply


_BINDINGS = {b.tool_id: b for b in BINDINGS}


def _local_day(timestamp: dt.datetime, tz: str) -> dt.date:
    return timestamp.astimezone(ZoneInfo(tz)).date()


def _jev_tapped(
    session: Session, deps: AgentDeps, thread: Thread, text: str
) -> decider.Decision | None:
    """The stored decision behind a tapped Jev clarify button, if text is one. A button only
    counts while its question is the thread's last assistant message and was asked today (its
    inputs hold that day's "today")."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = latest_message(session, thread, "assistant")
    if asked is None or last is None or (asked.after or {}).get("message_id") != last.id:
        return None
    if _local_day(asked.timestamp, deps.branch.timezone) != deps.today:
        return None
    chosen = ((asked.after or {}).get("options") or {}).get(text.strip())
    return decider.Decision.model_validate(chosen) if chosen else None


def _jev_query(
    session: Session, deps: AgentDeps, thread: Thread, text: str
) -> tuple[decider.Decision | None, actions.Query | None]:
    """A decision already made (a tapped button, an injection), or the query for Jev."""
    tapped = _jev_tapped(session, deps, thread, text)
    if tapped is not None:
        return tapped, None
    if classify(html.unescape(text), deps.today, deps.lang).injection:
        injection = decider.Decision(action="reply_only", args={"kind": "injection"}, confidence=1)
        return injection, None
    last = latest_message(session, thread, "assistant")
    return None, actions.build_query(deps, text, last.text if last else "")


def _jev_clarify(
    session: Session, deps: AgentDeps, thread: Thread, decision: decider.Decision
) -> ChatReply:
    """Ask "Did you mean" with one button per offerable alternative (its inputs kept, so a tap
    runs it without a new request) plus Something else; with none, ask to rephrase."""
    options: dict[str, dict[str, Any]] = {}
    for alt in decision.alternatives:
        spec = actions.ACTIONS.get(alt.action)
        if spec is None or spec.label_key is None or alt.missing is not None:
            continue
        label = t(spec.label_key, deps.lang)
        if label not in options:
            chosen = decider.Decision(action=alt.action, args=alt.args, confidence=alt.probability)
            options[label] = chosen.model_dump(mode="json")
    if not options:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    other = t("clarify.something_else", deps.lang)
    reply = store_reply(
        session,
        deps,
        thread,
        [
            TextBlock(text=t("clarify.question", deps.lang)),
            QuickRepliesBlock(options=[*options, other]),
        ],
    )
    options[other] = decider.Decision(action="clarify", confidence=1.0).model_dump(mode="json")
    events.emit(
        session,
        "decision.clarify_asked",
        ("thread", thread.id),
        None,
        {"options": options, "message_id": reply.message_id},
        deps.actor,
    )
    return reply


def _jev_act(
    session: Session, deps: AgentDeps, thread: Thread, decision: decider.Decision
) -> ChatReply:
    """Log the decision, then run its tool through the guard and word the reply."""
    events.emit(
        session,
        "decision.made",
        ("thread", thread.id),
        None,
        decision.model_dump(mode="json"),
        deps.actor,
    )
    if decision.action == "clarify":
        return _jev_clarify(session, deps, thread, decision)
    tool = actions.ACTIONS[decision.action].tool
    if tool is None:  # reply_only
        kind = str(decision.args.get("kind", "other"))
        return store_reply(session, deps, thread, replies.conversation_reply(kind, deps.lang))
    binding = _BINDINGS[f"{MANIFEST.id}.{tool}"]
    try:
        args = binding.input_type.model_validate(decision.args)
    except ValidationError:
        return reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    out = call_tool(deps, binding, args, new_id())
    return store_reply(session, deps, thread, replies.tool_reply(tool, out, deps.lang))


def _jev_failed(session: Session, deps: AgentDeps, thread: Thread, error: str) -> ChatReply:
    events.emit(
        session, "decision.failed", ("thread", thread.id), None, {"error": error}, deps.actor
    )
    return reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


async def _jev_turn(
    session: Session, deps: AgentDeps, thread: Thread, text: str, ctx: EgressContext
) -> ChatReply:
    """Jev picks the action, code runs it and words the reply (spec 2026-10-17-jev-decider).
    DB work runs in worker threads; the Jev request runs with no write lock held."""
    decision, query = await asyncio.to_thread(_jev_query, session, deps, thread, text)
    if decision is None and query is not None:
        try:
            with egress_context(replace(ctx, provider="typesafe", purpose=f"{MANIFEST.id}.decide")):
                decision = await decider.decide(query)
        except JevError as exc:
            return await asyncio.to_thread(_jev_failed, session, deps, thread, str(exc))
    assert decision is not None
    return await asyncio.to_thread(_jev_act, session, deps, thread, decision)


def _template_text(decided: Route, lang: str) -> str | None:
    """The reply text of a template route, or None when it has no text (the agent answers)."""
    if decided.kind != "template" or not decided.intent:
        return None
    key = _template_key(decided.intent)
    return t(key, lang) if key in STRINGS["en"] else None


def resolve_turn(
    session: Session, deps: AgentDeps, thread: Thread, text: str, jev: bool = False
) -> tuple[ChatReply | None, str]:
    """Classify and route one turn (shared by run_turn and the AG-UI run).

    Returns (reply, ""), already stored (the caller commits), for a template reply or a "Did
    you mean" question; or (None, text_for_the_agent) with deps.intent set when the agent should
    answer. With jev=True nothing is decided here. The caller ran the emergency script first.
    """
    decided, agent_text = _classify_turn(session, deps, thread, text)
    if jev:  # Jev decides everything (the service already ran the emergency script)
        return None, text
    if decided.kind == "clarify":
        return _reply_clarify(session, deps, thread, decided.options), ""
    template = _template_text(decided, deps.lang)
    if template is not None:
        return reply_text(session, deps, thread, template), ""
    deps.intent = decided.intent
    return None, agent_text


async def handle_turn(turn: Turn) -> ChatReply:
    """The shift supervisor's answer to one stored message: a template, a Did you mean
    question, Jev (MIA_DECIDER=jev) or the Pydantic AI agent. The caller commits."""
    session, deps, thread, text = turn.session, turn.deps, turn.thread, turn.text
    jev = get_settings().MIA_DECIDER == "jev"
    reply, agent_text = await asyncio.to_thread(resolve_turn, session, deps, thread, text, jev)
    if reply is not None:
        return reply
    if jev:
        return await _jev_turn(session, deps, thread, text, turn.ctx)
    agent = turn.agent or get_agent()
    try:
        with egress_context(turn.ctx):
            result = await agent.run(
                wrap_user_text(agent_text, deps.person),
                deps=deps,
                message_history=turn.past,
                usage_limits=USAGE_LIMITS,
            )
    except UsageLimitExceeded:
        return await asyncio.to_thread(reply_capped, session, deps, thread, text)
    return await asyncio.to_thread(finish, session, deps, thread, result)


def _run_due(session: Session, now: dt.datetime) -> int:
    """Cover escalation, then the alerts (missed check-ins, unstaffed visits, the daily plan).
    The escalation is committed first: the alerts roll back a failing branch's work."""
    advanced = cover.process_due(session, now)
    session.commit()
    return advanced + alerts.run_due(session, now)


SPEC = AgentSpec(
    manifest=MANIFEST,
    label_key=f"agent.{MANIFEST.id}.label",
    router_description=(
        "Shifts and attendance: rosters and who works when, being sick, late or absent,"
        " finding and answering cover, checking in and out, the day's plan, problems at"
        " a site or the shop, cleaning checklists."
    ),
    handle_turn=handle_turn,
    run_due=_run_due,
    stream_agent=get_agent,
)
