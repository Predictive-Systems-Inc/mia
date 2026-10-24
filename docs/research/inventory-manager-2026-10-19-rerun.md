# Jev inventory manager decider evaluation, rerun on a fresh gate half (19 Oct 2026)

Spec docs/superpowers/specs/2026-10-19-inventory-manager-design.md (sections 4 and 10). First
run: docs/research/inventory-manager-2026-10-19.md. Same question: does Jev pick the right
inventory action, kind and items from what Ferino's clerks, head staff and owner send?
Synthetic data only (D18). Raw results: `inventory-manager-2026-10-19-0653.raw.json` (run 1,
the fix wave's descriptions) and `inventory-manager-2026-10-19-0656.raw.json` (run 2, after
one tuning edit on the tune half).

**Result: the gate fails.** Run 2, fresh gate half, six gated languages (600 cases), against
the Q40 bar (`tests/evals/gate.py`): wrong at >= 0.6 is 0.3% (bar at most 2%: pass); right
61% to 89% per language (bar at least 80%: only en passes); ask 11% to 38% (bar at most 15%:
only en passes). Wrong items 0.8%, no errors. Two runs were allowed; this is the second.

**Do not tune on this gate half again.** Its texts were seen in two runs and its misses are
listed below; the next rerun needs a fresh gate half (new seeds), as this one was.

## Setup

Model `jev-1.13.0`, threshold 0.6, egress level `pseudonymised`, concurrency 4, Ferino's
seeded per run, `build_query` for the case's sender, `decider.decide` inside `egress_context`,
retries with back-off. 1,200 cases per run (600 tune, 600 gate), 0 errors, 118 s of wall time
each. Scoring as in the first run (right, wrong, wrong items, ask, other); a `place_order`
without a buy word becomes "Did you mean" in code (`decider.parse`, `has_buy_word`), so its
expected action stays `place_order` and the harness scores the clarify as ask. That is
intended: those three seeds measure the guard's cost, and they count against the ask bar.

## What changed since the first run

- fb91f4a: times with a space ("3 pm", "alas 2") are stripped before `pre_parse`; `received`
  is no longer a report kind; an unsure reason gives the reason buttons; a `place_order` pick
  without a buy word becomes "Did you mean"; local words in the reason criteria.
- 3ac0077: the retail opening hours helpers (no decider change).
- 1f9f83a: the seed's salted egg ingredient is "Salted duck eggs" (maalat, pula) and eggs has
  `itlog`.
- The case set: the first run's gate texts are folded into the tune half (TEXTS, ten per
  scenario and language), and GATE_TEXTS is a fresh gate half: ten new seeds per scenario, in
  each gated language, none of them in the file before, written before any result was seen.
  Spaced times in sell-outs (0, 4, 5, 8; "alas 2", "3 pm", "12:30") and counts (0, 3, 6);
  ingredient counts with units ("3 kg asukal na lang", "1 tank LPG left", "1 ka tangke lpg na
  lang bilin"); orders with a buy word (seven) and without (2, 6, 9: "send us 1 lpg tank
  tomorrow", "pakidala 1 tangke lpg bukas"); waste with local reason words (nasunog, napanis,
  matigas, gahi, matig-a, nahulog) and without; `itlog` for eggs and "itlog na maalat" for
  salted duck eggs. All languages of a seed share a half. The shape test now asks ten per
  (language, scenario, half).

## The tuning edit (once, from run 1's tune half only)

Run 1's tune half failed too (right 62% to 92%, ask 7% to 37%). Its misses: ingredient counts
with na lang still leaning to `place_order` (now asked by the buy-word guard, so ask, not
wrong); short codes (se, co, b4, kape) left unmapped in the `item` and `item_<i>` questions;
"halos wala na" read as sold out; local leftover, waste and low words, "aandamon", "may kulang
ba sa stock" and "mag-restock" under 0.6. Edits in `agents/inventory_manager/actions.py`,
descriptions and criteria text only:

- `KINDS`: more sold out, leftover, waste and low words from the tune half; almost none is low;
  a count with a unit and no buy word is a count.
- `report_stock`: an ingredient number with a unit and na lang, pa, bilin or left is a count;
  needing more (kailangan pa ng) is low.
