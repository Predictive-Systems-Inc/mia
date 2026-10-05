"""Running one chat turn: store the message, run the agent, check its blocks, store the reply.

Guarantees: the user's text reaches the model only inside <user_message> tags; approval cards
in a reply always point to approvals that exist, and every approval created in the turn gets a
card; user and assistant messages are stored through core services with events.
"""

import asyncio
import datetime as dt
import html
import time
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.agents.dispatcher.agent import MANIFEST
from mia.agents.dispatcher.classifier import detect_language
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
from mia.core.models import Actor, Approval, Branch, Event, Message, Person, Thread
from mia.i18n import t
from mia.i18n.strings import STRINGS
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
        thread_id=thread.id, message_id=message.id, agent_id=MANIFEST.id, blocks=blocks
    )


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


def _classify_turn(session: Session, deps: AgentDeps, thread: Thread, text: str) -> Route:
    """Route one turn. An exact option label answers a pending question; any other text is
    classified. Commits its events, so no write lock is held while the model runs."""
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
            return Route(kind="clarify")  # nothing fitted: ask to rephrase
        return Route(kind="agent", intent=chosen)
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
    return route(c, role, safety_floor=role.targets.safety_floor if role else 0.2)


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
        thread_id=thread.id, message_id=message.id, agent_id=MANIFEST.id, blocks=blocks
    )


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


def _reply_emergency(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply:
    """Safety script first; every supervisor of the branch is told, urgently."""
    country = "PH" if deps.branch.timezone.startswith("Asia/Manila") else "FI"
    people = session.exec(select(Person).where(Person.branch_id == deps.branch.id)).all()
    for sup in (p for p in people if "supervisor" in p.roles):
        notice = t("safety.supervisor_notice", sup.language, name=deps.person.name, text=text[:200])
        notify(session, sup, [TextBlock(text=notice)], deps.actor, MANIFEST.id, urgent=True)
    return _reply_text(session, deps, thread, t(f"safety.emergency_{country}", deps.lang))


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
    only the agent run stays on the loop.
    """
    thread, past, deps, ctx = await asyncio.to_thread(_prepare, session, person, text, thread_id)
    decided = await asyncio.to_thread(_classify_turn, session, deps, thread, text)
    if decided.kind == "emergency":
        return await asyncio.to_thread(_reply_emergency, session, deps, thread, text)
    if decided.kind == "clarify":
        return await asyncio.to_thread(_reply_clarify, session, deps, thread, decided.options)
    if decided.kind == "template" and decided.intent:
        key = _template_key(decided.intent)
        if key in STRINGS["en"]:  # a template intent without text goes to the agent instead
            return await asyncio.to_thread(_reply_text, session, deps, thread, t(key, deps.lang))
    deps.intent = decided.intent
    with egress_context(ctx):
        result = await agent.run(wrap_user_text(text, person), deps=deps, message_history=past)
    return await asyncio.to_thread(_finish, session, deps, thread, result)
