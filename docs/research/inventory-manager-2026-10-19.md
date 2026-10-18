# Jev inventory manager decider evaluation (19 Oct 2026)

Spec docs/superpowers/specs/2026-10-19-inventory-manager-design.md (sections 4 and 10). The
question: does Jev pick the right inventory action, with the right kind and items for a stock
report and the right lines for an order or a delivery, from what Ferino's clerks, head staff
and owner send? Synthetic data only (D18). Raw results:
`inventory-manager-2026-10-19-0554.raw.json` (run 1, committed descriptions) and
`inventory-manager-2026-10-19-0558.raw.json` (run 2, after one tuning edit on the tune half).

**Result: the gate fails.** Run 2, gate half, six gated languages (300 cases), measured against
the Q40 bar (docs/questions.md Q40, `tests/evals/gate.py`): wrong at >= 0.6 is 3.3% (bar at
most 2%: fail); right 56% to 90% per language (bar at least 80%: only en passes); ask 8% to
36% (bar at most 15%: only en passes). Wrong items 1.3%, no errors. Two runs were allowed;
this is the second.

**Router.** The router gate was not rerun: `router_cases.PENDING` is already empty, because the
inventory manager had router cases from the retail set, and its router description is
unchanged since the last rerun, so docs/research/router-2026-10-19-rerun.md stands. Nothing
was added to router_cases.py.

## Setup

Model `jev-1.13.0`, threshold 0.6, egress level `pseudonymised`, concurrency 4, Ferino's
seeded per run, `build_query` for the case's sender (clerk Ana, supervisor Marites, owner
Rosa), `decider.decide` inside `egress_context`, retries with back-off on overload. 600 cases
per run, 0 errors, 55 s and 59 s of wall time.

Scoring (`tests/evals/test_inventory_manager_evals.py`, checked offline by
`test_inventory_cases.py::test_scoring`):

