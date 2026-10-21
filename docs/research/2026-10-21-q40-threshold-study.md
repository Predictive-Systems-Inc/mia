# Q40 threshold study: what the failed gates read at other decider bars

Date: 21 October 2026. Input: the latest recorded gate half of every agent under docs/research
(the raw json rows hold Jev's top pick `raw_action` and its `confidence`). No model call was made
and no gate half was rerun: an ask that was only a confidence ask (no missing slot) is rescored
as right when the top pick equals the expected action at or above the bar, as wrong when it
differs, and a slot ask stays an ask. Script: the session scratchpad `q40_study.py` (eighteen
lines of scoring; kept out of the repository on purpose, the gate harness stays the only scorer).

## Reading

- Lowering the decider threshold trades asks for wrongs, and the wrongs cross the 2 percent line
  before the asks reach 15 percent in almost every regional language. Only two agents pass all
  six languages at a lower bar: customer_service at 0.5 and 0.45, hr_officer at every bar (its
  asks are slot asks, not confidence asks).
- The asks in the regional languages are mostly the right action below 0.6 (the earlier gate
  reports say the same): Jev is less sure on machine-drafted text, not systematically wrong.
- A bar of 0.5 is the only lowering worth considering, and only for customer_service (6 of 6)
  and the bookkeeper (4 of 6). For the sales supervisor, the inventory manager, the branch
  manager, the production planner and the retail shift supervisor no bar passes the Q40 line
  in the regional languages; the lever there is native drafts (Q28 to Q35), not the threshold.
- The retail shift supervisor is the hardest set (many actions, a shared agent): at 0.6 its
  regional languages sit at 52 to 65 percent right with 32 to 43 percent asks.

## A relaxed bar for machine-drafted languages (the Q40 proposal)

Keep wrong at most 2 percent everywhere (a wrong write is the harm; the rule 7 guards make the
remaining wrongs asks). For a language whose strings are machine drafts (Q28 to Q35), accept
right at least 65 percent and ask at most 30 percent until a native review lands; en and fil
keep the full bar. At the current threshold 0.6 that reads:

| agent | gate file | passing | failing (wrong / right / ask) |
|---|---|---|---|
| bookkeeper | bookkeeper-2026-10-21-0054.raw.json | bcl, ceb, en, war | fil (0.0% / 84% / 16%), hil (3.6% / 76% / 20%) |
| branch-manager | branch-manager-2026-10-20-2120.raw.json | ceb, en, fil, hil | bcl (2.2% / 78% / 20%), war (0.0% / 64% / 36%) |
| customer-service | customer-service-2026-10-20-0142.raw.json | bcl, ceb, en, fil, hil, war | none |
| hr-officer | hr-officer-2026-10-19-0755.raw.json | bcl, ceb, en, fil, hil, war | none |
| inventory-manager | inventory-manager-2026-10-19-0656.raw.json | bcl, en, hil, war | ceb (1.0% / 62% / 37%), fil (0.0% / 79% / 19%) |
| production-planner | production-planner-2026-10-21-0748.raw.json | en, war | bcl (4.0% / 68% / 28%), ceb (6.0% / 66% / 28%), fil (0.0% / 78% / 22%), hil (2.0% / 62% / 36%) |
| sales-supervisor | sales-supervisor-2026-10-19-0353.raw.json | bcl, ceb, en | fil (1.1% / 82% / 17%), hil (3.3% / 72% / 24%), war (3.3% / 71% / 26%) |
| shift-supervisor-retail | shift-supervisor-retail-2026-10-21-0306.raw.json | none | bcl (1.3% / 56% / 43%), ceb (4.0% / 60% / 36%), en (1.3% / 80% / 19%), fil (4.0% / 72% / 24%), hil (2.7% / 65% / 32%), war (5.3% / 52% / 43%) |

Under that bar customer_service and hr_officer pass; the bookkeeper, branch manager, inventory
manager and sales supervisor each miss on two or three languages by a few points; the production
planner and the retail shift supervisor miss on most. The retail shift supervisor's wrongs above
2 percent in four languages are the ones the fix wave turned into asks in code (the rule 7
guards landed after the gate run), so its next fresh-seed run should read lower on wrong.

## What a rerun needs

Every recorded half is spent. A rerun of any gate needs a fresh eval set (new seeds, new texts,
the same shape tests), the developer's word (Q40), and for the regional languages a native
review of the drafts first, or the rerun will read the same.

## Full tables (right / wrong / ask per language; "ok" marks the Q40 bar)

### bookkeeper (bookkeeper-2026-10-21-0054.raw.json, 330 gate rows)

| bar | bcl | ceb | en | fil | hil | war | languages passing |
|---|---|---|---|---|---|---|---|
| 0.6 | 91% / 0% / 9% ok | 80% / 2% / 18% | 96% / 0% / 4% ok | 84% / 0% / 16% | 76% / 4% / 20% | 82% / 0% / 18% | 2 of 6 |
| 0.5 | 91% / 0% / 9% ok | 82% / 2% / 16% | 98% / 0% / 2% ok | 89% / 0% / 11% ok | 84% / 4% / 13% | 85% / 0% / 15% ok | 4 of 6 |
| 0.45 | 95% / 0% / 5% ok | 84% / 2% / 15% ok | 98% / 0% / 2% ok | 93% / 0% / 7% ok | 87% / 4% / 9% | 89% / 2% / 9% ok | 5 of 6 |
| 0.4 | 96% / 0% / 4% ok | 84% / 4% / 13% | 100% / 0% / 0% ok | 95% / 2% / 4% ok | 87% / 5% / 7% | 89% / 2% / 9% ok | 4 of 6 |
| 0.35 | 96% / 0% / 4% ok | 89% / 4% / 7% | 100% / 0% / 0% ok | 96% / 2% / 2% ok | 91% / 5% / 4% | 91% / 2% / 7% ok | 4 of 6 |
| 0.3 | 96% / 2% / 2% ok | 93% / 5% / 2% | 100% / 0% / 0% ok | 96% / 4% / 0% | 93% / 5% / 2% | 93% / 4% / 4% | 2 of 6 |

### branch-manager (branch-manager-2026-10-20-2120.raw.json, 270 gate rows)

| bar | bcl | ceb | en | fil | hil | war | languages passing |
|---|---|---|---|---|---|---|---|
| 0.6 | 78% / 2% / 20% | 73% / 0% / 27% | 93% / 0% / 7% ok | 87% / 0% / 13% ok | 78% / 0% / 22% | 64% / 0% / 36% | 2 of 6 |
| 0.5 | 84% / 2% / 13% | 80% / 2% / 18% | 96% / 0% / 4% ok | 89% / 0% / 11% ok | 87% / 0% / 13% ok | 73% / 0% / 27% | 3 of 6 |
| 0.45 | 87% / 2% / 11% | 87% / 2% / 11% | 96% / 0% / 4% ok | 93% / 0% / 7% ok | 87% / 2% / 11% | 80% / 2% / 18% | 2 of 6 |
| 0.4 | 89% / 2% / 9% | 89% / 2% / 9% | 96% / 2% / 2% | 96% / 0% / 4% ok | 89% / 2% / 9% | 82% / 2% / 16% | 1 of 6 |
| 0.35 | 91% / 2% / 7% | 91% / 2% / 7% | 96% / 2% / 2% | 96% / 0% / 4% ok | 89% / 2% / 9% | 89% / 4% / 7% | 1 of 6 |
| 0.3 | 93% / 2% / 4% | 93% / 2% / 4% | 98% / 2% / 0% | 96% / 2% / 2% | 98% / 2% / 0% | 89% / 4% / 7% | 0 of 6 |

### customer-service (customer-service-2026-10-20-0142.raw.json, 240 gate rows)

| bar | bcl | ceb | en | fil | hil | war | languages passing |
|---|---|---|---|---|---|---|---|
| 0.6 | 90% / 0% / 10% ok | 85% / 0% / 15% ok | 98% / 0% / 2% ok | 90% / 0% / 10% ok | 85% / 0% / 15% ok | 82% / 0% / 18% | 5 of 6 |
| 0.5 | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 98% / 0% / 2% ok | 92% / 0% / 8% ok | 85% / 0% / 15% ok | 85% / 0% / 15% ok | 6 of 6 |
| 0.45 | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 100% / 0% / 0% ok | 92% / 0% / 8% ok | 90% / 0% / 10% ok | 85% / 0% / 15% ok | 6 of 6 |
| 0.4 | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 100% / 0% / 0% ok | 92% / 0% / 8% ok | 90% / 0% / 10% ok | 85% / 2% / 12% | 5 of 6 |
| 0.35 | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 100% / 0% / 0% ok | 92% / 0% / 8% ok | 90% / 0% / 10% ok | 85% / 2% / 12% | 5 of 6 |
| 0.3 | 90% / 2% / 8% | 90% / 2% / 8% | 100% / 0% / 0% ok | 95% / 2% / 2% | 92% / 2% / 5% | 85% / 5% / 10% | 1 of 6 |

### hr-officer (hr-officer-2026-10-19-0755.raw.json, 300 gate rows)

| bar | bcl | ceb | en | fil | hil | war | languages passing |
|---|---|---|---|---|---|---|---|
| 0.6 | 90% / 0% / 10% ok | 92% / 0% / 8% ok | 94% / 0% / 6% ok | 94% / 0% / 6% ok | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 6 of 6 |
| 0.5 | 90% / 0% / 10% ok | 92% / 0% / 8% ok | 94% / 0% / 6% ok | 94% / 0% / 6% ok | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 6 of 6 |
| 0.45 | 90% / 0% / 10% ok | 92% / 0% / 8% ok | 94% / 0% / 6% ok | 94% / 0% / 6% ok | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 6 of 6 |
| 0.4 | 90% / 0% / 10% ok | 92% / 0% / 8% ok | 94% / 0% / 6% ok | 94% / 0% / 6% ok | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 6 of 6 |
| 0.35 | 90% / 0% / 10% ok | 92% / 0% / 8% ok | 94% / 0% / 6% ok | 94% / 0% / 6% ok | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 6 of 6 |
| 0.3 | 90% / 0% / 10% ok | 92% / 0% / 8% ok | 94% / 0% / 6% ok | 94% / 0% / 6% ok | 90% / 0% / 10% ok | 90% / 0% / 10% ok | 6 of 6 |

### inventory-manager (inventory-manager-2026-10-19-0656.raw.json, 600 gate rows)

| bar | bcl | ceb | en | fil | hil | war | languages passing |
|---|---|---|---|---|---|---|---|
| 0.6 | 73% / 1% / 25% | 62% / 1% / 37% | 92% / 0% / 8% ok | 79% / 0% / 19% | 74% / 0% / 25% | 70% / 0% / 29% | 1 of 6 |
| 0.5 | 80% / 1% / 18% | 68% / 1% / 31% | 93% / 0% / 7% ok | 83% / 0% / 15% ok | 80% / 0% / 19% | 76% / 0% / 23% | 2 of 6 |
| 0.45 | 82% / 1% / 16% | 70% / 1% / 29% | 94% / 1% / 5% ok | 83% / 0% / 15% ok | 82% / 0% / 17% | 79% / 1% / 19% | 2 of 6 |
| 0.4 | 85% / 1% / 13% ok | 72% / 3% / 25% | 94% / 1% / 5% ok | 84% / 0% / 14% ok | 86% / 0% / 13% ok | 79% / 2% / 18% | 4 of 6 |
| 0.35 | 87% / 1% / 11% ok | 74% / 5% / 21% | 94% / 1% / 5% ok | 84% / 0% / 14% ok | 87% / 1% / 11% ok | 81% / 5% / 13% | 4 of 6 |
| 0.3 | 87% / 3% / 9% | 76% / 6% / 18% | 94% / 2% / 4% ok | 86% / 0% / 12% ok | 88% / 1% / 10% ok | 83% / 5% / 11% | 3 of 6 |

### production-planner (production-planner-2026-10-21-0748.raw.json, 300 gate rows)

| bar | bcl | ceb | en | fil | hil | war | languages passing |
|---|---|---|---|---|---|---|---|
| 0.6 | 68% / 4% / 28% | 66% / 6% / 28% | 86% / 2% / 12% ok | 78% / 0% / 22% | 62% / 2% / 36% | 78% / 2% / 20% | 1 of 6 |
| 0.5 | 76% / 4% / 20% | 72% / 6% / 22% | 86% / 4% / 10% | 80% / 2% / 18% | 70% / 2% / 28% | 82% / 2% / 16% | 0 of 6 |
| 0.45 | 80% / 4% / 16% | 74% / 6% / 20% | 88% / 4% / 8% | 82% / 2% / 16% | 70% / 2% / 28% | 86% / 4% / 10% | 0 of 6 |
| 0.4 | 82% / 6% / 12% | 74% / 8% / 18% | 88% / 4% / 8% | 86% / 2% / 12% ok | 74% / 4% / 22% | 88% / 4% / 8% | 1 of 6 |
| 0.35 | 82% / 8% / 10% | 82% / 10% / 8% | 90% / 4% / 6% | 90% / 2% / 8% ok | 74% / 4% / 22% | 90% / 4% / 6% | 1 of 6 |
| 0.3 | 84% / 8% / 8% | 82% / 14% / 4% | 92% / 6% / 2% | 90% / 4% / 6% | 80% / 6% / 14% | 90% / 4% / 6% | 0 of 6 |

### sales-supervisor (sales-supervisor-2026-10-19-0353.raw.json, 540 gate rows)

| bar | bcl | ceb | en | fil | hil | war | languages passing |
|---|---|---|---|---|---|---|---|
| 0.6 | 74% / 1% / 24% | 76% / 1% / 23% | 93% / 1% / 6% ok | 82% / 1% / 17% | 72% / 3% / 24% | 71% / 3% / 26% | 1 of 6 |
| 0.5 | 79% / 2% / 19% | 81% / 4% / 14% | 96% / 1% / 3% ok | 86% / 1% / 13% ok | 79% / 4% / 17% | 81% / 7% / 12% | 2 of 6 |
| 0.45 | 83% / 2% / 14% | 86% / 4% / 10% | 96% / 1% / 3% ok | 87% / 1% / 12% ok | 82% / 4% / 13% | 82% / 7% / 11% | 2 of 6 |
| 0.4 | 88% / 2% / 10% | 88% / 4% / 8% | 97% / 1% / 2% ok | 88% / 1% / 11% ok | 86% / 4% / 10% | 86% / 8% / 7% | 2 of 6 |
| 0.35 | 89% / 2% / 9% | 89% / 4% / 7% | 97% / 1% / 2% ok | 91% / 2% / 7% | 88% / 4% / 8% | 87% / 8% / 6% | 1 of 6 |
| 0.3 | 89% / 4% / 7% | 90% / 4% / 6% | 97% / 2% / 1% | 93% / 2% / 4% | 90% / 4% / 6% | 89% / 8% / 3% | 0 of 6 |

### shift-supervisor-retail (shift-supervisor-retail-2026-10-21-0306.raw.json, 450 gate rows)

| bar | bcl | ceb | en | fil | hil | war | languages passing |
|---|---|---|---|---|---|---|---|
| 0.6 | 56% / 1% / 43% | 60% / 4% / 36% | 80% / 1% / 19% | 72% / 4% / 24% | 65% / 3% / 32% | 52% / 5% / 43% | 0 of 6 |
| 0.5 | 64% / 1% / 35% | 73% / 5% / 21% | 88% / 1% / 11% ok | 81% / 4% / 15% | 72% / 3% / 25% | 67% / 8% / 25% | 1 of 6 |
| 0.45 | 69% / 1% / 29% | 76% / 5% / 19% | 92% / 3% / 5% | 81% / 4% / 15% | 81% / 4% / 15% | 73% / 11% / 16% | 0 of 6 |
| 0.4 | 72% / 3% / 25% | 76% / 7% / 17% | 93% / 3% / 4% | 83% / 7% / 11% | 83% / 4% / 13% | 73% / 12% / 15% | 0 of 6 |
| 0.35 | 77% / 3% / 20% | 77% / 8% / 15% | 93% / 3% / 4% | 88% / 7% / 5% | 83% / 7% / 11% | 73% / 12% / 15% | 0 of 6 |
| 0.3 | 81% / 7% / 12% | 81% / 8% / 11% | 93% / 3% / 4% | 89% / 7% / 4% | 87% / 7% / 7% | 76% / 12% / 12% | 0 of 6 |

