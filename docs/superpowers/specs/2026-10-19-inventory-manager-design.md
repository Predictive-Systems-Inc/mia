# Inventory manager v1: stock, sell-outs, leftovers and waste, the bake plan, supplier orders

19 Oct 2026. Built with `/mia-build-agent inventory_manager` (docs/agents-catalogue.md row).
Proof shop: Ferino's Bibingka. **Status: in execution** under the owner's "build all" (the
developer's three answers of step 1 are recorded assumptions: proof shop Ferino's; roles clerk,
supervisor, owner; the first five scenarios are 1 to 5 below).

## 1. Goal

A clerk tells Mia when an item sells out, how many are left, what was thrown away and what is
running low, in their own words; head staff and the owner see the stock side of the day without
asking; the baker gets a plain plan for tomorrow; a supplier order is drafted from what is low
and waits for the owner's tap. Jev picks, code counts, templates word.

Out of scope: reading the sales counts (a second reader of `sales_supervisor_counts` needs
data standard 1.5, Q39; the bake plan uses this agent's own records until then); ingredient
costing and the cash side (bookkeeper); photos of delivery slips, voice notes (next phase);
transfers between branches (follow-up).

## 2. Data standard check (gate 1, the owner)

| Table | Written by | Read by now | Read by later | Verdict |
| --- | --- | --- | --- | --- |
| `inventory_manager_stock_events` | inventory_manager | inventory_manager | branch_manager (part 3) | agent-owned now |
| `inventory_manager_orders` | inventory_manager | inventory_manager | bookkeeper (expenses) | agent-owned now |
| `retail_ingredients` (template) | seed, importer | inventory_manager | any retail agent | template, like `retail_items` |
| `retail_items`, `retail_branch_hours` (template) | existing | sales_supervisor, inventory_manager | | template, no change |
| `core.person`, `core.branch`, `approvals` | existing | all | | core, no change |

No core table changes, so no owner gate now. Promotion of the two agent-owned tables to core is
recorded as blocking before the bookkeeper reads orders (Q53).

## 3. Who talks to it

| Role | May | Scope |
| --- | --- | --- |
| clerk | report sell-outs, counts, leftovers, waste, low stock; ask what is low and the bake plan | own branch (`read_own` on events gates by role; branch scoping in code) |
| supervisor | the same, plus draft a supplier order and receive a delivery | own branch; `read_all` denied |
| owner, admin | all of it for every branch; approve or reject an order | `read_all`, `write_all`; approvers |

Languages: the ten of `i18n.SUPPORTED`; channels: web chat and the WhatsApp simulation, as the
sales supervisor. Policy lines: `agent:inventory_manager, use` exists for clerk and supervisor
(owner inherits); tool and data lines are added in the plan's Task 3.

## 4. Scenarios (the acceptance list)

1. **Sell-out with a time.** "sold out of special at 2pm", "ubos na ang ube" (no time: now).
   Reply: "Special sold out at 14:00." Event `stock.sold_out`. Test
   `test_a_clerk_reports_a_sell_out_with_the_time`.
2. **How many left.** "only 5 ube left", "15 classic pa". Reply echoes the count per item. Test
   `test_a_clerk_counts_what_is_left`.
3. **Closing leftovers and waste.** "3 trays leftover", "threw away 8 classic, too dry" (reason
   from a fixed list: too_dry, burnt, expired, dropped, other). Reply echoes; a waste without a
   reason, or with an unsure one, asks one with buttons ("8 Classic thrown away. Why?"). Tests `test_waste_with_a_reason_is_recorded`,
   `test_waste_without_a_reason_asks_one`.
4. **Low ingredient.** "running low on rice flour", "LPG is almost empty", "need more banana
   leaves by Friday". Reply: noted, and when the ingredient has a supplier, "Shall I draft an
   order?" with Yes and No buttons. Test `test_a_low_ingredient_offers_an_order`.
5. **What to bake tomorrow.** "what should we bake tomorrow" gives one line per item: more,
   same or fewer, from this agent's own records (section 7, pure code). Test
   `test_the_bake_plan_follows_the_last_four_same_weekdays`.
6. **Supplier order draft with approval.** "order 10 trays of eggs from Aling Nena": the tool
   has `risk: money`, so it calls `approvals.request()` and stops; the owner gets an approval
   card with the lines and the total when prices are known; a tap approves or rejects; the
   requester is told. An order decision on a message with no buy word (parsing.BUY_WORDS)
   asks "Did you mean" first, place an order the first button. Tests `test_an_order_waits_for_the_owners_approval`,
   `test_a_clerk_cannot_place_an_order`, `test_an_approved_order_tells_the_requester`.
7. **Delivery received.** "eggs delivered, 10 trays" closes the order's line (or records a
   receipt without an order); only a supervisor or owner receives (receive_delivery), and a
   receipt is no report kind. Test `test_a_delivery_closes_the_order_line`.
8. **What is low.** "what are we low on" lists ingredients at or under their reorder point
   from the latest counts. Test `test_what_is_low_lists_items_under_the_reorder_point`.
