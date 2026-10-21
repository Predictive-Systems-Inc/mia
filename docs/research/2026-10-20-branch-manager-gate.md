# Jev branch manager decider and router evaluation (20 Oct 2026)

Spec docs/superpowers/specs/2026-10-19-branch-manager-design.md (scenarios 3 to 7, section 10,
section 13); plan docs/superpowers/plans/2026-10-20-branch-manager.md, Task 8. Question: does
Jev pick the right branch manager action and, for a write, the right item, price, short code or
keep, from what Ferino's owner, head staff and clerks send; and does the router send the branch
manager's messages to it now that its router description changed. Synthetic data only (D18).
Raw results, all in this folder: `branch-manager-2026-10-20-2047.raw.json` (tune half, the
descriptions of 630b0f5), `-2048` (tune half after the one tuning edit), `-2049` (the gate
half, once) and `router-2026-10-20-2050.raw.json` (the router, once).

**Result: both gates fail, in run 1 and again in run 2 (fix round 1).** Run 2 is the last run
the developer allowed; nothing was tuned after it. Runs in order: decider tune `2047`, tune
`2048`, gate `2049` (run 1, now the spent half); router `2050` (run 1, now spent); fix round 1
(see the section at the end): decider tune `2119`, decider gate `2120` (run 2, the fresh gate
half), router `2121` (run 2, the fresh gate half).

| Gate | Run | wrong (all) | Languages that pass | Fails |
| --- | --- | --- | --- | --- |
| decider | 1 (`2049`) | 0.0% | en | fil, ceb, bcl ask; hil, war right and ask |
| decider | 2 (`2120`) | 0.4% | en, fil | ceb, hil, war, bcl right and ask |
| router | 1 (`2050`) | 3.2% | none | every language; wrong |
| router | 2 (`2121`) | 3.5% | en, ceb (on the ask bar), hil | fil ask, war right, bcl right and ask; wrong |

Run 1 as first reported:

- **Decider (`2049`, gate half, 270 cases):** wrong 0.0% (bar at most 2%: pass); right 66.7%
  to 93.3% (bar at least 80%: hil and war fail); ask 6.7% to 33.3% (bar at most 15%: fil, hil,
  war and bcl fail, ceb 15.6%). Only English passes.
- **Router (`2050`, gate half of the gated languages, 564 cases):** wrong 3.2% (bar at most 2%:
  fail); right 64.4% to 75.6% (every language fails); ask 15.6% to 23.3% (every language but
  hil fails).

## Setup

Model `jev-1.13.0` (the pinned `MIA_JEV_MODEL` default), threshold 0.6, egress level
`pseudonymised`, concurrency 4, 0 errors in every run. The decider harness seeds Ferino's with
the `bm_shop` fixture on Monday 26 Oct 2026 and pins today to the case set's `TODAY` (the same
Monday, never the run date), so "Lunes", "Sabado" and "bukas" resolve the same on every run.
Each case runs `build_query` and `decider.decide` inside `egress_context`, as the agent for
clerk Ana (how to sell), supervisor Marites (short codes, most weekly summaries, the last four
coaching questions and the last two experiments of each experiment scenario) or owner Rosa (the
rest). `MIA_EVAL_HALVES` picks the halves (`tune` for the two tuning runs, `gate` for the gate).
The router harness is unchanged (`test_router_eval.py`, all router cases, the gate asserts read
the gate half of the gated languages).

Code under test: 630b0f5 plus this round's description edit (the commit of this report). The
working tree also held other agents' uncommitted Task 4 edits, among them one change to
`branch_manager/decider.py` (`_propose`: no price but a picked strategy is no longer a missing
price). No case in any of the three runs reached that branch (no experiment with an item, a
strategy and no price), so no score depends on it.

