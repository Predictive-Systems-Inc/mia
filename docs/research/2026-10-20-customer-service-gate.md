# Jev customer service decider evaluation (20 Oct 2026)

Spec docs/superpowers/specs/2026-10-19-customer-service-design.md (scenarios 1 to 8, section
10). Question: does Jev pick the right customer service action, and for an order the right
lines, pickup time and day, from what Ferino's customers and staff send? Synthetic data only
(D18). Raw results: `customer-service-2026-10-20-0125.raw.json` (one run, both halves).

**Result: the gate fails.** Wrong 0.0% on the gate half (bar at most 2%: pass); right at least
80% in every gated language (pass); ask over 15% in Central Bikol: **bcl ask 17.5%** (7 of 40).
Waray sits on the bar at 15.0%. By the skill (step 7) a failing gate is reported as it is: no
action description was tuned, no second run was made, and a rerun is the developer's call. This
gate half has now been scored once; if a tuning edit follows it is to come from the tune half
only, and the report of any rerun has to say the gate half's result was known.

## Setup

Model `jev-1.13.0` (the pinned `MIA_JEV_MODEL` default), threshold 0.6, egress level `pseudonymised`, concurrency 4. Ferino's is
seeded by the `cs` fixture on Tuesday 20 Oct 2026, and the harness pins today to the case set's
`TODAY` (the same Tuesday, not the run date), so Mila's confirmed 15:00 pickup is today's one
order on the staff side and "bukas", "Sabado" and "Biyernes" resolve the same on every run.
Each case runs `build_query` on its side (customer for scenarios 1 to 7, staff for scenario 8)
and `decider.decide` inside `egress_context`. Customer cases act as the agent on behalf of the
seeded customer Mila (`public.customer_actor`); staff cases as the agent for clerk Ana, or
supervisor Marites for the last two seeds. 480 cases (240 tune, 240 gate), 0 errors, one run.

The decider path ran on the working tree, whose actions.py, decider.py, calc.py and parsing.py
were uncommitted Task 3 review changes at the time; the same files (same shasum) were committed
minutes later as 4e08c2b, so the gate measures 4e08c2b's decider. The action descriptions are
those of 1dadd33 (the review changes touch the staff order candidates and the line reader only).

Scoring: **right** is the expected action and, for `place_order`, the expected lines (item and
quantity, in order), the pickup time and the day; **wrong** is another line, time or day, or
another action at >= 0.6; **ask** is clarify or a missing input; **other** is an error or another
action below 0.6.

## Case set

`node/tests/evals/customer_service_cases.py`: eight scenarios (hours, prices, place_order,
order_status, delivery_area, complaint, cancel_order on the customer side; staff on the staff
side: four seeds of today's orders, three of marking ready, three of picked up) times ten seeds
times six languages (en, fil, ceb, hil, war, bcl). Seed n is one message in every language; even
seeds are the tune half, odd seeds the gate half, so no text is in both (the offline shape test
checks it, and that each order's lines come out of the decider's own line reader, its time is a
`find_times` candidate and its day a `find_dates` candidate or today). Ten per language and
scenario, five per half; the plan's test name says "ten per half", the binding gate rule says
ten per scenario and language, and the set follows the rule. English seeds first; the other five
are drafts by Claude, not native speakers (review: Q28 to Q35). Greetings, the language switch
and scenario 9 (security) are not in the set: they are outside scenarios 1 to 8 and covered by
the chat tests.

## Gate (gate half)

| Language | n | Right | Wrong | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- |
| English (`en`) | 40 | 100% | 0% | 0% | pass |
| Filipino (`fil`) | 40 | 97.5% | 0% | 2.5% | pass |
| Cebuano (`ceb`) | 40 | 92.5% | 0% | 7.5% | pass |
| Hiligaynon (`hil`) | 40 | 87.5% | 0% | 12.5% | pass |
| Waray (`war`) | 40 | 85.0% | 0% | 15.0% | pass (on the bar) |
| Central Bikol (`bcl`) | 40 | 82.5% | 0% | **17.5%** | **fail** (ask) |
| **Gated, all** | 240 | 90.8% | **0.0%** (bar <= 2%: pass) | 9.2% | **fail** |

The seven bcl asks on the gate half: "sala an order na itinao nindo" (complaint, top pick
cancel_order 0.32), "bastos an cashier sako" (complaint, greeting 0.22), "order 6 ube 6 special
kukuanon sa aga 2pm" (place_order with the right lines, time and day at 0.52), "siisay an makua
ngunyan?" and "igwa daw pickup ngunyan na hapon?" (today's orders, greeting 0.27 and clarify
0.37), "tapos na an order, lista nang kuanon" (mark ready, 0.42), "nakua na an order, isara na"
(picked up, 0.39).

| Scenario | n tune | Tune right | Tune ask | n gate | Gate right | Gate ask |
| --- | --- | --- | --- | --- | --- | --- |
| hours | 30 | 100% | 0% | 30 | 100% | 0% |
| prices | 30 | 60.0% | 40.0% | 30 | 90.0% | 10.0% |
| place_order | 30 | 100% | 0% | 30 | 90.0% | 10.0% |
| order_status | 30 | 93.3% | 6.7% | 30 | 96.7% | 3.3% |
| delivery_area | 30 | 100% | 0% | 30 | 100% | 0% |
| complaint | 30 | 60.0% | 40.0% | 30 | 80.0% | 20.0% |
| cancel_order | 30 | 86.7% | 13.3% | 30 | 100% | 0% |
| staff | 30 | 90.0% | 10.0% | 30 | **70.0%** | 30.0% |

No case in either half scored wrong or other: every miss is an ask.

## Tune half