9. **Closing stock summary.** At closes plus 45 minutes head staff get: sell-outs with times,
   leftovers, waste with reasons, low ingredients; owners get it per branch. A quiet night
   (nothing of these) sends nothing. Test
   `test_closing_summary_goes_to_head_staff_once`.
10. **Bake plan message.** At opens minus 60 minutes the clerks and supervisors of the branch
    get tomorrow's plan (scenario 5) as a notification. Test `test_bake_plan_message_before_opening`.

## 5. Data

Agent-owned, in `mia/agents/inventory_manager/models.py`:

| Table | Row |
| --- | --- |
| `inventory_manager_stock_events` | `kind` (sold_out, count, leftover, waste, low, received), `item_id` (FK `retail_items.id`, nullable), `ingredient_id` (FK `retail_ingredients.id`, nullable), `quantity: int | None`, `unit: str | None`, `reason: str | None`, `at: TZDateTime` (the sell-out time or the report time), `reported_by` (FK person), `business_date`, `source_message_id`, `order_id: str | None` |
| `inventory_manager_orders` | `supplier: str`, `lines: list[dict]` JSON (`ingredient_id`, `quantity`, `unit`, `unit_price: int | None`), `currency`, `total: int | None` (minor units), `status` (draft, approved, rejected, received), `approval_id: str | None`, `requested_by`, `business_date` |

Template, in `mia/templates/retail/models.py`: `retail_ingredients` (`branch_id` nullable,
`name`, `short_codes` list, `unit` (tray, kg, pack, tank, pcs), `reorder_point: int`,
`supplier: str | None`, `pack_price: int | None`, `currency`, `active`). The seed adds eight
ingredients for Ferino's (rice flour kg 10, eggs tray 5, coconut pcs 20, sugar kg 5, cheese kg
2, salted egg pcs 30, banana leaves pack 3, LPG tank 1) with a supplier and a pack price.

Rule 14: edit `0000_initial` in place; rebuild dev databases.

## 6. The agent

