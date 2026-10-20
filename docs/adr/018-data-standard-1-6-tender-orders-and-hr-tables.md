# ADR 018: Data standard 1.6, a tender on sales counts, supplier orders and the HR tables shared

## Status

Accepted (20 Oct 2026, the owner, D38).

## Context

The bookkeeper matches GCash and Maya settlements and Grab and Foodpanda payouts to the day's
sales, so a count must say how it was paid (Q84). Its monthly profit subtracts supplier spend
and payroll (Q85), so it becomes a second reader of the inventory manager's supplier orders and
the HR officer's payslips. Rule 9 makes a table shared once a second agent reads it, and Q59
left the HR tables agent-owned until a second reader existed.

## Decision

- Data standard 1.6, five changes in mia/core/models.py:
  - `sales_counts` gains `tender` (`str`, max 16, indexed, default `cash`), one of the code
    list `TENDERS`: cash, gcash, maya, grab, foodpanda. The clerk says it when it is not cash;
    the sales supervisor's count parser reads a tender word and never takes it for an item.
  - `inventory_manager_orders` (SupplierOrder) becomes `supplier_orders`.
  - `hr_officer_contracts` (Contract) becomes `contracts`.
  - `hr_officer_payslips` (Payslip) becomes `payslips`.
  - `hr_officer_leave` (Leave) becomes `leave`.
- Fields, indexes, foreign keys, the payslip's unique constraint and every `__redact__` set are
  unchanged; only the table and index names change.

## Consequences

- The rename and the new column are an in-place edit of `0000_initial` (no new migration), since
  there is no candidate release yet (rule 14). Dev databases are rebuilt: `rm data/mia.db &&
  uv run mia migrate && uv run mia seed`.
- The rbac data resources take the table names (`data:supplier_orders`, `data:contracts`,
  `data:payslips`, `data:leave`). Every role keeps exactly the rights it had: the admin
  wildcards `data:inventory_manager_*` and `data:hr_officer_*` became explicit `read_all` and
  `write_all` grants on the four tables, and the own-row rules (`read_own`, `write_own`) of
  staff on contracts, payslips and leave are kept. The rights-equality test in test_rbac covers
  the 1.5 and 1.6 tables.
- Event rows are never renamed (rule 2): events written before the rebuild carry the old
  `entity_type`; new rows carry the core names. No code reads these entity types.
- The bookkeeper reads payslip totals through the admin's existing `read_all` on
  `data:payslips` (owner and admin only, never a supervisor, never per person); no human role
  gains a right. Its own grants come with its agent.
