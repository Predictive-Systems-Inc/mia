# Jev bookkeeper decider and router evaluation (21 Oct 2026)

Spec docs/superpowers/specs/2026-10-20-bookkeeper-design.md (scenarios 1 to 8 and 10, section
10). Questions: does Jev pick the right bookkeeper action, and for a recording the right amount,
provider, category and petty cash kind, from what Ferino's head staff and owner send; and does
the router send the bookkeeper's messages to it now that its router description changed.
Synthetic data only (D18). Raw results, all in this folder: `bookkeeper-2026-10-21-0052.raw.json`
(tune half, the descriptions of 400f018), `-0053` (tune half after the one tuning edit),
`-0054` (the gate half, once) and `router-2026-10-21-0113.raw.json` (the router, once).

**What happened, in order.**

1. **Tune half (`0052`)**: right 88.4%, wrong 0.3% (one), ask 11.3%; hil ask 15.3% would fail.
2. **One tuning edit** to `agents/bookkeeper/actions.py` (descriptions only), from the tune
   half's misses; the tune half after it (`0053`): right 90.4%, wrong 0%, every language within
   the bar.
3. **Decider gate (`0054`, the gate half, once) failed.** fil ask 16.4%, ceb ask 18.2%, hil
   right 76.4% and ask 20.0%, war ask 18.2% (bar: right at least 80%, ask at most 15%); en and
   bcl pass; wrong 0.9% (bar at most 2%: pass). Reported as it is; nothing was tuned after it.
4. **Router gate (`0113`, the fresh gate half of 21 Oct, once) failed.** Wrong 4.6% (bar at
   most 2%); right below 80% in fil, ceb, hil, war and bcl; ask above 15% in fil, ceb and war;
   en passes. The bookkeeper's own gate seeds route at 97.6%; the misses are other agents'
   seeds. Reported as it is; no router description was edited (turn.py is Task 5's).

## Setup

Model `jev-1.13.0` (the pinned `MIA_JEV_MODEL` default), threshold 0.6, egress level
`pseudonymised`, concurrency 4. Ferino's is seeded by the `bk_shop` fixture on Tuesday 3 Nov
2026 (`BK_TODAY`), and the harness pins today to the case set's `TODAY` (the same Tuesday, not
the run date), so "kahapon", "last week" and "this quarter" resolve the same on every run. Each
case runs `build_query` and `decider.decide` inside `egress_context`, as the agent for
supervisor Marites (recordings, balances, utang) or owner Rosa (journal, tax, profit).
`MIA_EVAL_HALVES` picks the halves (`tune` for the tuning runs, `gate` for the gate run). 0
errors in every run. Code under test: 1471bc8 (Task 3's round 400f018 and Task 4's tools
c677a34 included) plus this round's description edit (the commit of this report).

Scoring: **right** is the expected action and, where the scenario has them, the expected amount
(minor units; `counted` for a cash count), provider, category and petty cash kind; **wrong** is
another of those, or another action at >= 0.6; **ask** is clarify or a missing input; **other**
is an error or another action below 0.6. The deposit's bank is recorded, not scored (the brief
names amount, provider and category).

## Case set

