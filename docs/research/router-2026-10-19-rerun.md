# Jev agent router evaluation on a fresh gate half (19 Oct 2026, rerun)

Spec docs/superpowers/specs/2026-10-18-router-follow-up-design.md (decision 1, second
paragraph, and "Carried over"), the owner's assumptions in docs/questions.md Q40. Follows
docs/research/router-2026-10-19.md, whose gate half is spent and now part of the tune half.
Synthetic data only (D18). Raw results: `router-2026-10-19-0341.raw.json` (run 1, the Q40
rules and descriptions as committed) and `router-2026-10-19-0345.raw.json` (run 2, after one
tuning edit on the tune half). The harness names the files by local time and never overwrites.
This report has the `-rerun` suffix because `router-2026-10-19.md` exists.

**Result: the gate fails.** Run 2, gate half, six gated languages: wrong agent at >= 0.6 is
2.2% (bar at most 2%: fail by four cases in 504); right per language (greetings left out) 73.8%
to 90.0% (bar at least 80%: only English passes); ask 7.5% to 18.8% (bar at most 15%: fil, war
and bcl fail). Two runs were allowed; this is the second.

## What changed since the first 19 Oct run

- **Q40 rule 1, the branch manager owns adding people.** HR's description says "not adding
  people to a branch"; the branch manager keeps "people and their roles".
- **Q40 rule 2, ask instead of keep.** With an agent active, Jev's top pick of another agent
  below 0.6 now asks with buttons (`chat/agent_router.decide`); a tap switches with the notice
  and `chat.agent_switched`. `unclear` at any confidence still keeps the active agent.
- **The bookkeeper owns a cash drawer short or over** (description).
- **The bar** (Q40): wrong at most 2% over every gate-half row of the gated languages (hard);
  per gated language, right at least 80% and ask at most 15% with the greetings and thanks
  (`any`) left out and reported apart.
- **A fresh gate half.** 64 new English seeds, written before any result was seen, with the
  same agent mix (10 per agent and 4 `any`), none reused from the old file, drafted in the nine
  other languages (Q28 to Q35 cover the review). The half is assigned by seed, so every
  language of a seed falls in one half. The gate half's follow-ups and switches have their own
  texts (13 context seeds, 7 replies and 3 new Mia questions per gated language), so no text
  is in two groups of the gate half. An offline test checks that no text (casefolded) is in
  both halves. The old seeds, follow-ups and switches (the spent gate half included) are the
  tune half. Finnish intent rows alternate tune and gate by row.

Route memory is not exercised by this eval: the harness calls `build_request` and `decide`
directly, so a learned key never routes and no tap is taken. Every ask counted here would, in
the chat, show buttons once, and a repeated message would route by memory after two taps.

## Setup

Model `jev-1.13.0`, threshold 0.6, egress level `pseudonymised`, concurrency 4. 1823 cases:
912 tune, 911 gate; per gated language and half 64 single, 10 follow-up, 10 switch. 0 errors
in both runs, each about 170 s for the module (the router test and the deferral test).

## The tuning edit (once, from run 1's tune half only)

Run 1's tune-half misses: corrections ("sorry, 4 special not 3") kept by the shift supervisor
with it active (6 of 6 languages) or asked; a morning sales total ("total ng umaga 1,450") to
the bookkeeper; "best day this month" to the shift supervisor (wrong at 0.61 to 0.80 in five
languages); Grab payouts to HR; leftovers and waste ("salin", "gilabay") and "a broken oven",
"brownout" asked or routed between shift and inventory; "add a new item" to inventory. Edits:

- sales supervisor: "corrections to a reported count (sorry, 4 special not 3), daily, morning
  and mid-day sales totals, ..., the best day";
- shift supervisor: "problems at a site or the shop (a broken oven, a power cut)" and "not a
  correction of a sales count, not the best sales day";
- inventory manager: "leftovers (trays left over) and waste (items thrown away)";
- bookkeeper: "Grab payouts" and "not a morning's or day's sales total";
- branch manager: "the menu and new menu items".

Contrast lines kept; `test_router_descriptions_carry_a_contrast_line` passes. Case set,
scoring, threshold and the bar were not touched.

| Gated languages | Run 1 right (no greetings) | Run 1 wrong | Run 1 ask | Run 2 right | Run 2 wrong | Run 2 ask |
| --- | --- | --- | --- | --- | --- | --- |
| tune half (504) | 77.7% | 1.6% | 18.3% | 90.0% | 0.4% | 9.0% |
| gate half (504) | 75.0% | **3.0%** | 16.7% | 78.5% | **2.2%** | 14.4% |

