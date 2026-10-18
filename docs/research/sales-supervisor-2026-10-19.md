# Jev sales supervisor decider evaluation (19 Oct 2026)

Spec docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (section 9). Does Jev pick
the right sales action, with the right items for a count, from what Ferino's clerks, head staff
and owner send? Synthetic data only (D18). Raw results: `sales-supervisor-2026-10-19-0245.raw.json`
(final run, tuned descriptions) and `sales-supervisor-2026-10-19-0243.raw.json` (first run,
committed descriptions). Harness `node/tests/evals/test_sales_supervisor_evals.py`, case set
`node/tests/evals/sales_cases.py`.

**Result: the gate fails on right, passes on wrong.** Gate half, six gated languages (270
cases): a wrong action at >= 0.6 is 0.7% (gate at most 2%: pass); right is 66.7% to 95.6% per
language (gate at least 90%: only English passes). Every miss that is not wrong is an ask (a
"Did you mean" or a which-item question); there were no errors. Two runs were allowed; this
is the second.

## Setup

- Model `jev-1.13.0`, threshold 0.6, egress level `pseudonymised`, concurrency 4. Per case:
  Ferino's seeded into a temp database, `build_query` for the case's sender (clerk Ana,
  supervisor Marites or owner Rosa) with `deps.lang` set to the case language, then
  `decider.decide` inside `egress_context` (provider `typesafe`, purpose
  `sales_supervisor.decide.eval/<i>`), so the request leaves through egress, pseudonymised.
  540 cases, 0 errors, about 53 s per run.
- Scoring: **right** when the decision's action is the expected one with no missing input
  and, for counts and corrections, the recorded (item name, quantity) pairs equal the expected
  ones (order-free); **wrong** when another action is chosen at >= 0.6; **wrong items** when
  the expected action is chosen with other items (a wrong write, counted apart; 0 in run 2);
  **ask** when the decision is clarify or a required input is missing; **other** on an error.
  The gate asserts read the gate half only.
- Run 1 used the committed descriptions. After it I edited the action descriptions and the
  item criteria once (no run was going), then ran again. Run 2 is the result.

## Case set

Ten messages per scenario per gated language (en, fil, ceb, hil, war, bcl), 90 per language,
540 in all; even positions within a (language, scenario) list tune, odd positions gate (five
and five). English seeds first, the five Philippine languages as Claude's drafts (Q28 to Q35
cover their review). Item names and short codes are the seed's.

