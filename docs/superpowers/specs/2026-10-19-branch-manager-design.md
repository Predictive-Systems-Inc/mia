# branch_manager v1: design

Date: 19 October 2026. Catalogue row: docs/agents-catalogue.md (branch_manager, part 3, and
"The split the owner chose"). Decisions: the split of 18 October (sales_supervisor records,
branch_manager leads), data standard 1.5 (ADR 017, D36). Shapes followed:
docs/superpowers/specs/2026-10-19-sales-supervisor-design.md and
2026-10-19-hr-officer-design.md. Filipino first, never "Tagalog".

## 1. Goal

The branch manager leads the sales staff of a Ferino's branch the way a good head would: a
morning message with yesterday's result against the target, one tip and one quote; a cheer when
a target or a personal best is met and a kind nudge after three misses; per-clerk coaching for
the owner and head staff from the sales counts and the "why" notes; answers to "how do I sell
more salted egg" from the branch's own notes first, then a curated list; price and promo
experiments proposed one at a time, approved by the owner on a card, scored by the sales
supervisor's numbers and reported plainly; a menu and price change on a date behind the owner's
approval; a weekly summary from sales and stock; a monthly numbers letter to the owner. Proof
shop: Ferino's Bibingka.

Out of scope for v1: branches, hours, people and roles edits (9), permits and renewals (10),
rent and fixed costs (11), the open-a-branch checklist (13), a narrative letter and anything
else that needs a generative model (next phase); cash and pay (their agents).

## 2. Data standard check (gate 1, the owner)

Reads core `sales_counts`, `sales_targets`, `sales_notes`, `stock_events` (data standard 1.5,
done), `person`, template `retail_items`, `retail_branch_hours`. Writes agent-owned
`branch_manager_experiments`, `branch_manager_tips` (the curated tips and quotes, seeded per
language with the source), `branch_manager_coaching` (what was sent to whom and when, so a
nudge is never repeated), and template `retail_items` (price and short codes, behind
approval; the sales_supervisor already reads it). No core change. Experiments become core when
the marketing_officer reads them (recorded as blocking then).

## 3. Who talks to it

Owner and admin: everything (`read_all`, `write_all`, the approvals for prices and
experiments). Supervisor: coaching views of their branch, the weekly summary, proposes
experiments (the owner decides). Clerk: receives the morning message, cheers and nudges, asks
"how do I sell more X" (own tips), reads their own numbers. Staff without sales duty: not
offered the agent. Languages: ten, Filipino first.

## 4. Scenarios (the acceptance list)

1. Morning message at opening to each clerk on shift: yesterday's amount against the day
   target (the owner's target wins, a day target beats a month target), one tip (rotating,
   never the same within 30 days), one quote with its source; quiet hours respected.
   `test_the_morning_message_has_result_tip_and_quote`.
2. A met target or a personal best (best day for that clerk in 90 days) earns a cheer at close;
   three missed day targets in a row earn one kind nudge (never two in a week).
   `test_a_met_target_is_cheered`, `test_three_misses_earn_one_nudge`.
3. Owner: "sino magaling magbenta ng itlog na maalat": per-clerk counts by item for 30 days,
   who improved against the 30 days before, one suggested pairing (the two items most often
   counted together). `test_per_clerk_coaching_for_the_owner`.
4. Clerk: "paano ko mabebenta ang salted egg": the branch's own "why it went well" notes for
   that item first (sales_notes themes), then two curated tips; nothing invented.
   `test_tips_come_from_notes_then_the_curated_list`.
