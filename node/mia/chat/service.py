"""Running one chat turn: store the message, the shared steps, hand it to the agent.

Guarantees: the user message is stored through core services with an event and committed
before any model runs; the emergency script comes before everything else, then the language
steps; the agent's handle_turn answers the rest; the caller commits the reply.
"""

import asyncio
import datetime as dt
import time
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from sqlmodel import Session

from mia.agents.base import AgentDeps, Turn
from mia.agents.registry import AGENTS, DEFAULT
from mia.chat import language
from mia.chat.blocks import ChatReply
from mia.chat.replies import history, latest_message, reply_text, tell_supervisors
from mia.core import events, people, store
from mia.core.egress import EgressContext
from mia.core.models import Actor, Branch, Message, Organisation, Person, Thread
from mia.i18n import t
from mia.i18n.strings import STRINGS
from mia.settings import get_settings
from mia.skills import runtime
from mia.skills.roles import load_role_plan


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
        lang=person.language,
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


def safety_reply(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply | None:
    """The emergency script when the node's safety classifier flags the message (every agent,
    before anything else); None otherwise. Every supervisor of the branch is told, urgently.
    ponytail: the shift supervisor's skill model is the node's only safety model (ADR 013);
    a node-wide one replaces it when it exists."""
    last = latest_message(session, thread, "assistant")
    start = time.perf_counter()
    c = runtime.get_classifier(DEFAULT).classify(text, last.text if last else "")
    latency_ms = round((time.perf_counter() - start) * 1000)
    role = load_role_plan(DEFAULT)
    if c.safety < (role.targets.safety_floor if role else 0.2):
        return None
    events.emit(  # the audit trail keeps emergencies (the agent's classify step never runs)
        session,
        "intent.classified",
        ("thread", thread.id),
        None,
        {
            "role": DEFAULT,
            "version": c.version,
            "intent": c.intent,
            "band": c.band,
            "latency_ms": latency_ms,
        },
        deps.actor,
    )
    org = session.get(Organisation, deps.organisation_id)
    guess = "PH" if deps.branch.timezone.startswith("Asia/Manila") else "FI"
    country = org.country.upper() if org is not None else guess
    if f"safety.emergency_{country}" not in STRINGS["en"]:
        country = "FI"
    tell_supervisors(
        session, deps, "safety.supervisor_notice", name=deps.person.name, text=text[:200]
    )
    return reply_text(session, deps, thread, t(f"safety.emergency_{country}", deps.lang))


def _before_agent(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply | str:
    """The steps every agent shares, in order: the emergency script, a language tap, the
    change command, the first-contact language question. Returns a stored reply (the caller
    commits), or the text the agent should answer (committed, so no write lock is held)."""
    if (reply := safety_reply(session, deps, thread, text)) is not None:
        return reply
    if (tap := language.tapped(session, thread, text)) is not None:
        code, original_id = tap
        people.set_language(session, Actor.person(deps.person), deps.person, code)
        deps.lang = code
        original = language.original_text(session, original_id)
        if original is None:
            name = t(f"language.name.{code}", "en")
            return reply_text(session, deps, thread, t("language.set", code, language=name))
        session.commit()
        return original
    if language.is_change_command(text) and language.offers_choice():
        return language.ask(session, deps, thread, None)
    if language.needs_asking(session, deps.person):
        user = latest_message(session, thread, "user")
        return language.ask(session, deps, thread, user.id if user else None)
    return text


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
    before = await asyncio.to_thread(_before_agent, session, deps, thread, text)
    if isinstance(before, ChatReply):
        return before
    text = before  # the text the agent answers (the original message after a language tap)
    spec = AGENTS[deps.manifest.id]
    return await spec.handle_turn(Turn(session, deps, thread, text, past, ctx, agent))