| Language | n | Right | Wrong | Ask |
| --- | --- | --- | --- | --- |
| en | 40 | 97.5% | 0% | 2.5% |
| fil | 40 | 92.5% | 0% | 7.5% |
| ceb | 40 | 80.0% | 0% | 20.0% |
| hil | 40 | 82.5% | 0% | 17.5% |
| war | 40 | 77.5% | 0% | 22.5% |
| bcl | 40 | 87.5% | 0% | 12.5% |
| all | 240 | 86.2% | 0% | 13.8% |

The tune half would fail the bar too (ceb, hil, war ask; war right).

## Confusions (both halves, 480 cases, from `raw_action`)

| Count | Expected | Jev's top pick (below 0.6, or no input) | Score | Examples |
| --- | --- | --- | --- | --- |
| 7 | complaint | place_order, then no lines (items missing) | ask | "panis na an puto bumbong", "bastos an cashier ha akon" |
| 6 | prices | place_order, then no lines (items missing) | ask | "pila ang bibingka ug puto bumbong" (0.74), "pila ang box of 4?" |
| 6 | staff_orders_today | clarify | ask | "may pickup ba mamayang hapon?", "hin-o an makuha yana?" |
| 5 | prices | clarify | ask | "hm ang salted egg", "pila ang bibingka?" |
| 5 | complaint | complaint | ask | "gahi kaayo ang bibingka gahapon" 0.33, "sira na ang puto bumbong" 0.59 |
| 3 | complaint | greeting | ask | "panis na ang puto bumbong", "bastos an cashier sako" |
| 3 | cancel_order | place_order, then no lines | ask | "diri ko na kinahanglan an order" (0.79) |
| 3 | place_order | place_order, right lines, time and day | ask | hil and bcl orders at 0.46 to 0.52 |
| 3 | staff_mark_ready | staff_mark_ready | ask | "handa na ang kay Mila" 0.57, "andam na an kan Mila" 0.39 |
| 2 | order_status | order_status | ask | "nadawat ba ninyo akong order?" 0.49 |
| 1 each | | prices to greeting; order_status to clarify; complaint to order_status, cancel_order, clarify; cancel_order to cancel_order; staff_orders_today to greeting; staff_mark_ready to greeting; staff_mark_picked_up to staff_mark_picked_up | ask | |

## Latency, tokens, cost (measured)

480 requests at concurrency 4 in 45 s of test time (seed included). Per request, measured in
the harness around `decider.decide`: mean 0.37 s, median 0.36 s, p95 0.43 s, max 0.67 s. Tokens
from the usage rows (input plus output): 794,663 for the run, 1,656 per message on average
(customer side 1,749, staff side 1,003; the staff request offers five actions and no order
slots). The usage rows carry no cost (`cost_minor` 0 in this harness's rows); at TypeSafe's list
price of $0.042 per million input tokens (output free) the run is at most $0.033, under
$0.0001 per message: a price applied to measured tokens, not a billed amount.

## Reading

- **No harmful action.** Wrong is 0% in both halves: no order with a wrong line, time or day,
  no complaint read as an order. The only write the customer side can start (`place_order`)
  still waits for a clerk's approval card.
- **"Not an order" falls through to ask, not to a write.** Sixteen non-order messages had
  place_order as Jev's top pick, sometimes above 0.6 ("pila ang bibingka ug puto bumbong" 0.74,
  "diri ko na kinahanglan an order" 0.79), and were saved by code: no count group, so the
  `items` input is missing and the customer is asked. That guard holds only while the message
  has no digits; "pila ang 10 bibingka" would make lines. The prices and cancel descriptions
  need the contrast ("asking a price is not ordering" is in prices; cancel has none).
- **Complaints in the regional languages** are the largest ask cost: food words (gahi, panis,
  aslom, maalsom, matagas) and service words (bastos, sala, sayop) with no complaint word in
  them. The complaint description lists Filipino words only (matigas, sira, kulang).
- **Staff questions about today's pickups** ("may pickup ba mamayang hapon?", "sino ang
  kukuha", "siisay an makua") read as unclear: the description names "orders today" and "sino
  ang kukuha ngayon" but not "pickup" questions. Gate half staff right 70%.
- **The bcl fail is seven messages over three scenarios** (complaint 2, staff 4, place_order
  1), at 17.5% against 15%: one message fewer asked would still fail (15.0% passes, 7 of 40 is
  17.5%, 6 of 40 is 15.0%).

## What remains (the developer decides)

- Whether to tune and rerun. Tuning candidates from the tune half only: the complaint
  description with the regional food words of the tune seeds (gahi, panis, aslom, maaslum,
  maalsom; the service words bastos, sala and sayop are gate seeds and stay out); the staff_orders_today description with "pickup"
  questions; prices and cancel_order with "a question about a price or a cancel is not an
  order". A rerun on this gate half would be a rerun with its result known; fresh gate seeds
  avoid that.
- The non-English messages are drafts (Q28 to Q35).
- Record `cost_minor` in the usage rows, so the next report reads cost, not a list price.

## Router

The router gate was not rerun. The router seeds do not change the agent's router description
(the manifest's, written by the scaffold with the contrast "customer orders and complaints; not
sales counts", owned by Task 4 and untouched here). `PENDING` is now empty, and
`router_cases.py` gains ten staff-side seeds for customer_service in every language (customers
bypass the router), five in each half:

- Tune: "what customer orders do we have today", "Mila's order is ready for pickup", "the
  customer already picked up the 3pm order", "any customer complaints today?", "who is picking
  up an order this afternoon".
- Gate: "list today's pickup orders", "the order for Mila is packed, mark it ready", "Mark
  collected his order", "mark the complaint about cold bibingka as resolved", "how many
  customer orders are waiting for confirmation".

These have not been scored by the router; the next router run reports them.
