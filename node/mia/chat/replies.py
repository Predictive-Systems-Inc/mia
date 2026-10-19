"""Storing Mia's replies: block checks, the assistant message and its event, and the replies
every agent shares (the cap). Agents and the chat service both import this module; it imports
no agent's turn code, only the shift supervisor's manifest (for EXPOSING_TOOLS).

Guarantees: the user's text reaches the model only inside <user_message> tags; approval cards
in a reply always point to approvals that exist, and every approval created in the turn gets a
card; assistant messages are stored through core services with events.
"""

import html
from typing import Any

from pydantic_ai import AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.usage import UsageLimits
from sqlmodel import Session, col, or_, select

from mia.agents.base import AgentDeps
from mia.agents.shift_supervisor import MANIFEST
from mia.channels.service import deliver
from mia.chat.blocks import (
    AgentReply,
    ApprovalCardBlock,
    Block,
    CardField,
    ChatReply,
    TextBlock,
)
from mia.chat.channels import NOTIFICATION, notify
from mia.core import events, store
from mia.core.models import Approval, Message, Person, Thread
from mia.i18n import t


def wrap_user_text(text: str, person: Person) -> str:
    """Boundaries around untrusted user content (architecture rule 8).

    Escapes <, > and & so no spelling of a tag (case, spaces, attributes) can close the boundary.
    """
    clean = html.escape(text, quote=False)
    roles = ",".join(person.roles)
    return f'<user_message source="app" sender_roles="{roles}">\n{clean}\n</user_message>'


def history(session: Session, thread: Thread, before: str | None = None) -> list[ModelMessage]:
    """The thread's Pydantic AI messages in order, for the next run's message history. With
    `before` (a resumed turn's message), that message and later user messages are left out;
    Mia's later replies stay."""
    stmt = select(Message).where(Message.thread_id == thread.id).order_by(col(Message.id))
    if before is not None:
        stmt = stmt.where(or_(col(Message.id) < before, col(Message.role) != "user"))
    rows = session.exec(stmt).all()
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


def finish(
    session: Session, deps: AgentDeps, thread: Thread, result: AgentRunResult[AgentReply]
) -> ChatReply:
    """Check the reply's blocks and store the assistant message (the caller commits). A switch
    notice in deps.notice comes first."""
    blocks = check_blocks(session, deps, result.output.blocks)
    new_messages = ModelMessagesTypeAdapter.dump_python(result.new_messages(), mode="json")
    return _store(session, deps, thread, blocks, new_messages)


def _store(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    blocks: list[Block],
    model_messages: list[dict[str, Any]],
) -> ChatReply:
    """Store Mia's message after deps.notice. A resumed turn's reply is a notification (event
    notification.sent) and goes out on the person's linked channels too. A sensitive reply
    (_sensitive) keeps its text and blocks in the row and out of its event, as notify() does."""
    blocks = [*deps.notice, *blocks]
    role, action = (NOTIFICATION, "notification.sent") if deps.resumed else ("assistant", None)
    sensitive = _sensitive(session, deps, thread, blocks)
    message = store.insert(
        session,
        Message(
            branch_id=deps.branch.id,
            thread_id=thread.id,
            role=role,
            sender_id=deps.manifest.roles.agent_role,
            agent_id=deps.manifest.id,
            text="\n".join(b.text for b in blocks if b.type == "text"),
            blocks=[b.model_dump(mode="json") for b in blocks],
            model_messages=model_messages,
        ),
        deps.actor,
        action=action,
        redact=("text", "blocks") if sensitive else (),
    )
    if deps.resumed:
        deliver(
            session,
            deps.person,
            blocks,
            deps.actor,
            urgent=True,
            source_id=message.id,
            sensitive=sensitive,
        )
    return ChatReply(
        thread_id=thread.id,
        message_id=message.id,
        agent_id=deps.manifest.id,
        blocks=blocks,
        sensitive=sensitive,
    )


# ponytail: the shift supervisor is the only agent whose tools expose access notes
EXPOSING_TOOLS = (f"{MANIFEST.id}.visit_details", "visit_details")


def _sensitive(session: Session, deps: AgentDeps, thread: Thread, blocks: list[Block]) -> bool:
    """The reply is sensitive when a block says so, the turn ran a tool the manifest marks
    sensitive (pay, hours, leave), a tool handed the model access notes in this turn, or an
    earlier turn of the thread did (the notes stay in the model history, so any later
    free-text reply may repeat them)."""
    if any(getattr(b, "sensitive", False) for b in blocks):
        return True
    marked = {s.id for s in deps.manifest.tools if s.sensitive}
    if any(e.tool in marked for e in deps.tool_log):
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


def latest_message(session: Session, thread: Thread, role: str) -> Message | None:
    """The thread's newest message with this role, or None."""
    return session.exec(
        select(Message)
        .where(Message.thread_id == thread.id)
        .where(Message.role == role)
        .order_by(col(Message.id).desc())
    ).first()


def store_reply(
    session: Session, deps: AgentDeps, thread: Thread, blocks: list[Block]
) -> ChatReply:
    """Store a reply the agent did not write (template, question, safety script)."""
    return _store(session, deps, thread, blocks, [])


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
    tell_supervisors(
        session,
        deps,
        "chat.capped_notice",
        name=deps.person.name,
        text=text[:200],
        tools=", ".join(tools) or "-",
    )
    return reply_text(session, deps, thread, t("chat.capped", deps.lang))


def tell_supervisors(session: Session, deps: AgentDeps, key: str, **params: str) -> None:
    """One urgent notification to every supervisor of the branch, in their language."""
    people = session.exec(select(Person).where(Person.branch_id == deps.branch.id)).all()
    for sup in (p for p in people if "supervisor" in p.roles):
        notice = t(key, sup.language, **params)
        notify(session, sup, [TextBlock(text=notice)], deps.actor, deps.manifest.id, urgent=True)


def reply_text(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply:
    """Store a plain-text reply the agent did not write (the caller commits)."""
    return store_reply(session, deps, thread, [TextBlock(text=text)])
