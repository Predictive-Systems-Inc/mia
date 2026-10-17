"""Running one chat turn: store the message, run the agent, check its blocks, store the reply.

Guarantees: the user's text reaches the model only inside <user_message> tags; approval cards
in a reply always point to approvals that exist, and every approval created in the turn gets a
card; user and assistant messages are stored through core services with events.
"""

import asyncio
import datetime as dt
import html
import time
from dataclasses import replace
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.usage import UsageLimits
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.dispatcher import actions, decider, replies
from mia.agents.dispatcher.agent import MANIFEST
from mia.agents.dispatcher.classifier import classify, detect_language
from mia.agents.dispatcher.tools import BINDINGS
from mia.chat.blocks import (
    AgentReply,
    ApprovalCardBlock,
    Block,
    CardField,
    ChatReply,
    QuickRepliesBlock,
    TextBlock,
)
from mia.chat.channels import notify
from mia.core import events, store
from mia.core.egress import EgressContext, egress_context
from mia.core.ids import new_id
from mia.core.models import Actor, Approval, Branch, Event, Message, Organisation, Person, Thread
from mia.i18n import t
from mia.i18n.strings import STRINGS
from mia.learning import catalogue
from mia.settings import get_settings
from mia.skills import runtime
from mia.skills.roles import load_role_plan
from mia.skills.routing import Route, route

# ponytail: one agent per chat today; read the role from the thread when there are more
ROLE = "dispatcher"


class ChatError(Exception):
    """Bad chat input (unknown actor or thread)."""


def wrap_user_text(text: str, person: Person) -> str:
    """Boundaries around untrusted user content (architecture rule 8).

    Escapes <, > and & so no spelling of a tag (case, spaces, attributes) can close the boundary.
    """
    clean = html.escape(text, quote=False)
    roles = ",".join(person.roles)
    return f'<user_message source="app" sender_roles="{roles}">\n{clean}\n</user_message>'


def history(session: Session, thread: Thread) -> list[ModelMessage]:
    """The thread's Pydantic AI messages in order, for the next run's message history."""
    rows = session.exec(
        select(Message).where(Message.thread_id == thread.id).order_by(col(Message.id))
    ).all()
    messages: list[ModelMessage] = []
    for row in rows:
        if row.model_messages:
            messages.extend(ModelMessagesTypeAdapter.validate_python(row.model_messages))
    return messages


def _approval_card(approval: Approval, lang: str) -> ApprovalCardBlock:
    return ApprovalCardBlock(
        approval_id=approval.id,
        title=t("approval.card_title", lang),
        summary=approval.summary,
        fields=[CardField(label=t("field.status", lang), value=approval.status)],
        status=approval.status,
    )


def check_blocks(session: Session, deps: AgentDeps, blocks: list[Block]) -> list[Block]:
    """Drop approval cards the model invented; add cards for approvals it left out."""
    created = {str(e.output["approval_id"]) for e in deps.tool_log if e.output.get("approval_id")}
    result: list[Block] = []
    shown: set[str] = set()
    for block in blocks:
        if isinstance(block, ApprovalCardBlock):
            row = session.get(Approval, block.approval_id)
            if row is None or row.branch_id != deps.branch.id:
                continue
            block.status = row.status
            shown.add(block.approval_id)
        result.append(block)
    for approval_id in sorted(created - shown):
        row = session.get(Approval, approval_id)
        if row is not None:
            result.append(_approval_card(row, deps.lang))
    return result