**Actions** (threshold 0.6): `report_stock` (tool `record_events`; slots per group: `item_<i>`
over items and ingredients plus none, `kind` over sold_out, count, leftover, waste, low,
`reason` over the waste reasons plus not_stated (an unsure reason is not stated), `time` over the pre-parsed time
candidates plus now), `bake_plan` (`plan_tomorrow`), `whats_low` (`low_stock`), `place_order`
(`draft_order`; slots `supplier` over the branch's known suppliers plus not_stated), `receive`
(`receive_delivery`), `answer_offer` (yes or no to "Shall I draft an order?", valid only when
that question is Mia's last message), `reply_only`, `clarify`.

**Tools** (each `_check`ed, branch scoped through `_branch` as the sales supervisor's):

| Tool | Risk | Writes | Who |
| --- | --- | --- | --- |
| `inventory_manager.record_events` | write_internal | stock_events | clerk, supervisor, owner |
| `inventory_manager.low_stock` | read | | all three |
| `inventory_manager.plan_tomorrow` | read | | all three |
| `inventory_manager.draft_order` | **money** (`approvals.request`, approvers owner and admin) | orders, approvals | supervisor, owner |
| `inventory_manager.receive_delivery` | write_internal | stock_events, orders | supervisor, owner |

The approval tap uses the existing approval card and `approvals.decide` path (as the shift
supervisor's cover override); on approve the order's status becomes approved (event
`inventory.order_approved`) and the requester gets a notification; on reject, rejected.

**Due work** (`due.py`, windows as datetimes across midnight, markers with sends, as the sales
supervisor's): closing summary at closes plus 45 (urgent, end of shift) to `alerts.supervisors`
and per branch to owners and admins; bake plan at opens minus 60 (not urgent) to the branch's
clerks and supervisors. Markers `inventory.summary_sent`, `inventory.plan_sent`.

**Events:** `stock.sold_out`, `stock.counted`, `stock.leftover`, `stock.waste`, `stock.low`,
`stock.received`, `inventory.order_drafted`, `inventory.order_approved`,
`inventory.order_rejected`, `inventory.summary_sent`, `inventory.plan_sent`.

## 7. Parsing and the plan rule

- `pre_parse(text, menu_tokens)` is shared with the sales supervisor: move it, `was_corrected`
  and the filler, negation and total words to `mia/agents/parsing.py` (the sales supervisor
  imports from there; its tests stay green). Menu tokens here are item and ingredient names
  and codes.
- Times: code finds `(\d{1,2})(:\d{2})?\s*(am|pm)` and 24-hour `HH:MM`, and the Filipino
  "alas <n>" with a small number-word list (una to dose; 1 to 6 and 12 are pm); candidates go
  to Jev's `time` slot as ids; `now` is the default. The times are stripped before
  `pre_parse`, so "3 pm" is never a count group.
- Kind without a word: a bare count ("5 ube") is `count`; "ubos", "sold out", "wala na" are
  sell-out words in a per-language list used only as criteria text, never matched in code.
- The bake plan (pure, `calc.plan`): for each active item over the last four same weekdays
  with any record: `more` when a sell-out was recorded on at least two of them before closing
  minus two hours; `fewer` when a leftover was recorded on at least two; else `same`; no record
  gives `same`. ponytail: a heuristic until the sales counts are readable (1.5); the message
  says it is a suggestion.
- Low stock: an ingredient is low when its latest count is at or under its reorder point, or a
  `low` event was reported today.

## 8. i18n

Keys `stock.*` (recorded lines per kind, the reason question and its buttons, the offer
question with Yes and No, the order drafted and waiting message, the approval card title and
lines, approved and rejected notices, the bake plan lines more/same/fewer, the low list, the
closing summary, the capabilities line) and `intent.inventory_manager.*` button labels, in all
ten languages (eight as machine drafts, Q28 to Q35). The label exists.

## 9. Seed and configuration

The Ferino's seed adds the eight ingredients, two suppliers (Aling Nena for eggs and coconut,
Metro Supply for the rest), a fortnight of stock events per branch (a sell-out at 14:00 on two
Saturdays for Special, leftovers for Classic on two weekdays, a waste row, a count under the
reorder point for LPG) and one received egg order (its delivery seeded, so no seeded order is
open). No item and ingredient share a name or a short code, and a code is one word (eggs carry
`itlog`; the ingredient is "Salted duck eggs" with `maalat` and `pula`). `config/org/ferinos/settings.yaml` lists
`inventory_manager` after `sales_supervisor` in `agents`.

## 10. Testing and gates

Unit: the time finder, `calc.plan`, low stock, the order total; tools with mocked deps and a
negative test per tool (clerk ordering, supervisor reading another branch, a stale offer tap);
chat through `run_turn` with the fake Jev for every scenario; due tests at fixed clocks across
midnight; the approval flow end to end (request, card, decide, notification). Decider gate at
the Q40 bar on a fresh gate half with ten messages per scenario and gated language; ten router
seeds per gated language and `PENDING` emptied; reports under docs/research/.

## 11. Open questions

- Q53: when the bookkeeper reads orders or the branch manager reads stock events, both tables
  move to core (data standard 1.5 with the sales tables). Blocking: before that agent.
- Q54: the bake plan without the sales counts is a heuristic on sell-outs and leftovers;
  assumed acceptable for v1 and said so in the message. Blocking: no.
- Q55: an order's total needs pack prices; without one the card shows the lines only and the
  owner approves blind. Assumed acceptable; prices are optional seed data. Blocking: no.

## 12. Order of work

1. Data (template ingredients, two tables, migration, seed, org config). 2. Shared parsing
module and the actions and decider. 3. Tools, manifest, policy, the approval path. 4. Turn
and replies for scenarios 1 to 4. 5. Scenarios 5 to 8. 6. Due work (9, 10). 7. Ten languages.
8. Evals, gates, docs.

## Carried over
- Decider gate (19 Oct, docs/research/inventory-manager-2026-10-19.md): fails on the gate half
  after one tuning edit. Wrong 3.3% (bar 2%; nine of ten are an ingredient count read as an
  order); right en 90%, fil 56%, ceb 56%, hil 66%, war 64%, bcl 64% (bar 80%); ask 8% to 36%.
  Router gate not rerun (PENDING already empty, router description unchanged).
- Decider gate rerun (19 Oct, docs/research/inventory-manager-2026-10-19-rerun.md): fresh gate
  half after the fix wave, one tuning edit on the tune half, still fails. Wrong 0.3% (bar 2%:
  pass); right en 89%, fil 77%, ceb 61%, hil 74%, war 69%, bcl 71% (bar 80%); ask 11% to 38%
  (bar 15%). Most asks are the right action under 0.6; do not tune on that gate half again.
- Follow-ups from the final review (19 Oct), not fixed in v1:
  - M1: a count is stored in the ingredient's unit ("12 eggs" is 12 trays) and the reply does
    not say the unit; a unit question later.
  - M3: an order's business_date is the approve-time date, not the request date.
  - M4: a handler failure on approve (an ingredient deactivated, the requester's role changed)
    leaves the approval pending with no notice; catch it, reject with a reason and notify.
  - M5: `SupplierOrder.requested_by`, `SupplierOrder.approval_id` and `StockEvent.order_id`
    have no foreign keys.
  - M6: `_stock_rows` loads the branch's whole stock history for each low list and summary;
    bound it by the latest count per ingredient.
  - M8: the street stall opens at 06:00 as Ferino's quiet hours end, so its bake plan arrives
    at opening; decide whether the plan is exempt from quiet hours.
  - M9: a waste whose reason is never tapped is not recorded (Q50 holds); record it as other
    after the day closes, or accept it.
  - M10: events reported after the summary went out, still on its business date, reach no
    summary.
  - M11: fixed by the seed codes (no shared item and ingredient name or code).
  - Q56: a delivery closes the oldest open order line of the ingredient whatever the supplier;
    match by supplier later.
  - The fix wave's local reason words and spaced times were read off the spent gate half: the
    rerun needs a fresh gate half (new seeds), with spaced times in it.
