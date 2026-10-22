# Sales operations: sessions, receipts, lines and payments (data standard 1.9 proposal)

Date: 22 October 2026. Branch feat/multi-agent at 0c73c91, reference at 70dd6f5. Proof shop:
Ferino's Bibingka (two kiosks and a commissary). Shapes followed:
docs/superpowers/specs/2026-10-19-sales-supervisor-design.md and
2026-10-20-bookkeeper-design.md.

**Status: proposal, waiting for the owner (gate 1).** Adding core tables is a data standard
change (rule 9), so nothing here is built and no migration is edited until the owner answers
section 11 (Q118 in docs/questions.md). The owner asked: "look for database schema of ERP and
create tables that are sales related", then "If you can get entire schema of odoo that is a good
starting point. We can start designing the backend, but focus on sales for now".

## 1. Goal

Let Ferino's keep today's count-based reporting exactly as it is, while making room for
receipt-level sales: one row per customer sale, its lines and its payments by tender, inside a
clerk's shift that opens at check-in and closes with the cash count. The design starts from
Odoo 17.0's point of sale (docs/reference/odoo-schema, extracted from the source models, commit
3682340 of odoo/odoo 17.0) and keeps the smallest set an ERP accountant would recognise.

Out of scope: the till itself (a POS screen or app that writes receipts is its own spec), BIR
accreditation of receipts, loyalty, invoices and a general ledger (section 10 orders them).

## 2. What exists today and what it lacks

Data standard 1.8 (node/mia/core/models.py, STANDARD_VERSION "1.8"):

| Table | Holds | Writer |
| --- | --- | --- |
| `sales_counts` (core, 1.5, tender 1.6) | one clerk's reported count of one item for a business date: quantity, amount, tender, supersedes and superseded_by | sales_supervisor |
| `sales_targets`, `sales_notes` (core, 1.5) | day or month targets; the clerk's words about the day | sales_supervisor |
| `stock_events` (core, 1.5) | sold_out, count, leftover, waste, low, received | inventory_manager, sales_supervisor |
| `customer_orders` (core, 1.8) | a customer's pickup or delivery order, lines as JSON | customer_service |
| `retail_items`, `retail_item_prices` (template) | what is sold, the default price, a branch's dated price from effective_on, bundle components, unit cost | seed, branch_manager |
| `bookkeeper_cash_counts` (agent-owned) | the closing count of a business date: counted, expected, difference | bookkeeper |
| `bookkeeper_settlements`, `bookkeeper_payouts` (agent-owned) | GCash and Maya settlements, Grab and Foodpanda payouts matched to sales by tender | bookkeeper |
| `branch_manager_experiments` (agent-owned) | a 14-day price, promo or bundle test of one item: from_price, to_price, starts_on, ends_on | branch_manager |

What it lacks for receipt-level sales:

- No single sale. A count is an aggregate a clerk types ("3 special 5 classic"), so there is no
  receipt number, no time of sale, no split tender within one sale, and no way to void or refund
  one sale; a correction supersedes a whole count.
- No shift. The cash count is per branch and business date; with two clerks on one day at the
  Mall kiosk there is no opening float and no count per clerk.
- No discount. A count's amount is quantity times price unless the clerk states a total, so a
  senior or PWD discount or a promo shows only as a lower amount with no reason.
- No link from a sale to the price that applied. The dated price is read at report time.

## 3. The reference designs mapped to Ferino's

Odoo names below are exact, from docs/reference/odoo-schema/sales-first.md and
point_of_sale.md. ERPNext names are from memory (not browsed, not checked against its source):
Customer, Item, Item Price, Price List, Pricing Rule, Sales Order and Sales Order Item, Sales
Invoice and Sales Invoice Item, Payment Entry, POS Profile, POS Opening Entry, POS Invoice and
POS Invoice Item, POS Closing Entry, Mode of Payment.

Odoo has two sales paths: the quotation path (`sale.order`, then `stock.picking`, then an
`account.move` with `move_type` `out_invoice`, then an `account.payment`) and the counter path
(`pos.session` on a `pos.config`, `pos.order` rows paid by `pos.payment` rows, one journal entry
per session at closing, `pos.session.move_id`). A kiosk is the counter path; Ferino's pickup and
delivery orders are a light quotation path.

