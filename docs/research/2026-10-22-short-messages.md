# Short messages, eight agents, 22 October 2026

The D42 yardstick: the short half of each agent's cases CSV (twelve en and twelve fil rows, two
of each language an expected ask) through its harness with `MIA_EVAL_HALVES=short
MIA_DECIDER=jev`, one agent at a time, at HEAD 41828d7 with a clean tree. The sales supervisor
ran twice, once per question shape (`MIA_SALES_QUESTION=choice`, the default, and `nouls`, a
yes-or-no per action). Nothing was tuned and nothing was rerun. The one hard rule is no wrong
write (`gate.wrong_writes`).

Raw files (each with its results CSV beside it):

| agent | run |
|---|---|
| bookkeeper | bookkeeper-2026-10-22-1152 |
| sales_supervisor, choice | sales-supervisor-2026-10-22-1153 |
| sales_supervisor, nouls | sales-supervisor-2026-10-22-1154 |
| branch_manager | branch-manager-2026-10-22-1154 |
| inventory_manager | inventory-manager-2026-10-22-1154 |
| production_planner | production-planner-2026-10-22-1154 |
| shift_supervisor (retail) | shift-supervisor-retail-2026-10-22-1154 |
| customer_service | customer-service-2026-10-22-1154 |
| hr_officer | hr-officer-2026-10-22-1155 |

No run had an error row. Calls: 216 Jev requests (24 per run, one per row, nine runs), 751,163
tokens in all.

## Results

Right, wrong and ask are the harness scores; an expected-ask row that asked is scored "ask", so
"of which expected" shows how many of the asks were the two deliberate ambiguous rows. Percent of
12 rows.

| agent | lang | rows | right | wrong | ask (of which expected) | wrong writes |
|---|---|---|---|---|---|---|
| bookkeeper | en | 12 | 7 (58.3%) | 0 (0%) | 5 (2) | 0 |
| bookkeeper | fil | 12 | 5 (41.7%) | 0 (0%) | 7 (2) | 0 |
| branch_manager | en | 12 | 8 (66.7%) | 0 (0%) | 4 (2) | 0 |
| branch_manager | fil | 12 | 5 (41.7%) | 1 (8.3%) | 6 (2) | 0 |
| inventory_manager | en | 12 | 9 (75.0%) | 1 (8.3%) | 2 (1) | **1** |
| inventory_manager | fil | 12 | 7 (58.3%) | 1 (8.3%) | 4 (1) | **1** |
| sales_supervisor, choice | en | 12 | 10 (83.3%) | 0 (0%) | 2 (2) | 0 |
| sales_supervisor, choice | fil | 12 | 8 (66.7%) | 1 (8.3%) | 3 (1) | 0 |
| production_planner | en | 12 | 5 (41.7%) | 0 (0%) | 7 (2) | 0 |
| production_planner | fil | 12 | 8 (66.7%) | 1 (8.3%) | 3 (1) | **1** |
| shift_supervisor (retail) | en | 12 | 7 (58.3%) | 1 (8.3%) | 4 (2) | 0 |
| shift_supervisor (retail) | fil | 12 | 3 (25.0%) | 0 (0%) | 9 (2) | 0 |
| customer_service | en | 12 | 10 (83.3%) | 0 (0%) | 2 (2) | 0 |
| customer_service | fil | 12 | 8 (66.7%) | 0 (0%) | 4 (2) | 0 |
| hr_officer | en | 12 | 7 (58.3%) | 0 (0%) | 5 (2) | 0 |
| hr_officer | fil | 12 | 8 (66.7%) | 1 (8.3%) | 3 (1) | 0 |

**The hard rule failed on two agents: three wrong writes in all** (inventory_manager 2,
production_planner 1). Their harnesses asserted and failed after writing the raw files; the
other seven runs passed.

### The sales supervisor, both question shapes

| shape | lang | right | wrong | ask (of which expected) | wrong writes | tokens |
|---|---|---|---|---|---|---|
| choice | en | 10 (83.3%) | 0 | 2 (2) | 0 | 77,970 (both langs) |
| nouls | en | 8 (66.7%) | 0 | 4 (2) | 0 | 95,093 (both langs) |
| choice | fil | 8 (66.7%) | 1 (8.3%) | 3 (1) | 0 | |
| nouls | fil | 6 (50.0%) | 0 | 6 (2) | 0 | |

