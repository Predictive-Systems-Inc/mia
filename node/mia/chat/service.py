"""Running one chat turn: store the message, run the agent, check its blocks, store the reply.

Guarantees: the user's text reaches the model only inside <user_message> tags; approval cards
in a reply always point to approvals that exist, and every approval created in the turn gets a
card; user and assistant messages are stored through core services with events.
"""

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.agents.dispatcher.agent import MANIFEST
from mia.agents.dispatcher.classifier import detect_language
from mia.chat.blocks import AgentReply, ApprovalCardBlock, Block, CardField, ChatReply
from mia.core import store
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Approval, Branch, Message, Person, Thread
from mia.i18n import t
from mia.settings import get_settings


class ChatError(Exception):
    """Bad chat input (unknown actor or thread)."""


def wrap_user_text(text: str, person: Person) -> str:
    """Boundaries around untrusted user content (architecture rule 8)."""
    clean = text.replace("</user_message>", "").replace("<user_message", "")
    roles = ",".join(person.roles)
    return f'<user_message source="app" sender_roles="{roles}">\n{clean}\n</user_message>'


def history(session: Session, thread: Thread) -> list[ModelMessage]:
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


async def run_turn(
    session: Session,
    agent: Agent[AgentDeps, Any],
    person: Person,
    text: str,
    thread_id: str | None = None,
) -> ChatReply:
    """One user message in, one structured reply out. Commits nothing; the caller does."""
    branch = session.get(Branch, person.branch_id)
    if branch is None:
        raise ChatError("person has no branch")
    human = Actor.person(person)
    if thread_id:
        thread = session.get(Thread, thread_id)
        if thread is None or thread.person_id != person.id:
            raise ChatError("thread not found")
    else:
        thread = store.insert(
            session,
            Thread(branch_id=branch.id, person_id=person.id, agent_id=MANIFEST.id, title=text[:60]),
            human,
        )
    past = history(session, thread)
    store.insert(
        session,
        Message(
            branch_id=branch.id, thread_id=thread.id, role="user", sender_id=person.id, text=text
        ),
        human,
    )
    lang = detect_language(text, person.language)
    deps = AgentDeps(
        session=session,
        actor=human.as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=dt.datetime.now(ZoneInfo(branch.timezone)).date(),
        lang=lang,
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
    with egress_context(ctx):
        result = await agent.run(wrap_user_text(text, person), deps=deps, message_history=past)
    output: AgentReply = result.output
    blocks = check_blocks(session, deps, output.blocks)
    reply_text = "\n".join(b.text for b in blocks if b.type == "text")
    new_messages = ModelMessagesTypeAdapter.dump_python(result.new_messages(), mode="json")
    message = store.insert(
        session,
        Message(
            branch_id=branch.id,
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