| Odoo 17 | ERPNext (from memory) | Ferino's today | This proposal |
| --- | --- | --- | --- |
| `res.partner` | Customer | `person` (staff), `customer_service_customers` (the public) | stays |
| `product.template`, `product.product` | Item (variants as Item with attributes) | `retail_items` (no variants: a flavour or a box is its own item, bundles in `components`) | stays |
| `product.pricelist`, `product.pricelist.item` | Price List, Item Price | `retail_item_prices` (one dated price per branch and item) | stays |
| `product.pricelist.item` with `date_start`, `date_end`; `loyalty.program` with `program_type` `promotion` | Pricing Rule | `branch_manager_experiments` (price, promo, bundle with dates) | stays, no pricing rule table |
| `sale.order`, `sale.order.line` | Sales Order, Sales Order Item | `customer_orders` (lines as JSON) | stays; a receipt may name the order it paid |
| `pos.config` | POS Profile | the branch (one kiosk, one till) | none |
| `pos.session` | POS Opening Entry, POS Closing Entry | `bookkeeper_cash_counts` (per date) | `sales_sessions` |
| `pos.order` | POS Invoice (Sales Invoice with is_pos) | `sales_counts` (aggregate) | `sales_receipts` |
| `pos.order.line` | POS Invoice Item | none | `sales_receipt_lines` |
| `pos.payment` | the payments table of a POS Invoice | `sales_counts.tender` | `sales_payments` |
| `pos.payment.method` | Mode of Payment | the code list `TENDERS` (fee and commission rates in settings) | stays |
| `account.move`, `account.move.line` | Sales Invoice, GL Entry | the bookkeeper's computed sales journal | later (section 10) |
| `account.payment` | Payment Entry | `bookkeeper_settlements`, `bookkeeper_payouts` | stays |
| `loyalty.program`, `loyalty.card` | Loyalty Program | none (no suki credit, Q86) | none |