Scoring (decider): **right** is the expected action and its inputs: the item (by name), the
price candidate for `propose_experiment` and `change_price`, the short code for
`set_short_code`, keep or go back for `decide_experiment_result`; **wrong** is another input or
another action at >= 0.6; **ask** is clarify, a missing input, or an experiment with no item
(the turn answers that with the engine's proposals); **other** is an error or another action
below 0.6. The plan's line is "action and item, plus the price candidate"; the code and keep
checks are added because they are the values a write carries. The experiment's kind and
strategy are reported, not scored.

## Case set

`node/tests/evals/branch_manager_cases.py`: nine scenarios (coaching, how_to_sell,
experiment_price, experiment_promo, change_price, short_code, weekly, monthly, keep), ten seeds
each in six languages (en, fil, ceb, hil, war, bcl), 540 cases; even seeds tune, odd seeds gate,
so a seed's languages share a half and no text (casefolded) is in both (shape test). Items as
clerks type them (Classic, Salted egg, Box of 4, cheese overload), never "bibingka" alone. The
typed experiments cover every strategy of the catalogue (charm, anchor, increase, decoy, volume,
markdown, seasonal, bundle) and two name none, and all three kinds (price, promo, bundle). Keep
cases reply to Mia's experiment result in their language (`RESULT`), five keep and five go back
split across both halves. The shape test checks every expected price is a `find_prices`
candidate, every price change names a `find_dates` day, and every short code is a word
`build_query` offers. English seeds first; the other five are drafts by Claude, not native
speakers (Q28 to Q35).

## Decider gate (`2049`, the gate half, once)

| Language | n | Right | Wrong | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- |
| English (`en`) | 45 | 93.3% | 0% | 6.7% | pass |
| Filipino (`fil`) | 45 | 80.0% | 0% | **20.0%** | **fail** (ask) |
| Cebuano (`ceb`) | 45 | 84.4% | 0% | **15.6%** | **fail** (ask) |
| Hiligaynon (`hil`) | 45 | **75.6%** | 0% | **24.4%** | **fail** |
| Waray (`war`) | 45 | **66.7%** | 0% | **33.3%** | **fail** |
| Central Bikol (`bcl`) | 45 | 82.2% | 0% | **17.8%** | **fail** (ask) |
| **Gated, all** | 270 | 80.4% | **0.0%** (bar <= 2%: pass) | 19.6% | **fail** |

| Scenario (gate) | n | Right | Ask |
| --- | --- | --- | --- |
| coaching | 30 | 90.0% | 10.0% |
| how_to_sell | 30 | 93.3% | 6.7% |
| experiment_price | 30 | 63.3% | 36.7% |
| experiment_promo | 30 | **50.0%** | **50.0%** |
| change_price | 30 | 93.3% | 6.7% |
| short_code | 30 | **53.3%** | **46.7%** |
| weekly | 30 | 96.7% | 3.3% |
| monthly | 30 | 83.3% | 16.7% |
| keep | 30 | 100% | 0% |

The 53 asks:

- **Experiments, 26.** In 24 Jev's top pick is `propose_experiment` with the right item and the
  right price, below 0.6 (0.25 to 0.58): the markdowns ("markdown test: Ube sa 35 pagkatapos ng
  6pm", "we keep throwing away Classic, test 32 after 7pm", 6 of 6 languages; "promo sa Special
  sa huling oras bago magsara, 40 bawat isa", 4), the increase on a sell-out item ("nauubos an
  Classic antes han udto, testingi an 44", 4), the premium anchor ("cheese overload at 65 as the
  premium one", 3), "kape sa 29 anay/muna" (3), one trial. One (war, the Special markdown) was
  `propose_experiment` at 0.76 with no item, and one (war, the Ube markdown) read as
  `decide_experiment_result` at 0.25.
- **Short codes, 14.** Eight are `set_short_code` with the right item and **no code** (the code
  slot not stated), five of them at 0.89 to 0.97 ("gawin nating seg ang short code ng salted
  egg" in five languages, "pirme gina-type sang clerk ang kl para sa Classic"); five are the
  right pick below 0.6; one (war, "seg") picked the word "egg" as the code at 0.34 (below the
  threshold, so asked, but a wrong code had it been above).
- **Monthly, 5.** "I need the month's totals per clerk and the best days" in five languages:
  `monthly_letter` at 0.43 to 0.56.
- **Coaching, 3; how to sell, 2** (all war): the right pick below 0.6, and "kumusta hi Pao
  kumpara han nakalabay nga bulan?" read as `monthly_letter` at 0.42.
- **Price change, 2.** "bag-o nga presyo sang/han Box of 4: 165 umpisa/tikang Sabado" (hil,
  war): `propose_experiment` at 0.21 and 0.54.
- **Weekly, 1.** "unsa ang labing halin ug labing hinay karong semanaha?" (ceb):
  `coaching_who` at 0.44.

Kind and strategy (reported, not scored): of the 34 right experiments the kind matched in 34
and the strategy in 30.

## The tuning edit (once, from the tune half)

The tune half with the descriptions of 630b0f5 (`2047`): right 80.7%, wrong 1.1%, ask 18.1%;
ceb 75.6%, hil, war and bcl 77.8%. Its misses: "who is good at selling salted egg?" read as
`how_to_sell` (hil 0.91, war 0.70, bcl 0.60: the three wrong); "puto bumbong is slow today,
what should I say to customers?" and "nobody buys salted egg in the afternoon, any advice?" as
`reply_only` or `how_to_sell` below 0.6 (9); typed experiments as `propose_experiment` below
0.6 ("experiment: puto bumbong at 39 starting Monday", "3 Classic sa 110", "2 kape sa 45",
"Box of 4 sa 150 isip bundle", "39 ang Classic ng dalawang linggo"; 23); "give cheese overload
the code cho" with no code (7); "binulan nga report" (4); "ipabilin/panatilihin ang bagong
presyo" (4, two read as `change_price` with no item).

Edits in `agents/branch_manager/actions.py`, action descriptions only: coaching_who names "who
on the team sells an item well or best (sino magaling magbenta ng salted egg, who is good at
selling the ube)" and says it is about people, not a tip for the sender; how_to_sell adds an
item selling slowly or nobody buying it with a request for advice or what to say (mabagal,
walang bumibili, payo, tambag, laygay, hatol) and "never a question about who sells well";
propose_experiment says any message that tests, tries or promotes an item at a price is this
action and lists the tune half's forms (a price for a few weeks, a message starting with
experiment, several pieces for one price, a bundle or combo at a price, a higher price for an
item that sells out) and verbs (subukan, sulayan, tilawan, testingan, probaran, i-test,
i-promo, i-trial); decide_experiment_result adds panatilihin and ipabilin and says that after
an experiment's result in `previous_mia_message`, keeping the new price is never change_price;
set_short_code adds "give the item the code cho" and "names the item and one short code word";
weekly_summary adds the week's numbers against target, numbers ng linggo, semana;
monthly_letter adds binulan and binulanang report. The strategy candidates, the questions, the
case set, the scoring, the threshold and the decider code were not touched.

| Tune half (n 270) | Before (`2047`) right | ask | After (`2048`) right | ask |
| --- | --- | --- | --- | --- |
| en | 93.3% | 6.7% | 95.6% | 4.4% |
| fil | 82.2% | 17.8% | 88.9% | 11.1% |
| ceb | 75.6% | 24.4% | 84.4% | 15.6% |
| hil | 77.8% | 20.0% | 91.1% | 8.9% |
| war | 77.8% | 20.0% | 88.9% | 11.1% |
| bcl | 77.8% | 20.0% | 88.9% | 11.1% |
| all | 80.7% | 18.1% (wrong 1.1%) | 89.6% | 10.4% (wrong 0%) |

After the edit the tune half's coaching, how to sell, weekly and monthly were 100% right; its
remaining asks were experiments (16, all the right pick below 0.6), short codes (8) and four
keep cases ("ipabilin na naton ang bag-o nga presyo", the right pick at 0.51 to 0.59).

## Router gate (`2050`, once)

The router description changed with the scaffold: the stub's "Running the shop: branches, the
menu and new menu items, prices and item short codes, who approves what, shop opening hours,
people and their roles, permits, the weekly summary, coaching and tips for staff; not a day's
counts and not a shift change" became "Coaching, tips and quotes for the sales staff, price and
promo experiments the owner approves, a price change on a date, the weekly summary and the
monthly letter; not sales counts or targets" (`branch_manager/turn.py`, not edited here; its
contrast line is the one the spec asks for). `router_cases.py` gains `BRANCH_MANAGER_SEEDS`: ten
seeds in the six gated languages, even seeds tune, odd seeds gate (coaching, a tip, a price
test, the promo experiment's progress, a dated price, what to promote, keeping a tested price,
the monthly letter, coaching a clerk, a bundle test). The stub's twenty branch manager seeds stay
as the brief says (out of v1 asks get the capabilities reply). `PENDING` was and stays empty.

| Language (gate half, no greetings) | n | Right | Wrong | Ask | Small talk | Gate |
| --- | --- | --- | --- | --- | --- | --- |
| en | 90 | 75.6% | 1.1% | 17.8% | 4.4% | **fail** |
| fil | 90 | 68.9% | 1.1% | 22.2% | 4.4% | **fail** |
| ceb | 90 | 66.7% | 3.3% | 21.1% | 5.6% | **fail** |
| hil | 90 | 71.1% | 3.3% | 15.6% | 4.4% | **fail** (right) |
| war | 90 | 64.4% | 3.3% | 23.3% | 4.4% | **fail** |
| bcl | 90 | 67.8% | 7.8% | 18.9% | 2.2% | **fail** |
| **all (564, with greetings)** | 564 | 70.2% | **3.2%** | 19.1% | 4.1% | **fail** |

Greetings and thanks (reported apart): 24, 95.8% right.

| Expected agent (gate half) | n | Right | Wrong | Ask | Small talk |
| --- | --- | --- | --- | --- | --- |
| branch_manager, the new seeds | 30 | 83.3% | 0% | 13.3% | 3.3% |
| branch_manager, the stub's seeds | 60 | **10.0%** | **15.0%** | 53.3% | 21.7% |
| customer_service | 30 | **0%** | 0% | 70.0% | 30.0% |
| sales_supervisor | 108 | 54.6% | 6.5% | 28.7% | 0% |
| inventory_manager | 78 | 73.1% | 0% | 20.5% | 0% |
| shift_supervisor | 108 | 94.4% | 0% | 2.8% | 0% |
| bookkeeper | 66 | 97.0% | 3.0% | 0% | 0% |
| hr_officer | 60 | 100% | 0% | 0% | 0% |

What moved, against the same 504 gate rows in the 19 Oct run 2 (`router-2026-10-19-0345`):
right 79.4% to 73.6%, wrong 2.2% to 3.6%, ask 13.9% to 16.5%. Almost all of it is the stub's
branch manager seeds, which the new description no longer covers: 20 went from right to ask, 7
from right to wrong (opening hours and "make Liza a supervisor" to shift_supervisor, the menu
to inventory_manager), 5 from right to small talk (permits, "what does co stand for"). The
other agents moved little (sales_supervisor 8 asks became right, 4 rights became asks).

Two causes outside this task's files:

- **The router harness cannot route to customer_service.** `test_router_eval.ROSTER` lists six
  agents without customer_service, so its ten seeds per language (added in d445935) can never be
  right: 30 gate rows, 70% ask, 30% small talk.
- **The stub's out-of-v1 seeds expect branch_manager**, but the built description names none of
  their subjects (menu, opening hours, people and roles, permits, approvals).

Leaving both out (reported, not the gate): 474 rows, wrong 1.9%, right en 89.3%, fil 81.3%,
ceb 78.7%, hil 84.0%, war 76.0%, bcl 80.0%, ask at most 16.0% (war). That would still fail on
ceb and war right and war ask.

The new seeds' tune half (30) was 60.0% right, 40.0% ask: "make Salted egg 52 from November 2"
(6 of 6 asked, top pick sales_supervisor below 0.6) and "keep the 49 price on Salted egg after
the test" (5 of 6 asked).

## Latency, tokens, cost (measured)

Per request, measured in the harness around `decider.decide` (decider) or `jev.ask` (router);
tokens from the usage rows (input plus output).

| Run | Cases | Mean s | p95 s | Max s | Tokens | Per message |
| --- | --- | --- | --- | --- | --- | --- |
| decider tune before (`2047`) | 270 | 0.39 | 0.44 | 0.65 | 974,435 | 3,609 |
| decider tune after (`2048`) | 270 | 0.39 | 0.45 | 0.70 | 1,064,273 | 3,941 |
| decider gate (`2049`) | 270 | 0.39 | 0.45 | 0.56 | 1,068,288 | 3,956 |
| router (`2050`, every case) | 1,983 | 0.37 | 0.43 | 0.86 | 1,862,546 | 939 |

The branch manager request is about twice the customer service's (1,841 per message): eleven
actions, the item, price, date, code, kind, keep and conversation questions and the eight
strategy descriptions. The edit adds about 330 tokens per message. The usage rows carry no cost
(`cost_minor` 0 in the harness rows); at TypeSafe's list price of $0.042 per million input
tokens (output free) the four runs (4.97 million tokens) are at most $0.21, under $0.0002 per
decider message: a price applied to measured tokens, not a billed amount.

## Reading

- **No harmful write in the decider.** Wrong is 0% on the gate half: no price, item, short code
  or keep read wrongly at >= 0.6. Both money writes still wait for the owner's approval.
- **The misses are confidence, not confusion.** 46 of the 53 gate asks are Jev's right action:
  38 below 0.6 with every input right (24 of them experiments with the right item and price)
  and 8 short codes with the code not picked (7 of them at >= 0.6). The experiment description lists forms
  and verbs; the gate's markdowns and sell-out increases use other words (pagkatapos ng 6pm,
  last hour before closing, nauubos bago mag-udto). Saying what an experiment is (a changed
  price or offer on an item for a while, with or without the word test) rather than listing
  forms is a next edit for the developer to decide.
