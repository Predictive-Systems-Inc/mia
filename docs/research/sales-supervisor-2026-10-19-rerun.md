# Jev sales supervisor decider evaluation on a fresh gate half (19 Oct 2026, rerun)

Spec docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (section 9). Follows
docs/research/sales-supervisor-2026-10-19.md, whose gate half is spent and now part of the tune
half. Same question: does Jev pick the right sales action, with the right items for a count,
from what Ferino's clerks, head staff and owner send? This run is the first after the
`pre_parse` fix in d9c0ca6 (a negation word drops the old number, so "5 classic hindi 6" is one
group). Synthetic data only (D18). Raw results: `sales-supervisor-2026-10-19-0349.raw.json`
(run 1, committed descriptions) and `sales-supervisor-2026-10-19-0353.raw.json` (run 2, after
one tuning edit on the tune half). The report has the `-rerun` suffix because
`sales-supervisor-2026-10-19.md` exists.

**Result: the gate fails on right and ask, passes on wrong.** Run 2, gate half, six gated
languages (540 cases), measured against the Q40 bar the router uses (docs/questions.md Q40):
wrong at >= 0.6 is 1.9% (bar at most 2%: pass); right 71.1% to 93.3% per language (bar at
least 80%: en and fil pass); ask 5.6% to 25.6% (bar at most 15%: only en passes). No wrong
items, no errors. Two runs were allowed; this is the second.

## What changed since the first 19 Oct run

- **The bar.** The harness now asserts the Q40 bar (the router's `_gate_failures`: wrong at
  most 2%, right at least 80% and ask at most 15% per gated language), not the old 90% right.
  The sales set has no greetings scored as `any`, so every row counts.
- **A fresh gate half.** Ten new messages per scenario per language (540), written before any
  result was seen. Message n of a scenario is one seed in every language, so a seed's
  languages share a half. The 540 old messages (the spent gate half included) are the tune
  half. New count cases carry their own expected items (`GATE_ITEMS`); the offline checks pass
  on them (`pre_parse` gives one group per expected item with the right quantity and an item
  word; a correction gives one group), and a new test checks that no text (casefolded) is in
  both halves.
- **`pre_parse` (d9c0ca6)**: negations, scored orientations.

## Setup

Model `jev-1.13.0`, threshold 0.6, egress level `pseudonymised`, concurrency 4, Ferino's
seeded per run, `build_query` for the case's sender, `decider.decide` inside `egress_context`.
1080 cases, 0 errors, 103 s and 107 s of wall time. Scoring as before (right, wrong, wrong
items, ask, other).

## The tuning edit (once, from run 1's tune half only)

Run 1's tune-half misses: corrections read as reports after `pre_parse` left one number
("5 classic hindi 6" to `report_sales` at 0.60 to 0.92, 10 wrong, 16 asks); lone counts
("10 sp", "8 special", "cl 8 sana") right but under 0.6; targets for the whole month asked
(15); "kumusta ang Sabado" and "kumusta kita kan Domingo" as `reply_only` (4 wrong, 7 asks);
why answers about the shop ("sarado ang katabing stall") asked; "who are you" asked. Edits in
`agents/sales_supervisor/actions.py`:

- `report_sales`: "a lone count is a report too", "not a correction (a count with a correction
  word)".
- `correct_sales`: the correction words in the gated languages as the tune half has them
  (hindi, dili, indi, diri, bako; dapat, unta; mali, sala, sayop; gawin, himoa, himua,
  gibuhon; ayusin, usba, ilisan, tadongon), examples, "a correction word makes it a correction
  even when only one number is left".
- `sales_period`: "which branch (or where) sells most of an item", "a 'kumusta' about a
  weekday or a past day is a question about that day's sales"; `reply_only`: "a message that
  names a day is about sales", "who Mia is".
- `set_target`: day or month in any wording, their branch or a named one.
- `why_answer`: a short statement about the shop, the items, a neighbour or a person.
- The period question also asks "which day is a count for", not stated for a plain count; the
  conversation option "capabilities" includes "who Mia is".