- **right**: the expected action; for `report_stock` the expected kind and the expected (name,
  quantity) pairs order-free; for `place_order` and `receive` the expected ingredient lines. A
  waste without a reason is right when Mia asks the reason (clarify with `missing: reason` at
  >= 0.6, the turn's reason buttons).
- **wrong**: another action at >= 0.6 (not clarify).
- **wrong items**: the expected action with another kind, other items, or a guessed reason
  (a wrong write, counted apart as in the sales set).
- **ask**: clarify, or a missing input other than the expected one.
- **other**: an error.

## Case set

`tests/evals/inventory_manager_cases.py`: ten messages per scenario per gated language (en,
fil, ceb, hil, war, bcl), 600 in all. Ten scenarios covering spec scenarios 1 to 8:
`sold_out` (five with a clock time, five without), `counts_left`, `leftovers`, `waste` (five
with a reason, five without), `low_ingredient`, `bake_plan`, `whats_low`, `place_order` (five
naming a supplier, five relying on the ingredient's own), `receive`, and `reply_only`
(greetings and thanks). Message n of a scenario is one seed in every language; its half is
n's parity (even tune, odd gate), so each (language, scenario) has five of each half. English
seeds came first; the five Philippine languages are Claude's drafts (Q28 to Q35 cover their
review). Item and ingredient names and short codes are the seed's. Clock times are written
"2pm" or "16:00" (a bare number is a count to `pre_parse`); "itlog" is avoided for eggs because
the seed codes it as the salted egg ingredient.

Offline checks (`tests/evals/test_inventory_cases.py`): counts per language, scenario and half;
expected actions in `ACTIONS`; no "Tagalog"; no text in both halves; every expected name is a
seeded item or ingredient; every counted case parses (`pre_parse`) to one group per expected
pair with its quantity and a word of that item, and a case without a number to no group.

## The tuning edit (once, from run 1's tune half only)

Run 1's tune-half misses: local sell-out, count, leftover and waste words read under 0.6 or as
another kind; "almost out" (paubos, hapit na mahurot, haros ubos) read as `sold_out`; "ubos"
picked as Ube; deliveries (niabot, nag-abot, nag-deliver) read as `report_stock` or
`place_order` (the `report_stock` description itself listed "a delivery that arrived");
"kuha og 30 niyog" read as a report; "need more banana leaves" as an order; "ano ang dapat
i-order" as an order without lines; "dagdagan ba ang ube bukas?" as an order. Edits in
`agents/inventory_manager/actions.py`:

- `KINDS`: the tune half's words for sold out, still here (count), leftover, thrown away and
  almost out, in the gated languages; low says "not yet sold out".
- `report_stock`: the delivery wording removed; "needing more of something, with no number, is
  running low"; "receive is a delivery that came in".
- `bake_plan`: how many to make, more or fewer of an item tomorrow, the words for tomorrow.
- `whats_low`: what to buy or order "without naming an ingredient and a number".
- `place_order`: the buy verbs (bili, kumuha, palit, kuha, bakal, kua); a delivery that came is
  receive.
- `receive`: the arrival verbs in the gated languages.
- The `item` question: "ubos, naubos, paubos, maubos are not Ube".

Case set, scoring and threshold were not touched.

| Half, gated languages (n 300) | Run 1 right | Run 1 wrong | Run 1 wrong items | Run 1 ask | Run 2 right | Run 2 wrong | Run 2 wrong items | Run 2 ask |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tune | 55.3% | 1.3% | 6.3% | 37.0% | 73.7% | 0% | 0.7% | 25.7% |
| gate | 55.7% | **3.7%** | 6.3% | 34.3% | 66.0% | **3.3%** | 1.3% | 29.3% |

## Gate (gate half, run 2)

| Language | n | Right | Wrong | Wrong items | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- | --- |
| English (`en`) | 50 | 90% | 2% | 0% | 8% | pass |
| Filipino (`fil`) | 50 | 56% | 6% | 2% | 36% | fail |
| Cebuano (`ceb`) | 50 | 56% | 6% | 2% | 36% | fail |
| Hiligaynon (`hil`) | 50 | 66% | 2% | 4% | 28% | fail |
| Waray (`war`) | 50 | 64% | 2% | 0% | 34% | fail |
| Central Bikol (`bcl`) | 50 | 64% | 2% | 0% | 34% | fail |
| **Gated, all** | 300 | 66.0% | **3.3%** (bar <= 2%: fail) | 1.3% | 29.3% | |

| Scenario (gate half) | n | Run 1 right | Run 1 wrong | Run 2 right | Run 2 wrong | Run 2 wrong items | Run 2 ask |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sold_out | 30 | 53.3% | 0% | 60.0% | 3.3% | 0% | 36.7% |
| **counts_left** | 30 | 10.0% | 26.7% | **26.7%** | **30.0%** | 0% | 43.3% |
| leftovers | 30 | 33.3% | 0% | 50.0% | 0% | 3.3% | 46.7% |
| **waste** | 30 | 16.7% | 0% | **16.7%** | 0% | 0% | 83.3% |
| low_ingredient | 30 | 33.3% | 0% | 63.3% | 0% | 10.0% | 26.7% |
| bake_plan | 30 | 90.0% | 0% | 90.0% | 0% | 0% | 10.0% |
| whats_low | 30 | 86.7% | 0% | 63.3% | 0% | 0% | 36.7% |
| place_order | 30 | 80.0% | 3.3% | 100% | 0% | 0% | 0% |
| receive | 30 | 53.3% | 6.7% | 90.0% | 0% | 0% | 10.0% |
| reply_only | 30 | 100% | 0% | 100% | 0% | 0% | 0% |

| Run 1, gate half | n | Right | Wrong | Wrong items | Ask |
| --- | --- | --- | --- | --- | --- |
| en | 50 | 90% | 0% | 4% | 6% |
| fil | 50 | 54% | 6% | 8% | 32% |
| ceb | 50 | 38% | 8% | 8% | 46% |
| hil | 50 | 54% | 2% | 4% | 40% |
| war | 50 | 48% | 0% | 10% | 42% |
| bcl | 50 | 50% | 6% | 4% | 40% |

## Tuning half (run 2)

| Language | n | Right | Wrong | Wrong items | Ask |
| --- | --- | --- | --- | --- | --- |
| en | 50 | 94% | 0% | 0% | 6% |
| fil | 50 | 76% | 0% | 2% | 22% |
| ceb | 50 | 62% | 0% | 0% | 38% |
| hil | 50 | 76% | 0% | 2% | 22% |
| war | 50 | 68% | 0% | 0% | 32% |
| bcl | 50 | 66% | 0% | 0% | 34% |
| **Gated, all** | 300 | 73.7% | 0% | 0.7% | 25.7% |

## Wrong actions and wrong items (gate half, run 2)

Ten wrong actions, nine of them one pattern: a count of an ingredient left ("na lang") read as
an order.

| Lang | Message | Expected | Chosen | Conf. |
| --- | --- | --- | --- | --- |
| ceb | rice flour 12 kg na lang bilin | report_stock count | place_order | 0.98 |
| fil | 1 tangke ng lpg na lang | report_stock count | place_order | 0.92 |
| bcl | 1 tangke nin lpg na sana | report_stock count | place_order | 0.92 |
| hil | 1 ka tangke lpg na lang | report_stock count | place_order | 0.87 |
| ceb | 1 ka tangke sa lpg na lang | report_stock count | place_order | 0.85 |
| fil | 4 kg asukal na lang | report_stock count | place_order | 0.82 |
| ceb | 3 ka trays eggs na lang | report_stock count | place_order | 0.82 |
| fil | rice flour 12 kg na lang | report_stock count | place_order | 0.70 |
| war | 1 ka tangke lpg na la | report_stock count | place_order | 0.65 |
| en | pb finished at 16:00 | report_stock sold_out | reply_only | 0.60 |

Wrong items (4): "halos wala nang flour", "halos wala nay flour", "halos wala na flour" (fil,
ceb, hil) as `sold_out` where `low` was meant; "ang nabilin 5 special kag 2 ube" (hil) as
`count` where `leftover` was meant.

Top ten confusions, both halves, run 2: report_stock asked (91), report_stock to place_order
asked (25), whats_low asked (14), report_stock to reply_only asked (13), report_stock to
place_order wrong (9), report_stock wrong items (6), report_stock to clarify (5), bake_plan
asked (4), whats_low to report_stock asked (2), receive asked (2).

## Latency, tokens, cost

Run 2: p50 0.37 s, p95 0.46 s. 3,410 tokens per message on average (run 1: 3,086; the longer
descriptions add about 320), about 2.05 million for the run; at TypeSafe's $0.042 per million
input tokens about $0.09, $0.00014 per message.

## Reading

- **English passes, the Philippine drafts do not.** en is 90% right and 8% ask on the gate
  half; the other five are 56% to 66% right with 28% to 36% ask. They are machine drafts (Q28
  to Q35), so part of the gap may be the texts themselves.
- **One harmful pattern makes the wrong rate.** Nine of ten wrongs are an ingredient count with
  a unit ("4 kg asukal na lang", "1 tangke lpg na lang") read as an order. The tuning did not
  move it (run 1 had the same pattern). In the chat a clerk cannot place an order (rbac) and an
  order waits for the owner's approval, so the harm is a wrong approval card, not a write; it is
  still the wrong action. The unit word plus a number looks like an order line to Jev.
- **Waste is the weakest scenario (16.7% right).** Without a reason the right action and the
  `reason` gap are found, but under 0.6, so the turn asks "Did you mean" instead of the reason
  buttons; with a reason, local words for burnt and dropped (nasunog, nahulog) are not picked
  as a reason, so Mia asks one that was given. `REASONS` was not tuned with local words.
- **The tuning carried over partly.** Tune half +18.4 points right, gate half +10.3. Deliveries
  (53% to 90%), orders (80% to 100%) and low ingredients (33% to 63%) carried over; whats_low
  lost 23 points on the gate half (right action under 0.6, "low stock ba?", "mag-restock").

## What remains

1. The gate is not met: wrong 3.3%, and right and ask in fil, ceb, hil, war and bcl. This gate
   half is spent.
2. Ingredient counts read as orders (rule 7 points at code): offer `place_order` only when the
   message has a buy word (order, buy, bili, palit, bakal, kuha, kua), or pass a `buy_word`
   flag in state; a count of an ingredient with "na lang", "pa" or "left" is then a report.
3. Waste reasons: the local words for burnt, dropped, expired and too dry in `REASONS`, and the
   reason question asked with the kind's confidence only, so a waste without a reason reaches
   the reason buttons.
4. The seed codes "itlog" (Filipino for egg) as the salted egg ingredient and "se" for both the
   salted egg item and ingredient; the case set avoids them. Worth a look when the seed is next
   touched.
5. The chat scenarios have not been run against real Jev.
