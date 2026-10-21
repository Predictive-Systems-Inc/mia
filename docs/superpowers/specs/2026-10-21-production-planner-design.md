# production_planner v1: design

Date: 21 October 2026. Catalogue row: docs/agents-catalogue.md (production_planner; the "Chain of
kiosks with a commissary (Ferino's)" variant). Shapes followed: docs/superpowers/specs/
2026-10-19-branch-manager-design.md and 2026-10-20-bookkeeper-design.md. Decisions read: D35
(the public sender), D36 and D38 (data standards 1.5 and 1.6), D37 (the owner's own request).
Filipino first, never "Tagalog". Draft: Q91 and Q92 wait for the owner.

## 1. Goal

The production planner runs Ferino's commissary, the kitchen that bakes for the Mall kiosk and
the Street stall: tomorrow's production plan per item from each kiosk's forecast and its
confirmed customer orders, rounded to whole batches; a batch sheet per item (ingredients for the
batches, cost per batch and per piece); yield and waste per batch; the dispatch list per kiosk,
confirmed by the driver on delivery and matched to the kiosk's receipt; and the commissary's
capacity for a date, so pre-orders can be checked against the ovens. Proof shop: Ferino's
Bibingka (two kiosks and one commissary).

Out of scope for v1: transfers between kiosks (inventory_manager), ingredient issue to batches
(the commissary head counts ingredients through the inventory manager as today), route planning
for the driver, the customer service check against capacity (interface named in section 6,
built in customer_service later), weather in the forecast, writing `retail_items.cost`.

## 2. Data standard check (gate 1, the owner)

Reads core `sales_counts` (live rows, tender ignored), `stock_events` (sold_out, leftover and
received at the kiosks), `branch`, `person`; template `retail_items` (components expand a
bundle, Box of 4 is four Classic), `retail_ingredients` (unit, pack_price),
`retail_item_prices`. Reads agent-owned `customer_service_orders`: the planner is its second
reader, so by rule 9 it becomes core `customer_orders` (data standard 1.7, the Q39 precedent,
D35's consequence): same fields, redaction of `delivery_note` kept, `customer_id` stays a
foreign key to `customer_service_customers` (customers stay agent-owned, D35), one migration
edit and ADR 019. **Stop until a yes on Q91.** Without a yes: nothing reads
`customer_service_orders`, the plan leaves orders out and says so on the card, and the
promotion is recorded as blocking before scenario 2.
Writes agent-owned `production_planner_recipes`, `_plans`, `_batches`, `_dispatches`. Never
writes `stock_events` (the inventory manager stays its only writer, section 6). Batch waste
stays in `production_planner_batches`; the bookkeeper's waste at cost reads it only after a
promotion (recorded as blocking before that reader). The commissary is a third `Branch` row
plus settings, no core column (Q92).

## 3. Who talks to it

Commissary head (supervisor of the commissary branch): the plan, changes to it, batch sheets,
yield and waste, the dispatch list. Owner and admin: everything, and they alone set recipes,
ovens and hours. Driver (staff at the commissary, skill `driver`, Q94): their dispatch list and
the delivered confirmation only. Kiosk supervisors: read the dispatch to their own kiosk and
the plan lines for it. Clerks: not offered the agent. Customers: never (D35). Languages: ten,
Filipino first. Rights: `read_own` for kiosk supervisors and the driver, `write_all` on the
commissary for its head, `read_all` and `write_all` for owner and admin.

## 4. Scenarios (the acceptance list)

1. At `plan_at` (14:00) the commissary head gets tomorrow's draft plan: per item the batches and
   pieces, the split per kiosk, each line's forecast, orders and leftover; "ok" confirms it.
   `test_the_plan_is_forecast_plus_orders_minus_leftovers_in_batches`,
   `test_the_draft_plan_reaches_the_head_once`.
2. A confirmed order of 30 Classic for pickup tomorrow at the Mall kiosk raises the Mall line by
   30; a waiting or rejected order changes nothing. `test_only_confirmed_orders_enter_the_plan`.
3. Head: "dagdagan ng isang batch ang ube": the line gains a batch when the ovens have room, else
   the reply names the free oven minutes. `test_a_change_beyond_capacity_is_refused`.
4. Head: "batch sheet classic": each ingredient times the batches, cost per batch and per piece
   from pack prices; an ingredient without a pack price shows no cost (Q55's rule); an item
   without a recipe says the owner must enter one. `test_the_batch_sheet_multiplies_the_recipe`,
   `test_an_item_without_a_recipe_has_no_sheet`.
5. Owner: "recipe classic: 48 piraso, 2 kg rice flour, 1 tray itlog, 6 niyog, 45 min": stored
   after a confirmation card; a supervisor's recipe message is refused.
   `test_the_owner_sets_a_recipe`, `test_a_supervisor_cannot_set_a_recipe`.
6. Head: "batch 2 classic 45 ok 3 sunog": yield 45 of 48, waste 3 with reason burnt; the closing
   line gives the day's yield percent per item. `test_a_batch_records_yield_and_waste`.
7. When the last batch is recorded (or at `dispatch_at`), the dispatch list per kiosk goes to the
   head and the driver; the driver taps "Delivered" per kiosk; the kiosk supervisor asks "ano
   ang darating" and reads their own list. `test_the_dispatch_list_splits_by_kiosk`,
   `test_the_driver_confirms_a_delivery`, `test_a_kiosk_supervisor_reads_their_own_dispatch`.
8. The kiosk records its receipt through the inventory manager; an hour after the kiosk opens the
   planner compares delivered with received and tells the head and the owner of a gap; no
   receipt at all is a gap too. `test_a_short_receipt_is_flagged`, `test_a_full_receipt_is_quiet`.
9. Owner: "kaya ba ang 200 classic sa Dec 24": free batches and pieces for that date after the
   planned ones. `test_capacity_counts_ovens_hours_and_planned_batches`.
10. Security: a kiosk supervisor cannot read the other kiosk's dispatch or change the plan; the
   driver can only confirm; customer order text never reaches the plan or the decider.
   `test_a_kiosk_supervisor_cannot_change_the_plan`, `test_a_driver_only_confirms`,
   `test_order_notes_never_reach_the_plan`.

## 5. Data

Agent-owned (ULIDs, minor units plus currency, aware times, `0000_initial` edited in place, rule
14), all on the commissary branch except dispatches:
- `production_planner_recipes`: id, item_id (a single item, never a bundle), batch_yield
  (pieces), oven_minutes, lines (JSON: ingredient_id, quantity_milli in thousandths of the
  ingredient's unit), keeps_overnight (bool, Q93), active, set_by. Entered by the owner.
- `production_planner_plans`: id, production_date, status (draft, confirmed), lines (JSON per
  item: per kiosk forecast, orders, leftover, demand, more_flag; batches, pieces, changed_by,
  change_note), confirmed_by. One row per date; a change is a store update with an event.
- `production_planner_batches`: id, plan_id, item_id, batch_no, planned_yield, good, waste,
  reason (burnt, undercooked, dropped, other), recorded_by, at.
- `production_planner_dispatches`: BranchScoped on the destination kiosk (so a kiosk supervisor
  reads by branch), from_branch_id (the commissary), plan_id, business_date, lines (JSON:
  item_id, quantity), status (packed, delivered, matched, short), delivered_by, delivered_at,
  received (JSON, filled by the match).
Template, core: none changed by the planner. Settings carry ovens and hours (section 9).

## 6. The agent

Actions (Jev): plan, change_plan (slots: item, batches or pieces), confirm_plan, batch_sheet
(item), set_recipe (item, lines), record_batch (item, batch_no, good, waste, reason),
dispatch (kiosk), delivered (kiosk), capacity (date, item, pieces), greeting, clarify.
Tools (all `write_internal` or `read`; none is money, external or delete, so no approval; the
recipe card is a confirmation, not an approval): `plan` (read), `change_plan` (write; precheck
`capacity`, `confirmed` for a past date), `confirm_plan`, `batch_sheet` (read), `set_recipe`
(write, owner and admin), `record_batch` (write, precheck: the item is in the day's plan,
good plus waste at most twice the batch yield), `dispatch_list` (read; read_own for a kiosk
supervisor), `confirm_delivery` (write, the driver and the head), `capacity` (read).
Receiving: the inventory manager remains the only writer of `stock_events`. Its kiosk
supervisor says "dumating na 40 classic" and the inventory manager records `received` rows
with `item_id` (a small extension of `receive_delivery` to item lines, owned by that agent,
Carried over). The planner's `match_tick` reads those rows by kiosk, business date and item and
sets the dispatch `matched` or `short` (Q95: no dispatch id on stock_events).
Capacity interface: `production_planner.capacity.free(session, commissary_id, day) ->
Capacity(minutes_free, per_item: {item_id: pieces_free})`, a pure read on settings, recipes and
the day's plan. The `capacity` tool wraps it; customer_service's `_order_precheck` may later call
the function (never the tool: a customer runs only customer_service tools, D35) and raise
LookupError("capacity").
Due work: `draft_plan` (at plan_at the day before, marker per commissary and date), `dispatch`
(after the last batch or at dispatch_at), `match_tick` (kiosk opening plus one hour),
`closing_yield` (production end plus one hour). Events: `production.recipe_set`,
`.plan_drafted`, `.plan_changed`, `.plan_confirmed`, `.batch_recorded`, `.dispatch_packed`,
`.delivered`, `.matched`, `.short`.

## 7. Parsing and the arithmetic (rule 7: code, never the model)

Code (`forecast.py`, `capacity.py`, pure, unit tested): forecast per kiosk and item is the mean
units on the same weekday in the 28 days before the production date (the shape of
`branch_manager.experiments.baseline`), live counts only, bundles expanded through components,
half up; under 2 such days it is "not enough data" and the line asks the head for a number.
Demand = forecast + confirmed order pieces with pickup on that business date at that kiosk,
less the expected leftover (the last closing leftover when the recipe keeps overnight, else 0),
never
below 0; plus one batch when `inventory_manager.calc.plan` says `more`. The commissary total per
item rounds up to whole batches; surplus pieces go to the kiosk with the larger forecast.
Capacity: ovens times the production window in minutes, less the planned batches times
oven_minutes; costs: quantity_milli times pack_price / 1000, half up, per batch then per piece.
Parsing: items and ingredients by short code, quantities and units (kg, g, tray, pcs, pack, min),
dates from `parsing.find_dates`, kiosks by name; Jev picks the action and the item among
candidates. A negated change ("huwag na dagdagan") is a no; a second number in the same
message is a correction of the first only when it follows "pala" or "I mean".

## 8. i18n

Keys `pp.*` (plan card, line, change, batch sheet, recipe card, batch, dispatch, delivered,
short, capacity, closing yield), `intent.production_planner.*`, the label
`agent.production_planner` ("Production planner"; fil "Tagaplano ng produksyon"), in the ten
languages of `i18n.SUPPORTED` (fi, en, fil, ceb, ilo, hil, war, bcl, pam, pag); en and fil by the
build, the eight others as machine drafts under Q28 to Q35. Every fixed number in a string is a
placeholder fed from constants.

## 9. Seed and configuration

Seed: a "Commissary" branch (Asia/Manila) with a head (supervisor) and a driver; recipes for
Classic, Special, Ube, Salted egg, Cheese overload and Puto bumbong (made-up batch yields of 48
or 36, the owner corrects them); one confirmed plan and its batches yesterday; one dispatch per
kiosk, one matched and one short. Settings in `node/config/org/ferinos/settings.yaml`:
`production_planner: {commissary: Commissary, serves: [Mall kiosk, Street stall], ovens: 2,
hours: {start: "03:00", end: "09:00"}, plan_at: "14:00", dispatch_at: "08:30"}` and
`production_planner` in `agents`. Policy: `agent:production_planner use` for supervisor, staff
with the driver skill, owner, admin; `data:production_planner_*` per section 3;
`data:customer_orders read` for the agent role (after Q91); read on `sales_counts` and
`stock_events` of the served kiosks for the agent role only (Q96).

## 10. Testing and gates

Pure-code tests for the forecast, demand, rounding, surplus split, capacity and costs (fixed
dates, a 28-day table); chat tests for scenarios 2 to 7, 9 and 10 through `run_turn`; due tests
at fixed clocks for 1, 7 and 8; negative tests for every role boundary and for the capacity
precheck; the decider gate at the Q40 bar on a fresh half; router seeds per gated language with
the contrast "the commissary's plan, batches and dispatch; not kiosk stock, not sales counts".

## 11. Open questions (into docs/questions.md in its shape, from Q91)

- Q91 Data standard 1.7, customer orders in core. Where: customer_service/models.py, core/models.py,
  0000_initial. Question: may `customer_service_orders` move to core as `customer_orders` so the
  planner counts confirmed orders? Assumed: yes, same fields and redaction, customers stay
  agent-owned, ADR 019. Blocking: yes, before Task 1.
- Q92 The commissary is a Branch plus a setting. Where: core/models.py (Branch), the Ferino's
  settings. Question: a third Branch named in `production_planner.commissary`, or a `kind`
  column on Branch? Assumed: the Branch plus the setting, no core change; it has no retail hours
  and the kiosk agents' due work skips a branch without hours (checked in Task 1). Blocking: yes,
  before Task 1 (a column would change the data standard).
- Q93 Leftovers carried to the next day. Where: `production_planner_recipes.keeps_overnight`.
  Question: which items may be sold the day after baking? Assumed: none, the field stays false.
  Blocking: no.
- Q94 Who the driver is. Where: policy.csv, the seed. Question: a new role `driver`, or staff at
  the commissary with the skill `driver`? Assumed: staff with the skill, granted only
  `confirm_delivery` and their own list. Blocking: no.
- Q95 Matching a dispatch to a receipt. Where: inventory_manager/tools.py (receive_delivery).
  Question: match by kiosk, business date and item, or add a dispatch id to `stock_events`?
  Assumed: by kiosk, date and item, no core column, one dispatch per kiosk and day. Blocking: no.
- Q96 Commissary staff and kiosk data. Where: policy.csv, rbac. Question: may the agent role read
  the served kiosks' counts and stock while the head reads only plan rows, and kiosk supervisors
  only their own kiosk's dispatch? Assumed: yes to both; no human role gains a cross-branch
  right. Blocking: yes, before the policy lines in Task 1 (a security rule).

## 12. Order of work

1. Data standard 1.7 (on a yes to Q91), the four tables, the commissary branch, settings, seed,
policy. 2. Pure code: forecast, demand, rounding, split, capacity, costs. 3. Actions and the
decider. 4. Tools and prechecks (no approvals). 5. Chat turn, scenarios 2 to 7, 9 and 10. 6. Due
work (draft plan, dispatch, match tick, closing yield). 7. Ten languages. 8. Evals, gates, docs.

## Carried over

- inventory_manager: `receive_delivery` accepts item lines (finished goods from the commissary),
  still the only writer of `stock_events` (owner: the inventory manager spec).
- inventory_manager: its bake plan (`plan_message`) is not sent at a kiosk the commissary serves
  (owner: inventory_manager due.py).
- customer_service: `_order_precheck` calls `capacity.free` for a pre-order (owner: the
  customer service spec, after this agent ships).
- bookkeeper: batch waste at cost and cost per piece from recipes, after a promotion of
  `production_planner_batches` (owner: the bookkeeper spec).
- production_planner (as built, 21 Oct 2026): the served kiosks' sales counts, stock events and
  customer orders are read by the agent role alone (`read_all` on the agent, D39, Q96); no human
  role gains a cross-branch right.
- the kiosk agents: their due work skips a branch that is not a shop (the `is_shop` guard,
  `retail_hours.is_shop`), so the commissary gets no kiosk message; `retail_hours.shops` keeps the commissary out of an owner's "every branch".
- shift_supervisor: kiosk staff only cover across kiosks; commissary staff (the driver) are never
  cover candidates (Q112).
- production_planner forecast: with no forecast at any kiosk the pieces of a whole batch are
  split evenly, the remainder to the first kiosk in `serves` (Q113).
- seed: the kiosks' receipts of the seeded dispatches are written straight as `stock_events`
  rows, and the seed loads its own role, until `receive_delivery` takes item lines (owner: the
  inventory manager spec).
- production_planner match tick: a short dispatch is flagged only an hour after it arrived (an
  08:35 dispatch was flagged at 08:50 before this rule), and it is never matched again after a
  later receipt.
- production_planner tests: the `send_after` asserts were dropped, because Message has no
  `send_after` field.
- production_planner capacity: `CapacityOut` carries no item name, so `capacity_text` lists the
  free pieces per item.
- production_planner gates (docs/research/2026-10-21-production-planner-gate.md): the decider
  gate failed (wrong 2.7%, right below 80% in fil, ceb, hil, war and bcl; en passes) and the
  router gate failed (wrong 4.5%, hil, war and bcl below the bar); reported as they are, a rerun
  of either needs fresh gate seeds.
- production_planner staff offer: every staff member is offered the agent and `dispatch_list`
  (policy.csv); the `use` line is by role; the skill is checked in confirm_delivery and
  dispatch_list.
- production_planner next fresh seeds (a rerun only with new seeds): name the arrival or the
  delivery in the dispatch texts; build DRAFT (the confirm scenario's previous message) from
  t(); reword the two disputed router seeds ("sick leave for Monday", "how is Liza doing at
  selling"), which are labelled right but read as the other agent.
- sales_supervisor: `sales.report.compare` carries a hard-coded "4-week" in its text and is
  allow-listed in the digit-free test (`NAMED_DIGITS`); a placeholder for the window is owed
  (owner: the sales supervisor).
- production_planner decider: the DIRECTIONS option text Jev reads still lists English and
  Filipino words only; the code guard (`words.DIRECTION_WORDS`, ten languages) covers the
  decision, and the text stays as the gate measured it.
