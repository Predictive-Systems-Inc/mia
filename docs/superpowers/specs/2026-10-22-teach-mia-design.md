# Teach Mia: unrecognised messages become phrases, design

22 October 2026. The owner, testing on the phones page: "when command is not recognize, we should
trigger a smart agent to create and clarify the command which will be added into our database for
future use. how can we implement this while keeping version control", then, after the design
below was given in chat: "okay with that... but when in dev mode (in /sim), we want to add new
commands as we go".

## 1. Two gaps, two paths

- **A phrase gap**: Mia can already do it, the words are new ("sales today?", "anong code ng
  ube"). Learned as data, no code change, after a person approves it.
- **A capability gap**: Mia cannot do it ("send me list of item codes" before 22 Oct). A tool
  carries permissions, risk and approvals (rule 3), so it is never created at runtime. It is
  recorded as a backlog item with the message and a note, and built by a developer through the
  normal agent build.

## 2. What a phrase is

A phrase maps a message key (route_memory.key_of: casefolded, numbers as #) to an agent and one
of its actions, at one branch or at every branch. A key needs a letter: a bare number ("#") is
never a phrase. Money, external and delete actions are never teachable; every other action with
a tool and a button label may be a phrase's target, for routing. A phrase picks the action for
the decider only when that action's tool reads: a write always keeps its question (Did you
mean, or the agent's own guard). The turn still runs the agent's own decider, guards and tool
rbac.

Storage is event-sourced like the learned routes (route_memory reads `chat.route_chosen`):
`phrase.taught`, `phrase.confirmed` and `phrase.retired` events on the hash chain, no new
table, so no data standard change. The phrasebook is the fold of the events that apply to a
branch; its version is the count of them at that branch; every `decision.made` records the
version it used.

## 3. How a phrase is used

1. Routing: an exact key match routes to the phrase's agent before any Jev request, the same
   place `_recalled` routes a learned tap. A taught phrase routes also when another agent is
   active (a person said what it means); a tapped phrase routes only when no agent is active,
   as `_recalled` does.
2. Deciding: the agent's Jev request adds up to three examples per action to that action's
   option text, only from phrases taught on the Teach path by an owner or admin, each at most
   60 characters (data, rule 8: quoted message text, never instructions, pseudonymised like
   the message). A tapped phrase is never an example. When Jev still asks only from its own
   doubt (its pick is clarify or below the threshold), a phrase whose action reads takes that
   action if it is one of Jev's alternatives with no missing input. A decision an agent's
   guard made (`Decision.guarded`: the bookkeeper's cash count or expense question, an order
   with no buy word, a closure, an action outside the side's options, a receipts kiosk's
   confirm) is never overridden.
3. Evals: `mia phrases export` writes each taught phrase as a short-half row of the agent's
   CSV (node/tests/evals/cases/<agent>.csv, intent = the action, extra `"taught": true`) for a
   pull request. The sets' loader leaves taught rows out of their own counts; one shared test
   holds every taught row to the no-wrong-write rule. `mia phrases import --branch` replays
   them at one branch (`--every-branch` for all).

### Learning from Did you mean taps

The owner, 22 Oct: "when I click total benta, it prompted Did you mean, sales today. When I
choose that, system must add confidence level to recognize in the future". A tap on an action
of an agent's "Did you mean" writes `phrase.confirmed` (the asked message's key, the agent, the
action, the person, the branch); Something else writes nothing, and nor does a key with no
letter. Per key, the confidence is the taps for the leading (agent, action) minus the taps for
any other; a key at 1 or more whose latest tap agrees is a learned phrase. It routes when no
agent is active and, for a read, is the hint to the decider; it never becomes an example. The
Phrases drawer shows its confidence and taps. A taught phrase counts as confirmed at once and
outranks taps. Only teachable actions are learned: a tap on a money, external or delete action
runs that turn and is never learned.

## 4. Dev mode on the phones page: teach as you go

On /sim (dev and loopback only), when Mia answers with a rephrase, a "Did you mean" or a reply the
tester did not want, the phone shows a **Teach** chip under that reply:

- It opens a picker of the phone owner's agents and their teachable actions (labels from the
  existing intent i18n keys), plus **Mia can't do this yet**.