def _prepare(
    session: Session, person: Person, text: str, thread_id: str | None, *, create: bool = False
) -> tuple[Thread, list[ModelMessage], AgentDeps, EgressContext]:
    """Store the user message and commit it; build the run's deps and egress context.

    With create=True an unknown thread_id starts a new thread with that id (AG-UI clients name
    their threads); a thread of another person is never continued.
    """
    branch = session.get(Branch, person.branch_id)
    if branch is None:
        raise ChatError("person has no branch")
    human = Actor.person(person)
    thread = session.get(Thread, thread_id) if thread_id else None
    if thread is not None and thread.person_id != person.id:
        raise ChatError("thread not found")
    if thread is None:
        if thread_id and not create:
            raise ChatError("thread not found")
        new = Thread(
            branch_id=branch.id, person_id=person.id, agent_id=MANIFEST.id, title=text[:60]
        )
        if thread_id:
            new.id = thread_id
        thread = store.insert(session, new, human)
    past = history(session, thread)
    store.insert(
        session,
        Message(
            branch_id=branch.id, thread_id=thread.id, role="user", sender_id=person.id, text=text
        ),
        human,
    )
    session.commit()
    deps = AgentDeps(
        session=session,
        actor=human.as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=dt.datetime.now(ZoneInfo(branch.timezone)).date(),
        lang=detect_language(text, person.language),
        manifest=MANIFEST,
    )
    ctx = EgressContext(
        session=session,
        actor=deps.actor,
        organisation_id=branch.organisation_id,
        agent_id=MANIFEST.id,
        purpose="chat",
        level=get_settings().MIA_EGRESS_LEVEL,
    )
    return thread, past, deps, ctx


def _finish(
    session: Session, deps: AgentDeps, thread: Thread, result: AgentRunResult[AgentReply]
) -> ChatReply:
    """Check the reply's blocks and store the assistant message (the caller commits)."""
    blocks = check_blocks(session, deps, result.output.blocks)
    reply_text = "\n".join(b.text for b in blocks if b.type == "text")
    new_messages = ModelMessagesTypeAdapter.dump_python(result.new_messages(), mode="json")
    message = store.insert(
        session,
        Message(
            branch_id=deps.branch.id,
            thread_id=thread.id,
            role="assistant",
            sender_id=MANIFEST.roles.agent_role,
            agent_id=MANIFEST.id,
            text=reply_text,
            blocks=[b.model_dump(mode="json") for b in blocks],
            model_messages=new_messages,
        ),
        deps.actor,
    )
    return ChatReply(
        thread_id=thread.id,
        message_id=message.id,
        agent_id=MANIFEST.id,
        blocks=blocks,
        sensitive=_sensitive(session, deps, thread, blocks),
    )


EXPOSING_TOOLS = ("dispatcher.visit_details", "visit_details")


def _sensitive(session: Session, deps: AgentDeps, thread: Thread, blocks: list[Block]) -> bool:
    """The reply is sensitive when a block says so, a tool handed the model access notes in
    this turn, or an earlier turn of the thread did (the notes stay in the model history, so
    any later free-text reply may repeat them)."""
    if any(getattr(b, "sensitive", False) for b in blocks):
        return True
    if any(e.tool in EXPOSING_TOOLS and e.output.get("access_notes") for e in deps.tool_log):
        return True
    return _thread_exposed(session, thread)


def _thread_exposed(session: Session, thread: Thread) -> bool:
    for row in session.exec(select(Message).where(Message.thread_id == thread.id)):
        for mm in row.model_messages:
            for part in mm.get("parts", []):
                if part.get("part_kind") != "tool-return":
                    continue
                if part.get("tool_name") not in EXPOSING_TOOLS:
                    continue
                content = part.get("content")
                if isinstance(content, dict) and content.get("access_notes"):
                    return True
    return False


def _latest_message(session: Session, thread: Thread, role: str) -> Message | None:
    return session.exec(
        select(Message)
        .where(Message.thread_id == thread.id)
        .where(Message.role == role)
        .order_by(col(Message.id).desc())
    ).first()


