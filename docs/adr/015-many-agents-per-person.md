# ADR 015: Many agents per person, with a router

## Status

Accepted.

## Context

The chat ran one agent: `chat/service.py` imported the shift supervisor and every turn went to
it. Retail needs several agents for one person (a clerk reports sales and stock and asks about
shifts; an owner also reads the money and HR), in one conversation and in nine languages
(spec docs/superpowers/specs/2026-10-18-multi-agent-routing-design.md).

## Decision

- An agent registry (`mia/agents/registry.py`): each agent is an `AgentSpec` (manifest, i18n
  label, an English router description, its turn and its due work). Agents not built yet are
  stubs (`mia/agents/stubs.py`) that say Mia cannot answer that yet. No chat code imports a
  specific agent.
- Access per role (`mia/chat/access.py`): a person's agents are those their organisation runs
  (org config `agents`, in that order) that their roles may use (policy `agent:<id>`, action
  `use`). Each tool still runs `rbac.require` (rule 4).
- A sticky Jev router (`mia/chat/agent_router.py`): one choice over the person's agents plus
  `unclear`, threshold 0.6. The active agent keeps the turn unless Jev is confident about
  another one; a switch puts a notice first in the reply and emits `chat.agent_switched`. With
  no active agent and no confident pick, Mia shows "Is this about" buttons. A person with one
  agent, a pending question of the active agent, and the safety steps skip the router.
- Turns are deferred while Jev is unreachable (`mia/chat/deferred.py`): one busy reply, later
  messages queue behind, each tick retries oldest first and delivers the answer proactively,
  and after 2 hours the turn expires to a question. The developer hears when an outage starts
  and ends.

## Consequences

- A new agent adds a spec, a registry entry and policy lines, not chat code.
- One conversation per person: the agents share the thread, and each reply carries its
  `agent_id`.
- The router costs one Jev request per message for people with more than one agent (about 770
  tokens, 0.36 s p50).
- The router gate failed on 18 Oct 2026 (docs/research/router-2026-10-18.md): wrong agent at
  >= 0.6 was 1.2% (pass, at most 2%), but right agent was 50% to 83% in the gated languages
  (fail, at least 90%), mostly from ask-back on greetings and in-flow replies with no context.
  The descriptions, the case set and greeting handling are tuned in a later task before more
  than the shift supervisor ships.
