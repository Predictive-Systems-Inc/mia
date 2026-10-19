# Jev customer service decider evaluation (20 Oct 2026)

Spec docs/superpowers/specs/2026-10-19-customer-service-design.md (scenarios 1 to 8, section
10). Question: does Jev pick the right customer service action, and for an order the right
lines, pickup time and day, from what Ferino's customers and staff send? Synthetic data only
(D18). Raw results, all in this folder: `customer-service-2026-10-20-0125.raw.json` (run 1, both
halves), `-0140` (tune half, run 1's descriptions, with the new tune-only cases), `-0141` (tune
half after the tuning edit) and `-0142` (run 2, the fresh gate half only).

**What happened, in order.**

1. **Run 1 (`0125`, the descriptions of 1dadd33) failed the gate.** Gate half, 240 cases: bcl
   ask 17.5% (bar at most 15%); war on the bar at 15.0%; wrong 0.0%; right 82.5% to 100%.
   Reported as it was and stopped there.
2. **The developer's decision** (the controller, recorded in the ledger): one tuning pass from
   the tune half, then one rerun on fresh gate seeds, never on the spent half.
3. **A fresh gate half was written first** (five seeds per scenario in six languages, 240
   texts, none a text of the tune half or the spent half), before any tuning run; the spent
   half stays in the case file marked `spent` and the harness never runs it.
4. **One tuning edit to `agents/customer_service/actions.py`** (descriptions only), from the
   tune half's misses (`0140`); the tune half after it is `0141`. Its wording for the staff
   pickup questions follows run 1's finding, which came from the spent gate half; see "The
   tuning edit".
5. **Run 2 (`0142`) on the fresh gate half failed.** **war ask 17.5%** (bar at most 15%); ceb
   and hil on the bar at 15.0%; wrong 0.0%; right 82.5% to 97.5%. The complaint scenario is
   36.7% right on it. Reported as it is; nothing was tuned after it and there is no run 3.

Both gate halves are now spent. A next attempt needs a third set of gate seeds and the
developer's word.

## Setup

Model `jev-1.13.0` (the pinned `MIA_JEV_MODEL` default), threshold 0.6, egress level
`pseudonymised`, concurrency 4. Ferino's is seeded by the `cs` fixture on Tuesday 20 Oct 2026,
and the harness pins today to the case set's `TODAY` (the same Tuesday, not the run date), so
Mila's confirmed 15:00 pickup is today's one order on the staff side and "bukas", "Sabado",
"Huwebes" and "Domingo" resolve the same on every run. Each case runs `build_query` on its side
(customer for scenarios 1 to 7, staff for scenario 8) and `decider.decide` inside
`egress_context`. Customer cases act as the agent on behalf of the seeded customer Mila
(`public.customer_actor`); staff cases as the agent for clerk Ana, or supervisor Marites for the
last two seeds of a list. `MIA_EVAL_HALVES` picks the halves of a run (`tune` for the tuning
runs, `gate` for run 2); the spent half is never run. 0 errors in every run.

Code under test: run 1 measured 4e08c2b's decider (the working tree then held uncommitted Task
3 review edits whose files are byte-identical to 4e08c2b) with 1dadd33's descriptions. Run 2
measured fd646aa plus this round's description edit (the commit of this report).

Scoring: **right** is the expected action and, for `place_order`, the expected lines (item and
quantity, in order), the pickup time and the day, and for `language_switch` the language;
**wrong** is another line, time, day or language, or another action at >= 0.6; **ask** is
clarify or a missing input; **other** is an error or another action below 0.6.

## Case set