- **The short code slot is the one real defect.** With the right action at up to 0.97 the code
  question still answers not stated for "seg", "kl" and "ubi". That is the `code` question in
  `build_request` (positions in `codes`), not a description, and was not touched (descriptions
  only).
- **The router's drop is the description's narrowing**, not the new seeds (83.3% right on the
  gate half). Whether out-of-v1 asks should still route to the branch manager (then the
  description must name them) or the stub's seeds should expect another agent or small talk is
  a decision for the developer; and `ROSTER` needs customer_service before any router gate can
  pass.

## What remains (the developer decides)

- A second description edit and a decider rerun, which needs fresh gate seeds: this gate half
  is spent.
- The short code question in `actions.build_request`.
- The router: the stub's out-of-v1 seeds against the new description, customer_service in the
  router harness's `ROSTER`, and a router rerun on fresh gate seeds.
- The non-English messages are drafts (Q28 to Q35).
- Record `cost_minor` in the usage rows, so the next report reads cost, not a list price.

## Fix round 1 (the developer's decision, 20 Oct 2026)

The controller, as the developer in the loop, allowed one round of fixes from the tune halves,
fresh gate seeds for both gates and one rerun each, all runs reported in order, stopping if
either still fails. Both still fail.

### What changed between run 1 and run 2

