# Inventory Manager v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clerks report sell-outs, counts, leftovers, waste and low ingredients in their own words; head staff and the owner get the stock side of the day; the baker gets tomorrow's plan; a supplier order waits for the owner's tap.

**Architecture:** The scaffolded package `mia/agents/inventory_manager/` (66d06f0: a Jev turn that greets) grows the sales supervisor's shape: two agent-owned tables plus a `retail_ingredients` template table; a shared parsing module `mia/agents/parsing.py` extracted from the sales supervisor; actions, decider, five tools (one with `risk: money` through `approvals.request`), replies, due work. No reads of the sales tables (Q39, Q53).

**Tech Stack:** as the sales supervisor (SQLModel, Alembic `0000_initial` in place, Jev through `core/jev.ask`, pytest with `tests/jev_fake.py`).

**Spec:** docs/superpowers/specs/2026-10-19-inventory-manager-design.md

## Global Constraints

The sales supervisor plan's list applies unchanged (docs/superpowers/plans/2026-10-19-sales-supervisor.md, Global Constraints), plus:
- Rule 3: `draft_order` has `risk: money`, `approval: always` is not needed (the risk alone requires an approver); the manifest lists `approvers: {inventory_manager.draft_order: [owner, admin]}`; the tool calls `approvals.request(...)` and raises `ApprovalRequired` through `guard` as the shift supervisor's cover override does; it never writes the order as approved.
- Rule 15: ids from `MANIFEST.id`; the scaffold already wired the registry, label, policy `use` lines, schema import and layout.
- The scaffolded files are the starting point: extend them, do not re-scaffold (`--force` is refused for a built id).
- `pre_parse`, `was_corrected`, `FILLER`, `NEGATIONS`, `TOTAL_WORDS` move to `mia/agents/parsing.py` in Task 2 with the sales supervisor importing from there; `tests/test_sales_actions.py` stays green.

## Review Focus (from checklist.md, pinned)

1. Branch scoping through casbin `read_all`/`write_all`; a clerk of the stall never reads or writes the mall (Task 3, `test_a_clerk_reads_only_their_branch_stock`).
2. A money tool never executes without an approval (Task 3, `test_an_order_waits_for_the_owners_approval`, `test_a_clerk_cannot_place_an_order`).
3. Business dates from the branch's local clock through `sales_supervisor.calc.business_date`'s rule (Task 3, `test_a_late_sell_out_belongs_to_the_closing_day`).
4. Due windows as datetimes across midnight, markers with sends, the summary urgent and the plan not (Task 6, `test_closing_summary_goes_to_head_staff_once`, `test_bake_plan_message_before_opening`).
5. A tapped decision validated against this agent's ACTIONS; a stale offer tap after a notification is plain text (Task 4, `test_a_stale_offer_tap_is_plain_text`).
6. Message parts in Jev state only, pseudonymised lists (Task 2, `test_item_instructions_carry_no_message_text`).
7. Every key in ten languages through the coverage test; tests assert through `t(...)` (Task 7).

---

### Task 1: Data

**Files:** Modify `node/mia/templates/retail/models.py` (`RetailIngredient`), `node/mia/agents/inventory_manager/models.py` (`StockEvent`, `SupplierOrder`), `node/migrations/versions/0000_initial.py`, `node/mia/templates/retail/seed.py` (ingredients, suppliers, four days of stock events, one approved order), `node/config/org/ferinos/settings.yaml` (`agents` gains `inventory_manager`). Test: `node/tests/templates/test_retail_seed.py` (counts), `node/tests/test_migrations.py`.

**Interfaces (produces):**
- `RetailIngredient(Stamped)` `retail_ingredients`: `branch_id: str | None` FK nullable, `name`, `short_codes: list[str]`, `unit: str`, `reorder_point: int`, `supplier: str | None`, `pack_price: int | None`, `currency: str`, `active: bool = True`.
- `StockEvent(BranchScoped)` `inventory_manager_stock_events`: `kind: str`, `item_id: str | None` FK `retail_items.id`, `ingredient_id: str | None` FK `retail_ingredients.id`, `quantity: int | None`, `unit: str | None`, `reason: str | None`, `at: dt.datetime` TZDateTime, `reported_by: str` FK person, `business_date: dt.date` index, `source_message_id: str | None`, `order_id: str | None`.
- `SupplierOrder(BranchScoped)` `inventory_manager_orders`: `supplier: str`, `lines: list[dict]` JSON, `currency: str`, `total: int | None`, `status: str`, `approval_id: str | None`, `requested_by: str`, `business_date: dt.date`.
- Seed constants `INGREDIENTS: list[tuple[str, list[str], str, int, str | None, int | None]]` (name, codes, unit, reorder point, supplier, pack price) with the eight rows of the spec.