As on 18 and 19 Oct, the edit moved the tune half much more than the gate half (+12.3 against
+3.5 points right), but the gate half moved the right way this time on every measure.

## Gate (gate half, run 2)

Right, ask, small talk and missed switch are over the 80 non-greeting rows per language;
wrong for the gate is over all 504 rows.

| Language | n | Right | Wrong | Ask | Small talk (miss) | Missed switch (kept) | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| English (`en`) | 80 | 90.0% | 0% | 7.5% | 1.2% | 1.2% | pass |
| Filipino (`fil`) | 80 | 77.5% | 1.2% | 16.2% | 1.2% | 3.8% | fail (right, ask) |
| Cebuano (`ceb`) | 80 | 76.2% | 3.8% | 15.0% | 1.2% | 3.8% | fail (right) |
| Hiligaynon (`hil`) | 80 | 78.8% | 2.5% | 11.2% | 1.2% | 6.2% | fail (right) |
| Waray (`war`) | 80 | 73.8% | 2.5% | 18.8% | 1.2% | 3.8% | fail (right, ask) |
| Central Bikol (`bcl`) | 80 | 75.0% | 3.8% | 17.5% | 0% | 3.8% | fail (right, ask) |
| **Gated, all 504** | 504 | 79.4% | **2.2%** (bar <= 2%: fail) | 13.9% | 1.0% | | |

Greetings and thanks, gate half, gated languages (reported apart): 24 cases, 95.8% right,
4.2% ask (run 1 the same).

| Run 1, gate half | n | Right | Wrong | Ask | Small talk | Missed switch |
| --- | --- | --- | --- | --- | --- | --- |
| en | 80 | 86.2% | 1.2% | 8.8% | 1.2% | 2.5% |
| fil | 80 | 73.8% | 2.5% | 18.8% | 1.2% | 3.8% |
| ceb | 80 | 73.8% | 3.8% | 17.5% | 1.2% | 3.8% |
| hil | 80 | 72.5% | 2.5% | 17.5% | 1.2% | 6.2% |
| war | 80 | 70.0% | 3.8% | 20.0% | 1.2% | 5.0% |
| bcl | 80 | 73.8% | 5.0% | 17.5% | 0% | 3.8% |

## Tuning half (run 2)

| Language | n | Right | Wrong | Ask | Small talk | Missed switch |
| --- | --- | --- | --- | --- | --- | --- |
| en | 80 | 95.0% | 0% | 3.8% | 1.2% | 0% |
| fil | 80 | 92.5% | 0% | 7.5% | 0% | 0% |
| ceb | 80 | 87.5% | 0% | 12.5% | 0% | 0% |
| hil | 80 | 93.8% | 0% | 5.0% | 0% | 1.2% |
| war | 80 | 83.8% | 1.2% | 13.8% | 0% | 1.2% |
| bcl | 80 | 87.5% | 1.2% | 11.2% | 0% | 0% |

## Reported languages (both halves, run 2)

| Language | n | Right | Wrong | Ask | Small talk |
| --- | --- | --- | --- | --- | --- |
| Finnish (`fi`) | 431 | 73.5% | 0.9% | 21.3% | 4.2% |
| Ilocano (`ilo`) | 128 | 60.9% | 4.7% | 33.6% | 0.8% |
| Kapampangan (`pam`) | 128 | 71.9% | 1.6% | 25.0% | 1.6% |
| Pangasinan (`pag`) | 128 | 66.4% | 3.9% | 27.3% | 2.3% |
| **All 1823** | 1823 | 78.3% | 1.6% | 17.3% | 1.6% |

By expected agent (both halves, all languages, run 2): hr officer 96.0%, bookkeeper 94.2%,
shift supervisor 82.8%, any 78.2%, branch manager 76.0%, inventory manager 68.7%, sales
supervisor 57.4% (ask 35.1%). Groups: follow_up 88.3%, single 77.9%, switch 74.2%.

## The Q40 rules, one line each

- **Branch manager owns adding people:** "add a new clerk named Carlo to the street stall"
  went to HR 0 times in 10 languages (2 right, 8 asks, 6 of them with branch manager as Jev's
  pick), against 8 HR routes of "add Maria as a clerk" on 19 Oct. "Make Liza a supervisor"
  went to HR 0 times; 6 of 10 ask with the shift supervisor as the low pick. The rule removed
  the wrong routes but left the cases as asks, not right.
