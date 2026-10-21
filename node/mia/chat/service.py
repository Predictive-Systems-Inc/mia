"""Running one chat turn: store the message, the shared steps, hand it to the agent.

Guarantees: the user message is stored through core services with an event and committed
before any model runs; the emergency script comes before everything else, then the language
steps; the agent's handle_turn answers the rest; the caller commits the reply.
"""

import asyncio
import html
import time
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, AgentSpec, Turn
from mia.agents.registry import AGENTS, DEFAULT
from mia.agents.shift_supervisor.classifier import classify
from mia.chat import agent_router, deferred, language, route_memory
from mia.chat.access import agents_for
from mia.chat.blocks import ChatReply, QuickRepliesBlock, TextBlock
from mia.chat.channels import NOTIFICATION
from mia.chat.replies import history, latest_message, reply_text, store_reply, tell_supervisors
from mia.core import events, people, store
from mia.core.db import utcnow
from mia.core.egress import EgressContext, Pseudonymiser, egress_context
from mia.core.jev import JevError, JevUnreachable
from mia.core.models import Actor, Branch, Event, Message, Organisation, Person, Thread
from mia.i18n import t
from mia.i18n.strings import STRINGS
from mia.settings import get_settings
from mia.skills import runtime
from mia.skills.roles import load_role_plan


class ChatError(Exception):
    """Bad chat input (unknown actor or thread)."""


def _store(
    session: Session, person: Person, text: str, thread_id: str | None, *, create: bool = False
) -> tuple[Thread, Message]:
    """Store the user message (and a new thread when needed) and commit it.

    With create=True an unknown thread_id starts a new thread with that id (AG-UI clients name
    their threads); a thread of another person is never continued.
    """
    if session.get(Branch, person.branch_id) is None:
        raise ChatError("person has no branch")
    human = Actor.person(person)
    thread = session.get(Thread, thread_id) if thread_id else None
    if thread is not None and thread.person_id != person.id:
        raise ChatError("thread not found")
    if thread is None:
        if thread_id and not create:
            raise ChatError("thread not found")
        new = Thread(
            branch_id=person.branch_id, person_id=person.id, agent_id=DEFAULT, title=text[:60]
        )
        if thread_id:
            new.id = thread_id
        thread = store.insert(session, new, human)
    message = store.insert(
        session,
        Message(
            branch_id=person.branch_id,
            thread_id=thread.id,
            role="user",
            sender_id=person.id,
            text=text,
        ),
        human,
    )
    session.commit()
    return thread, message


