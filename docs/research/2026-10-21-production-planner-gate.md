# Jev production planner decider and router evaluation (21 Oct 2026)

Spec docs/superpowers/specs/2026-10-21-production-planner-design.md (scenarios 1 to 7 and 9,
section 10). Questions: does Jev pick the right production planner action, and where the
scenario has them the right item, kiosk, direction and number, from what the commissary head,
the owner, the driver and a kiosk supervisor send; and does the router send the commissary's
plan, batches and dispatch to the planner while kiosk stock and sales counts stay with the
inventory manager and the sales supervisor. Synthetic data only (D18). Raw results, all in this
folder: `production-planner-2026-10-21-0747.raw.json` (the tune half, a harness check, no
tuning), `-0748` (the gate half, once) and `router-2026-10-21-0749.raw.json` (the router, once,
on a fresh gate half).

**What happened, in order.**

1. **Tune half (`0747`)**, run to check the harness end to end: right 69.3%, wrong 1.0% (3), ask
   29.7%. Nothing was tuned after it: the action descriptions (`production_planner/actions.py`)
   are not this task's, and the controller's rule for this gate is one run, reported as it is.
2. **Decider gate (`0748`, the fresh gate half, once) failed.** Wrong 2.7% (bar at most 2%:
   fail); right below 80% in fil, ceb, hil, war and bcl, ask above 15% in every language but en.
   en passes (86.0% right, 12.0% ask). Reported as it is.
3. **Router gate (`0749`, a fresh gate half, once) failed.** Wrong 4.5% (bar at most 2%: fail);
   right below 80% in hil, war and bcl, ask above 15% in hil, war and bcl; en, fil and ceb pass
   on right and ask. Reported as it is; no router description was edited.

## Setup

Model `jev-1.13.0` (the pinned `MIA_JEV_MODEL` default), threshold 0.6, egress level
`pseudonymised`, concurrency 4. Ferino's is seeded by the `pp_shop` fixture on Tuesday 10 Nov
2026 (`PP_TODAY`) with the clock at 10:00 Manila, so the production day the tools edit is
Wednesday 11 Nov; the harness drafts that plan (`tools.draft_plan`) before the run and pins
today to the case set's `TODAY`. Each case runs `build_query` and `decider.decide` inside
`egress_context`, as the agent for head Nonoy (commissary), owner Rosa, driver Berto (staff with
the `driver` skill) or supervisor Marites (Mall kiosk). The harness wraps the shared
`decider.parse` to keep Jev's slot answers per case (by message id), so the item, kiosk,
direction and number Jev picked can be scored; the decision itself is unchanged. 0 errors in
both decider runs and the router run.

Code under test: `node/mia` exactly as committed at df3374c (Task 4's fix round c3fc690 and
7652815, Task 7's ten languages df3374c; at run time those edits were in the working tree on
HEAD 23e8fb3, and `git diff 23e8fb3 df3374c -- node/mia` matches that tree, fingerprint
`1baf256fc6db`; no file under `node/mia` changed during the runs).

Scoring: **right** is the expected action and, where the scenario has them, the expected item
(by name), kiosk (by name), direction (add, remove, set) and number (the value of the number id
Jev picked); **wrong** is another of those, or another action at >= 0.6; **ask** is clarify or a
missing input; **other** is an error or another action below 0.6.

## Case set

