# Router follow-up: retail gate, small talk, and learning from taps

18 Oct 2026. Follows docs/superpowers/specs/2026-10-18-multi-agent-routing-design.md (part 1)
and its evaluation docs/research/router-2026-10-18.md, whose gate failed (right agent 50 to
83% in the gated languages, wrong agent 1.2%). This spec makes the gate measure the traffic a
shop sends, stops the router from asking about small talk, tunes the two descriptions that
collide, and makes Mia remember what people chose when she asked. It changes no data standard
table and adds no external service.

## Goal

A clerk at Ferino's Bibingka should rarely see "Is this about" buttons, and when they do tap
one Mia should not ask the same thing again. Measured: the part 1 gate (right agent at least
90% per gated language, wrong agent at most 2% overall) on a retail case set, and the ask rate
on repeated messages going to zero after two confirmations.

## What the evaluation showed

- 74.5% of greetings, thanks and conversation intents ask. Jev says `unclear` at 0.8 to 0.95:
  it is sure the message is for no agent. With no active agent the router turns that into a
  question, which is the wrong reading of a confident `unclear`.
- Many cases were replies inside a flow ("deal", "all of them pls") sent with no context. The
  chat never routes these (a pending question skips the router), so they do not belong in the
  gate.
- 16 of 60 switch cases kept the shift supervisor on a sales report (ceb, bcl, war). Sales and
  inventory were confused in both directions (a sell-out is both).

## Decisions

### 1. A confident "no agent" is small talk, not a question

