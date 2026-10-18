"""Running one chat turn: store the message, hand it to the agent, return the reply.

Guarantees: the user message is stored through core services with an event and committed
before any model runs; the agent's handle_turn answers; the caller commits the reply.
"""

import asyncio
import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from sqlmodel import Session

from mia.agents.base import AgentDeps, Turn
from mia.agents.registry import AGENTS, DEFAULT
from mia.agents.shift_supervisor.classifier import detect_language
from mia.chat.blocks import ChatReply
from mia.chat.replies import history
from mia.core import store
from mia.core.egress import EgressContext
from mia.core.models import Actor, Branch, Message, Person, Thread
from mia.settings import get_settings


class ChatError(Exception):
    """Bad chat input (unknown actor or thread)."""


def _prepare(
    session: Session, person: Person, text: str, thread_id: str | None, *, create: bool = False
) -> tuple[Thread, list[ModelMessage], AgentDeps, EgressContext]:
    """Store the user message and commit it; build the run's deps and egress context.

    With create=True an unknown thread_id starts a new thread with that id (AG-UI clients name
    their threads); a thread of another person is never continued.
    """
    spec = AGENTS[DEFAULT]
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
            branch_id=branch.id, person_id=person.id, agent_id=spec.manifest.id, title=text[:60]
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
        actor=human.as_agent(spec.manifest.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=dt.datetime.now(ZoneInfo(branch.timezone)).date(),
        lang=detect_language(text, person.language),
        manifest=spec.manifest,
    )
    ctx = EgressContext(
        session=session,
        actor=deps.actor,
        organisation_id=branch.organisation_id,
        agent_id=spec.manifest.id,
        purpose="chat",
        level=get_settings().MIA_EGRESS_LEVEL,
    )
    return thread, past, deps, ctx


async def run_turn(
    session: Session,
    agent: Agent[AgentDeps, Any] | None,
    person: Person,
    text: str,
    thread_id: str | None = None,
) -> ChatReply:
    """One user message in, one structured reply out. The message is committed before any
    model runs; the chosen agent's handle_turn answers; the caller commits the reply.
    `agent` is a Pydantic AI agent to use instead of the default one (tests)."""
    thread, past, deps, ctx = await asyncio.to_thread(_prepare, session, person, text, thread_id)
    spec = AGENTS[deps.manifest.id]
    return await spec.handle_turn(Turn(session, deps, thread, text, past, ctx, agent))