`node/tests/evals/customer_service_cases.py`: eight scenarios (hours, prices, place_order,
order_status, delivery_area, complaint, cancel_order on the customer side; staff on the staff
side) in six languages (en, fil, ceb, hil, war, bcl). Per scenario and language: ten messages in
the first set (even seeds tune, odd seeds the spent gate half of run 1) and five fresh gate
messages (run 2): five per half in three halves, no text in two of them (shape test). The
staff scenario's tune half asks today's orders, marks ready and picked up; the fresh gate half
has two orders-today, two mark-ready and one picked-up seed. The tune half also carries 66
cases outside scenarios 1 to 8, never gated: a price question and a cancel with a count ("pila
ang 10 ka bibingka?", "i-cancel ang 10 bibingka na inorder ko"), three security messages
(expected `greeting`), three greetings and three language switches. English seeds first; the
other five are drafts by Claude, not native speakers (review: Q28 to Q35). The shape test checks
each order's lines through the decider's own line reader, its time as a `find_times` candidate
and its day as a `find_dates` candidate or today.

## Run 2, fresh gate half (`0142`)

| Language | n | Right | Wrong | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- |
| English (`en`) | 40 | 97.5% | 0% | 2.5% | pass |
| Filipino (`fil`) | 40 | 90.0% | 0% | 10.0% | pass |
| Cebuano (`ceb`) | 40 | 85.0% | 0% | 15.0% | pass (on the bar) |
| Hiligaynon (`hil`) | 40 | 85.0% | 0% | 15.0% | pass (on the bar) |
| Waray (`war`) | 40 | 82.5% | 0% | **17.5%** | **fail** (ask) |
| Central Bikol (`bcl`) | 40 | 90.0% | 0% | 10.0% | pass |
| **Gated, all** | 240 | 88.3% | **0.0%** (bar <= 2%: pass) | 11.7% | **fail** |

| Scenario (run 2 gate) | n | Right | Ask |
| --- | --- | --- | --- |
| hours | 30 | 96.7% | 3.3% |
| prices | 30 | 96.7% | 3.3% |
| place_order | 30 | 90.0% | 10.0% |
| order_status | 30 | 93.3% | 6.7% |
| delivery_area | 30 | 96.7% | 3.3% |
| **complaint** | 30 | **36.7%** | **63.3%** |
| cancel_order | 30 | 100% | 0% |
| staff | 30 | 96.7% | 3.3% |

Run 2's 28 asks: complaint 19 ("sunog ang ube" 5 of 5 languages, "sobra ang singil" 5 of 5,
"yupi na ang kahon pagdating" 5 of 5, "bastos ang rider" 4 of 5; top picks complaint below 0.6,
place_order with no lines, greeting, clarify, order_status, hours); place_order 3 (right lines,
time and day below 0.6: "pa-deliver sang 10 salted egg sa Pasig sa Huwebes 4:30pm" hil, "4
special 4 cheese overload, I'll get it Sunday 10am" en and ceb); order_status 2 ("akong order
para ugma, okay na ba?" ceb and war, place_order at 0.62 and 0.87 with no lines, so asked);
one each in hours ("sarado bala kamo kada Lunes?"), prices ("pila na ang puto bumbong karon?"),
delivery_area ("tagpira an delivery pakadto Marikina") and staff ("pira an customer orders
yana?"). The seven war asks: four complaints, one order_status, one delivery_area, one staff.

## The tuning edit (once, from the tune half)

The tune half with run 1's descriptions (`0140`, scenarios 1 to 8): right 85.4%, ask 14.6%;
ceb 75.0%, war 77.5%. Its misses: complaints without a complaint word (gahi, panis, aslom,
maaslum, maalsom, sira; 12 of 30), price questions read as orders or unclear ("pila ang ube nga
bibingka", "hm ang salted egg"; 12 of 30), "no longer need the order" messages (4: three read as
place_order with no lines, one cancel below 0.6), "andam na ang kang Mila" (4); outside the gate, "pila ang 10 ka bibingka?" and "tagpira an
10 nga bibingka?" read as place_order at 0.84 and 0.74 with the right lines, saved only by the
missing pickup time, and "hello, who is this?" asked in every language.

Edits in `agents/customer_service/actions.py`, descriptions only: prices names pila, tagpila,
tagpira and a count ("magkano ang 10 bibingka") and says a price question, with or without a
count, is never an order; place_order adds palit and bakal and says asking a price, cancelling
or complaining is not ordering; complaint says "also without a complaint word" and names the
tune half's food words (gahi, panis, napanis, maasim, aslom, maaslum, maalsom, malamig, bugnaw);
cancel_order names "no longer wants it" with the tune words (i-void, hindi ko na kailangan, dili
na nako kinahanglan, dai ko na kaipuhan) and "also naming its items", never a new order;
staff_mark_ready adds andam na, handa na, lista na; greeting adds "who is this, sino ito" and
requests for staff or other customers' data (payroll, the customer list). staff_orders_today
adds "who picks up an order today or this afternoon ... may pickup ba, list of customer orders":
the tune half had no pickup question; this line follows run 1's finding on the spent gate half
(the developer's instruction), and the fresh gate half, written before the edit, has two
pickup questions ("what pickups do we have today", "how many customer orders today?"). Case
set, scoring, threshold and decider code were not touched.

| Tune half, scenarios 1 to 8 (n 240) | Before (`0140`) right | ask | After (`0141`) right | ask |
| --- | --- | --- | --- | --- |
| en | 97.5% | 2.5% | 97.5% | 2.5% |
| fil | 92.5% | 7.5% | 92.5% | 7.5% |
| ceb | 75.0% | 25.0% | 97.5% | 2.5% |
| hil | 82.5% | 17.5% | 92.5% | 7.5% |
| war | 77.5% | 22.5% | 95.0% | 5.0% |
| bcl | 87.5% | 12.5% | 95.0% | 5.0% |
| all | 85.4% | 14.6% | 95.0% | 5.0% |

Tune-only cases after the edit (`0141`): the price and cancel with a count 12 of 12 right (the
concern of run 1: a price question with a digit no longer reads as an order); security 16 of
18 (two bcl asks); greetings 12 of 18 ("hello, who is this?" still asked in all six); language
switch 17 of 18. Wrong 0 in both tune runs.

## Run 1 (`0125`), as reported before the decision

### Run 1, gate half (now spent)

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

### Run 1, tune half

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

### Run 1, confusions (both halves, 480 cases, from `raw_action`)

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

Per request, measured in the harness around `decider.decide`; tokens from the usage rows (input
plus output).

| Run | Cases | Mean s | p95 s | Max s | Tokens | Per message |
| --- | --- | --- | --- | --- | --- | --- |
| 1 (`0125`, both halves) | 480 | 0.37 | 0.43 | 0.67 | 794,663 | 1,656 |
| tune before (`0140`) | 306 | 0.37 | 0.48 | 0.64 | 511,511 | 1,672 |
| tune after (`0141`) | 306 | 0.36 | 0.40 | 0.66 | 568,841 | 1,859 |
| 2 (`0142`, gate) | 240 | 0.37 | 0.44 | 0.66 | 441,809 | 1,841 |

The edit adds about 185 tokens per message (the longer descriptions). The usage rows carry no
cost (`cost_minor` 0 in this harness's rows); at TypeSafe's list price of $0.042 per million
input tokens (output free) the four runs together (2.32 million tokens) are at most $0.10, under
$0.0001 per message: a price applied to measured tokens, not a billed amount.

## Reading

- **No harmful action in any run.** Wrong is 0% in every run and half: no order with a wrong
  line, time or day, no complaint or price question read as an order above the bar with lines.
  The only write the customer side can start (`place_order`) still waits for a clerk's card.
- **The word lists did not generalise to complaints.** The edit named the tune half's food
  words, and the tune half's complaints went from 60% to 93%; the fresh gate half's complaints
  use other words (sunog, sobra ang singil, yupi ang kahon, bastos ang rider) and were 36.7%
  right. The complaint description would need to say what a complaint is about (the food's
  state, the price charged, the packaging, a person's manner, a late or wrong order) rather
  than list words; that is a next edit for the developer to decide, not made here.
- **The price and cancel contrast worked.** Prices went from 60% (tune, before) to 96.7% on the
  fresh gate half, cancel_order to 100%, and the price questions with a count are right.
- **The staff pickup questions are fixed** (fresh gate staff 96.7%, run 1's spent half 70%),
  with the caveat in the tuning section on where that wording came from.
- **A day word with "okay na ba"** ("akong order para ugma, okay na ba?") reads as an order:
  safe (no lines, so asked) but an order-status question; the order_status description has no
  "my order for tomorrow" example.

## What remains (the developer decides)

- Whether to make a second edit (the complaint description by kind, the order_status "order for
  tomorrow") and a run 3, which needs a third set of gate seeds: both gate halves are spent.
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