| Scenario | Expected action | Sender | Examples (en) |
| --- | --- | --- | --- |
| counts_codes | report_sales | clerk | "3 sp 5 cl 2 se", "ube 7", "4 se 2 co total 310" |
| counts_names | report_sales | clerk | "3 special 5 classic 2 salted egg", "2 boxes" |
| correction | correct_sales | clerk | "sorry, 4 special not 3", "change special to 9" |
| today | sales_today | clerk, supervisor, owner | "how are we doing today" |
| target | set_target | owner, supervisor | "target today 3,500", "the target for October is 75,000" |
| period | sales_period | supervisor, owner | "best day this month?", "how did Saturday go" |
| branch_item | sales_period | owner | "which branch sells most salted egg" |
| why | why_answer | clerk (after Mia's why question) | "it was payday, lots of customers" |
| reply_only | reply_only | clerk, owner | "hello po", "what can you do?", an injection |

The offline check `test_sales_cases.py` asserts the counts, that every expected action is in
`ACTIONS`, that `pre_parse` gives each count case the expected quantities in order, no
"Tagalog", and balanced halves. Spec scenarios 4 to 6 (closing reminder, end-of-day report,
morning message) are due work with no message to decide and are covered by the unit tests;
scenario 10 (first contact on a channel) is `mia person add --ask-language` plus the language
question.

## The tuning edit (once)

From run 1's tune-half misses: why answers read as `reply_only` (12 of 30), "kumusta ... Domingo"
read as a greeting (wrong at 0.74 to 0.97), "how many have we sold today" read as a count,
lone counts ("cl 8", "ube 7") below 0.6, corrections without "no, it was" read as counts, and
"kahon" (box) not matched. Edits in `actions.py`: `report_sales` names short codes, either
order and lone counts, "not a question about how many were sold"; `correct_sales` lists the
correction words (not, should be, wrong, mistake, sorry, change, fix, in any language);
`sales_today` names "how much or how many were sold so far"; `sales_period` names the best
day, how a weekday went, a past target and branch comparisons; `why_answer` points at
`previous_mia_message` and lists kinds of reasons; `reply_only` excludes an answer to Mia's
question and a "kumusta" about sales or a day. The item criteria now ask which item the
group's number counts, allow the name in the sender's language, say a correction may name the
item after the number, and choose none for money, a target or a total. The case set, scoring
and threshold were not touched.

| Half, gated languages (n 270) | Run 1 right | Run 1 wrong | Run 2 right | Run 2 wrong |
| --- | --- | --- | --- | --- |
| tune | 70.0% | 3.0% | 85.9% | 1.9% |
| gate | 64.4% | 2.6% | 75.6% | 0.7% |

Unlike the router run, the edit carried over to the gate half (right +11.2 points, wrong
-1.9 points), so the misses are general wording problems more than one-off messages.

## Gate (gate half, run 2)

| Language | n | Right | Wrong | Wrong items | Ask | Gate (right >= 90%) |
| --- | --- | --- | --- | --- | --- | --- |
| English (`en`) | 45 | 95.6% | 0% | 0% | 4.4% | pass |
| Filipino (`fil`) | 45 | 77.8% | 0% | 0% | 22.2% | fail |
| Cebuano (`ceb`) | 45 | 71.1% | 0% | 0% | 28.9% | fail |
| Hiligaynon (`hil`) | 45 | 66.7% | 0% | 0% | 33.3% | fail |
| Waray (`war`) | 45 | 71.1% | 2.2% | 0% | 26.7% | fail |
| Central Bikol (`bcl`) | 45 | 71.1% | 2.2% | 0% | 26.7% | fail |
| **Gated, all** | 270 | 75.6% | **0.7%** (gate <= 2%: pass) | 0% | 23.7% | |

| Scenario (gate half) | n | Right | Wrong | Ask |
| --- | --- | --- | --- | --- |
| counts_codes | 30 | 70.0% | 0% | 30.0% |
| counts_names | 30 | 80.0% | 0% | 20.0% |
| correction | 30 | 30.0% | 3.3% | 66.7% |
| today | 30 | 76.7% | 0% | 23.3% |
| target | 30 | 76.7% | 0% | 23.3% |
| period | 30 | 83.3% | 0% | 16.7% |
| branch_item | 30 | 86.7% | 3.3% | 10.0% |
| why | 30 | 90.0% | 0% | 10.0% |
| reply_only | 30 | 86.7% | 0% | 13.3% |

## Tuning half (run 2)

| Language | n | Right | Wrong | Ask |
| --- | --- | --- | --- | --- |
| en | 45 | 97.8% | 2.2% | 0% |
| fil | 45 | 84.4% | 0% | 15.6% |
| ceb | 45 | 84.4% | 4.4% | 11.1% |
| hil | 45 | 80.0% | 0% | 20.0% |
| war | 45 | 84.4% | 2.2% | 13.3% |
| bcl | 45 | 84.4% | 2.2% | 13.3% |
| **Gated, all** | 270 | 85.9% | 1.9% | 12.2% |

Both halves, all 540: right 80.7%, wrong 1.3%, ask 18.0%.

## Wrong actions (all seven at >= 0.6, run 2)

| Lang | Half | Message | Expected | Chosen | Conf. |
| --- | --- | --- | --- | --- | --- |
| bcl | tune | kumusta kita kan Domingo? | sales_period | reply_only | 0.85 |
| ceb | tune | kumusta ta sa Dominggo? | sales_period | reply_only | 0.84 |
| war | tune | kumusta kita han Domingo? | sales_period | reply_only | 0.84 |
| war | gate | hain kita pinakadamu nakabaligya hin kape? | sales_period | sales_today | 0.77 |
| en | tune | how are we doing today | sales_today | reply_only | 0.71 |
| bcl | gate | tadongon: classic 10 | correct_sales | report_sales | 0.67 |
| ceb | tune | sayop, kape unta 6 | correct_sales | report_sales | 0.63 |

## Top ten confusions (all non-right, both halves, run 2)

| Expected -> Jev's pick (score) | Cases |
| --- | --- |
| correct_sales -> report_sales (ask) | 22 |
| report_sales -> report_sales (ask) | 20 |
| sales_period -> sales_period (ask) | 10 |
| set_target -> set_target (ask) | 7 |
| sales_period -> reply_only (ask) | 7 |
| why_answer -> why_answer (ask) | 7 |
| sales_today -> sales_today (ask) | 7 |
| reply_only -> reply_only (ask) | 5 |
| sales_period -> reply_only (wrong) | 3 |
| correct_sales -> correct_sales (ask) | 3 |

## Latency, tokens, cost

p50 0.38 s, p95 0.46 s (highest language p95 0.51 s, Waray). 2,894 tokens per message on
average (run 1: 2,698; the longer descriptions add about 200), 1,562,574 in all for run 2;
at TypeSafe's $0.042 per million input tokens about $0.07 for the run, $0.00012 per message.
A sales request is about three times a router request (864) because each count group adds an
`item_<i>` question with the whole menu.

## Reading

- **Wrong is rare; ask is the problem.** 0.7% wrong on the gate half, no wrong items at all:
  when Jev records a count, it records the right items. The misses are asks (23.7%), which
  cost a tap, not a wrong row.
- **Corrections are the weak scenario (30% right on the gate half).** Two causes, both in the
  shape of the request rather than the descriptions: "5 classic hindi 6" splits into two
  groups, Jev reads it as a report of two counts, and the second group ("6", no words) has no
  item, so it asks which item (11 of 20 gate-half correction asks). "gawin mong 9 ang special"
  (make special 9) and "ayusin: classic ay 10" read as reports below 0.6. In the chat a
  report whose action is clear (>= 0.6) with an unknown item asks which item for the second
  number; if the clerk taps an item, that would record two new counts instead of a correction.
- **Lone counts and confident slots.** "ube 7" and "cl 8" still ask in five languages: the
  action is right but below 0.6. Asks with no missing input had confidences of 0.12 to 0.59;
  the confidence is the least certain judgment the action used (the action, period or branch
  slot), so a vague period ("best day this month") or an unsure branch pulls a right action
  under the threshold.
- **English passes, the Philippine languages trail by 18 to 29 points.** The tuning carried
  over to the gate half, so another wording pass is likely to help, but it has to be measured
  on a fresh gate set.
- **Not a latency problem**: 0 errors, 0.46 s p95.

## What remains

1. The gate is not met for right in fil, ceb, hil, war, bcl. The gate half is spent as a
   measure; a further pass needs a fresh gate set.
2. Corrections need code, not wording (rule 7): when the message has a correction word (not,
   hindi, dili, indi, diri, bako) between two numbers, `pre_parse` should give one group with
   the new quantity, so Jev sees one count and the turn never asks which item the old number
   is. A test for "5 classic hindi 6" belongs with it.
3. `pre_parse` also splits a multi-item count with a leading word ("sold 3 special 5 classic"
   gives "3 sold", "5 special classic"); the case set avoids that form, so this run does not
   measure it. It needs the same fix before real traffic.
4. Decide whether 90% right per language is the bar for the sales supervisor too, given asks
   are safe and wrong is 0.7% (see Q40 for the router's answer: right at least 80%, ask at
   most 15%).
5. The chat scenarios (`agents/sales_supervisor/tests/scenarios.yaml`, run by
   `test_sales_supervisor_scenarios.py`) have not been run against real Jev yet.