- **Ask instead of keep:** in the gate half, gated languages, 12 of 120 context cases asked
  under the new rule (run 2); under the old rule all 12 would have kept the active agent, a
  silent missed switch. In 8 of the 12 Jev's low pick was the right agent, so one tap answers
  it (7 sales reports while the shift supervisor was active). 18 context cases still kept the
  wrong agent: Jev picked the active agent or `unclear`, which the rule leaves alone. Run 1:
  12 asks (5 with the right pick), 20 kept. The rule turns missed switches into asks; it does
  not cut wrong routes, and it adds to the ask rate.
- **Bookkeeper owns a drawer short or over:** "the drawer is over by 80" and "the cash is 200
  less than the sales" were right in all 10 languages in both runs (20 of 20).
- **The bar:** wrong 2.2% fails the hard 2% by four cases; right at least 80% is met only in
  English; ask at most 15% fails in fil, war and bcl.

## Wrong routes (all 11 at >= 0.6, gate half, gated languages, run 2)

| Lang | Group | Message | Expected | Routed | Conf. |
| --- | --- | --- | --- | --- | --- |
| hil | single | sin-o ang mabuksan sang kiosk sa Lunes? | shift | branch | 0.96 |
| bcl | single | siisay an mabukas kan kiosk sa Lunes? | shift | branch | 0.96 |
| war | single | hin-o an magbubukas han kiosk ha Lunes? | shift | branch | 0.92 |
| bcl | single | gibuhon na 6 an ube, bako 5 | sales | inventory | 0.85 |
| war | follow_up | hilom an mall, ha sunod nga semana pa an sweldo | sales | hr | 0.82 |
| bcl | follow_up | tahimik an mall, sa masunod na semana pa an sweldo | sales | hr | 0.80 |
| ceb | single | pwede ba ta moabli og alas 8 kada Sabado? | branch | shift | 0.77 |
| fil | single | end of day count: 11 special 8 classic 5 salted egg | sales | inventory | 0.71 |
| ceb | single | end of day count: 11 special 8 classic 5 salted egg | sales | inventory | 0.69 |
| ceb | single | nabayran na ang kuryente, 3,400 | bookkeeper | shift | 0.65 |
| hil | follow_up | hilway ang mall, sa masunod nga semana pa ang sweldo | sales | hr | 0.61 |

Run 1 had 15, the same message types plus "make that 6 ube, not 5" (en, fil, ceb, hil) to
inventory, "which item sold best this week" (ceb) to inventory and "gibuhon na supervisor si
Liza" to the shift supervisor.

## Latency, tokens, cost

Run 2: p50 0.37 s, p95 0.43 s (highest language p95 0.69 s, Hiligaynon). 954 tokens per
message on average (run 1: 879; the tuned descriptions add about 75), about 1.74 million for
the run; at TypeSafe's $0.042 per million input tokens about $0.07, $0.00004 per message.

## Reading

- **Closer, still short.** Gate-half wrong fell from 6.7% (19 Oct) to 3.0% (run 1) and 2.2%
  (run 2); right rose from 69.8% to 78.5% (no greetings). The fresh half and the Q40 rules
  made the bar reachable in English only.
- **The remaining wrong routes are new seams, not the old ones.** Who opens the kiosk on a
  weekday reads as shop hours (branch manager) in three languages; "open at 8 on Saturdays"
  reads the other way. A correction of a count ("6 ube, not 5") and an end-of-day count read
  as stock. A reply about payday in a sales follow-up goes to HR because of "sweldo". None of
  these was in the tune half, so a description edit for them would be fitting the gate half.
- **Ask is the cost of Q40.** The rule trades silent keeps for buttons; with memory a repeated
  message stops asking after two taps, which this eval does not show.

## What remains

1. The gate is not met; this gate half is now spent as well. A next pass needs another fresh
   half, and the clearest fixes are rules in code (rule 7), not more wording: a count with a
   correction word, or with only item words and numbers, is the sales supervisor's when it is
   one of the person's agents, before Jev.
2. Opening times: "who opens" (a shift) against "what time do we open" (shop hours) needs a
   contrast line, measured on fresh data.
3. Finnish, Ilocano, Kapampangan and Pangasinan stay reported only.