- Picking an action writes `phrase.taught` at once (dev mode: the tester is the approver; actor
  the person on that phone, on behalf of the tester) and resends the message, so the tester sees
  the taught answer immediately.
- **Mia can't do this yet** asks for a one-line note and writes `capability.requested` (the
  message, the person's role, the note); `mia phrases export` also writes these to
  docs/backlog/capabilities.csv for the developer.
- A **Phrases** drawer in the top bar lists taught phrases with Retire, and shows the phrasebook
  version.

No model is called on the teach path: the tester picks. Nothing here runs in required mode.

## 4b. Request a feature (every user, every mode)

The owner, 22 Oct: "add a button for users to request to support certain action. this is a
global database of feature request".

- Every person can ask for something Mia cannot do: a **Request a feature** button in the app's
  menu and on each phone of the phones page, and in chat the reply to a capability gap offers it
  as a button ("Ask for this feature"). Staff on WhatsApp can also type "request: <what>".
- The request holds: what the person wants in their own words (data, rule 8), the message that
  failed if there was one, the person's role, branch and language, and the time. It is written as
  `feature.requested` on the node's hash chain (no new table, no data standard change) and the
  person is told it was sent.
- The same request from several people is grouped by code (the key of the text, as phrases);
  each person's request still counts.
- **Global**: the node's requests go to one shared list across every Mia node, where the
  developer sees them and marks them planned, built or declined; the node shows each request's
  status back to whoever asked. Where that list lives is the owner's decision (Q130): it is a new
  external service, and the request text leaves the node (pseudonymised: names and numbers
  masked as for Jev). The owner's answer (22 Oct, Q130): keep it on the node for now. Each node
  keeps its own list, `mia requests export` writes it for the developer, nothing leaves the node,
  and the developer marks a request's status with `mia requests status <id> planned|built|declined`
  so the asker sees it. A shared place is chosen later (for example when Mia Cloud exists).

## 4c. Phase 1c: report questions

The owner, 22 Oct: "benta last week per item... we need a smart model to respond to this? cache
the result. As developer, I dont think we can think of all possible inquiries... so we can let
agent collaborate and clarify what user needs. This should then be added as a global rule."
D45 (23 Oct): a hosted model through the egress point fills a fixed report form; code computes
every figure (rule 7).

**The global rule.** When a person asks for figures no existing read answers, Mia does not
guess and does not say "rephrase": a model turns the words into a fixed form, or picks one
clarifying question from a fixed list, and code does the rest. The model never sees a sales
figure and never writes one. Today the rule is built for sales (the sales supervisor); another
agent adopts it with its own form when its owner asks.

**When the step runs** (code decides, never the model):
- the sales supervisor's decider ends in `clarify` with no offerable alternative (today's
  "rephrase") or in `reply_only` of kind `other` or `capabilities`, and the message is
  report-like: it holds a report word (`REPORT_WORDS` in actions.py, en and fil: benta, sales,
  sold, nabenta, magkano, ilan, how many, how much, total, report, per, bawat, kada, compare) and
  is not counts only (`Query.counts_only` false);
- or the person taps **Something else** on a "Did you mean" asked about a report-like message
  (the asked message found as `phrases.confirm_tap` finds it).
The person must hold the report tool (below), checked before any model request. Anything else
keeps today's reply. With the step off (below) the old reply stands.

**What leaves the node** (rule 6, purpose `sales_supervisor.report`): the message, with person
names as Person_n (egress.Pseudonymiser, as for the gateway) and mobile numbers as "<number>"
(events.mask_value, as jev.ask does); the other digits of the message stay, the form needs them
("last 2 weeks"). Beside it, as data: today's business date, the branch menu (item ids and
names), the kiosks the person may read (ids and names), the period ids, and the schema. The
message sits inside a quoted boundary and is never an instruction (rule 8). No sales figure, no
count and no receipt is sent. The request goes through `EgressTransport`, so it is logged in
`egress_log` and metered in `usage_cloud_requests`; `MIA_EGRESS_LEVEL=none` blocks it and the
old reply stands.