Case set, scoring and threshold were not touched; the item criteria were not changed.

| Half, gated languages (n 540) | Run 1 right | Run 1 wrong | Run 1 ask | Run 2 right | Run 2 wrong | Run 2 ask |
| --- | --- | --- | --- | --- | --- | --- |
| tune | 80.7% | 3.0% | 16.1% | 88.1% | 0.6% | 11.3% |
| gate | 74.4% | **4.8%** | 20.7% | 78.1% | **1.9%** | 20.0% |

## Gate (gate half, run 2)

| Language | n | Right | Wrong | Wrong items | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- | --- |
| English (`en`) | 90 | 93.3% | 1.1% | 0% | 5.6% | pass |
| Filipino (`fil`) | 90 | 82.2% | 1.1% | 0% | 16.7% | fail (ask) |
| Cebuano (`ceb`) | 90 | 75.6% | 1.1% | 0% | 23.3% | fail |
| Hiligaynon (`hil`) | 90 | 72.2% | 3.3% | 0% | 24.4% | fail |
| Waray (`war`) | 90 | 71.1% | 3.3% | 0% | 25.6% | fail |
| Central Bikol (`bcl`) | 90 | 74.4% | 1.1% | 0% | 24.4% | fail |
| **Gated, all** | 540 | 78.1% | **1.9%** (bar <= 2%: pass) | 0% | 20.0% | |

| Scenario (gate half) | n | Run 1 right | Run 1 wrong | Run 2 right | Run 2 wrong | Run 2 ask |
| --- | --- | --- | --- | --- | --- | --- |
| counts_codes | 60 | 61.7% | 0% | 71.7% | 0% | 28.3% |
| counts_names | 60 | 73.3% | 0% | 78.3% | 0% | 21.7% |
| **correction** | 60 | **38.3%** | **35.0%** | **66.7%** | **11.7%** | 21.7% |
| today | 60 | 85.0% | 3.3% | 83.3% | 1.7% | 15.0% |
| target | 60 | 85.0% | 0% | 83.3% | 0% | 16.7% |
| period | 60 | 83.3% | 1.7% | 91.7% | 0% | 8.3% |
| branch_item | 60 | 73.3% | 1.7% | 68.3% | 1.7% | 30.0% |
| why | 60 | 80.0% | 1.7% | 80.0% | 1.7% | 18.3% |
| reply_only | 60 | 90.0% | 0% | 80.0% | 0% | 20.0% |

| Run 1, gate half | n | Right | Wrong | Ask |
| --- | --- | --- | --- | --- |
| en | 90 | 91.1% | 1.1% | 7.8% |
| fil | 90 | 78.9% | 3.3% | 17.8% |
| ceb | 90 | 72.2% | 7.8% | 20.0% |
| hil | 90 | 71.1% | 4.4% | 24.4% |
| war | 90 | 66.7% | 7.8% | 25.6% |
| bcl | 90 | 66.7% | 4.4% | 28.9% |

## Corrections, called out

On the first 19 Oct run, before the `pre_parse` fix, corrections were 30.0% right on that
gate half, almost all asks: "5 classic hindi 6" split into two groups and the second asked
which item. With the fix, run 1 (committed descriptions) shows the other side: one group
left, Jev reads a report, so corrections are 38.3% right and **35.0% wrong** (21 of 60, each
a new count where a correction was meant). After the tuning edit (correction words in the
description), run 2 is 66.7% right, 11.7% wrong (7 of 60) and 21.7% ask. Every remaining
wrong is `report_sales` for a correction: "classic 3 hindi 4" (fil, ceb, hil at 0.63), "ube
sadang 6" and "ayda an box, 4 sadang" (war), "special 11, indi 10" (hil), "ribayan an kape
nin 2" (bcl). In the chat that records a second count instead of replacing the first, the
one harmful write this decider makes; the correction words are known to code (`NEGATIONS`),
so rule 7 points at code here, not wording.

## Tuning half (run 2)