def _pending_clarification(session: Session, thread: Thread) -> Event | None:
    """The clarify question that is the thread's last assistant message, if any."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "intent.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = _latest_message(session, thread, "assistant")
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
    role = load_role_plan(ROLE)
    last = _latest_message(session, thread, "assistant")
    start = time.perf_counter()
    c = runtime.get_classifier(ROLE).classify(text, last.text if last else "")
    latency_ms = round((time.perf_counter() - start) * 1000)
    events.emit(
        session,
        "intent.classified",
        ("thread", thread.id),
        None,
        {
            "role": ROLE,
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


def _store_reply(
    session: Session, deps: AgentDeps, thread: Thread, blocks: list[Block]
) -> ChatReply:
    """Store a reply the agent did not write (template, question, safety script)."""
    text = "\n".join(b.text for b in blocks if b.type == "text")
    message = store.insert(
        session,
        Message(
            branch_id=deps.branch.id,
            thread_id=thread.id,
            role="assistant",
            sender_id=MANIFEST.roles.agent_role,
            agent_id=MANIFEST.id,
            text=text,
            blocks=[b.model_dump(mode="json") for b in blocks],
            model_messages=[],
        ),
        deps.actor,
    )
    return ChatReply(
        thread_id=thread.id,
        message_id=message.id,
        agent_id=MANIFEST.id,
        blocks=blocks,
        sensitive=_sensitive(session, deps, thread, blocks),
    )


MAX_MODEL_CALLS = 8  # D22: a turn stops after this many model requests
USAGE_LIMITS = UsageLimits(request_limit=MAX_MODEL_CALLS)


def reply_capped(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply:
    """The reply when the turn hit the model-call cap (D22): a short translated text, the event
    `chat.turn_capped` on the thread (with the tools that ran and committed before the cap),
    and a notice to the supervisors so "a supervisor will follow up" is true."""
    tools = [e.tool for e in deps.tool_log]
    events.emit(
        session,
        "chat.turn_capped",
        thread,
        None,
        {"model_calls": MAX_MODEL_CALLS, "tools": tools},  # USAGE_LIMITS caps requests only
        deps.actor,
    )
    _tell_supervisors(
        session,
        deps,
        "chat.capped_notice",
        name=deps.person.name,
        text=text[:200],
        tools=", ".join(tools) or "-",
    )
    return _reply_text(session, deps, thread, t("chat.capped", deps.lang))


def _tell_supervisors(session: Session, deps: AgentDeps, key: str, **params: str) -> None:
    """One urgent notification to every supervisor of the branch, in their language."""
    people = session.exec(select(Person).where(Person.branch_id == deps.branch.id)).all()
    for sup in (p for p in people if "supervisor" in p.roles):
        notice = t(key, sup.language, **params)
        notify(session, sup, [TextBlock(text=notice)], deps.actor, MANIFEST.id, urgent=True)


def _reply_text(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply:
    return _store_reply(session, deps, thread, [TextBlock(text=text)])


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
        return _reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    other = t("clarify.something_else", deps.lang)
    reply = _store_reply(
        session,
        deps,
        thread,
        [
            TextBlock(text=t("clarify.question", deps.lang)),
            QuickRepliesBlock(options=[*labels, other]),
        ],
    )
    user = _latest_message(session, thread, "user")
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


def _jev_tapped(session: Session, thread: Thread, text: str) -> decider.Decision | None:
    """The stored decision behind a tapped Jev clarify button, if text is one. A button only
    counts while its question is the thread's last assistant message."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = _latest_message(session, thread, "assistant")
    if asked is None or last is None or (asked.after or {}).get("message_id") != last.id:
        return None
    chosen = ((asked.after or {}).get("options") or {}).get(text.strip())
    return decider.Decision.model_validate(chosen) if chosen else None