**The form** (`ReportForm`, pydantic, every field closed):
- `measure`: `pieces` or `amount` (sales amount); later `expenses` (not in 1c).
- `group_by`: `none`, `item`, `day`, `weekday`, `kiosk`, `tender`, `clerk`.
- `period`: a named period (the decider's period ids: today, yesterday, this_week, last_week,
  this_month, last_month, a weekday) or explicit `start` and `end` dates; at most
  `sales.MAX_SALES_DAYS` (400) days, never after today.
- `filters`: `items` (menu ids), `kiosks` (branch ids), `tenders` (cash, gcash, maya, grab,
  foodpanda: `models.TENDERS`).
- `compare_to`: `none`, `previous_period` (the same length just before), `same_period_last_year`.
Combinations code refuses: a tender grouping or tender filter with `pieces`, or with `item` or
`clerk` grouping (`DaySales.by_tender` is per branch and day only); a compared range that needs
more than 400 days.

**Or a clarifying question**: instead of a form the model may return one of `which_kiosk`,
`which_period`, `which_measure`, with the partial form. Code builds the buttons (the kiosks the
person may read, plus "all" for an owner or admin; the named periods; pieces or amount), each
button holding the completed form, as every "Did you mean" button holds its decision. A tap runs
the form; a typed answer starts a new turn. One question per message: a second clarify on the
same message gets today's rephrase.

**Code runs the form** through one new read tool, `sales_supervisor.report` (risk read, no
approval, reads as `period_report`; rule 3): validate the form (an invalid one gets today's
rephrase and is logged as `decision.failed`), check rbac exactly as `period_report` does (the tool
is held by supervisors, admins and owners, as `period_report` is; a clerk holds neither, so her
report question keeps today's reply and the step calls no model for her; another kiosk or "all"
needs `read_all` on the counts and the receipt tables, so owners and admins only), and `group_by`
`clerk` needs `read` on
`sales_counts` without the reporter shortcut (supervisors, admins, owners; a clerk is refused, as
today she never sees another clerk's figures). The sums come from `sales.sale_rows` (pieces and
amounts per branch, date, clerk and item) and `sales.days_sales` (`by_tender`), each date from its
one source. A refused range answers `sales.refused.range` as today.

**The reply**: a text table (i18n keys, the person's language): a head line (measure, period,
grouping, total), then one line per group, largest first (menu order for `item` with no compare,
date order for `day`), the top 10 (`replies.TOP`) then "and N more" (`sales.period.more`); with
a compare each line and the total add the percent change (`calc.compare`). On a receipts day item
amounts are before a receipt discount and tender amounts after it, as `DaySales` says.