| Language | n | Right | Wrong | Ask |
| --- | --- | --- | --- | --- |
| en | 90 | 96.7% | 0% | 3.3% |
| fil | 90 | 94.4% | 0% | 5.6% |
| ceb | 90 | 87.8% | 0% | 12.2% |
| hil | 90 | 83.3% | 0% | 16.7% |
| war | 90 | 82.2% | 2.2% | 15.6% |
| bcl | 90 | 84.4% | 1.1% | 14.4% |
| **Gated, all** | 540 | 88.1% | 0.6% | 11.3% |

## Wrong actions (all ten at >= 0.6, gate half, run 2)

| Lang | Message | Expected | Chosen | Conf. |
| --- | --- | --- | --- | --- |
| en | how many have we sold since opening | sales_today | sales_period | 0.95 |
| war | ube sadang 6 | correct_sales | report_sales | 0.88 |
| war | ayda an box, 4 sadang | correct_sales | report_sales | 0.81 |
| hil | special 11, indi 10 | correct_sales | report_sales | 0.79 |
| war | hain gimaopay nga baligya an cheese overload? | sales_period | sales_today | 0.75 |
| bcl | ribayan an kape nin 2 | correct_sales | report_sales | 0.71 |
| fil | classic 3 hindi 4 | correct_sales | report_sales | 0.63 |
| ceb | classic 3 dili 4 | correct_sales | report_sales | 0.63 |
| hil | classic 3 indi 4 | correct_sales | report_sales | 0.63 |
| hil | madamo nga office workers nga nag-lunch break | why_answer | reply_only | 0.62 |

Top confusions, both halves, run 2: report_sales asked (36), set_target asked (23),
sales_period asked (20), reply_only asked (17), correct_sales asked (14), why_answer asked
(11), correction read as a report (10 asks, 9 wrong).

## Latency, tokens, cost

Run 2: p50 0.38 s, p95 0.45 s. 3,378 tokens per message on average (run 1: 3,109; the longer
descriptions add about 270), about 3.65 million for the run; at TypeSafe's $0.042 per million
input tokens about $0.15, $0.00014 per message.

## Reading

- **Wrong is under the bar, ask is the problem.** 1.9% wrong and no wrong items on the gate
  half. 20% ask, mostly the right action under 0.6: lone counts and code counts (28.3% ask),
  branch comparisons (30%), targets (16.7%).
- **The tuning carried over partly.** Tune half +7.4 points right, gate half +3.7; the
  correction words carried over best (correction right 38.3% to 66.7% on fresh text), the rest
  barely moved, and reply_only lost 10 points on the gate half.
- **English passes, Filipino nearly; the Visayan and Bikol drafts trail by 18 to 22 points.**
  These are machine drafts (Q28 to Q35), so part of the gap may be the texts themselves.

## What remains

1. The gate is not met for right in ceb, hil, war, bcl or for ask outside English; this gate
   half is spent too.
2. Corrections by code (rule 7): when `pre_parse` drops a negated number, or the message has
   a correction word next to the one count, offer Jev only `correct_sales` and `clarify` for
   the action, or pass a `correction` flag in state. This is the only wrong write left.
3. Confidence is the least certain judgment the action uses; for a lone count the period slot
   pulls a right `report_sales` under 0.6. Dropping the period judgment for a count with no
   day word (code) would turn most count asks into rights.
4. The chat scenarios have still not been run against real Jev.

Under D40 (21 Oct 2026) this run reads: bcl, ceb and en pass; fil fails (ask 17%, above 15%), hil fails (wrong 3.3%), war fails (wrong 3.3%). Computed from the relaxed-bar table in docs/research/2026-10-21-q40-threshold-study.md; no rerun, the numbers and verdict above stand.

## D40 rerun on the fresh gate half (21 Oct 2026, `2053`, once)