1. **The router harness routes to every agent.** `test_router_eval.ROSTER` is now
   `list(AGENTS)` (the registry), so customer_service is an option and the next agent cannot be
   missed; an offline test checks it. Run 1 (`2050`) re-scored offline from its raw file, no
   new call: its 30 customer_service rows were answered with customer_service absent, so they
   cannot be re-scored and are left out: 534 rows, wrong 3.4%; right en 80.0%, fil 72.9%, ceb
   70.6%, hil 75.3%, war 68.2%, bcl 71.8%; ask 11.8% to 20.0%. Still failing on every
   measure.
2. **The router description names the catalogue's subjects** (items 8 to 13), committed by
   Task 5 in b5ae07f (`branch_manager/turn.py`, not edited here): "Leading the shop: coaching
   and tips for staff, price and promo experiments, menu prices, short codes and combos, opening
   hours, people and roles and who approves what, permits and renewals, the weekly summary and
   the monthly numbers; not sales counts or targets and not a shift change." The stub's seeds
   stay as they were. The router run waited for that commit.
3. **Short code candidates in code** (`actions.code_candidates`, rule 7): whole tokens of 2 to
   6 letters or digits (so "bag-o" is no candidate), not a number, not an item's code, not a
   word or part of an item's name ("egg" of Salted egg), not a function or code word of the
   six languages (`NOT_CODES`), shortest first, at most four; the code question says the most
   likely word is first and "not stated" only when no new code is named. Unit tests in
   `test_branch_manager_actions.py`; the shape test checks every short code case's code is the
   first candidate.
