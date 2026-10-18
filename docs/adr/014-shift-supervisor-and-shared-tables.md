# ADR 014: The dispatcher becomes the shift supervisor; its tables become shared

## Status

Accepted.

## Context

Agents are named after real jobs (D16). Retail (the sales supervisor agent, part 2) needs the
same work the dispatcher does (rosters, absences, cover, check-in) under a shop's job title.
Its tables carried the agent prefix (rule 9) although HR and payroll read absences and
timesheets, and a shop's broken oven is the same record as a cleaner's site problem.

## Decision

- Agent id `dispatcher` becomes `shift_supervisor` in code, config, ids and data.
- Data standard 1.4: `absences`, `cover_requests`, `timesheets` and `incidents` (was
  `dispatcher_site_problems`) are core tables; `cleaning_checklist_ticks` belongs to the
  cleaning template. Migration 0008 renames in place.
- Dated documents (research reports, specs and plans before 18 Oct 2026, skill reports) are
  not rewritten: "dispatcher" in them means `shift_supervisor`.

## Consequences

- Event rows written before 0008 keep `dispatcher.*` names (append-only, rule 2). All data is
  seed and demo, so no compatibility map; reseed when history matters.
- Event rows written before 0008 also keep the old table names as entity_type and action (for
  example `dispatcher_absences.created`), not only `dispatcher.*` tool and intent ids.
- Migration 0008 also renames the agent id in chat threads, chat messages (agent id and
  assistant sender) and approvals (type prefix and agent requester), because code looks those
  up by the new id. Events stay as written.
- Q20 (where timesheets live) is answered: core.
- New agents start with job ids: sales_supervisor, inventory_manager, bookkeeper, hr_officer,
  branch_manager.