5. Owner: "subukan natin 50 ang bibingka" or the agent's own proposal (one open experiment at
   a time per branch): an experiment card (item, from price to price, start date, 14 days, the
   baseline: the same weekdays of the previous 28 days), the owner approves (money); on approve
   the price changes on the start date and reverts at the end unless the owner keeps it; the
   result after 14 days: units, amount, against the baseline, in plain words ("sold 12% more
   pieces, 4% more pesos"). `test_an_experiment_waits_for_the_owner`,
   `test_an_approved_experiment_changes_the_price_on_the_day`, `test_an_experiment_is_scored_against_its_baseline`.
6. A promo or bundle experiment the same way (a bundle is a retail item with a bundle price
   and components); a seasonal suggestion from the same month last year when there is data.
   `test_a_bundle_experiment_is_proposed_from_last_year`.
7. Owner: "gawin nating 48 ang bibingka simula Lunes": a price change on a date behind the
   owner's approval, the sales supervisor's counts use the new price from that date; short code
   edits the same way without approval (no money). `test_a_price_change_on_a_date_needs_the_owner`.
8. Weekly summary on Monday at opening to the owner and supervisors: sales against target per
   branch, best and worst items, waste from stock_events, the open experiment's progress.
   `test_the_weekly_summary_reads_sales_and_stock`.
9. Monthly numbers letter on the first business day: the month against target, the best days,
   per-clerk totals, experiments decided; a template, not prose. `test_the_monthly_letter_is_numbers`.
10. Security: a clerk cannot see another clerk's coaching or the owner's experiment card; a
    supervisor's proposal does not change a price; the quotes and tips come only from the
    curated table (negative test: a note text never lands in a tip). `test_a_clerk_sees_only_their_own_coaching`,
    `test_a_supervisor_cannot_change_a_price`, `test_tips_never_come_from_free_text`.

## 5. Data

Agent-owned (ULIDs, minor units, aware times, `0000_initial` edited in place):
- `branch_manager_experiments`: id, branch_id, kind (price, promo, bundle), item_id, from_price,
  to_price, currency, starts_on, ends_on, baseline (JSON: days, units, amount), result (JSON,
  nullable), status (proposed, approved, running, done, rejected, kept), approval_id, proposed_by,
  decided_by.
- `branch_manager_tips`: id, language, kind (tip or quote), item_id (nullable), text, source,
  active. Seeded, edited only by the owner through a tool (no free text from staff ever lands
  here).
- `branch_manager_coaching`: id, branch_id, person_id, kind (morning, cheer, nudge, tip), sent_on,
  tip_id (nullable), message_id; `__redact__ = set()` (no sensitive content, but nudges are
  written as kind only).
Template write: `retail_items.price` and `short_codes` through a template service function that
emits `retail.item_price_changed` with the effective date (a dated price row
`retail_item_prices` if the sales supervisor needs history: ask in Q73).

## 6. The agent

Actions (Jev): coaching_who, how_to_sell (slot: item), propose_experiment (slots: item, price,
start), decide_experiment_result, change_price (slots: item, price, date), set_short_code,
weekly_summary, monthly_letter, greeting, clarify.
Tools: `coaching` (read_all for owner and supervisor, read_own for a clerk), `how_to_sell`
(read), `propose_experiment` (money, approval always; approvers owner and admin), `score_experiment`
(read), `change_price` (money, approval always; approvers owner and admin), `set_short_code`
(write_all owner and supervisor), `weekly_summary` and `monthly_letter` (read_all). Approve
handlers apply the experiment or the price from the evidence on the start date (a dated change
is applied by the tick, not at approval time); reject notifies.
Due work: `morning_message` (per clerk on shift, marker per person and business date, quiet
hours), `closing_cheers_and_nudges` (after close), `experiment_tick` (start, end, revert,
score), `weekly_summary` (Monday opening), `monthly_letter` (first business day). Events:
`branch_manager.morning_sent`, `.cheered`, `.nudged`, `.tip_given`, `.experiment_proposed`,
`.experiment_started`, `.experiment_ended`, `.experiment_scored`, `.price_changed`,
`.short_code_set`, `.weekly_sent`, `.monthly_sent`.

## 7. Parsing

Code: item names and short codes from `retail_items`, prices in pesos ("50", "₱50", "50 pesos")
to minor units, dates from `parsing.find_dates`; the baseline and the score are pure functions
(`experiments.py`) with unit tests: same weekdays of the previous 28 days, units and amount
deltas in percent, "not enough data" under 7 baseline days. Jev picks the action and the item;
it never computes a price, a delta or a tip.

## 8. i18n

Keys `bm.*` (morning, cheer, nudge, coaching lines, experiment card and result, price card,
weekly and monthly templates), `intent.branch_manager.*`, the label; en and fi by the build,
the eight Philippine modules as machine drafts (Q28 to Q35). Tips and quotes are data rows per
language, seeded with sources (public-domain or the owner's own), not i18n keys.

## 9. Seed and configuration

Seed: 20 tips (10 general, 10 per item for bibingka, puto bumbong, salted eggs) and 20 quotes
in fil and en with sources; one done experiment last month and one running; targets already
seeded by the sales supervisor. Settings: `branch_manager.experiment_days` (14),
`branch_manager.nudge_after_misses` (3). Policy: `agent:branch_manager use` for clerk,
supervisor, owner, admin; `data:branch_manager_*` per role as above;
`data:retail_items write_all` for the agent role only through the approved tools.

## 10. Testing and gates

Unit tests for the baseline and score, the tip rotation, the nudge rule, the price parser; chat
tests for scenarios 3 to 7 and 10 through `run_turn`; due tests at fixed clocks for 1, 2, 8, 9;
approval tests (owner approves, supervisor cannot, requester never decides, the price applies on
the date); the decider gate at the Q40 bar on a fresh half; ten router seeds per gated language
with the contrast line "coaching, tips, experiments and prices; not counts or targets".

## 11. Open questions

Q73 price history (assumed: a dated `retail_item_prices` row so counts keep the price of their
day; the sales supervisor reads the price in force on the business date). Q74 who may propose
an experiment (assumed: supervisor proposes, owner decides; the agent proposes at most one a
month per branch). Q75 the sources of quotes (assumed: public-domain and the owner's own list;
no scraping).

## 12. Order of work

1. Models, migration, seed (tips, quotes), settings, policy. 2. experiments.py (baseline,
score) and the tip and nudge rules as pure code. 3. Actions and the decider. 4. Tools and the
two approvals with their handlers. 5. Chat turn, scenarios 3 to 7 and 10. 6. Due work (1, 2, 8,
9). 7. Ten languages. 8. Evals, gates, docs.

## Carried over

(filled by the reviews)