One request per row in both shapes. The yes-or-no shape removed the one wrong row ("yung
kahapon" now asks) but asked on four rows the choice got right: "best day this wk", "payday
crowd", "mali pala ube 4 dapat", "benta kahapon street". It costs about 22% more tokens. On this
set the choice is the better shape; the yes-or-no only trades rights for asks.

## Every wrong row

| agent | lang | text | expected | pick (confidence) | wrote |
|---|---|---|---|---|---|
| inventory_manager | en | eggs 10 | ask | report_stock (0.78), a count of 10 trays of eggs | **yes** |
| inventory_manager | fil | ilan pa ube | ask | report_stock (0.63), an on-hand count of Ube with no quantity | **yes** |
| production_planner | fil | ok na po | ask | confirm_plan (0.88), no production date | **yes** |
| branch_manager | fil | ok ba yung test | experiment_status | reply_only (0.63) | no |
| sales_supervisor, choice | fil | yung kahapon | ask | sales_period (0.95), yesterday | no |
| shift_supervisor (retail) | en | my sched tmrw | get_my_visits | get_my_visits (0.99), right action; the resolved date came back under time, not date | no |
| hr_officer | fil | sahod | ask | payday (0.71) | no |

## Every ask, by cause

The threshold is 0.6. "No clear pick" is a clarify or another action below the threshold (Jev
did not pick the expected action); it is not in the brief's three groups but holds most of the
expected asks.

**bookkeeper** (en 5, fil 7)
- Right pick under the threshold: maya in 1850 (settlement 0.28), grab payout 8900 (payout
  0.58), petty 150 ice (petty_cash 0.13), nag remit grab 7650 (payout 0.38), bayad sa tubero 800
  (expense 0.49), petty 200 pamasahe (petty_cash 0.49), kita ng oktubre (profit 0.48).
- No clear pick: closing 13250 po (reply_only 0.32, expected cash_count); expected asks 12450,
  gcash, 3200 kahapon, bayad na.

**branch_manager** (en 4, fil 6)
- A slot missing: tips to sell more sp (item, "sp" not resolved), use ch for overload (code),
  classic 48 (date, expected ask), gawing 52 se simula lunes (item, "se" not resolved), sp 45
  (item, expected ask), subukan 45 sp ngayong linggo (propose_experiment 0.97 with no item, the
  harness's ask for an experiment without an item).
- Right pick under the threshold: pano mabenta ube (how_to_sell 0.58), gawin bx code ng box
  (set_short_code 0.40).
- No clear pick: expected asks ube price, presyo.

**inventory_manager** (en 2, fil 4)
- Right pick under the threshold: need to order anything (whats_low 0.45), ilan gagawin bukas
  (bake_plan 0.41).
- A slot missing: 2 sp tapon sunog (kind, report_stock 0.26), may ioorder ba tayo (lines,
  place_order 0.71, expected whats_low).
- No clear pick: expected asks ube, itlog po.

**sales_supervisor, choice** (en 2, fil 3)
- Right pick under the threshold: benta ko 5 se 3 co (report_sales 0.41).
- A slot missing: benta nung isang linggo (items, report_sales 0.53, expected sales_period).
- No clear pick: expected asks cl 8 or 9, ube pls, ube pa.

**sales_supervisor, nouls** (en 4, fil 6)
- A guard ask (two yeses, the RUNNER_UP rule): best day this wk (0.67), yung kahapon (0.60,
  expected ask).
- A slot missing: cl 8 or 9 (item_1, expected ask).
- No clear pick: payday crowd (0.52, expected why_answer), benta ko 5 se 3 co (0.45), mali pala
  ube 4 dapat (0.51), benta kahapon street (0.45), benta nung isang linggo (0.53); expected asks
  ube pls, ube pa.

**production_planner** (en 7, fil 3)
- A slot missing: less classic 2 batch (item), recipe ube 36 pcs 2kg flour (recipe lines),
  capacity 200 cl dec 24 (item, "cl" not resolved), recipe se 36 piraso 45 min (recipe lines),
  ube 2 and classic 3 (unit, both expected asks).
- Right pick under the threshold: delivered mall (delivered 0.59), whats coming to mall
  (dispatch 0.45), kaya ba 150 ube sab (capacity 0.04).
- No clear pick: expected ask done (reply_only 0.58).

**shift_supervisor (retail)** (en 4, fil 9)
- Right pick under the threshold: late 15m traffic (record_absence 0.43), late ako 10 mins
  (0.54), masakit ulo ko absent muna (0.49), nakalimutan ko time out 9pm (correct_time 0.38),
  sarado mall sa sabado (close_day 0.45).
- A slot missing: who can cover ana tmrw and sino pwede kay ana bukas (visit, find_replacements
  0.92 and 0.93), palit kami ni liza sab (date, swap 0.91), liza fri (visit, expected ask).
- No clear pick: sched ko bukas (clarify 0.22, expected get_my_visits); expected asks 9pm, bukas
  po, liza po.

**customer_service** (en 2, fil 4)
- A slot missing: pa order 12 cl bukas (pickup time, place_order 0.98), 10 ube (pickup time,
  expected ask).
- No clear pick: hm po ung special (0.40, expected prices); expected asks tmrw 3pm, pano po,
  yung order.

**hr_officer** (en 5, fil 3)
- A slot missing: sick leave tmrw pls (leave start, file_leave 1.00), holiday pay nov 30 (day,
  holiday_pay 0.97), day off ako sab pls (leave start, 0.99), ilan pa leave ko (leave start,
  file_leave 0.85, expected leave_balance), leave po (leave start, expected ask).
- Right pick under the threshold: vl dec 2 to 3 (file_leave 0.45).
- No clear pick: expected asks cutoff, nov 30.

## A reading per agent (no edits made)

- **bookkeeper**: Jev picks the right action on seven of the eight non-expected asks, all under
  the threshold. The option texts would need the provider-first shapes ("maya in", "grab payout",
  "nag remit") for settlement and payout, "petty <amount> <what>" for petty cash, and "closing
  <amount>" for the cash count.
- **branch_manager**: most asks are the item parser, not the question: "sp" and "se" did not
  resolve to Special and Salted egg here. The question needs "ok ba yung test" (is the experiment
  working) named under experiment_status, and "pano mabenta" under how_to_sell.
- **inventory_manager**: the wrong writes are the question's problem. "eggs 10" (a bare item and
  number) and "ilan pa ube" (how many left, a question) both went to report_stock above the
  threshold. The report_stock option would need to say a stock report states what happened
  (counted, wasted, received), and a "how many left" question would need its own option text
  (on hand, "ilan pa") so it is not read as a count; a bare item and number would need to be
  named as unclear in the instructions.
- **sales_supervisor**: the choice is the shape to keep. "yung kahapon" (the one from yesterday)
  needs the instructions to say a bare reference without a verb is unclear. "benta nung isang
  linggo" went to report_sales: sales_period's option text needs "benta nung <period>".
- **production_planner**: "ok na po" confirmed a plan with no date at 0.88, a write. The
  instructions would need to say a bare acknowledgement is not a confirmation unless the
  previous turn proposed a plan. The en asks are mostly slots ("cl" unresolved, recipe lines
  not parsed from "2kg flour").
- **shift_supervisor (retail)**: the weakest fil score, mostly the right pick under the threshold
  on absences ("late ako", "absent muna"), time corrections ("nakalimutan ko time out") and
  closures ("sarado"). The option texts would need those Filipino phrasings. "my sched tmrw"
  is the resolver putting tomorrow under time, not a question issue.
- **customer_service**: clean; the asks are a missing pickup time, which is right. "hm po"
  (how much) would need to be named under prices.
- **hr_officer**: "tmrw", "sab" and "nov 30" were not parsed as dates for leave and holiday pay
  (slot asks with the right pick at 0.97 to 1.00). "ilan pa leave ko" went to file_leave: the
  leave_balance option would need "ilan pa leave". "sahod" alone was read as payday at 0.71, no
  write.