`node/tests/evals/production_planner_cases.py`: ten asks (plan and confirm for scenario 1, orders
in the plan for 2, change for 3, batch_sheet 4, recipe 5, batch 6, dispatch and delivered for 7,
capacity 9) in six languages (en, fil, ceb, hil, war, bcl), ten seeds each, even seeds tune and
odd seeds gate (a seed's languages share a half; no text in both halves, shape test): 600 cases,
300 per half, 50 per language and half. Senders: the head for plan, confirm (with Mia's draft
plan as the previous message), orders, change, batch sheet and batch; the owner for recipe and
capacity; a kiosk supervisor for dispatch; the driver for delivered. English seeds first; the
other five are drafts by Claude, not native speakers (review: Q28 to Q35). The shape test checks
that code reads every value Jev picks (rule 7): each expected number is a `words.numbers`
candidate, each batch report a `words.batch` parse, each recipe a full `words.recipe` parse
(yield, oven minutes, lines, no unknown part), and each added or removed item a line of the
drafted plan; no change text names today (subong, karon, yana), which would ask for another
day's plan. Scenarios 8 (the match tick) and 10 (role boundaries) have no chat ask and are
covered by the due and chat tests.

## Decider gate (`0748`, the gate half, once)

| Language | n | Right | Wrong | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- |
| English (`en`) | 50 | 86.0% | 2.0% | 12.0% | pass |
| Filipino (`fil`) | 50 | **78.0%** | 0% | **22.0%** | **fail** |
| Cebuano (`ceb`) | 50 | **66.0%** | 6.0% | **28.0%** | **fail** |
| Hiligaynon (`hil`) | 50 | **62.0%** | 2.0% | **36.0%** | **fail** |
| Waray (`war`) | 50 | **78.0%** | 2.0% | **20.0%** | **fail** |
| Central Bikol (`bcl`) | 50 | **68.0%** | 4.0% | **28.0%** | **fail** |
| **Gated, all** | 300 | 73.0% | **2.7%** (bar <= 2%: fail) | 24.3% | **fail** |

| Ask (spec scenario) | Tune (`0747`) right | Gate (`0748`) right | Gate ask | Gate wrong |
| --- | --- | --- | --- | --- |
| plan (1) | 70.0% | 80.0% | 20.0% | 0% |
| confirm (1) | 100% | 93.3% | 6.7% | 0% |
| orders (2) | **30.0%** | **46.7%** | 53.3% | 0% |
| change (3) | 73.3% | 60.0% | 30.0% | **10.0%** |
| batch_sheet (4) | **33.3%** | **53.3%** | 36.7% | 10.0% |
| recipe (5) | 100% | 100% | 0% | 0% |
| batch (6) | 80.0% | 96.7% | 3.3% | 0% |
| dispatch (7) | 80.0% | 56.7% | 36.7% | 6.7% |
| delivered (7) | 53.3% | 66.7% | 33.3% | 0% |
| capacity (9) | 73.3% | 76.7% | 23.3% | 0% |

Each row is 30 cases (five seeds in six languages).

- **Worst on wrong: Cebuano** (6.0%, three of its fifty: two of the removes read as sets and
  one "itlog ... ube" read as Salted egg).
- **The 8 wrongs.** Three are writes: a remove read as a set ("kuhai og usa ka batch ang
  classic" and "kuhai og 2 ka batch ang ube" in ceb, "kuhai hin 2 nga batch an ube" in war; 0.61
  to 0.73), so code would set the line to 1 or 2 batches instead of taking them off; the
  direction options name only the English and Filipino words ("remove: bawasan, bawas, less"),
  not ceb or war "kuhai" (the hil "buhini" was asked, below). Three are reads: "how many eggs
  for the ube" (ceb, hil, bcl "itlog ... ube") picked the item Salted egg at 0.61 to 0.75. Two are
  reads too: "how many pieces are we getting tomorrow?" (en, bcl) from a kiosk supervisor read
  as the plan, not the dispatch (0.67, 0.79).
- **The 73 asks: 45 are the right action below 0.6** (Jev's own pick, `raw_action`): change 7,
  delivered 7, capacity 7, plan 6, orders 10, batch sheet 4 and others. The rest: questions about
  orders in the plan answered with clarify (5) or a change (1); "how much rice flour / how many
  coconuts for the classic" read as the plan, a recipe or a change (7); a kiosk supervisor's "ano
  an maabot yana" or "is our bibingka on its way" answered with clarify (5) or read as the plan
  below 0.6 (4); the driver's "nahatod na" in ceb read as small talk (2) and bcl "naitao na"
  answered with clarify (1); the hil "buhini" (take off) read as a batch report
  (2, missing batch, so nothing was written); fil "aprubahan ang plano" picked change_plan at
  0.13 (asked).
- **Code reads all it should**: every recipe of the gate half was right with its item (30 of
  30), every batch report but one (29 of 30), and no case had a wrong number or a wrong kiosk.

## Router gate (`0749`, once)

The router description at HEAD (Task 5, `production_planner/turn.py`): "The commissary's
production: tomorrow's plan per item and its batches, batch sheets and recipes, yield and waste
of a batch, the dispatch to each kiosk and its delivery, oven capacity for a date; not kiosk
stock, not sales counts." The harness is unchanged (`test_router_eval.py`, `ROSTER` every
registered agent, the spent half never run).

`router_cases.py` changes: `PRODUCTION_PLANNER_SEEDS`, ten seeds per gated language, even seeds
tune ("add one batch of ube to tomorrow's plan", "what's the production plan for tomorrow?",
"batch sheet for the classic", "recipe ube: 36 pieces, 2 kg rice flour, 1 tray eggs, 45 min",
"dispatch list for the Mall kiosk"), odd seeds gate ("batch 3 ube 34 ok 2 burnt", "what's coming
to our kiosk from the commissary today?", "can the ovens do 200 classic on Dec 24?", "the Street
stall delivery is done", "approve tomorrow's production plan"); `PENDING` emptied. **Halves:**
the 21 Oct (second) gate half (`GATE_SHIFT_SEEDS`, `GATE_SHIFT_CONTEXT` and the odd
`SHIFT_RETAIL_SEEDS`) was scored in `router-2026-10-21-0301` and is now `spent`; a fresh gate
half was written before any run of it (`GATE_PLANNER_SEEDS`, `GATE_PLANNER_CONTEXT`: five
singles for every other agent, the inventory manager's naming kiosk stock and "received 40
classic from the commissary", the sales supervisor's naming counts; two greetings, five
follow-ups and five switches per gated language, two of each to or from the planner). The
inventory manager and sales supervisor seeds that name stock or counts are kept.
`test_kiosk_stock_and_counts_stay_off_the_planner` checks those seeds are in the gate half and
that the description ends on the contrast; `test_short_cash_routes_to_the_bookkeeper` now reads
its Q108 seeds from the spent half.

| Language (gate half, no greetings) | n | Right | Wrong | Ask | Gate |
| --- | --- | --- | --- | --- | --- |
| en | 50 | 90.0% | 4.0% | 6.0% | pass (right, ask) |
| fil | 50 | 84.0% | 6.0% | 8.0% | pass (right, ask) |
| ceb | 50 | 86.0% | 4.0% | 8.0% | pass (right, ask) |
| hil | 50 | **76.0%** | 4.0% | **18.0%** | **fail** |
| war | 50 | **74.0%** | 4.0% | **20.0%** | **fail** |
| bcl | 50 | **74.0%** | 6.0% | **16.0%** | **fail** |
| **all (312, with greetings)** | 312 | 80.8% | **4.5%** (bar <= 2%: fail) | 12.8% | **fail** |

Other (below 0.6 on another agent, the active one kept): 1.9% (6). Greetings 10 of 12 right.
By agent (gate half, no greetings): bookkeeper 100%, shift_supervisor 95.2%, inventory_manager
83.3%, sales_supervisor 83.3%, customer_service 80.0%, hr_officer 80.0%, branch_manager 76.7%,
**production_planner 52.1%** (25 of 48; ask 31.2%, other 12.5%, wrong 4.2%). By group: singles
81.3%, follow-ups 90.0%, switches 66.7%.

- **The 14 wrongs.** Six are one seed: "I'd like sick leave for Monday" went to the shift
  supervisor in all six languages (0.89 to 0.97); the seed was written as the HR officer's (a
  leave filing), but the shift supervisor's description names "being sick", so the label is
  arguable. Six are one seed: "how is Liza doing at selling?" went to the sales supervisor in all
  six (0.90 to 0.99; coaching per clerk is the branch manager's). Two are the planner's: fil
  "tapos na ang hatid sa Street stall" and bcl "tapos na an hatod sa Street stall" went to
  customer_service (0.73, 0.68).
- **No other agent's gate message went to the planner**, and every inventory manager and sales
  supervisor seed naming kiosk stock, a commissary receipt or counts went to its own agent or was
  asked, none to the planner. The contrast holds; the planner's own misses are confidence and
  the driver's delivered message.
- **The planner's 23 misses**: its batch report, kiosk question and plan changes asked below 0.6,
  in hil, war and bcl and once in fil (10); the driver's "the Street stall delivery is done" asked or sent to
  customer_service in five languages (6 of 6 missed); the switch "delivered the bibingka to the
  Mall kiosk" kept on the active shift supervisor in five languages (other, 0.47 to 0.67) and
  asked in en; "saro pang batch nin special sa plano sa aga" kept on the active inventory
  manager (bcl, 0.42).
- **Four customer_service asks had the planner as top pick, below 0.6**: "how many delivery
  orders tomorrow?" in en, fil, ceb and hil (0.37 to 0.42, asked, so nothing went to the
  planner; war and bcl picked customer_service, also below 0.6). The planner's "delivery" words
  pull at customer orders for delivery; none crossed the threshold.

Tune half (1,082 rows, all languages): right 77.8%, wrong 1.4%; gated languages 83.9%, wrong
0.8%. The planner's tune seeds route at 100% (30 of 30).

## Latency, tokens, cost (measured)

Per request, measured in the harness around `decider.decide` (decider) or `jev.ask` (router);
tokens from the usage rows (input plus output).

| Run | Cases | Mean s | p95 s | Max s | Tokens | Per message |
| --- | --- | --- | --- | --- | --- | --- |
| decider tune (`0747`) | 300 | 0.36 | 0.44 | 0.65 | 727,729 | 2,426 |
| decider gate (`0748`) | 300 | 0.35 | 0.40 | 0.62 | 722,958 | 2,410 |
| router (`0749`, tune and fresh gate) | 1,394 | 0.35 | 0.41 | 1.67 | 1,572,586 | 1,128 |

The usage rows carry no cost (`cost_minor` 0); at TypeSafe's list price of $0.042 per million
input tokens (output free) the three runs are at most $0.13 (3.02 million tokens): a price
applied to measured tokens, not a billed amount.

## Reading

- **What would write wrong**: three removes read as sets in ceb and war (the line set to the
  number instead of reduced by it). The capacity precheck still runs in the tool, so no change
  past the ovens is written, but the plan line would be wrong until the head looks at the card.
- **Recipes and batch reports are code's and hold** (100% and 96.7% on the gate half); the
  misses are in the questions (orders in the plan, ingredient amounts, what is coming), where the
  Visayan languages ask most.
- **The router keeps kiosk stock and counts off the planner** (no wrong route to it), but the
  driver's delivered message and the planner's Visayan asks fall below the bar, and the gate's
  wrong rate is two seeds of other agents.

## What remains (the developer decides)

- The decider: whether to name the Visayan remove words ("kuhai", "buhini", "bawasi") in the
  `remove` direction, the ingredient words in batch_sheet ("ilang itlog", "ilang kilo"), the
  orders question in plan and the kiosk supervisor's "what am I getting" in dispatch, then tune
  on the tune half and rerun on fresh decider gate seeds: this gate half is spent.
- The item pick: "itlog ... ube" picked Salted egg (an egg word in the item's name); code could
  prefer an item named in full over a word inside another item's name.
- The router: the driver's delivered line (customer_service and a kept shift supervisor), the
  sick leave and per-clerk selling seeds (label or description); a rerun needs a fresh router
  gate half (`GATE_PLANNER_SEEDS` and `GATE_PLANNER_CONTEXT` are spent with `0749`).
- The non-English messages are drafts (Q28 to Q35).
- Record `cost_minor` in the usage rows.

## Notes after the run (numbers unchanged, no rerun)

- 21 Oct 2026, fix wave B: the decider changed after `0748`. Add and remove words in all ten
  languages (`words.DIRECTION_WORDS`): a change whose add or remove word disagrees with Jev's
  direction, or has one with the direction not stated, asks (missing "direction"); set applies
  only without either kind of word, so the three ceb and war removes read as sets now ask. The
  items the message names are found by code (`words.named`): one item named and another picked,
  or two named, asks (missing "item"), so "itlog ... ube" picking Salted egg now asks. A unit word
  wins over Jev's unit, and a capacity number with no unit and no item named asks. A menu name
  with a digit ("Box of 4") is never a count, and "ibig kong sabihin" (and its regional forms)
  corrects a number as "pala" does. Tests: `test_production_planner_actions.py`.
- 21 Oct 2026, fix wave B: router descriptions changed after `0749`. hr_officer's gains "filing
  sick or vacation leave for a date" (the "sick leave for Monday" seed is labelled right: the HR
  officer has file_leave); sales_supervisor's contrast gains "not how a clerk is doing" (the "how
  is Liza doing at selling" seed is labelled right: coaching per clerk is the branch manager's);
  the planner's own description gains the driver's delivered words (fix wave A).
- These gates are not rerun: both gate halves are spent, and a rerun needs fresh gate seeds
  (spec, Carried over).
