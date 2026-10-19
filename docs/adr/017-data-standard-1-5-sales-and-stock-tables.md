# ADR 017: Data standard 1.5, the sales and stock tables become shared

## Status

Accepted (19 Oct 2026, the owner).

## Context

Rule 9 makes a table shared once a second agent reads it. The sales supervisor's counts, targets
and notes and the inventory manager's stock events were agent-owned (`sales_supervisor_*`,
`inventory_manager_stock_events`) until a second reader existed (Q39, Q53). The second readers
are now known: the branch_manager (the day's sales, the why answers, stock in the weekly
summary), the bookkeeper (sales and stock for the books) and customer_service (sell-out
answers, D35). Q59 asked whether the HR tables move in the same promotion.

## Decision

- Data standard 1.5: four tables move to mia/core/models.py under core names.
  - `sales_supervisor_counts` (SalesCount) becomes `sales_counts`.
  - `sales_supervisor_targets` (SalesTarget) becomes `sales_targets`.
  - `sales_supervisor_notes` (SalesNote) becomes `sales_notes`.
  - `inventory_manager_stock_events` (StockEvent) becomes `stock_events`.
- Fields, indexes and foreign keys are unchanged; only the table and index names change.
- `inventory_manager_orders` (SupplierOrder) stays agent-owned: it has one reader so far.
- The HR tables (`hr_officer_*`, Q59) are not part of this promotion and stay agent-owned.

## Consequences

- The rename is an in-place edit of `0000_initial` (no new migration), since there is no
  candidate release yet (rule 14). Dev databases are rebuilt: `rm data/mia.db && uv run mia
  migrate && uv run mia seed`.
- The rbac data resources take the table names (`data:sales_counts` and so on). Every role keeps
  exactly the rights it had: the admin wildcards `data:sales_supervisor_*` became explicit grants
  on the three sales tables, and `data:stock_events` got the admin `read_all` and `write_all`
  that `data:inventory_manager_*` gave it. The resources are bare table names because the tools
  derive them from `__tablename__`; putting them under `data:core.*` would not have widened
  anything either (the supervisor already reads and the admin already writes all four). The
  `data:core.<singular>` names (`core.timesheet`, `core.absence`, `core.incident`) are the older
  convention of the data standard 1.4 tables. A new reader gets its grants with its own agent.
- Event rows are never renamed (rule 2): events written before the rebuild carry the old
  `entity_type`; new rows carry the core names. No code reads these entity types.
- The branch_manager and the bookkeeper may now be built on these tables; customer_service may
  read `stock_events` for sell-out answers (D35).