4. **One more description edit from the tune half** (`actions.py`): propose_experiment names the
   typed shapes in the six languages' own words from the tune half (subukan natin <price> ang
   <item>, sulayan nato og, tilawan naton sang, testingan naton hin, probaran ta, i-test ang
   <item> sa <price>, i-promo natin: 3 Classic sa 110) and says an experiment is a changed
   price or offer on an item for some days, with or without the word test; change_price names
   gawin nating <price> ang <item> simula <date> and its ceb, hil, war and bcl forms (himoon
   nato nga, himuon naton nga, himoon naton nga, gibohon tang; sugod, umpisa, tikang, poon).
   A line on late-day cuts was drafted and taken out: it came from the spent half's markdowns,
   not the tune half. Threshold untouched (Q40).
5. **Fresh gate seeds for both gates**, written before any run of them and before the
   description edit: decider `GATE_*` lists (five per scenario and language, 270), router
   `FRESH_SEEDS` and `FRESH_CONTEXT` (five singles per agent with customer_service, two
   greetings, five follow-ups and five switches per gated language, 282). The run 1 gate halves
   are marked `spent` (decider: the odd seeds of `2049`; router: every earlier gate text of
   `2050`) and both harnesses never run them; shape tests check the three sets per language
   share no text.

Also in this round, from other tasks, at HEAD for both round 1 runs: the decider's coaching_who
now carries an item when one is named (b5ae07f); no case scores it.