- [ ] Failing tests: extend `test_org_template_selects_the_retail_seed` with `assert len(session.exec(select(RetailIngredient)).all()) == 8`, `>= 8` stock events per branch, one `SupplierOrder` with `status == "approved"`; `test_migrations` must stay green.
- [ ] Implement; `uv run pytest node/tests/templates/test_retail_seed.py node/tests/test_migrations.py --no-cov`.
- [ ] Full checks; commit `inventory: stock events and supplier orders (agent-owned), retail ingredients with reorder points and suppliers, the Ferino's seed and org config`.

---

### Task 2: Shared parsing, actions and decider

**Files:** Create `node/mia/agents/parsing.py`; modify `node/mia/agents/sales_supervisor/actions.py` (imports from parsing), `node/mia/agents/inventory_manager/actions.py`, `decider.py`; tests `node/tests/test_parsing.py` (moved pre_parse tests), `node/tests/test_inventory_actions.py`.

**Interfaces (produces):**
- `parsing.pre_parse(text, menu_tokens) -> tuple[list[Group], int | None]`, `parsing.was_corrected(text) -> bool`, `parsing.Group`, `parsing.find_times(text) -> list[tuple[str, dt.time]]` (ids `t0`, `t1`... with the parsed time; 12-hour with am/pm, 24-hour `HH:MM`, Filipino "alas <n>" with una, dos, tres, kuwatro, singko, sais, siyete, otso, nuwebe, diyes, onse, dose; afternoon assumed for "alas 2" when the shop is open then: keep it simple, `alas n` is `n` o'clock with `pm` when n is 1 to 6 else `am`, with a ponytail note).
- `ACTIONS`: `report_stock` (tool `record_events`), `bake_plan` (`plan_tomorrow`), `whats_low` (`low_stock`), `place_order` (`draft_order`), `receive` (`receive_delivery`), `answer_offer` (tool None; handled by the turn), `reply_only`, `clarify`; label keys `intent.inventory_manager.<action>` built from `MANIFEST.id`.
- `Query`: message, previous_mia_message, role, today, groups, items (`{id: "name (codes)"}` over active items and ingredients, with a parallel `kinds: {id: "item" | "ingredient"}`), times (`{id: "14:00"}`), suppliers (`{name: name}` from the branch's ingredients), offer_asked (previous Mia message in `offer_texts(lang)`), corrected.
- `build_request`: state `{message, previous_mia_message, sender_role, today, groups, times}`; questions `action`, one `item_<i>` per group (items and ingredients plus none), `kind` (sold_out, count, leftover, waste, low, received, not_stated), `reason` (too_dry, burnt, expired, dropped, other, not_stated), `time` (the time ids plus now), `supplier` (plus not_stated), `conversation`; `item` only without a number group (the sales rule); no message text in instructions.
- `_args`: `report_stock` -> `{"events": [{"kind", "item_id" or "ingredient_id", "quantity", "unit", "reason", "at"}], "source_message_id"}` where a group's kind defaults from the pick (a bare count is `count`; no group and kind sold_out with an item pick from `item` is one event with quantity None), a waste without a reason gives `missing = "reason"`; `place_order` -> `{"supplier", "lines": [{"ingredient_id", "quantity", "unit"}]}` with `missing = "supplier"` when more than one supplier fits and none stated; `receive` -> `{"lines": [...]}`; `bake_plan`, `whats_low` -> `{}`; `answer_offer` -> `{"yes": bool}` only when `offer_asked`, else missing "offer".

- [ ] Failing tests: `test_parsing.py` holds the moved tests plus `find_times` ("at 2pm" -> 14:00, "14:30", "alas dos" -> 14:00, none -> []); `test_inventory_actions.py`: "sold out of special at 2pm" -> one event kind sold_out item Special at 14:00; "only 5 ube left" -> count 5; "threw away 8 classic" with reason not_stated -> missing reason; "running low on rice flour" -> kind low ingredient; "order 10 trays of eggs from Aling Nena" -> place_order lines eggs 10 tray supplier Aling Nena; `test_item_instructions_carry_no_message_text`; a pseudonymised `groups` list (the shared decider test already covers lists; add one here for `times`).
- [ ] Implement; `uv run pytest node/tests/test_parsing.py node/tests/test_sales_actions.py node/tests/test_inventory_actions.py --no-cov`.
- [ ] Full checks; two commits: `agents: pre_parse, corrections and time finding shared in mia/agents/parsing.py` and `inventory: actions and the Jev request (kinds, reasons, times, suppliers), the argument mapping`.

---

### Task 3: Tools, manifest, policy, the approval path

**Files:** `node/mia/agents/inventory_manager/tools.py`, `calc.py` (pure: `plan`, `low`, `order_total`), `manifest.yaml` (grants, five tool rows, approvers), `node/config/policies/policy.csv`, `node/tests/conftest.py` (`CLOCK_USERS`), test `node/tests/test_inventory_tools.py`, `node/tests/test_inventory_calc.py`.

**Interfaces (produces):**
- `calc.plan(records: Sequence[Record], items: Sequence[str], today: dt.date, closes: dt.time) -> dict[str, Literal["more", "same", "fewer"]]` with `Record(kind, item_id, at, business_date)`; the rule of the spec's section 7.
- `calc.low(latest_counts: Mapping[str, int], reorder: Mapping[str, int], low_today: set[str]) -> list[str]`.
- `calc.order_total(lines, prices: Mapping[str, int | None]) -> int | None` (None when any line lacks a price).
- Tools `record_events(deps, RecordEventsInput, tool_call_id) -> RecordEventsOutput(recorded: list[EventOut], business_date)`, `low_stock(...) -> LowStockOutput(ingredients: list[LowOut])`, `plan_tomorrow(...) -> PlanOutput(lines: list[PlanLine], note_heuristic: bool)`, `draft_order(deps, DraftOrderInput, tool_call_id)`: `_check` write on orders, then `approvals.request(session, actor, tool_id, input, ...)` as the shift supervisor's override path and raise `ApprovalRequired` (read `mia/core/approvals.py` and `shift_supervisor/tools.py` for the exact call); on the approval decision the existing approvals flow calls back: implement `apply_order_approval(session, approval, actor)` registered the way cover override's approval is applied (find the hook in `core/approvals.py` or `chat/`; if approvals only record a decision and the tool is re-run, follow that pattern: the re-run with `deps.approved` containing the approval id writes the order as approved and notifies the requester); `receive_delivery(...)`: records `received` events and closes matching order lines.
- Business date through `sales_supervisor.calc.business_date` with the branch's hours (import the function; it is pure).
- Manifest: grants for the four data resources, `tool:inventory_manager.<name>:execute` for five, `approvers: {inventory_manager.draft_order: [owner, admin]}`; rows with `risk: money` for draft_order.
- Policy: clerk `record_events, low_stock, plan_tomorrow` execute, events `write_own`/`read_own`, `retail_ingredients` read; supervisor all five, events and orders read/write; admin `read_all`/`write_all` on both; owner inherits.

- [ ] Failing tests: calc (plan rule with four weekdays, the two-of-four thresholds, low list, order total None without a price); tools: record a sell-out and a count for Ana, `test_a_clerk_reads_only_their_branch_stock`, `test_a_clerk_cannot_place_an_order` (PermissionDenied), `test_an_order_waits_for_the_owners_approval` (ApprovalRequired, an Approval row, no order row with status approved), `test_an_approved_order_is_written_and_the_requester_told` (through the approvals decide path), `test_a_late_sell_out_belongs_to_the_closing_day` (00:30 after a 23:00 close), `test_receive_closes_the_order_line`.
- [ ] Implement; focused tests; full checks; commit `inventory: five tools behind rbac (a supplier order waits for the owner's approval), the bake plan and low-stock rules as pure code`.

---

### Task 4: Turn and replies, scenarios 1 to 4

**Files:** `node/mia/agents/inventory_manager/turn.py` (grow the scaffolded turn: tools, the reason question, the offer question, taps), `replies.py`, `node/mia/i18n/strings.py` (en, fi), test `node/tests/test_inventory_manager_chat.py` (extend the scaffolded file).

**Interfaces:** the turn mirrors the sales supervisor's (`_tapped`, `_query`, `_act`, `_failed`); `stock.which_reason` with five buttons whose values are the decision with the reason filled; `stock.offer_order` with Yes and No whose values are `answer_offer` decisions; a Yes runs `draft_order` for the low ingredient (quantity = reorder point times two, unit from the ingredient; said in the reply) and lands on the approval path; `replies.tool_reply` words each kind (`stock.sold_out` "{item} sold out at {time}", `stock.counted`, `stock.leftover`, `stock.waste` with the reason, `stock.low` plus the offer, `stock.order_waiting`, `stock.received`, `stock.plan` lines, `stock.low_list`); a tool refusal maps as the sales supervisor's (`sales.not_allowed.branch` style key `stock.not_allowed`).

- [ ] Failing tests through `run_turn` with the fake Jev: scenarios 1 to 4 (`test_a_clerk_reports_a_sell_out_with_the_time`, `test_a_clerk_counts_what_is_left`, `test_waste_with_a_reason_is_recorded`, `test_waste_without_a_reason_asks_one` then the tap records, `test_a_low_ingredient_offers_an_order` then Yes drafts and waits for approval, `test_a_stale_offer_tap_is_plain_text`, injection is data, the greeting).
- [ ] Implement; full checks; commit `inventory: the inventory manager answers in chat: sell-outs with times, counts, leftovers and waste (a reason asked with buttons), low ingredients with an order offer`.

---

### Task 5: Scenarios 5 to 8

**Files:** turn.py, replies.py, strings.py; test `test_inventory_manager_chat.py`.

- [ ] Failing tests: `test_the_bake_plan_follows_the_last_four_same_weekdays` (seeded sell-outs on two Saturdays make Special "more"), `test_what_is_low_lists_items_under_the_reorder_point` (LPG from the seed), `test_a_supervisor_drafts_an_order_and_the_owner_approves_it` (end to end: Marites asks, Rosa taps approve on the card, Marites gets `stock.order_approved`), `test_a_delivery_closes_the_order_line`, `test_a_clerk_asking_to_order_is_told_who_can`.
- [ ] Implement; full checks; commit `inventory: the bake plan, what is low, a supplier order approved by the owner on a card, deliveries received against the order`.

---

### Task 6: Due work

**Files:** `node/mia/agents/inventory_manager/due.py`, turn.py (`run_due`), strings.py; test `node/tests/test_inventory_due.py`.

**Interfaces:** `run_due(session, now) -> int`; windows through the same helpers the sales supervisor's due.py uses (import `_at`/`_after_close` style helpers if they are reusable, else copy the small ones and say so): `closing_summary` at closes plus 45 under the closing's business date (urgent), `plan_message` at opens minus 60 (not urgent); recipients via `alerts.supervisors` and the branch's clerks; markers `inventory.summary_sent`, `inventory.plan_sent`; the org gate (`MANIFEST.id in orgconfig.load().agents`).

- [ ] Failing tests at fixed clocks: `test_closing_summary_goes_to_head_staff_once`, `test_summary_crosses_midnight_under_the_closing_day` (23:00 close), `test_bake_plan_message_before_opening`, `test_nothing_runs_for_an_organisation_without_the_inventory_manager`, quiet hours (summary urgent, plan held).
- [ ] Implement; full checks; commit `inventory: due work on the tick: the closing stock summary to head staff and owners, the bake plan before opening`.

---

### Task 7: Ten languages

**Files:** the eight i18n modules, strings.py if a key lacks fi; `docs/questions.md` note under Q28 to Q35. Test: `node/tests/test_i18n_languages.py`, `test_i18n_variants.py`.

- [ ] Add every `stock.*` and `intent.inventory_manager.*` key to fil.py first, watch the coverage test name the rest, fill the seven others; placeholders identical; chat tests asserting a fil reply go through `t(...)`.
- [ ] Full checks; commit `i18n: the inventory manager's replies, questions and buttons in all ten languages (Philippine languages as machine drafts, Q28 to Q35)`.

---

### Task 8: Evals, gates and docs

**Files:** `node/tests/evals/inventory_manager_cases.py` (ten messages per scenario 1 to 8 per gated language, tune and gate halves by seed), `test_inventory_manager_evals.py` (the scaffolded harness, filled), `node/tests/evals/router_cases.py` (ten seeds per gated language for the inventory manager in both halves, `PENDING` emptied), the research reports, README, docs/layout.md, docs/questions.md (Q53 to Q55).

- [ ] Offline: the shape tests (counts, halves, no text in both halves, no Tagalog, `PENDING` empty).
- [ ] Run both gates once (tune once on the tune half if needed, rerun once), reports `docs/research/inventory-manager-<date>.md` and `router-<date>-inventory.md`, stated as they are.
- [ ] Docs; full checks; commit `inventory: decider eval set and gate, router seeds, reports, README and layout, questions`.

## Self-review

Every spec scenario has a test (1 to 4 in Task 4, 5 to 8 in Task 5, 9 and 10 in Task 6); every Review Focus line has a task and a test; the data standard gate is satisfied (no core change, Q53 recorded); `pre_parse` moves once (Task 2) and both agents import it.
