# ADR 020: Data standard 1.8, customer orders shared

## Status

Accepted (21 Oct 2026, the owner, D39).

## Context

Customer orders lived in `customer_service_orders`, agent-owned by the customer service (Q67's
assumed answer and D35: promotion with an ADR once the production planner or the sales
supervisor reads them, the Q39 precedent). The production planner reads confirmed orders
(lines, status, pickup_at, branch_id) to plan tomorrow's batches per kiosk, so the table becomes
shared (rule 9; Q91 in the planner's spec, answered by D39). D39 named
data standard 1.7 and ADR 019 for this; the retail shift supervisor's incident kinds took both
first, so this change is 1.8 and ADR 020 (the plan's numbering note of 21 Oct 2026).

## Decision

- Data standard 1.8, in mia/core/models.py: `CustomerOrder`, table `customer_orders`, with the
  fields, constraints, docstring and `__redact__ = frozenset({"delivery_note"})` of the old
  `customer_service.models.Order` unchanged. `customer_id` still references
  `customer_service_customers.id` and `Complaint.order_id` references `customer_orders.id`.
- `STANDARD_VERSION = "1.8"`; the customer service's manifest declares 1.8.
- The customers, messages and complaints stay agent-owned (`customer_service_*`): the planner
  never reads who ordered, only the order lines.
- The one rename only: no field, column, foreign key target or redaction changes.

## Consequences

- Rights kept equal: the policy lines on `data:customer_service_orders` are renamed to
  `data:customer_orders` (customer read_own and write_own, clerk and supervisor read and write,
  the agent role read and write through its manifest), and the admin wildcard
  `data:customer_service_*` gains explicit `read_all` and `write_all` lines for
  `customer_orders` (the owner inherits). `test_shared_tables_keep_exactly_the_rights_they_had`
  pins the role-by-action table, the customer role included.
- An in-place edit of `0000_initial` (table, index names and the complaint foreign key), since
  there is no candidate release yet (rule 14). Dev databases are rebuilt: `rm data/mia.db &&
  uv run mia migrate && uv run mia seed`.
- Event rows written under the old table name are never renamed (rule 2); new rows name
  `customer_orders`.
- The production planner reads `customer_orders` through its agent role only (`read_all`, no
  `on_behalf_of`); no person gains a cross-branch right. Its grants arrive with the planner.
