# Jev decider for the dispatcher (design, 17 Oct 2026)

## Why

Gemma 4 12B alone reaches 77 to 79% on the dispatcher suite and 89% (English) or 77% (Finnish)
on intent classification (docs/research/local-models-2026-10-12.md), under the 95% gate of D18.
Most misses are format errors, extra tool calls and confused neighbouring intents. This design
tries a different shape: Jev (TypeSafe's System One model) picks the action and its inputs as
typed choices with probabilities, code runs the tool, and reply templates word the answer. No
model writes text and no model calls tools.

## Scope and data

- A second decider next to the Pydantic AI agent, chosen by `MIA_DECIDER=agent|jev` (default
  `agent`). The agent path does not change.
- Jev is a hosted service (`POST https://api.typesafe.ai/v1/systemone`). Under D18 it sees
  synthetic and demo data only: the eval suites Gemma was measured on. Real Hype traffic stays
  on `agent`. Using Jev with real data needs TypeSafe's data terms checked and an ADR amending
  D18 first.
- Out of scope: the role skill models (training waits on Gate 1, Q26), other agents, real
  authentication changes, new tables.

## Actions

Jev chooses exactly one of 12 actions per message.

| Action | Tool inputs (who fills them) | From intents |
| --- | --- | --- |
| `get_my_visits` | `start`, `end` (code parses dates, Jev picks), `person_name` (Jev picks from people) | my_visits |
| `record_absence` | `date` (candidates), `reason` (sick, late, leaving_early, other), `partial_day` (morning, afternoon, none), `person_name` | report_absence, absence_scope |
| `find_replacements` | `visit_id` (Jev picks from visits) or `location_name`, `date`, `time` | find_cover |
| `assign_cover` | `visit_id` (thread state: the visit find_replacements showed), `candidate_id` (Jev picks from the candidates shown) | assign |
| `respond_to_cover` | `accept` (yes or no) | cover_reply |
| `check_in`, `check_out` | `location_name` (Jev picks from today's sites) | check_in, check_out |
| `visit_details` | `location_name` | visit_details |
| `report_site_problem` | `kind` (cannot_access, site_problem), `text` (the message, copied), `location_name` | cannot_access_site, site_problem |
| `checklist` | `item` (Jev picks from the visit's checklist items), `location_name` | checklist |
| `clarify` | none; options are the top 2 or 3 actions, or the candidate visits or sites | low confidence, missing input |
| `reply_only` | none | greetings, thanks, send_photos (the reply says to attach them), other, injections |

Jev fills only closed sets (choices, yes or no). Every value it can pick is a candidate code
listed first: dates parsed from the message (the regex classifier already extracts them), the
branch's sites and people, the person's visits today and this week, checklist items. Each
input also has a "stated" question; when the message does not state it, the tool's default
applies. Free text is copied, never generated.

## Flow

```
message -> safety step (unchanged) -> decide() -> call_tool() -> reply() -> channel
```

1. Safety step: the emergency script and injection flag in `_classify_turn`
   (mia/chat/service.py) run first. A flagged injection becomes `reply_only` without a Jev call.
2. State for Jev: the message, the last Mia message in the thread (for absence_scope and
   cover_reply), the person's role and the candidate lists. Messages are data, set apart in
   `state` from the instructions (rule 8).
3. One Jev request: a choice question over the 12 actions plus every action's input
   questions; code reads only the chosen action's answers. The request goes through
   `egress.send()` (rule 6, pseudonymised at the default level, logged in egress_log) with no
   write lock held (rule 11).
4. Decision: the call's confidence is its least certain judgment. At or above the threshold
   the tool runs through `call_tool()` in mia/agents/base.py (guard, rbac.require, events,
   actor and on_behalf_of; rules 3 to 5). Below it, or with a required input missing, the
   action is `clarify`.
5. Reply: a template key from action and outcome, a random variant, blocks added by code
   (details card, quick replies).
6. Follow-ups: a tapped quick reply runs its action directly, without a new Jev call.
   Multi-turn state (absence then scope, find then assign) stays in the thread as today.

## Components

| File | Guarantees |
| --- | --- |
| `mia/agents/dispatcher/actions.py` (new) | The typed table of the 12 actions: Jev description, input questions, candidate source, required inputs, the confidence threshold. |
| `mia/agents/dispatcher/decider.py` (new) | `decide(deps, message, last_mia_text) -> Decision(action, args, confidence, alternatives)`. Builds state and questions, calls Jev through egress, parses answers. Runs no tool, writes nothing but egress_log and the `decision.made` event. |
| `mia/agents/dispatcher/replies.py` (new) | `reply(decision, tool_output, lang) -> Message`. Picks key and variant, fills it from the tool output, adds blocks. |
| `mia/i18n/__init__.py` | `t()` accepts a string or a list of variants; a list picks one with an optional `random.Random` (seeded in tests). Single strings work as before. |
| `mia/i18n/strings.py` | `reply.<action>.<outcome>` keys, 3 to 5 variants each, fi and en. |
| `mia/chat/service.py` | After the safety step, `MIA_DECIDER=jev` takes decide, call_tool, reply; otherwise the agent. DB work in worker threads (rule 12). |
| `mia/settings.py`, `.env.example` | `MIA_DECIDER`, `MIA_TYPESAFE_URL`, `MIA_TYPESAFE_KEY`, `MIA_JEV_MODEL` (pinned, for example `jev-1.12`, never `jev-latest`, so measurements compare). |

No new dependency: the call is one httpx POST (no TypeSafe SDK or cooksafe). No schema change:
decisions go to the events log.

## Errors

| Case | Behaviour |
| --- | --- |
| 429 or 529 | Up to 2 retries with backoff, then `reply.unavailable`; the message is kept. |
| Other error or 10 s timeout | `reply.unavailable` and a `decision.failed` event with the code. No fallback to the agent, so a measurement is Jev alone. |
| Egress level `none` | EgressBlocked before the network; `reply.unavailable`. |
| Tool not allowed for the role | guard() refuses; `reply.not_allowed`. |
| Required input missing | `clarify` with the candidates as quick replies. |
| Tool returns `invalid` | Its outcome template, for example `reply.check_in.too_early`. |

## Tests

Unit tests, offline, Jev behind a mock transport:
- decider: request shape; answer parsing; low confidence and a missing input give clarify;
  errors give unavailable.
- Negative tests: egress `none` blocks the call; a forbidden tool is refused; an injection
  never reaches Jev.
- replies: every action and outcome has fi and en keys; all variants of a key share their
  placeholders; a seeded generator gives a known variant.
- i18n: `t()` with a single string is unchanged.

## Measurement

The same tests as the Gemma report of 12 Oct, with `MIA_DECIDER=jev`:
- the 48 dispatcher scenarios (`-m evals`);
- the intent test split, English (1091) and Finnish (1051).

The threshold is chosen on the dev split; the test split is read once. The report goes to
`docs/research/jev-2026-10-<day>.md` with the Gemma tables side by side, plus latency and
cost per message.

## Open points

- TypeSafe's data retention, region and processing terms are not in its docs; they decide
  whether Jev can ever see real data (ADR then).
- The eval scenarios check tool calls and blocks; scenarios that check the model's wording may
  need a template-aware assertion. Found while wiring the suite, not decided here.