- `place_order`: buying only with a buy word.
- `bake_plan`: dagdagan, dugangan, and the prepare words. `whats_low`: the stock questions.
  `receive`: may delivery, kararating lang.
- `item` and `item_<i>`: a short code names the row that lists it; a sold out item is a menu
  item.

Case set, scoring and threshold were not touched. Some tuned words (itapon, basurahan,
kailangan pa) also occur in gate texts, because the languages share them; none was taken from
the gate half.

| Half, gated languages (n 600) | Run 1 right | Run 1 wrong | Run 1 wrong items | Run 1 ask | Run 2 right | Run 2 wrong | Run 2 wrong items | Run 2 ask |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tune | 70.7% | 0.2% | 0.5% | 28.7% | 83.8% | 0.2% | 0.5% | 15.5% |
| gate | 66.3% | **0%** | 1.0% | 32.7% | 73.5% | **0.3%** | 0.8% | 25.3% |

## Gate (gate half, run 2)

| Language | n | Right | Wrong | Wrong items | Ask | Gate (right >= 80%, ask <= 15%) | Run 1 right / ask |
| --- | --- | --- | --- | --- | --- | --- | --- |
| English (`en`) | 100 | 89% | 0% | 0% | 11% | pass | 88% / 10% |
| Filipino (`fil`) | 100 | 77% | 0% | 2% | 21% | fail | 65% / 33% |
| Cebuano (`ceb`) | 100 | 61% | 1% | 0% | 38% | fail | 51% / 49% |
| Hiligaynon (`hil`) | 100 | 74% | 0% | 1% | 25% | fail | 69% / 29% |
| Waray (`war`) | 100 | 69% | 0% | 1% | 30% | fail | 61% / 39% |
| Central Bikol (`bcl`) | 100 | 71% | 1% | 1% | 27% | fail | 64% / 36% |
| **Gated, all** | 600 | 73.5% | **0.3%** (bar <= 2%: pass) | 0.8% | 25.3% | | 66.3% / 32.7% |

| Scenario (gate half) | n | Run 1 right | Run 2 right | Run 2 wrong | Run 2 wrong items | Run 2 ask |
| --- | --- | --- | --- | --- | --- | --- |
| sold_out | 60 | 71.7% | 73.3% | 0% | 0% | 26.7% |
| counts_left | 60 | 43.3% | 75.0% | 0% | 1.7% | 23.3% |
| leftovers | 60 | 61.7% | 71.7% | 0% | 3.3% | 25.0% |
| waste | 60 | 58.3% | 65.0% | 0% | 0% | 35.0% |
| low_ingredient | 60 | 63.3% | 76.7% | 0% | 3.3% | 20.0% |
| bake_plan | 60 | 86.7% | 81.7% | 0% | 0% | 18.3% |
| whats_low | 60 | 70.0% | 75.0% | 0% | 0% | 25.0% |
| place_order | 60 | 50.0% | 53.3% | 3.3% | 0% | 43.3% |
| receive | 60 | 86.7% | 91.7% | 0% | 0% | 8.3% |
| reply_only | 60 | 71.7% | 71.7% | 0% | 0% | 28.3% |

Slices (gate half, run 2; run 1 in brackets): orders with a buy word 76% right (71%), without
one 89% ask and 11% wrong (100% ask); ingredient counts 86% right (42%), one picked
`place_order` (17); waste with a reason 73% right (67%), without 57% (50%); sell-outs and
counts with a clock time 65% right (57%), without 82% (58%).

## Tuning half (run 2)

| Language | n | Right | Wrong | Wrong items | Ask |
| --- | --- | --- | --- | --- | --- |
| en | 100 | 95% | 1% | 0% | 4% |
| fil | 100 | 81% | 0% | 1% | 18% |
| ceb | 100 | 76% | 0% | 0% | 24% |
| hil | 100 | 90% | 0% | 0% | 10% |
| war | 100 | 80% | 0% | 0% | 20% |
| bcl | 100 | 81% | 0% | 2% | 17% |
| **Gated, all** | 600 | 83.8% | 0.2% | 0.5% | 15.5% |

## Wrong actions and wrong items (gate half, run 2)