def _context(
    session: Session, person: Person, thread: Thread, before: str | None = None
) -> tuple[list[ModelMessage], AgentDeps, EgressContext]:
    """The run's history (only messages older than `before` when given), deps and egress
    context, for a message already stored."""
    spec = AGENTS[DEFAULT]
    branch = session.get(Branch, person.branch_id)
    if branch is None:
        raise ChatError("person has no branch")
    deps = AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(spec.manifest.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=utcnow().astimezone(ZoneInfo(branch.timezone)).date(),
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
    return history(session, thread, before), deps, ctx


def _prepare(
    session: Session, person: Person, text: str, thread_id: str | None, *, create: bool = False
) -> tuple[Thread, list[ModelMessage], AgentDeps, EgressContext]:
    """Store the user message and commit it; build the run's deps and egress context."""
    thread, _ = _store(session, person, text, thread_id, create=create)
    return thread, *_context(session, person, thread)


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
        deps.answer_id = original_id
        return original
    if language.is_change_command(text) and language.offers_choice():
        return language.ask(session, deps, thread, None)
    if language.needs_asking(session, deps.person):
        user = latest_message(session, thread, "user")
        return language.ask(session, deps, thread, user.id if user else None)
    return text


ROUTE_ASKED = "chat.route_asked"


def _last_mia(
    session: Session, thread: Thread, *, questions: bool = False, notifications: bool = True
) -> Message | None:
    """Mia's latest message on the thread (assistant, or notification unless
    notifications=False). The busy reply is always skipped (it belongs to no agent and asks
    nothing); unless questions=True, so are the route and language questions: they are stored
    under the default agent but belong to no agent."""
    actions = [deferred.DEFERRED] if questions else [deferred.DEFERRED, ROUTE_ASKED, language.ASKED]
    asked = session.exec(
        select(Event).where(Event.entity_id == thread.id).where(col(Event.action).in_(actions))
    ).all()
    key = {deferred.DEFERRED: "busy_message_id"}
    skip = [str((e.after or {}).get(key.get(e.action, "message_id"))) for e in asked]
    roles = ["assistant", NOTIFICATION] if notifications else ["assistant"]
    return session.exec(
        select(Message)
        .where(Message.thread_id == thread.id)
        .where(col(Message.role).in_(roles))
        .where(col(Message.id).not_in(skip))
        .order_by(col(Message.id).desc())
    ).first()


def active_agent(session: Session, thread: Thread) -> str | None:
    """The agent of the thread's latest Mia message (assistant or notification), if any."""
    row = _last_mia(session, thread)
    return row.agent_id if row is not None else None


def _pending(session: Session, thread: Thread) -> Message | None:
    """Mia's latest message when it is a question (it has buttons): its agent keeps the turn."""
    row = _last_mia(session, thread)
    if row is None or not any(b.get("type") == "quick_replies" for b in row.blocks):
        return None
    return row


def _route_tapped(
    session: Session, thread: Thread, text: str
) -> tuple[str, str | None, dict[str, Any]] | None:
    """(agent id, original message id, the question's event after) for a tap on the "Is this
    about" question that is the thread's last Mia message; otherwise None (a stale button is
    plain text)."""
    asked = session.exec(
        select(Event)
        .where(Event.action == ROUTE_ASKED)
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    last = _last_mia(session, thread, questions=True)  # a notification after it makes it stale
    after = (asked.after or {}) if asked is not None else {}
    if last is None or after.get("message_id") != last.id:
        return None
    agent_id = (after.get("options") or {}).get(text.strip())
    return (str(agent_id), after.get("original_message_id"), after) if agent_id else None


MAX_ROUTE_BUTTONS = 6  # QuickRepliesBlock allows six options


def _ask_route(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    agents: list[AgentSpec],
    original_id: str | None = None,
    picked: str | None = None,
    confidence: float | None = None,
) -> ChatReply:
    """ "Is this about" with one button per agent of the person; the tap answers the message
    (`original_id`, by default the thread's latest user message). The event keeps Jev's pick
    and confidence (None without Jev) for the route memory. Over MAX_ROUTE_BUTTONS agents: that many
    buttons, the agent Jev leaned to first (an owner of eight agents asked with all eight was a 500)."""
    if len(agents) > MAX_ROUTE_BUTTONS:
        # ponytail: the rest keep the organisation's order and the tail is dropped; a typed
        # message is routed again, a ranked list from Jev if the dropped ones are missed
        agents = sorted(agents, key=lambda a: a.id != picked)[:MAX_ROUTE_BUTTONS]
    options = {t(a.label_key, deps.lang): a.id for a in agents}
    reply = store_reply(
        session,
        deps,
        thread,
        [TextBlock(text=t("route.question", deps.lang)), QuickRepliesBlock(options=list(options))],
    )
    if original_id is None:
        user = latest_message(session, thread, "user")
        original_id = user.id if user else None
    events.emit(
        session,
        ROUTE_ASKED,
        ("thread", thread.id),
        None,
        {
            "options": options,
            "message_id": reply.message_id,
            "original_message_id": original_id,
            "picked": picked,
            "confidence": confidence,
        },
        deps.actor,
    )
    return reply


def _deps_for(deps: AgentDeps, spec: AgentSpec) -> AgentDeps:
    """The same turn, acted by another agent (its actor and manifest)."""
    return replace(
        deps,
        actor=Actor.person(deps.person).as_agent(spec.manifest.roles.agent_role),
        manifest=spec.manifest,
    )


# (spec, the person's agents, the active agent id, the text to answer, chosen by a route tap)
Chosen = tuple[AgentSpec | None, list[AgentSpec], str | None, str, bool]


def _choose(session: Session, deps: AgentDeps, thread: Thread, text: str) -> ChatReply | Chosen:
    """The steps before the router: no agent (a stored reply), a tap on "Is this about", a
    pending question, one agent, an injection. Returns Chosen; spec None means the router
    decides. A tap on another agent than the active one is a switch (chat.agent_switched);
    every tap is remembered (chat.route_chosen). Commits nothing."""
    agents = agents_for(session, deps.person)
    if not agents:
        return reply_text(session, deps, thread, t("reply.no_agent", deps.lang))
    ids = {a.id: a for a in agents}
    active = active_agent(session, thread)
    active = active if active in ids else None
    tap = _route_tapped(session, thread, text)
    if tap is not None and tap[0] in ids:
        original = language.original_text(session, tap[1])
        if original is not None:
            deps.answer_id = tap[1]
        if active is not None and tap[0] != active:
            spec = ids[tap[0]]
            after = {"from": active, "to": spec.id}
            actor = _deps_for(deps, spec).actor
            events.emit(session, "chat.agent_switched", ("thread", thread.id), None, after, actor)
        options = [str(a) for a in (tap[2].get("options") or {}).values()]
        asked_pick, asked_p = tap[2].get("picked"), tap[2].get("confidence")
        route_memory.remember(session, deps, thread, tap[1], tap[0], asked_pick, asked_p, options)
        return ids[tap[0]], agents, active, original or text, True
    pending = _pending(session, thread)
    if pending is not None and pending.agent_id in ids:
        return ids[pending.agent_id], agents, active, text, False
    if len(agents) == 1:
        return agents[0], agents, active, text, False
    if classify(html.unescape(text), deps.today, deps.lang).injection:
        return ids[active] if active else agents[0], agents, active, text, False
    return None, agents, active, text, False


def _router_input(session: Session, deps: AgentDeps, thread: Thread) -> tuple[str, Pseudonymiser]:
    """Mia's last reply or question in the thread (the router's context; a notification, such
    as a daily plan or an alert, never leaves) and the branch's pseudonymiser."""
    last = _last_mia(session, thread, notifications=False)
    return (last.text if last else ""), Pseudonymiser.for_branch(session, deps.branch.id)


def _settle(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    picked: agent_router.Route,
    agents: list[AgentSpec],
    error: str | None,
) -> ChatReply | AgentDeps:
    """Act on the router's outcome: the "Is this about" question (a stored reply), or the deps
    of the agent that answers (with the switch notice and its event on a switch)."""
    if error is not None:
        events.emit(
            session, "chat.route_failed", ("thread", thread.id), None, {"error": error}, deps.actor
        )
    if picked.kind == "ask" or picked.agent_id is None:
        p = picked.confidence if picked.raw is not None else None  # no Jev, no confidence
        return _ask_route(session, deps, thread, agents, None, picked.raw, p)
    spec = AGENTS[picked.agent_id]
    chosen = _deps_for(deps, spec)
    if picked.kind == "switch":
        label = t(spec.label_key, deps.lang)
        chosen.notice = [TextBlock(text=t("chat.switched", deps.lang, agent=label))]
        events.emit(
            session,
            "chat.agent_switched",
            ("thread", thread.id),
            None,
            {"from": active_agent(session, thread), "to": spec.id},
            chosen.actor,
        )
    return chosen


def _recalled(
    session: Session, deps: AgentDeps, text: str, agents: list[AgentSpec], active: str | None
) -> agent_router.Route | None:
    """The learned route (chosen) for the message (route_memory), or None when an agent is
    active (Jev decides: a learned switch of a live conversation on a generic key such as a
    bare number is too risky), nothing is learned for its key, or the learned agent is no
    longer one of the person's (rule 4)."""
    if active is not None:
        return None
    hit = route_memory.recall(session, deps.branch.id, utcnow()).get(route_memory.key_of(text))
    if hit is None or hit not in {a.id for a in agents}:
        return None
    return agent_router.Route("chosen", hit)


async def route_turn(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    text: str,
    ctx: EgressContext,
    keep: str | None = None,
) -> ChatReply | tuple[AgentSpec, AgentDeps, EgressContext, str]:
    """Pick the agent for a message (spec 2026-10-18, A turn, steps 4 to 7). Returns a stored
    reply (the caller commits), or the agent, its deps and egress context, and the text it
    answers. The Jev request runs with no write lock held. A live turn is deferred while the
    thread waits or when Jev is unreachable; for a resumed turn JevUnreachable propagates.
    `keep` is an agent already chosen (a turn resumed at the agent stage), if still offered.
    A learned key routes before any Jev request when no agent is active."""
    chosen = await asyncio.to_thread(_choose, session, deps, thread, text)
    if isinstance(chosen, ChatReply):
        return chosen
    spec, agents, active, text, tapped = chosen
    if keep is not None and keep in {a.id for a in agents}:
        spec = AGENTS[keep]
    if not deps.resumed and await asyncio.to_thread(deferred.waiting, session, thread):
        lead_id = spec.id if spec is not None else active or agents[0].id
        stage: deferred.Stage = "agent" if tapped else "route"  # a tapped agent is kept
        return await asyncio.to_thread(defer_turn, session, deps, thread, stage, lead_id)
    if spec is not None:
        agent_deps = _deps_for(deps, spec)
        if tapped and active is not None and spec.id != active:  # _choose emitted the switch
            label = t(spec.label_key, deps.lang)
            agent_deps.notice = [TextBlock(text=t("chat.switched", deps.lang, agent=label))]
    else:
        error: str | None = None
        recalled = await asyncio.to_thread(_recalled, session, deps, text, agents, active)
        if recalled is not None:
            picked = recalled  # an exact repeat of a learned tap: no Jev request
        # configuration, not an outage: no request, no failure event. The router is gated like
        # the shift supervisor's decider (D18): MIA_DECIDER=jev turns both on.
        elif ctx.level == "none" or get_settings().MIA_DECIDER != "jev":
            picked = agent_router.fallback(agents, active)
        else:
            previous, pseudo = await asyncio.to_thread(_router_input, session, deps, thread)
            await asyncio.to_thread(session.commit)
            lead = AGENTS[active] if active else agents[0]
            router_ctx = replace(
                ctx,
                actor=_deps_for(deps, lead).actor,
                agent_id=lead.id,
                provider="typesafe",
                purpose="chat.route",
            )
            active_spec = AGENTS[active] if active else None
            try:
                with egress_context(router_ctx):
                    picked = await agent_router.route(text, agents, active_spec, previous, pseudo)
            except JevUnreachable:
                if deps.resumed:
                    raise  # deferred.retry_due tries again next tick
                return await asyncio.to_thread(defer_turn, session, deps, thread, "route", lead.id)
            except JevError as exc:
                picked, error = agent_router.fallback(agents, active), str(exc)
        settled = await asyncio.to_thread(_settle, session, deps, thread, picked, agents, error)
        if isinstance(settled, ChatReply):
            return settled
        agent_deps = settled
        spec = AGENTS[agent_deps.manifest.id]
    agent_ctx = replace(ctx, actor=agent_deps.actor, agent_id=spec.id)
    return spec, agent_deps, agent_ctx, text


def defer_turn(
    session: Session, deps: AgentDeps, thread: Thread, stage: deferred.Stage, agent_id: str
) -> ChatReply:
    """Defer the thread's latest user message (the live turn); a busy reply is the agent's."""
    user = latest_message(session, thread, "user")
    assert user is not None  # the live turn's message is stored before anything runs
    lead = _deps_for(deps, AGENTS[agent_id])
    return deferred.defer(session, lead, thread, user.id, stage, agent_id)


def _expire(
    session: Session,
    deps: AgentDeps,
    thread: Thread,
    message: Message,
    stage: str | None,
    agent_id: str | None,
) -> ChatReply:
    """A turn deferred too long: the agent's ask to rephrase (agent stage) or "Is this about"
    for the message (router stage)."""
    if stage == "agent" and agent_id in AGENTS:
        lead = _deps_for(deps, AGENTS[agent_id])
        return reply_text(session, lead, thread, t("clarify.rephrase", deps.lang))
    return _ask_route(session, deps, thread, agents_for(session, deps.person), message.id)


def resumed_reply(session: Session, person: Person, thread: Thread, agent_id: str) -> ChatReply:
    """The unavailable reply for a deferred turn that failed when resumed, as a notification
    from its agent (the caller commits)."""
    _, deps, _ = _context(session, person, thread)
    deps.resumed = True
    lead = _deps_for(deps, AGENTS[agent_id]) if agent_id in AGENTS else deps
    return reply_text(session, lead, thread, t("reply.unavailable", deps.lang))


async def respond(
    session: Session,
    person: Person,
    thread: Thread,
    message: Message,
    *,
    agent: Agent[AgentDeps, Any] | None = None,
    resumed: bool = False,
    expire: bool = False,
    stage: str | None = None,
    agent_id: str | None = None,
) -> ChatReply:
    """The turn for a stored user message; the caller commits the reply. A live turn runs the
    shared steps first and is deferred when Jev is unreachable. A resumed turn (a deferral
    retried, its shared steps already done; `message` is the one it answers) replies as a
    notification and raises JevUnreachable instead; at the agent stage the same agent answers
    again, and with expire it asks instead of answering (`stage` and `agent_id` come from the
    deferral). `agent` is a Pydantic AI agent for the default agent (tests)."""
    before = message.id if resumed else None
    past, deps, ctx = await asyncio.to_thread(_context, session, person, thread, before)
    deps.resumed = resumed
    if expire:
        return await asyncio.to_thread(_expire, session, deps, thread, message, stage, agent_id)
    text = message.text
    if not resumed:
        shared = await asyncio.to_thread(_before_agent, session, deps, thread, text)
        if isinstance(shared, ChatReply):
            return shared
        text = shared
    keep = agent_id if resumed and stage == "agent" else None
    routed = await route_turn(session, deps, thread, text, ctx, keep)
    if isinstance(routed, ChatReply):
        return routed
    spec, agent_deps, agent_ctx, text = routed
    own = agent if spec.id == DEFAULT else None  # the caller's agent is the default agent's
    try:
        return await spec.handle_turn(Turn(session, agent_deps, thread, text, past, agent_ctx, own))
    except JevUnreachable:
        if resumed:
            raise
        return await asyncio.to_thread(defer_turn, session, agent_deps, thread, "agent", spec.id)


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
    thread, message = await asyncio.to_thread(_store, session, person, text, thread_id)
    return await respond(session, person, thread, message, agent=agent)