Router table change (`chat/agent_router.decide`): when Jev picks `unclear` with confidence at
or above the threshold (0.6) and no agent is active, the route is `chosen` for the person's
lead agent (the first agent of `agents_for`), kind `small_talk`. The lead agent answers as it
does any greeting (the shift supervisor's `reply_only`). No "Is this about" buttons, no
switch notice, no `chat.agent_switched`. With an agent active, a confident `unclear` keeps the
active agent as today.

"Is this about" buttons remain for the case they were made for: Jev unsure between agents
(confidence below 0.6), no active agent, and no learned answer (decision 4).

### 2. The gate measures retail traffic

`node/tests/evals/router_cases.py` is rebuilt from the scenario list in
docs/superpowers/specs/2026-10-18-sales-supervisor-design.md (when it exists; until then the
agent and scenario catalogue agreed on 18 Oct, kept in that file's appendix):

- Per gated language (en, fil, ceb, hil, war, bcl) at least 60 single cases spread over the
  six agents (counts, corrections, "how are we doing", sick, late, cover, sold out, leftovers,
  cash count, expenses, payslip, SSS, price change, new clerk, permits), 10 follow-up cases
  with an agent active, 10 switch cases. Greetings and thanks stay in the set but are scored
  right when the route is `small_talk` or any agent.
- In-flow replies are removed from the single group. They may appear only as follow-up cases
  with the right `previous_mia_message` and active agent.
- Finnish, Ilocano, Kapampangan and Pangasinan are reported, not gated, as before.
- The gate asserts stay as in part 1. The harness keeps `picked`, the 30 s per-request
  timeout, and gains a `small_talk` column in the report.

Machine-drafted texts in the Philippine languages carry the same review note as before
(docs/questions.md Q28 to Q35).

### 3. Descriptions that do not collide

`agents/stubs.py` and `agents/shift_supervisor/turn.py` router descriptions are rewritten
with a contrast line each, in the shape "X, not Y". Sales: "what was sold and for how much;
not how much stock is left". Inventory: "stock, ingredients and what to bake; not sales
counts. A sell-out message is inventory". Shift supervisor: "who works when; not what they
sold". The descriptions are tuned only against the training half of the case set; the gate
runs on the held-out half (the harness splits by case id parity).

### 4. Mia remembers what people chose

Three pieces, in the chat layer, so every agent gets them.

**a. The event.** When a person taps an "Is this about" button, `chat/service._route_tapped`
leads to one event `chat.route_chosen` on the thread: `original_message_id`, `agent_id`
(chosen), `picked` and `confidence` (what Jev said), `options` (the agent ids shown), `lang`.
Events are the memory (rule 2). No new table.

**b. Exact repeats are routed by code.** Before calling Jev, `chat/route_memory.py`
(new, pure functions plus one query) looks for a learned answer:

- key: the message text normalised (casefold, whitespace collapsed, trailing punctuation
  dropped, digits replaced by `#` so "3 sp 2 cl" and "5 sp 1 cl" are one key), per branch;
- a key is learned for an agent when at least two `chat.route_chosen` events in the branch
  carry it for the same agent and none for another agent in the last 90 days;
- a later `chat.agent_switched` away from that agent on a message with the same key within
  one hour unlearns it (the same undo idea as `learning/harvest._undone`);
- a learned key routes `chosen` with kind `learned`, confidence 1.0, before any Jev call, only
  when no agent is active or the learned agent differs from the active one (then it is a
  `switch` with the usual notice and event). With the same agent active nothing changes.

The lookup is one query over `chat.route_chosen` events of the branch, in `asyncio.to_thread`
(rule 12). ponytail: a scan of the branch's route_chosen events per message; an index or a
cached table when a branch passes thousands of taps.

**c. Harvest for the local model.** `learning/harvest.py` gains a source
`real-route-choice`: each `chat.route_chosen` becomes a `Record` with `role = "router"`,
`intent = agent_id`, pseudonymised text and context, pending review, under the same undo and
sensitivity rules as intent clarifications. The records feed the skill-models pipeline
(D27) when a router model is trained; this spec does not train one.

**Out of this spec:** examples in Jev descriptions and a local router model (step 3 of the
plan). They are measured against the ask rate after a and b have run on real taps.

### 5. The owner can see and clear it

`mia learned <branch>` (CLI) lists the learned keys per agent with their counts. `mia forget
<branch> <key>` emits `chat.route_forgotten` with the key, after which the key is not learned
until two new taps. The web page is part 2 work. Events, so auditable; no table.

## Guardrails that stay

- A tap is data (rule 8): only the agent id is learned, never the text as an instruction.
- Nothing new leaves the node. The learned route skips the Jev call. Harvested records stay in
  `MIA_LEARNING_DIR`, pseudonymised, and leave only under D27.
- Rule 4: the learned agent must still be in `agents_for(person)`; a person who lost access to
  an agent does not reach it through memory (the key is ignored, Jev decides).
- Rule 7: the learning rule (two confirmations, 90 days, one hour undo) is code with unit
  tests; Jev only answers when memory has nothing.
- Rule 15: no agent id literal outside manifests and `stubs.py`; the memory stores ids it read
  from events.

## Events (new)

| Event | Entity | After |
| --- | --- | --- |
| chat.route_chosen | thread | original_message_id, agent_id, picked, confidence, options, lang |
| chat.route_forgotten | branch | key, agent_id, actor |

`chat.route_asked` and `chat.agent_switched` are unchanged. A learned route emits
`chat.agent_switched` only when it switches.

## i18n

No new user-facing strings in the chat. CLI output goes through i18n keys `cli.learned.*` in
all ten languages, machine drafts noted as before.

## Testing

- Unit: `decide` with confident `unclear` and no active agent gives `small_talk`; with an
  active agent keeps it; below threshold still asks.
- Unit: `route_memory` normalisation, the two-confirmation rule, the 90-day window, the
  one-hour undo, the access check, the forget event.
- Chat tests (fake Jev): a tap emits `chat.route_chosen` with Jev's pick and confidence; the
  third identical message routes without a Jev call (the fake counts calls); a switch away
  within the hour unlearns; a notification does not make a tap stale for the memory.
- Harvest: a route choice becomes a pending `router` record; an undone one does not.
- Real-Jev eval (opt in): the gate on the held-out half of the retail set, with the
  `small_talk` column. Report in docs/research/router-<date>.md, like part 1.

## Open questions (docs/questions.md)

- Q36: should a learned key be per person or per branch? Assumed per branch: clerks share
  the shop's words and one clerk's confirmation helps the next.
- Q37: should the owner be told when Mia learns a key? Assumed no; `mia learned` is enough
  until the owner page exists.

## Order of work

1. Decision 1 (small talk) and 3 (descriptions), with the unit tests.
2. Decision 2 (retail case set) and the eval run; the gate must pass on the held-out half
   before 4 ships, so that memory does not hide a routing problem.
3. Decision 4a and 4b, then 5, then 4c.