**Save as a report** ("cache the result": the form, never the figures): the answered reply
carries a **Save as a report** button when the period is a named period (a form with explicit
dates is not saved: its key has the dates as # and would replay the old dates). A tap writes
`report.saved` (the key of the message, `route_memory.key_of`; the form; the person; the branch)
on the hash chain, folded in `mia/chat/phrases.py` beside the phrases (no table, no data standard
change), so the phrasebook version counts it; `report.retired` withdraws a key (Retire in the
Phrases drawer, an owner or admin). The next message with the same key at that branch routes to
the sales supervisor as a taught phrase does and runs the saved form through
`sales_supervisor.report` with no Jev and no model request; rbac is checked again for whoever
asks. Anyone who got the answer may save it (it only reads, as a learned tap). `mia phrases
export` writes the saved reports to `node/tests/evals/cases/sales_supervisor_reports.csv`
(text, key, form as JSON) for a pull request, a test validates every row's form, and `mia phrases
import` replays them as `report.saved` by the system actor. The Phrases drawer lists them with
the form in words.

**Which model.** A new setting `MIA_REPORT_MODEL`, default empty. Empty means `MIA_MODEL` when
that is a `gateway/<route>` (the route the node already pays for), else the step is off.
The repo configures no hosted route today: `MIA_MODEL` defaults to `test`, `.env.example` names
`gateway/shift_supervisor-default` only as an example, and the dev and Ferino's test nodes run
`local/qwen3.5:9b`. So on today's settings the step is off until a route is set.
`MIA_REPORT_MODEL=gateway/<route>` (through `MIA_GATEWAY_URL`, `MIA_GATEWAY_KEY` and egress, as
`agents.base.build_model` builds it) or `local/<model>` (nothing leaves; a small local model may
fill the form badly, measure first); `test` is a deterministic fake (keywords to forms and
clarify answers) for tests, and tests never reach a network. Cost and latency (estimates to
check on the first runs, metered per request in `usage_cloud_requests`): one request is about
1.5k input tokens (instructions, schema, menu, kiosks) and under 200 output tokens; on a small
hosted model that is well under one US cent and one to three seconds. A saved report costs
nothing after its first answer.

**Tests**: the form validator refuses each bad combination and a range over 400 days; a
supervisor's `kiosk` grouping is denied, an owner's passes; a clerk's report question calls no
model; the executor's sums equal
`period_report`'s for the same period on counts and receipts days; with the fake, "benta last week
per item" answers the per-item table and its figures come from the database, never the model's
answer (a fake that returns figures is ignored); a clarify answer shows code-built buttons and a
tap runs the form; the step does not run with the setting off, with egress `none`, or on a counts
message; Save writes `report.saved` and the next identical message runs with no model request
and no Jev request; export and import round-trip; the egress log row carries purpose
`sales_supervisor.report` and no person name.

## 5. Production: the nightly proposal (phase 2)

Unblocked by D45 (23 Oct): the same hosted model, through the same egress rules (names as
Person_n, mobile numbers masked, the message quoted as data, logged and metered), with its own
purpose `phrases.propose`.

- When a turn ends in a rephrase, or in a Something else tap that phase 1c did not answer, Mia
  writes `intent.unrecognised` (the message id, the agent, the branch; the text stays in the
  messages table, not in the event).
- Once a night (the tick, after the branch's closing hour) each branch's unrecognised messages
  of the day, at most 50, by distinct key, skipping keys already in the phrasebook, go to the
  model with each agent's teachable actions (ids and their English option text). The model
  answers per key: an action id, `report` (phase 1c should have taken it: logged only),
  `capability_gap`, or `none`.
- Code keeps only an action that is teachable for that agent (never money, external or delete),
  writes `phrase.proposed`, and raises one approval card per proposal for the owner or an admin
  (D45 keeps the spec's default); approving writes `phrase.taught` with the approver as the
  actor, declining writes nothing more. A `capability_gap` becomes a `capability.requested` row
  in the backlog export. Nothing is taught without a person.
- Off with `MIA_REPORT_MODEL` off or egress `none`. Its own plan, after phase 1c.

## 6. Version control

- Runtime: events, append-only, each with actor and time; version = event count; rollback =
  `phrase.retired` (nothing is deleted); decisions record the version.
- Git: `mia phrases export` writes the CSV rows and the backlog file; a pull request carries them;
  CI runs the rows; merging is the release of those phrases as test data. A phrase that causes a
  wrong write fails CI and is retired.
- A fresh database starts with no phrases; `mia phrases import` replays the exported rows as
  `phrase.taught` events by the system actor, so a test database can be rebuilt with them.

## 7. Tests

A taught phrase routes the next identical message (numbers aside) to its agent without a Jev route
request, also with another agent active; a retired phrase stops routing; a money or delete action
is refused as a teach target; the teach route is 404 outside dev mode and off loopback; the
export writes valid CSV rows and import replays them; the decision event carries the phrasebook
version; Rosa's "sales today?" taught to sales_today then answers at once.

## 8. Not in phase 1

The nightly model review and the approval card (phase 2, unblocked by D45, its own plan after
phase 1c); report questions are phase 1c (section 4c); teaching slot values (a
phrase names an action, the agent's parser still reads the details); per-person phrases.