`node/tests/evals/bookkeeper_cases.py`: eleven scenarios (cash_count, settlement, payout,
expense, petty_cash, deposit, not_built for utang, balances, journal, tax_quarter, profit) in six
languages (en, fil, ceb, hil, war, bcl), ten seeds each, even seeds tune and odd seeds gate (a
seed's languages share a half; no text in both halves, shape test): 660 cases, 330 per half.
The tune half also carries scenario 10's security asks, never gated: three injected
instructions (expected `reply_only`) and one 12,000 peso oven repair (an expense over the
owner's limit; code sends it to the approval card), 24 cases. Amounts are typed as head staff
type them ("12,450", "₱3,210", "P12,000", "1,500.50"); "2k" is not read by `find_prices`, so no
case uses it. English seeds first; the other five are drafts by Claude, not native speakers
(review: Q28 to Q35). The shape test checks every expected amount is a `words.amounts`
candidate and every provider is the tender word the text names.

## Decider gate (`0054`, the gate half, once)

| Language | n | Right | Wrong | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- |
| English (`en`) | 55 | 96.4% | 0% | 3.6% | pass |
| Filipino (`fil`) | 55 | 83.6% | 0% | **16.4%** | **fail** (ask) |
| Cebuano (`ceb`) | 55 | 80.0% | 1.8% | **18.2%** | **fail** (ask; right on the bar) |
| Hiligaynon (`hil`) | 55 | **76.4%** | 3.6% | **20.0%** | **fail** |
| Waray (`war`) | 55 | 81.8% | 0% | **18.2%** | **fail** (ask) |
| Central Bikol (`bcl`) | 55 | 90.9% | 0% | 9.1% | pass |
| **Gated, all** | 330 | 84.8% | **0.9%** (bar <= 2%: pass) | 14.2% | **fail** |

| Scenario | Tune before (`0052`) right | Tune after (`0053`) right | Gate (`0054`) right | Gate ask | Gate wrong |
| --- | --- | --- | --- | --- | --- |
| cash_count | 90.0% | 96.7% | **63.3%** | 26.7% | **10.0%** |
| settlement | 76.7% | 80.0% | 70.0% | 30.0% | 0% |
| payout | 73.3% | 70.0% | 93.3% | 6.7% | 0% |
| expense | 100% | 100% | 83.3% | 16.7% | 0% |
| petty_cash | 83.3% | 86.7% | 93.3% | 6.7% | 0% |
| deposit | 100% | 100% | 100% | 0% | 0% |
| not_built | 100% | 100% | 80.0% | 20.0% | 0% |
| balances | 96.7% | 96.7% | 83.3% | 16.7% | 0% |
| journal | 100% | 100% | 93.3% | 6.7% | 0% |
| tax_quarter | 60.0% | 63.3% | 86.7% | 13.3% | 0% |
| profit | 83.3% | 93.3% | 86.7% | 13.3% | 0% |

- **The three wrongs are one word.** "8,730 ang cash pagsira" (ceb, 0.74), "8,730 ang cash sang
  pagsira" (hil, 0.79) and "kwarta sang kaha sa pagsira 9,540" (hil, 0.60) were read as
  expenses in the repairs category: "pagsira" is closing in Cebuano and Hiligaynon, but "sira"
  is broken in Filipino (and in `CATEGORIES`' repair words). The same seeds in war were asked
  (expense below 0.6). Both amounts are over the 5,000 peso expense limit, so `tool_for` would
  have sent them to `record_large_expense` and the owner's card, not written them; a closing
  count under the limit with the same word would have been written as a repair. The tune half
  had "pagsira" too ("total sa drawer human sa pagsira: 7,600", "pagsira" in other seeds) and
  scored right, so this was not visible there.
- **The 47 asks: 35 are the right action below 0.6** (Jev's own pick, `raw_action`). The other
  12: three more "pagsira" counts read as repair expenses below 0.6 (war 8,730, ceb and war
  9,540); four "how much should I still bring to the bank?" read as a deposit with no amount
  (ceb, hil, war, bcl; balances expected); three "ilista ... kay Aling Nena" (credit without
  the word utang) as reply_only below 0.6; "kumita ba tayo noong Oktubre?" (fil) as clarify;
  "pila ang nabilin nato sa miaging bulan human sa tanan?" (ceb) as balances below 0.6.
- **By scenario:** settlements (Maya settlement came in, PayMaya, nag-transfer ang Maya: 9 asks,
  all settlement with the right amount and provider below 0.6), closing counts (8 asks: "closing
  cash is 8,730", "closing count ng cash 13,980"), utang without the word (6), the bank question
  (5), expenses (5: abang sa stall, pliti, OR numbers).
- **Every amount, provider, category and kind Jev picked on a right action was right**; the
  only wrong inputs are the three repair expenses above.

## The tuning edit (once, from the tune half)

The tune half with 400f018's descriptions (`0052`): right 88.4%, wrong 0.3%, ask 11.3%; by
language en 96.6%, fil 91.5%, ceb 84.7%, hil 84.7% (ask 15.3%), war 86.4%, bcl 86.4%. Its misses:
tax questions (2550Q, "kwentaha ang VAT", buhis; 12 of 30), weekly Grab payouts and "remitted"
(8), "GCash sent us" and money that "hit the bank" (7), petty spends at low confidence (4) and
one wrong ("nibutang og 1,000 sa petty cash box", a refill read as a spend at 0.70), "lugi" and
"per branch" profit asks (5), "ihap sa kwarta" counts (3).

Edits in `agents/bookkeeper/actions.py`, descriptions only: cash_count names "ihap sa kwarta,
isip sang kwarta"; settlement says paid in, sent or transferred, also told as money that
reached the bank ("nagpadala ang GCash"); payout says paid, paid out or remitted, also a weekly
payout ("nag-remit ang GrabFood"); petty_cash says money taken out for something or put into it
("nibutang sa petty cash box"); tax_quarter says due or owed to BIR, or compute it (2550Q,
buwis, buhis, kwentaha ang VAT); profit says profit or loss, of the kiosk or per branch
(ganansya, lugi); the petty refill option names top up, lagay, butang. Case set, scoring,
threshold, decider code and `words.SPEND_WORDS` were not touched (the tune half showed no
petty message misread through "for": every petty spend with "for" was a spend).

| Tune half (n 354, with the 24 security cases) | Before (`0052`) right | ask | After (`0053`) right | ask |
| --- | --- | --- | --- | --- |
| en | 96.6% | 3.4% | 93.2% | 6.8% |
| fil | 91.5% | 8.5% | 93.2% | 6.8% |
| ceb | 84.7% | 13.6% | 88.1% | 11.9% |
| hil | 84.7% | 15.3% | 88.1% | 11.9% |
| war | 86.4% | 13.6% | 86.4% | 13.6% |
| bcl | 86.4% | 13.6% | 93.2% | 6.8% |
| all | 88.4% | 11.3% | 90.4% | 9.6% |

Security, tune-only, 24 of 24 right in both runs (the three injections reply_only, the 12,000
peso repair an expense with its amount and category). Wrong 1 then 0.

## Router gate (`0113`, once)

The router description at HEAD (a1e0d10, Task 5, `bookkeeper/turn.py`): "Money: the closing
cash count against sales, a drawer short or over, expenses and receipts, petty cash, bank
deposits, GCash and Maya settlements, Grab and Foodpanda payouts, VAT, the BIR sales book and
monthly profit; not sales counts, not a day's sales total and not pay." It names the agent's
subjects and the contrast the spec asks for (cash, expenses, deposits, settlements and tax; not
sales counts and not pay). The harness is unchanged (`test_router_eval.py`, `ROSTER` every
registered agent, the spent half never run).

`router_cases.py` changes (commit 1): `BOOKKEEPER_SEEDS`, ten seeds per gated language, even
seeds tune ("closing cash count is 7,250", "the GCash settlement for yesterday came in, 2,340",
"paid 1,200 for the water bill, receipt 4471", "how much is left in petty cash?", "what's our
VAT for this quarter?"), odd seeds gate ("deposited 15,000 at BDO this morning", "Foodpanda paid
out 6,300 for last week", "petty cash 300 for ice and cups", "send me the sales journal for
October", "how much profit did the kiosk make last month after payroll?"); the stub's twenty
bookkeeper seeds stay (the utang seed now gets the not-built reply). The 20 Oct gate half
(`FRESH_SEEDS`, `FRESH_CONTEXT`) was scored in `router-2026-10-20-2121` and is now `spent`; a
fresh gate half was written before any run of it (`GATE_1021_SEEDS`, `GATE_1021_CONTEXT`: five
singles for every other agent, two greetings, five follow-ups and five switches per gated
language). `PENDING` stays empty. `test_router_cases.py`'s balance check (tune against spent)
became "at least five tune cases per language and group", since the spent half now grows with
every gate run.

| Language (gate half, no greetings) | n | Right | Wrong | Ask | Gate |
| --- | --- | --- | --- | --- | --- |
| en | 45 | 91.1% | 4.4% | 4.4% | pass on right and ask |
| fil | 45 | **77.8%** | 4.4% | **17.8%** | **fail** |
| ceb | 45 | **68.9%** | 4.4% | **24.4%** | **fail** |
| hil | 45 | **77.8%** | 6.7% | 13.3% | **fail** (right) |
| war | 45 | **64.4%** | 2.2% | **28.9%** | **fail** |
| bcl | 45 | **77.8%** | 6.7% | 13.3% | **fail** (right) |
| **all (282, with greetings)** | 282 | 77.0% | **4.6%** | 16.7% | **fail** (wrong) |

Greetings 11 of 12 right. By agent (gate half): bookkeeper 97.6% (41 of 42; one ask, war "ipadara
an sales journal han Oktubre" at 0.47), customer_service 96.7%, hr_officer 83.3% (wrong
16.7%), shift_supervisor 78.6%, sales_supervisor 70.8% (wrong 10.4%), inventory_manager 54.8%
(ask 40.5%), branch_manager 53.3% (ask 43.3%). By group: singles 76.6%, follow-ups 83.3%
(wrong 13.3%), switches 73.3%.

The 13 wrongs: six are one seed, "I'd like a day off on the 15th", routed to shift_supervisor
at 0.61 to 0.81 in all six languages (a day off is a schedule change as much as leave; the
seed's expectation is arguable); four are the follow-up "there was a long brownout" after "Sales
are lower than last Tuesday. Do you know why?" (shift_supervisor at 0.61 to 0.81: a shop problem
as much as a sales reason); one each "pila na ang atong halin karong semanaha?" (ceb, to
shift_supervisor 0.63), "pirang classic an lulutuon mi para sa Biyernes?" (bcl, to
shift_supervisor 0.70), "himua nga 30 ang Kape umpisa Lunes" (hil, to shift_supervisor 0.75).
Without the two arguable seeds the gate half would be wrong 1.1% (3 of 272). None of the 13
went to the bookkeeper.

**The bookkeeper as the active agent keeps a sales question.** The switch "how are sales so
far today?" with the bookkeeper active stayed with the bookkeeper in ceb, hil, war and bcl (0.33
to 0.73; scored other, a kept wrong agent): the contrast "not a day's sales total" does not
reach "kumusta ang benta". The asks are mostly the inventory manager's sell-outs and waste
("ubos na", "itinapon", "gilabay"; 17) and the branch manager's letter and price change
("isulat", "himoa nga 30"; 13), Jev's pick below 0.6.

Tune half of the gated languages (594 rows): right 87.9%, wrong 2.2%. The bookkeeper's tune rows
(90: the stub's ten and the five new tune seeds) 91.1% right, 5.6% wrong: "GCash sales today
2,100" (a stub seed) went to sales_supervisor at 0.61 to 0.70 in five languages; the new
description says "not a day's sales total", and a GCash sales total is one, so that seed's
expectation now contradicts the description it is scored against.


## Latency, tokens, cost (measured)

Per request, measured in the harness around `decider.decide` (decider) or `jev.ask` (router);
tokens from the usage rows (input plus output).

| Run | Cases | Mean s | p95 s | Max s | Tokens | Per message |
| --- | --- | --- | --- | --- | --- | --- |
| decider tune before (`0052`) | 354 | 0.38 | 0.44 | 0.65 | 1,025,406 | 2,896 |
| decider tune after (`0053`) | 354 | 0.38 | 0.42 | 0.70 | 1,068,571 | 3,018 |
| decider gate (`0054`) | 330 | 0.39 | 0.44 | 1.63 | 998,775 | 3,026 |
| router (`0113`, tune and fresh gate) | 1,304 | 0.37 | 0.44 | 0.66 | 1,320,146 | 1,012 |

The edit adds about 120 tokens per message. The usage rows carry no cost (`cost_minor` 0); at
TypeSafe's list price of $0.042 per million input tokens (output free) the runs above are at
most $0.19 (4.41 million tokens): a price applied to measured tokens, not a billed amount.

## Reading

- **No write slipped past code.** Every amount, provider and category Jev picked was one code
  parsed; the three wrong actions were large enough to land on the owner's approval card. Still,
  "pagsira" read as a repair is the one finding that matters for money: a closing count under
  5,000 pesos would be recorded as an expense. Two fixes are open to the developer: a
  description line that a closing word (pagsara, pagsira) with a cash amount is a count, or a
  code check that a message with a count word is never an expense (rule 7 prefers the code).
- **The asks are mostly confidence, not confusion**, as in the earlier agents: 35 of 47 are the
  right action and inputs below 0.6. Settlements in fil, hil, war and closing counts are the bulk.
- **The router routes the bookkeeper's messages (97.6% on the fresh gate half) and none of the
  other agents' messages to it**, except the sales question it keeps while active; the router
  gate fails on the other agents' seeds, two of them arguable, as on 20 Oct.
- **Payout and tax moved with the edit** (gate 93.3% and 86.7%, against 70.0% and 63.3% on the
  tune half); settlements did not (gate 70.0%).

## What remains (the developer decides)

- Whether to fix "pagsira" (description or code) and tune once more, which needs fresh decider
  gate seeds: this gate half is spent.
- The router: the "day off" and "brownout" expectations, a "not how sales are going" line in
  the bookkeeper's description (Task 5's turn.py) and the "GCash sales today" stub seed; a rerun
  needs a third router gate half.
- The non-English messages are drafts (Q28 to Q35); the tax table is checked with the accountant
  (Q97).
- Record `cost_minor` in the usage rows.

Under D40 (21 Oct 2026) this run reads: bcl, ceb, en and war pass; fil fails (ask 16%, above 15%), hil fails (wrong 3.6%, above 2%). Computed from the relaxed-bar table in docs/research/2026-10-21-q40-threshold-study.md; no rerun, the numbers and verdict above stand.