def _jev_query(
    session: Session, deps: AgentDeps, thread: Thread, text: str
) -> tuple[decider.Decision | None, actions.Query | None]:
    """A decision already made (a tapped button, an injection), or the query for Jev."""
    tapped = _jev_tapped(session, thread, text)
    if tapped is not None:
        return tapped, None
    if classify(html.unescape(text), deps.today, deps.lang).injection:
        injection = decider.Decision(action="reply_only", args={"kind": "injection"}, confidence=1)
        return injection, None
    last = _latest_message(session, thread, "assistant")
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
        return _reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    other = t("clarify.something_else", deps.lang)
    reply = _store_reply(
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
        return _store_reply(session, deps, thread, replies.conversation_reply(kind, deps.lang))
    binding = _BINDINGS[f"{MANIFEST.id}.{tool}"]
    try:
        args = binding.input_type.model_validate(decision.args)
    except ValidationError:
        return _reply_text(session, deps, thread, t("clarify.rephrase", deps.lang))
    out = call_tool(deps, binding, args, new_id())
    return _store_reply(session, deps, thread, replies.tool_reply(tool, out, deps.lang))


def _jev_failed(session: Session, deps: AgentDeps, thread: Thread, error: str) -> ChatReply:
    events.emit(
        session, "decision.failed", ("thread", thread.id), None, {"error": error}, deps.actor
    )
    return _reply_text(session, deps, thread, t("reply.unavailable", deps.lang))


async def _jev_turn(
    session: Session, deps: AgentDeps, thread: Thread, text: str, ctx: EgressContext
) -> ChatReply:
    """Jev picks the action, code runs it and words the reply (spec 2026-10-17-jev-decider).
    DB work runs in worker threads; the Jev request runs with no write lock held."""
    decision, query = await asyncio.to_thread(_jev_query, session, deps, thread, text)
    if decision is None and query is not None:
        try:
            with egress_context(replace(ctx, provider="typesafe", purpose="dispatcher.decide")):
                decision = await decider.decide(query)
        except decider.DecideError as exc:
            return await asyncio.to_thread(_jev_failed, session, deps, thread, str(exc))
    assert decision is not None
    return await asyncio.to_thread(_jev_act, session, deps, thread, decision)


def _reply_emergency(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply:
    """Safety script first; every supervisor of the branch is told, urgently."""
    org = session.get(Organisation, deps.organisation_id)
    guess = "PH" if deps.branch.timezone.startswith("Asia/Manila") else "FI"
    country = org.country.upper() if org is not None else guess
    if f"safety.emergency_{country}" not in STRINGS["en"]:
        country = "FI"
    _tell_supervisors(
        session, deps, "safety.supervisor_notice", name=deps.person.name, text=text[:200]
    )
    return _reply_text(session, deps, thread, t(f"safety.emergency_{country}", deps.lang))


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

    Returns (reply, ""), already stored (the caller commits), for the emergency script, a
    template reply or a "Did you mean" question; or (None, text_for_the_agent) with deps.intent
    set when the agent should answer. With jev=True only the emergency script is decided here.
    """
    decided, agent_text = _classify_turn(session, deps, thread, text)
    if decided.kind == "emergency":
        return _reply_emergency(session, deps, thread, text), ""
    if jev:  # the safety step stays; Jev decides everything else (run_turn)
        return None, text
    if decided.kind == "clarify":
        return _reply_clarify(session, deps, thread, decided.options), ""
    template = _template_text(decided, deps.lang)
    if template is not None:
        return _reply_text(session, deps, thread, template), ""
    deps.intent = decided.intent
    return None, agent_text


async def run_turn(
    session: Session,
    agent: Agent[AgentDeps, Any],
    person: Person,
    text: str,
    thread_id: str | None = None,
) -> ChatReply:
    """One user message in, one structured reply out.

    Commits the user message before the model runs, so no write lock is held while waiting on
    the network; tool calls and egress commit their own writes. The caller commits the reply.
    Each turn is classified first and goes to the emergency script, a template reply, a Did you
    mean question or the agent. Database and classifier work run in worker threads (rule 12);
    only the agent run stays on the loop. With MIA_DECIDER=jev, Jev picks the action instead of
    the agent; the AG-UI run (chat/runs.py) keeps the agent.
    """
    thread, past, deps, ctx = await asyncio.to_thread(_prepare, session, person, text, thread_id)
    jev = get_settings().MIA_DECIDER == "jev"
    reply, agent_text = await asyncio.to_thread(resolve_turn, session, deps, thread, text, jev)
    if reply is not None:
        return reply
    if jev:
        return await _jev_turn(session, deps, thread, text, ctx)
    try:
        with egress_context(ctx):
            result = await agent.run(
                wrap_user_text(agent_text, person),
                deps=deps,
                message_history=past,
                usage_limits=USAGE_LIMITS,
            )
    except UsageLimitExceeded:
        return await asyncio.to_thread(reply_capped, session, deps, thread, text)
    return await asyncio.to_thread(_finish, session, deps, thread, result)
