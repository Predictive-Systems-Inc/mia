# Jev agent router evaluation on the fresh Ferino's gate half (21 Oct 2026, D40 rerun)

The D40 rerun of the router on a fresh gate half over the full Ferino's agent list. Synthetic
data only (D18). Raw results: `router-2026-10-21-2058.raw.json` (the harness names the file by
local time and never overwrites). Run once with
`MIA_EVAL_HALVES=gate MIA_DECIDER=jev uv run pytest node/tests/evals/test_router_eval.py::test_router -m evals -s --no-cov`.
No agent, description, case or harness changed before or during the run.

**Note, 21 Oct 2026, after the run.** The router descriptions of five agents changed after
`router-2026-10-21-2058` for the description gaps below: the shift supervisor's contrast gains
"not opening hours, prices or who is the supervisor"; the sales supervisor's gains "not advice on
how to sell more"; the branch manager names how to sell more and advice on low sales, upselling
and who is in charge; the production planner names what the driver brings to a kiosk; the
inventory manager's "what to prepare or bake tomorrow" became what a kiosk needs on hand tomorrow,
with "not the commissary's production" in its contrast. The numbers in this report stand as run;
they measure the old descriptions. This gate half is spent, so a rerun needs fresh seeds.

**Result: the gate fails on wrong.** Wrong agent at >= 0.6 is 2.8% over all 570 gate rows (16
rows; the bar is at most 2%), and over 2% in every gated language but en.

## Setup

- Cases: `GATE_FERINOS_SEEDS` and `GATE_FERINOS_CONTEXT` in `router_cases.py`, the fresh gate
  half, written before any run of it; every earlier block (GATE_PLANNER_* included, scored in
  `router-2026-10-21-0749`) is spent and was not run.
- The agents: every case routes over ROSTER, every registered agent, which is the eight of
  config/org/ferinos (bookkeeper, branch_manager, customer_service, hr_officer,
  inventory_manager, production_planner, sales_supervisor, shift_supervisor; pinned by
  `test_router_cases.py`). No org setting selects them and the request does not read MIA_ORG.
- The bar: D40 in `node/tests/evals/gate.py` (wrong at most 2% on all rows and in every gated
  language; en and fil right at least 80% and ask at most 15%; ceb, hil, war, bcl right at
  least 65% and ask at most 30%; greetings left out of the per-language rows).
- Route memory is not exercised: the harness calls `build_request` and `decide` directly.

## Gate half (570 rows: 480 singles, 60 follow-ups, 30 switches)

The printed summary and a recount from the raw file agree; no error rows.

| Language (no greetings) | n | Right | Wrong | Ask | Other | D40 |
| --- | --- | --- | --- | --- | --- | --- |
| en | 90 | 91.1% (82) | 1.1% (1) | 7.8% (7) | 0 | pass |
| fil | 90 | 81.1% (73) | **2.2%** (2) | **15.6%** (14) | 1 | **fail** (wrong, ask) |
| ceb | 90 | 76.7% (69) | **2.2%** (2) | 20.0% (18) | 1 | **fail** (wrong) |
| hil | 90 | 77.8% (70) | **2.2%** (2) | 17.8% (16) | 2 | **fail** (wrong) |
| war | 90 | 71.1% (64) | **5.6%** (5) | 21.1% (19) | 2 | **fail** (wrong) |
| bcl | 90 | 75.6% (68) | **4.4%** (4) | 16.7% (15) | 3 | **fail** (wrong) |
| **all (with greetings)** | 570 | 79.8% (455) | **2.8%** (16) | 15.8% (90) | 9 | **fail** (wrong) |

Greetings 29 of 30 right. At 90 rows one wrong is 1.1%, so the cap allows one: fil, ceb and
hil fail on their second wrong row, fil's ask on one row (14 against the 13 that 15% allows).
war (5) and bcl (4) are more than one row over.

By agent (gate half): bookkeeper 100%, customer_service 100%, hr_officer 95.5%,
shift_supervisor 95.5%, sales_supervisor 73.6%, production_planner 66.7%, inventory_manager
65.3%, branch_manager **39.4%** (wrong 19.7%, ask 40.9%). By group: singles 80.4% (wrong
3.3%), follow-ups 88.3%, switches 53.3% (other 16.7%).

## The sixteen wrongs

A router pick writes nothing itself: the picked agent's decider runs next, and its own guards
and tools decide what is written. None of the sixteen sends a message to the bookkeeper, the
HR officer or customer service.

