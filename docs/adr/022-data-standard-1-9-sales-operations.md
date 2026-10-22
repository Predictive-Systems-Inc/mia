# ADR 022: Data standard 1.9, sales operations tables

## Status

Accepted (22 Oct 2026, the owner, D43).

## Context

A kiosk's sales are the clerks' aggregate counts (`sales_counts`, 1.5). The owner asked for a full
sales operation, receipt by receipt, from an ERP schema. The design
(docs/superpowers/specs/2026-10-22-sales-operations-design.md) maps Odoo's `pos.session`,
`pos.order`, `pos.order.line` and `pos.payment` onto Ferino's. The owner answered Q118 on
22 October 2026 (D43): the four tables join the standard now as core tables, a session is one
clerk's shift, a void needs head staff's approval and a refund the owner's or admin's (money
risk), and each kiosk uses counts or receipts as the source of a day's sales, never both.

## Decision

- Data standard 1.9, in mia/core/models.py: `SalesSession` (`sales_sessions`), `SalesReceipt`
  (`sales_receipts`), `SalesReceiptLine` (`sales_receipt_lines`) and `SalesPayment`
  (`sales_payments`), with the fields of the design's section 4. Branch scoped, ULIDs, integer
  minor units with a currency, TZDateTime. One open session per person and branch (a partial
  unique index), `receipt_no` unique per branch, `__redact__ = {"void_reason"}` on receipts.
- `STANDARD_VERSION = "1.9"`; the manifests of the agents that move with it declare 1.9.
- Services in mia/core/sales.py, each write through store with an event: `open_session`
  (`sales.session_opened`), `close_session` (`sales.session_closed`, expected and difference
  frozen), `record_receipt` (`sales.receipt_recorded` or `sales.refund_recorded`, with
  `sales.payment_recorded` per payment, one flush), `void_receipt` (`sales.receipt_voided`).
  Totals, the payment sum, the dated unit price and the expected cash are code (rule 7); a
  refusal raises before any row is written.
- A void is checked against an approved `sales.void` approval of that receipt decided by head
  staff (supervisor or above), a refund against an approved `sales.refund` approval of the sale
  decided by the owner or an admin; both carry money risk and are used once.
- The source of a day: org setting `sales.receipts_from`, a branch name to its first receipts
  day. `sales.day_sales(session, branch_id, business_date)` returns sales by item and by tender
  from the live counts before that day (or with no entry) and from the paid receipts from it.
  Ferino's has no entry, so every kiosk stays on counts.

## Consequences

- No existing table changes. `0000_initial` is edited in place (no candidate release yet,
  rule 14) and dev databases are rebuilt: `rm data/mia.db && uv run mia migrate && uv run mia
  seed`.
- Rights: clerk read_own and write_own, supervisor read and write, admin read, write, read_all
  and write_all (the owner inherits) on the four `data:` resources; the shared-rights table in
  test_rbac pins them. Agent grants arrive with the agent that reads the tables, the receipt
  tools and the void and refund cards with the till (the design's section 12).
- A core service reads the retail template (hours for the business date, dated prices); the
  tables already reference `retail_items`.
- `day_sales` repeats the sales supervisor's live count filter because core cannot import an
  agent; a test pins the two equal until the agents read through `day_sales`.
