# Jev hr officer decider evaluation (19 Oct 2026)

Spec docs/superpowers/specs/2026-10-19-hr-officer-design.md (sections 4 and 10). Question:
does Jev pick the right hr action, with the right leave dates, holiday day and contribution,
from what Ferino's clerks, head staff and owner send? Synthetic data only (D18). Raw results:
`hr-officer-2026-10-19-0753.raw.json` (run 1, the committed descriptions) and
`hr-officer-2026-10-19-0755.raw.json` (run 2, after one tuning edit on the tune half).

**Result: the gate passes.** Run 2, gate half, six gated languages (300 cases), against the
Q40 bar (`tests/evals/gate.py`): wrong at >= 0.6 is 0.0% (bar at most 2%: pass); right 90% to
94% per language (bar at least 80%: all pass); ask 6% to 10% (bar at most 15%: all pass). No
errors. Run 1 failed (hil right 78%; hil, war and bcl ask 20%, 20% and 16%). Two runs were
allowed; this is the second.

**Do not tune on this gate half again.** Its texts were scored in two runs and its misses are
listed below; the next rerun needs a fresh gate half (new seeds).

## Setup

Model `jev-1.13.0`, threshold 0.6, egress level `pseudonymised`, concurrency 4, Ferino's
seeded per run (`MIA_ORG=ferinos`), `build_query` for the case's sender, `decider.decide`
inside `egress_context`. Today is pinned to `TODAY` (Monday 14 Dec 2026) so weekday phrases
resolve the same on every run and Christmas is inside the fourteen days (h0..h13) a holiday
question picks from. 600 cases per run (300 tune, 300 gate), 0 errors, 58 s and 57 s of wall
time.

Scoring: **right** is the expected action with every expected input (for `file_leave` the ISO
start and end, for `holiday_pay` the day, for `contributions` the `which`); **wrong** is
another input value, or another action at >= 0.6; **ask** is clarify or a missing input;
**other** is an error or another action below 0.6.

## Case set

`node/tests/evals/hr_officer_cases.py`: ten scenarios (my_hours, payday, thirteenth,
contributions, file_leave, leave_balance, holiday_pay, my_payslip, certificate, reply_only
greetings and thanks) times ten seeds times six languages (en, fil, ceb, hil, war, bcl). Seed n
is one message in every language; even seeds are the tune half, odd seeds the gate half, so no
text is in both. Senders: clerk Ana, supervisor Marites for two hours seeds (8 and 9), owner
Rosa for the certificates. English seeds first; the other five are drafts by Claude, not native
speakers (review: Q28 to Q35). Dates are written as clerks write them ("next week Monday to
Wednesday", "sa susunod na linggo Lunes", "Dec 21 to Dec 23", "bukas", "ugma", "sa Martes").
`find_dates` reads no "today" or "tomorrow" word in hil, war or bcl and no "next week" in ceb,
hil, war or bcl, so those leave messages name the weekday or the date; the offline shape test
(`test_hr_cases.py`) checks that every expected leave date is a `find_dates` candidate and
every holiday day is within h0..h13.

## The tuning edit (once, from run 1's tune half only)

Run 1's tune-half misses: leave balance questions read as leave requests ("natitirang sick
leave ko", "pila pa ka adlaw ko pwede mo-leave": `file_leave` with no date, so asked, 11 of
30); "Pasko" and "Bisperas" with no day picked (6); "next week Friday" in ceb, war, bcl as this
Friday (3 wrong); "kanus-a / san-o / nuarin ang sweldo" below 0.6 (5); "pa-file VL", "absent",
"rest on Tuesday" below 0.6 (8); "maupay nga kulop", "uy", "oy" asked. Edits in
`agents/hr_officer/actions.py`: the my_hours, payday, file_leave, leave_balance and reply_only
descriptions name the words the tune half uses (ilang oras, pila ka oras; kailan, kanus-a,
san-o, nuarin; VL, SL, pa-file, pahinga, pahulay, pahuway, pahingalo; natitira, nabilin,
natada, leave credits, SIL, "names no day or date"; greetings in any language); the `day`
question says Christmas is 25 December, Christmas Eve 24 December, and "next week" with a
weekday is the following week. Case set, scoring and threshold were not touched.

| Half, gated languages (n 300) | Run 1 right | Run 1 wrong | Run 1 ask | Run 2 right | Run 2 wrong | Run 2 ask |
| --- | --- | --- | --- | --- | --- | --- |
| tune | 85.0% | 1.0% | 14.0% | 92.0% | 1.3% | 6.7% |
| gate | 86.0% | 0.3% | 13.7% | 91.7% | **0.0%** | 8.3% |

## Gate (gate half, run 2)

| Language | n | Right | Wrong | Ask | Gate (right >= 80%, ask <= 15%) |
| --- | --- | --- | --- | --- | --- |
| English (`en`) | 50 | 94% | 0% | 6% | pass |
| Filipino (`fil`) | 50 | 94% | 0% | 6% | pass |
| Cebuano (`ceb`) | 50 | 92% | 0% | 8% | pass |
| Hiligaynon (`hil`) | 50 | 90% | 0% | 10% | pass |
| Waray (`war`) | 50 | 90% | 0% | 10% | pass |
| Central Bikol (`bcl`) | 50 | 90% | 0% | 10% | pass |
| **Gated, all** | 300 | 91.7% | **0.0%** (bar <= 2%: pass) | 8.3% | |