| Expected | Picked | Rows | Messages |
| --- | --- | --- | --- |
| branch_manager | shift_supervisor | 5 | "open the Mall kiosk at 9 instead of 10 from now on" (en 0.65, fil 0.78, ceb 0.95, hil 0.81, bcl 0.90) |
| branch_manager | sales_supervisor | 4 | "any tips, my sales are always slow in the afternoon" (ceb 0.60, hil 0.75, war 0.83, bcl 0.92) |
| branch_manager | sales_supervisor | 2 | war "paonan-o ako makakabaligya hin mas damo nga puto bumbong" 0.92, war "naayo na ba hi Pao ha pag-upsell?" 0.70 |
| branch_manager | shift_supervisor | 2 | bcl "itaas an special sa 85 poon Lunes" 0.62 (a price), war "himoa hi Ana nga supervisor ha stall" 0.65 (a role) |
| production_planner | inventory_manager | 2 | "what do I bring to the stall this afternoon?" (fil 0.73, bcl 0.68) |
| inventory_manager | shift_supervisor | 1 | war "pira pa an aton galapong ha stall?" 0.60 |

Eleven of the sixteen are the branch manager's seeds: opening hours (5) go to the shift
supervisor, who has no opening-hours tool (it would ask or reply, not write); the coaching and
selling questions (6) go to the sales supervisor, whose writes are counts and targets, so a
coaching question there would ask or answer with sales figures. The price change to the shift
supervisor has no price tool there either. Whether a misrouted message would write a wrong
row is decided by the receiving decider; this eval does not run it.

## The asks by cause (90) and other (9)

Right agent below 0.6, no agent active: 50 (inventory_manager 15, branch_manager 13,
sales_supervisor 10, production_planner 6, hr_officer 3, shift_supervisor 3). Right agent below
0.6 with an agent active: 9. Another agent below 0.6: 31 (production_planner seeds to
inventory_manager 5 and shift_supervisor 4, branch_manager to shift_supervisor 5, sales to
unclear 4, and smaller groups). Other (9, a kept active agent): the ceb, hil, war, bcl follow-up
"dugang pa, ang batch 1 sa special 36 ang maayo" kept with the inventory manager (4); a sales
count "nakabaligya sang 9 classic kag 2 ube halin nagbukas" kept with the inventory manager in
hil, war, bcl (3); "ubos na ang paper bag sa stall" kept with the production planner as unclear
in fil and bcl (2).

## What remains (the developer decides)

- The branch manager's description against the shift supervisor's (opening hours, roles,
  prices) and the sales supervisor's (selling tips, coaching): eleven of the sixteen wrongs.
- "what do I bring to the stall" between the production planner (dispatch) and the inventory
  manager.
- This gate half is spent; a rerun needs a fresh one.

### Primary metric (D41)

Primary metric (D41, en and fil at the full bar: wrong at most 2 percent, right at least 80, ask at most 15): en pass (right 91.1%, wrong 1 (1.1%), ask 7.8%); fil fail (right 81.1%, wrong 2 (2.2%), ask 15.6%: both on one row).

The regional languages (ceb, hil, war, bcl) keep the D40 reading above, reported and not blocking (D41).

fil wrong rows:

- fil "buksan ang Mall kiosk ng 9 imbes na 10 mula ngayon": expected branch_manager, picked shift_supervisor at 0.78.
- fil "ano ang dadalhin ko sa stall ngayong hapon?": expected production_planner, picked inventory_manager at 0.73.

fil ask rows by cause (14; text and Jev's confidence):

- branch_manager, right agent below 0.6 (3): "pakisend ang buod ng numbers natin sa Oktubre" 0.29; "itaas sa 85 ang special simula Lunes" 0.37; "Mia, paano ko mapapasubok sa customer ang ube?" 0.33
- inventory_manager, right agent below 0.6 (2): "itinapon ko ang 7 salted egg, napanis na" 0.3; "gaano pa karami ang galapong natin sa stall?" 0.42
- sales_supervisor, right agent below 0.6 (1): "ay, 6 na cheese overload pala, hindi 9" 0.55
- sales_supervisor read as unclear (1): "kumusta ngayon kumpara noong nakaraang Sabado?" 0.52
- inventory_manager read as shift_supervisor (1): "ano ang paubos na sa Mall kiosk?" 0.38
- inventory_manager read as production_planner (1): "ilan pa ang puto bumbong natin ngayon?" 0.24
- branch_manager read as shift_supervisor (1): "gawing supervisor si Ana sa stall" 0.54
- branch_manager read as sales_supervisor (1): "may payo ka ba, laging mahina ang benta ko sa hapon" 0.46
- production_planner read as inventory_manager (1): "naibaba ko na ang mga tray sa Mall kiosk, tapos na" 0.51
- shift_supervisor, right agent below 0.6 (1): "tatlong oras nang late ang delivery ng cups, wala pa rin" 0.57
- production_planner, right agent below 0.6 (1): "saka, ang batch 1 ng special ay 36 ang maayos" 0.45