### Decider, tune half after the round (`2119`)

| Language | n | Right | Wrong | Ask |
| --- | --- | --- | --- | --- |
| en | 45 | 97.8% | 0% | 2.2% |
| fil | 45 | 84.4% | 0% | 15.6% |
| ceb | 45 | 86.7% | 0% | 13.3% |
| hil | 45 | 82.2% | 0% | 17.8% |
| war | 45 | 86.7% | 0% | 13.3% |
| bcl | 45 | 88.9% | 0% | 11.1% |
| all | 270 | 87.8% | 0% | 12.2% |

Against `2048` (89.6%) the tune half did not improve: experiments stayed at 73.3% and 63.3%
right, short codes 73.3% (now the right code below 0.6 instead of no code, one wrong word
"bigyan" below 0.6), coaching lost two ("sin-o ang maayo magbaligya sang salted egg?" at 0.55
and 0.59).

### Decider gate, run 2 (`2120`, the fresh gate half, once)

| Language | n | Right | Wrong | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- |
| English (`en`) | 45 | 93.3% | 0% | 6.7% | pass |
| Filipino (`fil`) | 45 | 86.7% | 0% | 13.3% | pass |
| Cebuano (`ceb`) | 45 | **73.3%** | 0% | **26.7%** | **fail** |
| Hiligaynon (`hil`) | 45 | **77.8%** | 0% | **22.2%** | **fail** |
| Waray (`war`) | 45 | **64.4%** | 0% | **35.6%** | **fail** |
| Central Bikol (`bcl`) | 45 | **77.8%** | 2.2% | **20.0%** | **fail** |
| **Gated, all** | 270 | 78.9% | **0.4%** (bar <= 2%: pass) | 20.7% | **fail** |

| Scenario | Run 1 right | Run 2 right | Run 2 ask |
| --- | --- | --- | --- |
| coaching | 90.0% | 80.0% | 20.0% |
| how_to_sell | 93.3% | 93.3% | 6.7% |
| experiment_price | 63.3% | 73.3% | 26.7% |
| experiment_promo | 50.0% | 60.0% | 40.0% |
| change_price | 93.3% | 83.3% | 16.7% |
| short_code | 53.3% | 66.7% | 33.3% |
| weekly | 96.7% | 90.0% | 10.0% |
| monthly | 83.3% | 76.7% | 23.3% |
| keep | 100% | 86.7% | 10.0% (wrong 3.3%) |

- **The one wrong:** bcl "dai, pundohon na an bagong presyo" (no, stop the new price) read as
  keep at 0.66. A keep goes to the owner's own decision on the experiment, so it is a wrong
  money decision were it acted on; it is the first wrong in any decider gate run.
- **The short code fix worked on the slot:** 9 of 10 short code asks have the right code
  picked, below 0.6; one (war, "sx") has no code at 0.85 (run 1: 8 with no code).
- **Experiments, 20 asks,** all `propose_experiment` with the right item below 0.6; in two the
  price was "3" (the count of "3 kape for 65", en and ceb), so scored right they would not be.
  The strategy matched in 40 of 40 right experiments, the kind in 37.