| Lang | Message | Expected | Chosen | Conf. |
| --- | --- | --- | --- | --- |
| ceb | padalha og 1 tangke lpg ugma | place_order | report_stock count (LPG 1) | 0.66 |
| bcl | ipadara an 1 tangke lpg sa aga | place_order | report_stock count (LPG 1) | 0.69 |

Both are orders without a buy word; the run 2 edit ("a number with a unit and no buy word is
a count") pushed them to a count, a wrong write of 1 tank of LPG left.

Wrong items (5): "kape 12, pb 5 natitira" (fil) as leftover, "5 classic di nabili" (fil) and
"1 b4 box ang nabilin" (hil) as count where leftover was meant, "hapit na maubos an itlog nga
maalat" (war) as the Salted egg item instead of the Salted duck eggs ingredient, "haros ubos
na man an asukal" (bcl) as sold out where low was meant.

Top ten confusions, gate half, run 2: report_stock asked (64), place_order asked (24, of them
16 the buy-word guard), reply_only asked (12), whats_low asked (11), bake_plan asked (9),
report_stock to reply_only asked (8), report_stock wrong items (5), report_stock to
place_order asked (5), receive asked (4), reply_only to bake_plan asked (3, "kita tayo
bukas" and its kin: see you tomorrow read as the plan).

## Latency, tokens, cost

Run 2: p50 0.38 s, p95 0.46 s (gate half). 3,819 tokens per gate message on average (run 1:
3,488; the edit adds about 330), 4.61 million for the 1,200-case run; at TypeSafe's $0.042 per
million input tokens about $0.19, $0.00016 per message.

## Reading

- **The harmful pattern is gone.** The first run's nine ingredient counts read as orders are
  down to one `place_order` pick (asked, not acted on) and ingredient counts are 86% right.
  Wrong is 0.3% and passes the bar; the two wrongs are the opposite trade, an order without a
  buy word read as a count.
- **Ask is the gap, not choice.** 124 of the 152 asked gate cases had the expected action as
  Jev's pick, under 0.6. The Philippine drafts sit 12 to 28 points under English, as in the
  first run; they are machine drafts (Q28 to Q35), so some of the gap may be the texts.
- **The buy-word guard costs what it should.** Orders without a buy word are asked (16 of 18),
  which is its purpose; they alone are up to 3 points of ask per language (and 16 of the 124
  above).
- **Spaced times are parsed but still harder.** Timed sell-outs and counts are 65% right, 17
  points under untimed ones; the times reach `times` and leave no count group, so the gap is
  Jev's confidence on the longer message.
- **The tuning carried over partly again.** Tune +13.1 points right, gate +7.2.

## What remains

1. The gate is not met: right and ask in fil, ceb, hil, war and bcl. **Do not tune on this
   gate half again**; a further rerun needs fresh seeds.
2. Confidence under 0.6 on the right action is most of the ask. Options for rule 7 code rather
   than more words: a lower bar when the action matches the kind's own pick, or a native
   speaker pass on the drafts (Q28 to Q35) before the next gate.
3. Orders without a buy word: the count wording in the edit turns some into a count (two
   wrongs). Either accept that only buy words order, or keep "send", "padalha", "ipadara" as
   buy words.
4. "Salted duck eggs" versus the Salted egg item: one swap; the `item` question could say an
   ingredient that is running low is never a menu item.
5. The chat scenarios have not been run against real Jev.

Under D40 (21 Oct 2026) this run reads: bcl, en, hil and war pass; ceb fails (right 62%, ask 37%), fil fails (right 79%, ask 19%). Computed from the relaxed-bar table in docs/research/2026-10-21-q40-threshold-study.md; no rerun, the numbers and verdict above stand.

## D40 rerun on the fresh gate half (21 Oct 2026, `2052`, once)

Raw file `docs/research/inventory-manager-2026-10-21-2052.raw.json`. The fresh gate half of
`inventory_manager_cases.py` (half "gate"; the 19 Oct rows are spent and were not run), 360
rows, 60 per gated language, run once with `MIA_EVAL_HALVES=gate MIA_DECIDER=jev`. No agent,
description, case or harness changed before or during the run. The printed summary and a
recount from the raw file agree; no error rows.

| Language | n | Right | Wrong | Wrong items | Ask | D40 |
| --- | --- | --- | --- | --- | --- | --- |
| en | 60 | 91.7% (55) | 0.0% (0) | 0.0% (0) | 8.3% (5) | pass |
| fil | 60 | **75.0%** (45) | 0.0% (0) | 0.0% (0) | **25.0%** (15) | **fail** (right, ask) |
| ceb | 60 | 66.7% (40) | 0.0% (0) | 0.0% (0) | **33.3%** (20) | **fail** (ask) |
| hil | 60 | 71.7% (43) | 0.0% (0) | 0.0% (0) | 28.3% (17) | pass |
| war | 60 | 65.0% (39) | 0.0% (0) | 1.7% (1) | **33.3%** (20) | **fail** (ask) |
| bcl | 60 | **60.0%** (36) | 0.0% (0) | 0.0% (0) | **40.0%** (24) | **fail** (right, ask) |
| **all** | 360 | 71.7% (258) | 0.0% (0) | 0.3% (1) | 28.1% (101) | wrong passes |

**Verdict under D40: fail**, on asks, in fil, ceb, war and bcl (none on one row: fil 15 asks
against the 9 that 15% allows, ceb and war 20 against 18, bcl 24 against 18; fil and bcl also
fail right). No wrong action anywhere; wrong passes. The harness scores wrong_items apart (a
wrong write of the expected action) and `gate.py` does not count it as wrong.

**The one wrong write (wrong_items, it writes).** war "4 nga classic ginlabog" (4 classic
thrown away): Jev picked report_stock at 0.62 with kind count, so record_events
(write_internal, `approval: never`) would record an end-of-day count of 4 classic instead of a
waste of 4. "ginlabog" is in the waste description; no code guard checks the kind against the
message's words. A rule 7 fix would be a waste-word check in code (a waste word with a picked
count asks the kind).

**The asks by cause (101).** report_stock right action below 0.6: 32 (leftovers, "co left how
many?", "tira pagkatapos ng shift"). report_stock read as reply_only under 0.6: 12 (fil "1 se
ang tira pagsara", "4 classic itinapon", ceb "hapit na mahurot ang dahon"). A missing input
asked on report_stock: 22 (reason 7, quantity 5, lines 4, kind 3, item 3; the waste without a
reason or a number scores right only when Mia asks that, so these are the other missing
slots). reply_only below 0.6: 9 ("salamat gid", "sige, mopauli na ko"). whats_low: 12 (missing
item 8, low confidence 4). report_stock read as clarify: 3 ("pila na lang co?"). The rest, 11:
bake_plan 4, place_order 3, a count read as place_order 1, "how does this work?" read as
clarify 1, whats_low missing lines 1, receive 1. bcl's 24 asks spread over the same causes.

### Primary metric (D41)

Primary metric (D41, en and fil at the full bar: wrong at most 2 percent, right at least 80, ask at most 15): en pass (right 91.7%, wrong 0 (0.0%), ask 8.3%); fil fail (right 75.0%, wrong 0 (0.0%), ask 25.0%).

The regional languages (ceb, hil, war, bcl) keep the D40 reading above, reported and not blocking (D41).

fil wrong rows: none.

fil ask rows by cause (15; text and Jev's confidence):

- report_stock, right action below 0.6 (6): "tira pagkatapos ng shift 2 classic 3 special" 0.27; "6 pb tira ngayong araw" 0.38; "special na tira ngayong gabi, 6 pcs" 0.53; "gaano pa karami ang rice flour sa stock" 0.41; "may kape pa ba? ilan" 0.38; "ilan pang se ang hindi pa nabebenta?" 0.39
- report_stock read as reply_only (2): "1 se ang tira pagsara" 0.35; "4 classic itinapon" 0.3
- report_stock, missing lines (1): "naubusan kami ng salted egg mga 1:30pm" 0.43
- report_stock, missing reason (1): "3 pb tumigas, tinapon" 0.79
- report_stock, missing item_0 (1): "1 sp tinapon sa basurahan" 0.6
- whats_low, right action below 0.6 (1): "pakita ng mga paubos na stock" 0.39
- whats_low, missing item (1): "low stock report nga po" 0.54
- reply_only, right action below 0.6 (1): "kita tayo sa susunod na shift" 0.59
- report_stock read as clarify (1): "ilan na lang co?" 0.26