| Scenario (gate half) | n | Run 1 right | Run 2 right | Run 2 wrong | Run 2 ask |
| --- | --- | --- | --- | --- | --- |
| my_hours | 30 | 93.3% | 93.3% | 0% | 6.7% |
| payday | 30 | 73.3% | 96.7% | 0% | 3.3% |
| thirteenth | 30 | 100% | 100% | 0% | 0% |
| contributions | 30 | 96.7% | 96.7% | 0% | 3.3% |
| **file_leave** | 30 | 60.0% | **63.3%** | 0% | **36.7%** |
| leave_balance | 30 | 60.0% | 90.0% | 0% | 10.0% |
| holiday_pay | 30 | 86.7% | 86.7% | 0% | 13.3% |
| my_payslip | 30 | 100% | 100% | 0% | 0% |
| certificate | 30 | 100% | 100% | 0% | 0% |
| reply_only | 30 | 90.0% | 90.0% | 0% | 10.0% |

| Run 1, gate half | n | Right | Wrong | Ask |
| --- | --- | --- | --- | --- |
| en | 50 | 96% | 0% | 4% |
| fil | 50 | 92% | 0% | 8% |
| ceb | 50 | 86% | 0% | 14% |
| hil | 50 | 78% | 2% | 20% |
| war | 50 | 80% | 0% | 20% |
| bcl | 50 | 84% | 0% | 16% |

## Tune half (run 2)

| Language | n | Right | Wrong | Ask |
| --- | --- | --- | --- | --- |
| en | 50 | 98% | 0% | 2% |
| fil | 50 | 92% | 0% | 8% |
| ceb | 50 | 94% | 2% | 4% |
| hil | 50 | 90% | 2% | 8% |
| war | 50 | 90% | 2% | 8% |
| bcl | 50 | 88% | 2% | 10% |

The four tune wrongs are one seed: "holiday ba ang Biyernes sa sunod semana?" (ceb, hil, war,
bcl) answered with this Friday (18 Dec) at 0.71 to 0.91, not next week's (25 Dec). The `day`
wording did not move it.

## Top ten confusions (run 2, both halves, 600 cases)

The harness does not record Jev's top pick under a clarify; it is read from the inputs the
clarify carries.

| Count | Expected | Got | Score |
| --- | --- | --- | --- |
| 16 | file_leave | clarify, top pick file_leave (right dates, below 0.6) | ask |
| 9 | my_hours | clarify, top pick my_hours | ask |
| 7 | holiday_pay | clarify, top pick holiday_pay (4 with no day: "buwas", "sa aga", "Pasko") | ask |
| 6 | reply_only | clarify, top pick reply_only ("salamat gid", "salamat tabi", "uy") | ask |
| 4 | leave_balance | clarify, top pick file_leave with no date ("may vacation leave pa ba ako") | ask |
| 4 | holiday_pay | holiday_pay, this Friday for "Biyernes sa sunod semana" | wrong |
| 1 | payday | clarify ("kanus-a ta bayran") | ask |
| 1 | contributions | clarify, top pick contributions ("pira an akon share ha Pagibig") | ask |
| 1 | leave_balance | clarify ("pila pa akong leave?") | ask |

## Latency, tokens, cost

Wall time 58 s (run 1) and 57 s (run 2) for 600 requests at concurrency 4, about 0.38 s per
request on average. This harness does not yet record per-case seconds or the usage rows' tokens
(the inventory harness does); the request is the same shape as the inventory decider's (about
3,800 tokens per message there), so a 600-case run is roughly 2.3 million tokens and, at
TypeSafe's $0.042 per million input tokens, about $0.10. That is an estimate, not a measure.

## Reading

- **No harmful write on the gate half.** The only write action is `file_leave`, and every
  leave Jev picked had the right start and end; its misses are all asks, and the leave still
  goes to head staff for approval after a tap.
- **Leave requests are the ask cost.** `file_leave` is 63% right on the gate half, every miss
  a clarify whose top pick is `file_leave` with the right dates below 0.6 ("sick today, I
  can't come in", "please file a leave for me next week Tuesday", "i-file akong leave sa Dec
  22"). In the chat that is a "Did you mean" tap, not a wrong answer. The leave kind and the
  date slots carry their own confidence into the action's; a lower bar for a write that is
  approved anyway is a decision for the owner of the threshold, not a tuning step.
- **Words code could resolve.** "next week" with a weekday in ceb, hil, war and bcl, and
  "buwas", "sa aga", "subong", "yana", "ngunyan" are not in `parsing.find_dates`; Jev guesses
  them from h0..h13 (the four wrongs and four of the holiday asks). By rule 7 these belong in
  `NEXT_WEEK` and `DAY_WORDS`, so the day is code's, not the model's.
- **Balance versus request** improved most from the edit (leave_balance 60% to 90% on the gate
  half): "names no day or date" separates them.

## What remains

- **Do not tune on this gate half again.** A next rerun needs fresh gate seeds.
- Add the ceb, hil, war and bcl "next week" and today or tomorrow words to `find_dates`, and let
  code resolve the holiday day from them.
- Record per-case seconds, Jev's top pick (`raw_action`) and the usage tokens in this harness,
  as the inventory harness does.
- The non-English messages are drafts (Q28 to Q35).

## Router

The router gate was not rerun. The hr officer already has router cases (20 references in
`router_cases.py`), `PENDING` is empty, and its router description has not changed since the
last router rerun (docs/research/router-2026-10-19-rerun.md). Nothing was added to
`router_cases.py`.