Two Odoo facts that shape the proposal: Odoo 17 has no `account.payment` state of its own (a
payment uses its journal entry's `state` through `_inherits` on `move_id`), and loyalty points
live on `loyalty.card` (no points history table). Neither is copied: Ferino's has no ledger yet
and no loyalty.

## 4. Proposed tables (core, data standard 1.9)

All four are core under rule 9: the sales supervisor reads them for reports, the bookkeeper for
the close, settlements, the journal and profit, the branch manager for experiments, the
production planner for demand, and a till writes them. Conventions: `BranchScoped` (ULID `id`,
`branch_id`, `created_at`, `updated_at`), money as integer minor units with `currency`, times
`TZDateTime` with offset, `business_date` a local date by the sales supervisor's existing rule,
every write through a service in mia/core (rule 1) via mia/core/store.py so each row emits an
event. A receipt with its lines and payments is one short write transaction (rule 11).

### 4.1 `sales_sessions` (Odoo `pos.session`)

A clerk's shift at a kiosk: opened at check-in, closed by the cash count.

| Field | Type | Notes |
| --- | --- | --- |
| `person_id` | str, FK person, indexed | the clerk (Odoo `user_id`) |
| `visit_id` | str or None, FK visit | the shift's Visit from check-in (D39), None when opened without a roster |
| `business_date` | date, indexed | the opening's business date |
| `opened_at` | TZDateTime | Odoo `start_at` |
| `closed_at` | TZDateTime or None | Odoo `stop_at` |
| `state` | str, indexed | `open` or `closed` |
| `opening_float` | int | Odoo `cash_register_balance_start`; defaults to the last closed session's counted |
| `counted` | int or None | Odoo `cash_register_balance_end_real` |
| `expected` | int or None | Odoo `cash_register_balance_end` (computed there, stored here at close) |
| `difference` | int or None | counted less expected (Odoo `cash_register_difference`, computed there) |
| `currency` | str, 3 | |
| `closed_by` | str or None, FK person | head staff who counted (bookkeeper spec: cashiering is head staff's) |
| `note` | str | data, never instructions |

At most one open session per person and branch (a partial unique index, `state = 'open'`).
`expected` is code (rule 7): opening_float plus the session's cash payments (refunds negative)
less the cash that left the drawer (`drawer_out`, Q99's rule). Expected and difference are
frozen at close because the close is what the owner signs off; Odoo recomputes them.
Dropped from `pos.session`: `config_id`, `name`, `sequence_number`, `login_number`,
`cash_journal_id`, `move_id`, `statement_line_ids`, `bank_payment_ids`, `picking_ids`,
`update_stock_at_closing`, `rescue`, `opening_notes` (one `note` is enough), and the states
`opening_control` and `closing_control` (a kiosk opens and counts in one step each).
`__redact__`: none (cash amounts are already on the chain in `bookkeeper_cash_counts`).

### 4.2 `sales_receipts` (Odoo `pos.order`)

One customer sale or one refund.

| Field | Type | Notes |
| --- | --- | --- |
| `session_id` | str, FK sales_sessions, indexed | required (Odoo `session_id`) |
| `receipt_no` | str, 32 | the printed or shown number (Odoo `pos_reference`); unique with `branch_id` |
| `business_date` | date, indexed | from `sold_at` |
| `sold_at` | TZDateTime | Odoo `date_order` |
| `clerk_id` | str, FK person | Odoo `user_id` |
| `customer_id` | str or None, FK customer_service_customers | when known (Odoo `partner_id`); the 1.8 precedent |
| `order_id` | str or None, FK customer_orders | the order this sale paid at pickup |
| `kind` | str | `sale` or `refund` |
| `refund_of` | str or None, FK sales_receipts | the receipt a refund returns |
| `subtotal` | int | sum of the line totals |
| `discount` | int | receipt-level discount, minor units, 0 when none |
| `discount_reason` | str or None | `senior`, `pwd`, `promo`, `staff`, `other` |
| `total` | int | subtotal less discount (Odoo `amount_total`); negative on a refund |
| `currency` | str, 3 | |
| `status` | str, indexed | `paid` or `voided` |
| `voided_by` | str or None, FK person | |
| `void_reason` | str or None | data, never instructions |
| `approval_id` | str or None, FK approval | the void or refund approval (section 9) |
| `source` | str | `pos` (a till) or `chat` (typed by a clerk) |
| `source_message_id` | str or None | |

Code checks: total equals subtotal less discount; the payments add up to the total. A refund is
a new receipt with negative lines that point at the lines they return (the Odoo way:
`refunded_orderline_id`), never an edit of the sale. A void marks a receipt of the open session
`voided` (Odoo `state` `cancel`); once the session is closed only a refund is possible.
Dropped from `pos.order`: `name`, `ticket_code`, `sequence_number`, `shipping_date`,
`to_invoice`, `config_id`, `company_id`, `amount_tax` (VAT stays computed by the bookkeeper from
the journal, D38), `amount_paid` and `amount_return` (change is code at the till, not stored),
`tip_amount`, `is_tipped`, `pricelist_id`, `fiscal_position_id`, `account_move`, `sale_journal`,
`picking_ids`, `procurement_group_id`, `note`, and the states `draft`, `done`, `invoiced`.
`__redact__`: `void_reason` (free text stays on the node).

### 4.3 `sales_receipt_lines` (Odoo `pos.order.line`)

| Field | Type | Notes |
| --- | --- | --- |
| `receipt_id` | str, FK sales_receipts, indexed | |
| `item_id` | str, FK retail_items, indexed | Odoo `product_id`; a bundle is one line of its item |
| `quantity` | int | negative on a refund (Odoo `qty`) |
| `unit_price` | int | the dated price at `sold_at` (Odoo `price_unit`) |
| `price_id` | str or None, FK retail_item_prices | the dated row used; None means the item's default price |
| `experiment_id` | str or None, FK branch_manager_experiments | the running test whose price applied |
| `discount` | int | line discount in minor units (Odoo `discount` is a percent; percent rounding is code) |
| `line_total` | int | quantity times unit_price less discount (Odoo `price_subtotal_incl`) |
| `refunded_line_id` | str or None, FK sales_receipt_lines | Odoo `refunded_orderline_id` |
| `currency` | str, 3 | |

No variant column: Ferino's sells no variants (each flavour and the Box of 4 is its own
`retail_items` row), the Odoo split of `product.template` and `product.product` is dropped.
Dropped from `pos.order.line`: `full_product_name`, `name`, `tax_ids`, `price_subtotal` (tax
excluded; no tax on lines), `total_cost` (profit reads `retail_items.cost`), `pack_lot_ids`,
`customer_note`, `combo_parent_id`, `uuid`, and the loyalty fields. The experiment link is the
one FK from core to an agent-owned table besides the customer; it is nullable and read only for
the experiment's result.

### 4.4 `sales_payments` (Odoo `pos.payment`)

| Field | Type | Notes |
| --- | --- | --- |
| `receipt_id` | str, FK sales_receipts, indexed | Odoo `pos_order_id` |
| `session_id` | str, FK sales_sessions, indexed | copied for the close's cash sum |
| `tender` | str, 16, indexed | one of `TENDERS` (Odoo `payment_method_id`) |
| `amount` | int | the amount applied, net of change; negative on a refund |
| `currency` | str, 3 | |
| `paid_at` | TZDateTime | Odoo `payment_date` |
| `reference` | str or None, 64 | the GCash or Maya reference number, for settlement matching |

Dropped from `pos.payment`: `is_change` (change is never stored), `card_type`,
`cardholder_name`, `transaction_id`, `payment_status`, `ticket`, `account_move_id`,
`company_id`. `__redact__`: none.

### Why tables and not JSON lines

`customer_orders` keeps its lines as JSON, and that stays. Receipts are different: the day's
sales by item and by tender is read every day by four agents over thousands of rows, a refund
points at one line, and settlements sum payments by tender. Those are plain indexed queries on
tables and awkward ones on JSON.

## 5. What stays, what is derived

Stay unchanged: `sales_counts`, `sales_targets`, `sales_notes`, `stock_events`,
`customer_orders`, `retail_items`, `retail_item_prices`, every `bookkeeper_*` table,
`branch_manager_experiments`. No pricing rule or promo table: `retail_item_prices` is the
pricelist (one dated price per branch) and `branch_manager_experiments` already holds price,
promo and bundle tests with dates; a promo price at the till is the running experiment's
`to_price`, linked on the line.

Derived, never stored:

- The day's sales by item and tender is one query, `sales.day_sales(branch, date)` in mia/core:
  on a counts day it reads the live `sales_counts`; on a receipts day it reads the `paid`
  receipts' lines (by item) and payments (by tender), refunds included as negatives. The
  sales supervisor's reports, the bookkeeper's `tender_sales` and journal, the branch manager's
  experiment results and the planner's forecast all read through it.
- Session totals, the day's receipt count, average ticket and discounts by reason: queries.
- A branch's expected cash for a date: the sum of its closed sessions on a receipts day; the
  existing `bookkeeper_cash_counts` rule on a counts day.

### How `sales_counts` relates to receipts

A count is a clerk's aggregate report; a receipt is the sale itself. For one branch and business
date exactly one of them is the source of sales, never both written. A branch setting,
`sales.receipts_from` (a local date, absent today), names the first receipts day. Before it,
everything works as now. From it, the sales supervisor writes no counts: a clerk's count message
gets the day's receipts figures back as a check, and a difference over the threshold is told to
head staff (reconciled, not stored). The bookkeeper's closing count on a receipts day closes the
open sessions instead of writing a `bookkeeper_cash_counts` row. So Ferino's runs on counts until
the owner sets the date, and nothing double counts.

## 6. Who writes each table

| Table | Writes | Reads |
| --- | --- | --- |
| `sales_sessions` | opened by the core service on a retail clerk's check-in (shift supervisor) or at a till's sign-in; closed by the bookkeeper's closing count (head staff) | sales_supervisor, bookkeeper, branch_manager |
| `sales_receipts`, `sales_receipt_lines`, `sales_payments` | a future till through `sales.record_receipt`; voids and refunds through `sales.void_receipt` and `sales.refund_receipt` | sales_supervisor, bookkeeper, branch_manager, production_planner, customer_service (its order paid) |
| `sales_counts` | sales_supervisor, counts days only | as today, through `day_sales` |

The rbac data resources take the table names (`data:sales_sessions` and so on); the admin gets
`read_all` and `write_all` like the 1.5 tables, other grants arrive with the writer (the till's
own spec), and a supervisor stays within their branch.

## 7. Migration plan (rule 14)

There is no candidate release yet, so `0000_initial` is edited in place: four new tables with
their indexes, the unique (`branch_id`, `receipt_no`) and the partial unique open session. No
existing column changes. `STANDARD_VERSION = "1.9"`; the spec.md data standard table gains four
rows; ADR 022 records the decision; the rights-equality test pins the new resources. Dev
databases are rebuilt: `rm data/mia.db && uv run mia migrate && uv run mia seed`. The seed adds
no receipts until a till exists (Ferino's stays on counts). From the first candidate on, the same
change would be migration 0001.

## 8. Order of work, after the owner's yes

1. Models, the migration edit, ADR 022, the spec.md rows, the rbac lines.
2. `sales.day_sales` in mia/core, and the sales supervisor and bookkeeper moved onto it with
   their tests unchanged (counts days).
3. The session, receipt, void and refund services with unit tests (totals, the payment sum,
   negative tests for a void after close and a refund without approval).
4. The till: its own spec.

## 9. Risks

- **Double counting.** A count and a receipt for the same sale. Guarded by one source per
  branch and date (`sales.receipts_from`) and one read path (`day_sales`); a test writes both
  and asserts the count is refused on a receipts day.
- **Voids and refunds.** The classic till fraud is a void after the customer left. A void is
  allowed only on the open session and records who; a refund is a new receipt pointing at the
  original lines and cannot return more than was sold. Both are money risk (rule 3): proposed,
  a void needs head staff's approval and a refund the owner's or admin's (question 4).
- **Discounts.** Senior citizen and PWD discounts are a legal 20 percent with VAT exemption in
  the Philippines; the reason is stored so the bookkeeper's VAT can exclude them. The ID number
  the law asks a shop to log is personal data and is not proposed here (question 5).
- **Not an official receipt.** These rows are internal records. A BIR-accredited POS or official
  receipt is a separate legal step; until then the BIR sales journal stays the bookkeeper's.
- **Prices at the time.** `unit_price` is copied from the dated price at `sold_at`, so a later
  price change never rewrites a sale.
- **Empty tables.** Without a till nobody writes receipts; the tables would sit empty
  (question 1 offers to wait).

## 10. How the backend would grow (sketch, not designed)

After sales, in this order, each its own spec and data standard step:

1. **Purchase and stock** (Odoo `purchase.order`, `purchase.order.line`, `stock.move`,
   `stock.quant`): `supplier_orders` lines as rows, received goods and receipt lines as stock
   moves, stock on hand derived.
2. **HR attendance and leave** (Odoo `hr.attendance` with `check_in`, `check_out`; `hr.leave`):
   today's Visit actual times already act as attendance; `leave` exists; the step is mostly
   naming and reports.
3. **Accounting** (Odoo `account.account`, `account.journal`, `account.move`,
   `account.move.line`): one journal entry per closed session (as `pos.session.move_id`),
   settlements and payouts as payments, the sales journal stored instead of computed.

## 11. Questions for the owner (Q118)

1. Add the four tables `sales_sessions`, `sales_receipts`, `sales_receipt_lines` and
   `sales_payments` to the data standard now (1.9), before any till writes them? (No means the
   design is approved and the tables arrive with the till.)
2. Are all four core tables (shared), not agent-owned?
3. Is a session one clerk's shift (several sessions a day at the Mall kiosk, each with its own
   float and count), not one per kiosk per day?
4. Does a void need head staff's approval, and a refund the owner's or admin's?
5. Leave the senior and PWD ID number out of these tables for now?
6. Does Ferino's stay on counts until you set a receipts date per kiosk, with counts and
   receipts never both the source of one day's sales?

With yes to 1 and 2 this becomes data standard 1.9 and ADR 022.

## 12. Carried over (after data standard 1.9, 22 Oct 2026)

Built with 1.9 (ADR 022): the four tables, `mia/core/sales.py` (`open_session`, `close_session`,
`record_receipt` for sales and refunds, `void_receipt`, `receipts`, `day_sales`), the setting
`sales.receipts_from` (branch name to first receipts day; empty at Ferino's, so every kiosk is on
counts) and the human rights in policy.csv. What was waiting for the till or a receipt entry
path then (the chat path, the void and refund cards, the moves onto `day_sales` and the
sessions are now built, see the dated note below):

- The till's own receipt tools (the till's own spec); the read grants of the sales supervisor,
  bookkeeper, branch manager and inventory manager are in (round 1), the production planner's
  and the customer service's arrive with their reads.
- Voiding a sale together with its refunds (refused in v1).
- A running experiment's `to_price` at the till: `experiment_id` is stored as given, the unit
  price is the dated price.

### Sales receipts in the chat (22 Oct 2026, plan 2026-10-22-sales-receipts-chat)

Built by that plan: the chat path (a clerk on a receipts kiosk rings a receipt with `source`
chat at the dated price, `sales_supervisor.record_receipt`; a count typed there with a receipt
word is rung as a receipt, and one without asks first with the computed receipt on a button; a
receipt typed on a counts kiosk is a count, said once); the void and refund cards
(`sales_supervisor.void_receipt` raises `sales.void` for head staff, `refund_receipt` raises
`sales.refund` for the owner or admin with `evidence["amount"]` the computed amount, each
approval used once); the session at check-in (a clerk's check-in on a receipts kiosk opens her
drawer with the branch's `sales.opening_float`, a cover's at the visit's kiosk) and at the count
(the bookkeeper's closing count closes a drawer: the only one open when the date has no count
yet, else the one head staff names on its button; a recount never closes a drawer nobody named,
and a correction of a receipts day's count says it is final); a cover's sales turn works at the
shop of her checked-in visit of the day (`sales_supervisor.tools.at_visit`); the moves onto
`day_sales` (the sales supervisor's today and the owner's report, the bookkeeper's
`tender_sales`, the BIR sales journal and the cost of goods in `monthly_profit`); the closing
reminder and the missing counts notice are skipped on a receipts day (not moved); and the
clerk's receipts read in the chat (`read_receipts`, today or last). Jev is offered the receipt
actions (record, void, refund, read) and `receipts_which` only on a receipts kiosk, so a counts
kiosk's request is the one before the plan, and a counts kiosk reads a typed total only after a
receipt word. The end to end day is `test_a_receipts_day_at_the_mall_kiosk` in
tests/test_day_sales_clerk.py.

**Do not switch a kiosk to receipts yet** (`sales.receipts_from`): the branch manager's reads
and the production planner's forecast below still read counts only, so on a receipts day they
see no sales. Switch a kiosk only after they move onto `day_sales` (their own plan), and after
a Jev run on the counts kiosks' corrections.

Still carried over:

- Split tender and discounts (senior, PWD) in the chat; a receipt has one tender and no discount.
- The app's check-in route (`mia/api/schedule.py`) opens no session; the chat is a receipts
  kiosk's check-in path (Q125).
- `period_report` on receipts (it reads the counts; sales_supervisor/tools.py `period_report`).
- The branch manager's reads onto `day_sales` (each reads `live_counts`, counts only):
  branch_manager/tools.py `daily` (experiment results), `branch_numbers` (two reads, best days
  and the year), `coaching`, `_branch_week` and `monthly_letter`; branch_manager/due.py
  `_amounts`.
- The production planner's demand forecast onto `day_sales`: production_planner/tools.py
  `kiosk_data` (a receipts kiosk's forecast falls toward zero).
- `drawer_out` in the session's own expected cash (the count's expected holds it, Q122).
- A session's handover float (each session opens with the branch's float).
- Voiding a sale together with its refunds (refused in v1).
- A running experiment's `to_price` at the till (the unit price is the dated price).
- The owner's report total from `by_tender` once receipt discounts exist (it sums `by_item`,
  before the discount, today).
- `_morning` and `_why` read counts only on a receipts day.
- A clerk's `today` totals are branch-wide while her receipts list is her own.
- `tender_sales` over a month or quarter is one `day_sales` query pair per day.
- A refund is paid only from the requester's own drawer (Q127).
- Head staff cannot request a refund in the chat.
- A stale drawer is closed by the next count, the CashCount dated by the closing date.
- A cover's void or refund card goes to her home branch's deciders (an approval's branch is
  the requester's), while the handler runs at the receipt's kiosk.
- Two open drawers whose clerks share a first name get one button between them.
- The money guard does not recognise a `sales.void` approval in `deps.approved` (it fails
  closed: an approved void runs through its handler, never a second tool call).