Raw file `docs/research/sales-supervisor-2026-10-21-2053.raw.json`. The fresh gate half of
`sales_cases.py` (half "gate"; the rows scored in the earlier runs are spent and were not run),
270 rows, 45 per gated language, run once with `MIA_EVAL_HALVES=gate MIA_DECIDER=jev`. No agent,
description, case or harness changed before or during the run. The printed summary and a
recount from the raw file agree; no error rows, no wrong items.

| Language | n | Right | Wrong | Ask | D40 |
| --- | --- | --- | --- | --- | --- |
| en | 45 | 97.8% (44) | 0.0% (0) | 2.2% (1) | pass |
| fil | 45 | 82.2% (37) | **2.2%** (1) | **15.6%** (7) | **fail** (wrong, ask) |
| ceb | 45 | **64.4%** (29) | 0.0% (0) | **35.6%** (16) | **fail** (right, ask) |
| hil | 45 | 75.6% (34) | **2.2%** (1) | 22.2% (10) | **fail** (wrong) |
| war | 45 | **64.4%** (29) | **2.2%** (1) | **33.3%** (15) | **fail** (wrong, right, ask) |
| bcl | 45 | 71.1% (32) | 0.0% (0) | 28.9% (13) | pass |
| **all** | 270 | 75.9% (205) | 1.1% (3) | 23.0% (62) | wrong passes |

**Verdict under D40: fail**, in fil, ceb, hil and war. On one row each: fil, hil and war wrong
(one row is 2.2% at 45 rows, the cap allows none), fil ask (7 against the 6 that 15% allows),
ceb and war right (29 of 45 is 64.4%, 30 would pass). ceb ask (16 against 13) and war ask (15
against 13) are more than one row.

**The three wrongs (none writes a wrong row).**
- fil "bumaba ang mga taga-opisina para mag-lunch" and war "nanaog an mga taga-opisina para
  mangaon hin paniudto", after Mia asked why sales went well: expected why_answer (record_note),
  Jev picked reply_only at 0.71. Nothing is written; the reason is lost (a missed note, not a
  wrong one). The ceb twin picked reply_only at 0.53 and asked.
- hil "sige, makit-anay kita dason" (a goodbye): expected reply_only, Jev picked sales_today at
  0.63. A read: the clerk gets today's sales instead of a goodbye. No write.

**The asks by cause (62).** Right action below 0.6: 46 (report_sales 14, the short counts "2 pb
only", "4 b4 pa lang"; sales_period 11, mostly ceb; reply_only 10, "ano ang itatawag ko sa
iyo?"; set_target 4; why_answer 3; sales_today 3; correct_sales 1). A missing input: 9
(sales_period amount 3 and items 2, report_sales item 2 and second item 1, correct_sales item
1). Another pick under 0.6: 7 (why_answer read as
reply_only 3, report_sales read as sales_today 2, reply_only and sales_period read as
sales_today 2). ceb's 16 and war's 15 asks are sales_period confidences and the "4 b4" counts.

### Primary metric (D41)

Primary metric (D41, en and fil at the full bar: wrong at most 2 percent, right at least 80, ask at most 15): en pass (right 97.8%, wrong 0 (0.0%), ask 2.2%); fil fail (right 82.2%, wrong 1 (2.2%), ask 15.6%: both on one row).

The regional languages (ceb, hil, war, bcl) keep the D40 reading above, reported and not blocking (D41).

fil wrong rows:

- fil "bumaba ang mga taga-opisina para mag-lunch" (after Mia asked why sales went well): expected why_answer, picked reply_only at 0.71 (no write; the note is lost).

fil ask rows by cause (7; text and Jev's confidence):

- report_sales, right action below 0.6 (2): "4 b4 pa lang" 0.35; "2 pb lang po" 0.23
- sales_period, missing items (2): "benta ng ube bawat branch noong nakaraang buwan" 0.43; "benta ng salted egg bawat kiosk ngayong linggo" 0.17
- reply_only, right action below 0.6 (2): "ano ang itatawag ko sa iyo?" 0.49; "ayos, kita tayo mamaya" 0.35
- why_answer, right action below 0.6 (1): "nagpatikim si Ana sa lahat nang libre" 0.53