- **Others:** monthly 7 ("ano ang mga best days natin ngayong buwan?" in five languages, "Oktubre
  sa numero"), coaching 6 ("ikumpara si Ana ug Pao", "who has been missing the target lately"),
  change_price 5 (three "bag-uha/usba ang kape sa 28 ... dili test" read as experiments below
  0.6), weekly 3, keep 3, how to sell 2. 49 of the 56 asks are Jev's right action below 0.6.

### Router gate, run 2 (`2121`, the fresh gate half, once)

| Language (gate half, no greetings) | n | Right | Wrong | Ask | Gate |
| --- | --- | --- | --- | --- | --- |
| en | 45 | 91.1% | 2.2% | 6.7% | pass |
| fil | 45 | 82.2% | 2.2% | **15.6%** | **fail** (ask) |
| ceb | 45 | 80.0% | 4.4% | 13.3% | pass (on the right bar) |
| hil | 45 | 84.4% | 4.4% | 8.9% | pass |
| war | 45 | **77.8%** | 4.4% | 13.3% | **fail** (right) |
| bcl | 45 | **68.9%** | 4.4% | **22.2%** | **fail** |
| **all (282, with greetings)** | 282 | 81.6% | **3.5%** | 12.8% | **fail** (wrong) |

Greetings 12 of 12 right. By agent (gate half): customer_service 100% (0% in run 1, unroutable),
bookkeeper 97.2%, shift_supervisor 90.7%, inventory_manager 81.0%, hr_officer 80.0%,
sales_supervisor 72.9%, branch_manager **36.7%** (wrong 26.7%, ask 36.7%). By group: singles
84.2%, follow-ups 80.0%, switches 63.3% (six "keep" of the active sales supervisor: "who covers
Ana tomorrow", "naubusan kita sang paper bag").

The ten wrongs: six are one seed, "who on my team is selling the most salted egg?", routed to
sales_supervisor at 0.85 to 1.0 in all six languages (who sells most of an item is a sales
number as much as coaching; the seed's expectation is arguable); two are the price test "29 ang
Kape sa duha ka semana" (ceb to inventory_manager 0.67, hil to sales_supervisor 0.77); one each
"karuyag ko mag-leave ha Biyernes" (war, shift_supervisor 0.61) and a follow-up "igwang welga kan
jeep" (bcl, a switch to shift_supervisor 0.68).

The new description on the tune half: the stub's twenty seeds went from 10.0% right on run 1's
gate half to 76.7% right on the tune half (60 rows, 0 wrong); the ten new seeds' tune half
60.0% right, 23.3% wrong. Whole tune half of the gated languages: 88.7% right, 1.8% wrong.

### Latency and tokens, round 1

| Run | Cases | Mean s | p95 s | Max s | Tokens | Per message |
| --- | --- | --- | --- | --- | --- | --- |
| decider tune (`2119`) | 270 | 0.39 | 0.45 | 1.03 | 1,108,888 | 4,106 |
| decider gate (`2120`) | 270 | 0.37 | 0.41 | 0.60 | 1,112,166 | 4,119 |
| router (`2121`, tune and fresh gate) | 1,274 | 0.36 | 0.41 | 1.23 | 1,280,741 | 1,005 |

The decider request grew about 165 tokens per message with the round's descriptions; the
router's about 65 with the longer description and the seventh agent. Round 1 used 3.5 million
tokens, at most $0.15 at the list price above.

### Reading, round 1

- **Wrong stays near zero in the decider (0.4%), but the asks did not fall.** The descriptions
  moved the tune half no further and the fresh gate's experiments, monthly and coaching
  phrasings land just under 0.6 in ceb, hil, war and bcl. A third description edit is unlikely
  to close a 10 to 20 point gap; the remaining levers are outside this task's rules (the
  threshold, Q40) or the Philippine drafts themselves (Q28 to Q35).
- **The router's wrong is now mostly one arguable seed.** Without "who on my team is selling the
  most salted egg?" the fresh gate half would be wrong 1.4% (4 of 276), with en, ceb and hil
  passing and fil (ask 15.9%), war (right 79.5%) and bcl still failing; the description change itself fixed the out-of-v1 subjects (76.7% on the
  tune half) and customer_service routes at 100%.
- **Stopped here,** as decided: both gates are reported failing after the one round.

Under D40 (21 Oct 2026) this run reads: ceb, en, fil and hil pass; bcl fails (wrong 2.2%, above 2%), war fails (right 64% below 65%, ask 36% above 30%). Computed from the relaxed-bar table in docs/research/2026-10-21-q40-threshold-study.md; no rerun, the numbers and verdict above stand.
