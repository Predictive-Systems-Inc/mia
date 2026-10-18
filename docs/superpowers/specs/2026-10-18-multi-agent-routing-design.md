# Multi-agent routing (design, 18 Oct 2026)

Part 1 of 4, after part 0 (2026-10-18-shift-supervisor-rename-design.md: `dispatcher` becomes
`shift_supervisor`, shared tables): (1) more than one agent per person, (2) the sales supervisor
agent v1 (daily sales reports, Ferino's Bibingka), (3) sales experiments, (4) the
`/mia-build-agent` skill, written while building part 2. This part builds no new agent; it
makes room for them.

## Why

The chat turn is wired to one agent: `chat/service.py` imports the shift supervisor's
MANIFEST, BINDINGS, classifier, Jev actions and decider, and sets `ROLE`. A person who is both an
owner (sales) and a supervisor (cover) cannot reach two agents, and every new agent would copy
the turn code. This design moves the shift supervisor behind one interface, adds a router that picks
the agent for each message, lets each person choose their language once, and queues messages
while Jev is unreachable.

## Scope and data

- In scope: an agent registry, the shift supervisor behind it, access per person, a Jev router,
  agent switching with a notice, per-person language (9 languages), a queue for turns while
  Jev is down, developer alerts, and a real-Jev routing evaluation.
- Stubs (label and router description only) for the other agents of the roster below, so
  routing can be measured before they exist; no organisation enables them yet.
- Out of scope: the sales supervisor agent itself, new tables, real authentication, the role skill
  models (ADR 013).
- No schema change. The active agent comes from `Message.agent_id`; deferrals and language
  choice are events. Jev under D18 sees synthetic and demo data only (Q27 still open).

## Components

| Unit | Job |
| --- | --- |
| `agents/registry.py` | `AgentSpec(id, manifest, label_key, router_description, handle_turn, run_due)` and `AGENTS: dict[str, AgentSpec]`. `run_due(session, now) -> int` is optional. |
| `agents/shift_supervisor/turn.py` | The shift supervisor's `handle_turn`: today's classify, template, clarify, Jev and agent paths, moved out of `chat/service.py` without behaviour change. |
| `agents/stubs.py` | Stub specs for the roster agents not built yet: label and router description; `handle_turn` replies with the `reply.unavailable` text. |
| `chat/access.py` | `agents_for(session, person) -> list[AgentSpec]`: agents enabled for the organisation (org config `agents`, default `[shift_supervisor]`) and allowed by RBAC (`agent:<id>`, action `use`). |
| `chat/agent_router.py` | `route(session, person, thread, text, agents) -> Route`; one Jev request. |
| `chat/language.py` | The language question, the change command, `person.language_chosen`. |
| `chat/deferred.py` | Deferring a turn, retrying deferred turns, the outage alerts. |
| `chat/service.py` | Agent neutral: store, safety checks, language, route, switch notice, `spec.handle_turn`. `chat/runs.py` (AG-UI) uses the same steps. |
| `api/main.py` | The tick calls `run_due` of every registered agent and `deferred.retry_due`, instead of importing the shift supervisor's alerts. |
| `i18n` | `SUPPORTED = ("fi", "en", "fil", "ceb", "ilo", "hil", "war", "bcl", "pam", "pag")`, one strings module per language; a missing key falls back to English. |
| `config/policies/policy.csv` | `agent:<id>`, `use` lines per role, and the new `clerk` role (see Roster). |

## Roster and access

Agents are named after real jobs (D16). For a food shop:

| Agent | Responsibilities | Status |
| --- | --- | --- |
| `sales_supervisor` | clerks' item counts, reminders, day summaries, owner reports, seasonal targets, cheers and tips, why a day beat its target, experiments | part 2 and 3 |
| `shift_supervisor` | rosters, absences, cover, check-in and check-out, daily plan | built (cleaning template) |
| `inventory_manager` | stock and sold-out items, closing leftovers and waste, what to prepare tomorrow, supplier orders | stub |
| `bookkeeper` | cash count against sales, expenses, deposits, VAT and BIR records | stub |
| `hr_officer` | hours, payroll, 13th month, leave, SSS, PhilHealth and Pag-IBIG | stub |
| `branch_manager` | branches, menu, prices, short codes, people and roles, weekly summary | stub |

Access is per role. An organisation lists the agents it runs (`agents` in
`config/org/<org>/settings.yaml`); `policy.csv` says which roles may use each (`agent:<id>`,
action `use`); `Person.roles` says who has which role. A person gets the intersection.

| Role | Agents |
| --- | --- |
| `clerk` (new, under `staff`: `g, clerk, staff, *`) | sales_supervisor, shift_supervisor, inventory_manager |
| `staff` | shift_supervisor |
| `supervisor` | shift_supervisor, sales_supervisor, inventory_manager (every branch) |
| `owner` | all six |

## A turn

1. `_prepare` stores and commits the user message (unchanged).
2. Emergency script, then the injection check. Both before anything else, for every agent.
3. Language: a person with no `person.language_chosen` event gets the language question (see
   Language) and the turn stops; their message is answered after the tap. The exact words
   `language`, `wika`, `pinulongan`, `lengguahe` (with or without a leading `/`) show the
   language buttons and are never routed.
4. `agents_for(person)`. One agent: chosen, no router call. None: the `reply.no_agent` text.
5. Pending question: when Mia's last message in the thread is a question of the active agent
   (clarify buttons, a pending clarification, an open cover request), the agent keeps the turn
   and the router is skipped. A tap on "Is this about" buttons routes to the tapped agent.
6. Router (below). Outcomes: keep the active agent, switch, or ask.
7. On a switch the reply's first block is the `chat.switched` notice ("*(Sales)*", variants,
   in the person's language) and a `chat.agent_switched` event records from and to.
8. `spec.handle_turn(session, deps, thread, text)`; the assistant message carries the agent's
   `agent_id`, and `deps.actor` and `deps.manifest` are that agent's.

## Router

One Jev choice question, `agent`, whose options are the person's agents (`router_description`)
plus `unclear`. State: the message (data, rule 8), the active agent's label, and Mia's last
message. Threshold 0.6, as in the shift supervisor's decider.

| Jev answer | Active agent | Result |
| --- | --- | --- |
| the active agent, any confidence | yes | keep |
| another agent, >= 0.6 | yes | switch |
| another agent or `unclear`, < 0.6 | yes | keep (ties go to the active agent) |
| an agent, >= 0.6 | no | that agent |
| anything < 0.6, or `unclear` | no | "Is this about" buttons, one per agent of the person |
| an answer outside the options | either | treated as a failure (below) |

Pseudonymised like the decider (names in state only). Egress purpose `chat.route`, provider
`typesafe`.

## Language

- The question: `language.ask` in Filipino and English, with one button per organisation
  language, each label in its own language (Filipino, English, Cebuano, Ilocano, Hiligaynon,
  Waray, Bikol, Kapampangan, Pangasinan; Suomi for fi organisations). A tap sets
  `person.language` through the person service and emits `person.language_chosen`.
- Not asked: people created by the seed or an import get `person.language_chosen` at creation
  (their language is known), so today's Finnish users are never asked.
- `detect_language` is removed: every reply uses `person.language`.
- Templates for `fil`, `ceb`, `ilo`, `hil`, `war`, `bcl`, `pam`, `pag` are machine drafts until
  a native speaker reviews them; `docs/questions.md` gets one line per language.
- Pangasinan free text is weak in Jev (docs/research/jev-languages-2026-10-18.md); the rule for
  acting on it belongs to each agent (part 2: confirm before recording).

## Jev unreachable

A network error, timeout, 5xx, or 429/529 after the decider's two retries, in the router or in
an agent's Jev decision:

1. A `turn.deferred` event (message id, thread, agent if known). The message is already stored.
2. One reply per waiting stretch: `reply.busy` ("Mia is busy right now and will answer you
   soon", variants). While a thread has an open deferral, its new messages are deferred
   behind it with no further reply, so answers keep the order the messages came in.
3. Each tick retries deferred turns oldest first, one at a time. Success runs the turn; the
   reply goes out as a proactive message (`chat/channels.py`, so the app and WhatsApp), and
   `turn.resumed` closes the deferral. Still failing: stop the round, try next tick.
4. After 2 hours deferred: the "Is this about" buttons (router) or the agent's clarify (agent
   decision), and `turn.resumed` with `expired: true`.
5. Developer alerts to `MIA_DEVELOPER_PERSON_ID` (their thread and linked channels; empty
   setting means the log only): one when an outage starts (first deferral after a success), one
   when it ends with the count and the longest wait. No message text in either.

`MIA_EGRESS_LEVEL=none` is configuration, not an outage: the router keeps the active agent or
asks with buttons, and nothing is deferred. The shift supervisor's current `decision.failed` reply
(`reply.unavailable`) is replaced by deferral for outages; malformed answers keep the
unavailable reply.

## Errors and safety

- Access is checked twice: `agents_for` filters the options, and `handle_turn` runs with that
  agent's actor, whose tools call `rbac.require` (rule 4).
- The router never sees the language command, emergencies or injection attempts.
- A deferred turn keeps its original actor and message; retrying never runs a turn twice
  (`turn.resumed` is checked under the write lock before running, rule 11).

## Testing

Offline (fake Jev transport, `tests/jev_fake.py`):
- The refactor: the full suite passes with the shift supervisor behind `handle_turn`; its
  tests change imports only.
- Access: only enabled and permitted agents; an agent the person may not use is never offered,
  and a fake Jev answer naming it is a failure (negative test).
- Router: one agent, no Jev call; a pending question keeps the agent; a confident other agent
  switches with the notice in the person's language and the event; an unsure answer keeps the
  active agent; with none active, buttons and a tap; an out-of-options answer fails.
- Language: first contact asks and answers the original message after the tap; seeded people
  are not asked; the change words show buttons and never reach the router; every new i18n key
  exists in all 10 languages.
- Deferral: Jev down defers, replies once, alerts once; Jev back retries oldest first, delivers
  proactively, records `turn.resumed`, sends the end alert with the count; 2 hours expires to
  buttons; egress `none` does not defer; a retry never runs a turn twice.
- Safety: emergency and injection before routing (negative tests).

Real Jev (`node/tests/evals/test_router_eval.py`, `-m evals`, skipped without a key):
- Set (synthetic, D18): the shift supervisor intent test split, the 270 spike messages (sales
  supervisor), about 60 switch cases (a person with both agents moving between sales and cover in
  one thread), and follow-ups after Mia's questions.
- Agents: all six of the roster (the shift supervisor and five stubs), so neighbours like a
  sales report and "puto is sold out" (inventory) compete.
- Measured per language and per agent: right agent at >= 0.6, wrong agent at >= 0.6, ask-back
  rate, p50 and p95 latency, cost per message.
- Pass: wrong agent at >= 0.6 at most 2% of messages, and right agent at least 90% for `en`,
  `fil`, `ceb`, `hil`, `war`, `bcl`. `ilo`, `pam` and `pag` are reported, not gated.
- A deferral check against real Jev: one real request, then the transport is cut, and the
  deferral and recovery are checked end to end.
- Report: `docs/research/router-<date>.md`.

## Docs

- ADR 015: one agent per chat becomes many agents per person, with a router.
- ADR 016: per-person language chosen once replaces language detection.
- `docs/layout.md`: the new modules. README: the router eval command. `.env.example`:
  `MIA_DEVELOPER_PERSON_ID`.
