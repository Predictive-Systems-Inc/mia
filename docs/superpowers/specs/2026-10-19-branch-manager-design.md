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
8. Weekly summary on Monday at opening (the first open day after a closed Monday) to the owner
   and supervisors: sales against target per branch, best and worst items, waste from
   stock_events, the open experiment's progress.
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

## 13. Pricing strategies (added 20 October, owner's instruction)

Price and promo experiments rest on proven pricing strategies, never on a guess. The strategies
are data rows (`branch_manager_strategies`: id, name key, kind, rule parameters as JSON, source,
active), seeded with their sources the way tips are, and the proposal engine in
`experiments.py` is code: it reads the branch's own numbers (counts, targets, waste from
`stock_events`, baskets, last year's month) and picks the strategies whose conditions hold for an
item. The model never invents a price or a strategy. Every proposal names its strategy, the
rationale in the branch's numbers, the expected effect, the guard rails, and the 14-day test.

The v1 catalogue (sources are the published works the rows cite; the owner may add their own):
1. Charm pricing (left-digit effect): a price ending in 0 or 5 tested one peso under the next
   ten (50 to 49). Source: Thomas and Morwitz, "Penny Wise and Pound Foolish" (2005).
2. Anchoring with a premium option: when a line has one size, test a larger or premium variant
   priced high so the regular looks fair. Source: Kahneman and Tversky on anchoring; Nagle and
   Muller, "The Strategy and Tactics of Pricing".
3. Bundling: items often bought together (the pairing rule) tested as a bundle priced below
   the sum. Source: Stremersch and Tellis, "Strategic Bundling of Products and Prices" (2002).
4. Volume tiers: a per-piece price that drops at a quantity when multi-piece orders are common.
   Source: Nagle and Muller (nonlinear pricing).
5. Time-of-day markdown against waste: a late-day price cut on an item with recurring
   leftovers in `stock_events`, sized to clear the average leftover, never below cost. Source:
   revenue management for perishables (Talluri and van Ryzin, "The Theory and Practice of
   Revenue Management").
6. Price increase test on a sell-out item: an item that sells out before closing on most days
   tested at a higher price (5 to 10 percent), the baseline and score as for any experiment.
   Source: elasticity testing, Simon and Fassnacht, "Price Management".
7. Seasonal pricing from last year: the best seller of the same month last year priced or
   promoted ahead of its season. Source: the shop's own history (data standard 1.5).
8. Decoy or good-better-best: three variants where the middle is the one to sell. Source:
   Ariely, "Predictably Irrational"; Nagle and Muller.

Guard rails, in code with unit tests: never below the item's cost (`retail_items.cost`, nullable,
minor units; without a cost no cut deeper than 20 percent); never more than 20 percent from the
price in force; one open experiment per branch; no second experiment on the same item within 28
days; 14 days and revert unless the owner keeps it; the baseline rule of section 7 (same
weekdays of the previous 28 days, at least 7 days) or "not enough data". The owner's card shows
strategy, rationale, numbers, guard rails and the baseline, and the result after 14 days names
the strategy and whether the numbers supported it. Strategies and the decision are recorded on
the experiment row (strategy_id, rationale JSON).

Data changes: `branch_manager_strategies` (agent-owned), `branch_manager_experiments` gains
`strategy_id` and `rationale`, `retail_items.cost` (template, nullable; Q79 asks the owner for
the costs). Out of v1: cost of goods computed from ingredients (production_planner), dynamic
pricing, competitor prices.

## Carried over

- 20 Oct 2026, the gates (docs/research/2026-10-20-branch-manager-gate.md): run 1 failed both
  gates (decider: only English passed; router: wrong 3.2%). Fix round 1 (the developer's
  decision): the router harness routes to every registered agent, the router description names
  the catalogue's subjects, short code candidates ranked in code, one more description edit,
  fresh gate seeds; run 2 failed both again (decider wrong 0.4%, en and fil pass, ceb, hil, war
  and bcl ask 20.0% to 35.6%; router wrong 3.5%, en, ceb and hil pass). Stopped there; every
  gate half so far is spent. Open: the asks just under 0.6 in the four Visayan and Bikol
  languages (threshold is Q40, drafts are Q28 to Q35); the seed "who on my team is selling the
  most salted egg?" (sales_supervisor at 0.85 to 1.0 in six languages); "stop the new price"
  read as keep once (bcl, 0.66); a count read as the promo price ("3 kape for 65");
  `cost_minor` in the usage rows.
- 20 Oct 2026, the due work (Task 6, node/mia/agents/branch_manager/due.py), rulings made in
  the build: a quote given is stored as a Coaching row of kind `tip` (the Tip row's kind tells a
  tip from a quote); a nudge counts misses only on open days with counts and a target (a day
  the node was down or nobody reported is never a miss); a cheer and a nudge are independent (a
  personal best on a missed day gets both); owners and admins are never cheered or nudged; the
  weekly summary and the monthly letter go per branch (an owner gets one per branch) and run
  the tools as each recipient, so rbac decides what each reads. A Monday the branch is closed
  moves the weekly summary to the week's first open day (fix wave). When every recipient is
  denied nothing is sent and no marker is written, so the tools run again on each tick of the
  window.
- 20 Oct 2026, the fix wave after the whole-branch review: an experiment is refused
  `price_scheduled` while the item has a price dated after the business date, and a price
  change waits until a done experiment's revert took effect (`open_experiment`), so a revert
  row never undoes an approved price; a typed keep with a negation word (`dai`, `huwag`, `no`,
  `stop` and the rest of `parsing.NEGATION_WORDS`) gets the keep and revert buttons and never
  keeps; a number right before a menu word is a count, never a price candidate, unless no
  other amount is left; a keep or revert tap stays valid until the revert takes effect
  (`too_late` is the deadline), not only on the day it was asked; a typed price under a
  strategy whose condition does not hold is refused `no_strategy` (every proposal names its
  rationale); D37 reaches money, external and delete requests only, and never from the shell;
  a request whose approve handler refused is recorded `approval.refused` and closed as expired,
  and only the reject handlers that opt in tell the requester (the branch manager's two);
  every fixed number in a `bm.*` string is a placeholder fed from the constants
  (`tools.WORDED`); `retail_item_prices.set_by` is the person who set the price, None for the
  system, and the approval and people ids are foreign keys.
- 21 Oct 2026, people from the chat (Q117): `add_person` (an admin adds a clerk, staff,
  supervisor or admin, never an owner, through people.add_person, then the invite or a linked
  number) and `set_phone` (a Philippine mobile number linked through linking.link_phone, the
  address redacted in channel.linked, the last four digits in replies). Review finding, account
  takeover: a linked number acts as the person and receives their WhatsApp login, so a number
  goes only to a clerk, staff or supervisor, to an admin only from the owner, never to the
  owner, never as a second number (no silent replace) and never away from another person.
