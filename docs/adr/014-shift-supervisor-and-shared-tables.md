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
  cleaning template.
- Migrations 0001 to 0008 are squashed into one `0100_initial` (data standard 1.4; a new id so a
  database stamped with any squashed revision fails loudly). Mia has no
  production release and all data is seed and demo, so databases are rebuilt from scratch
  (`mia migrate && mia seed`) instead of upgraded. From here on every schema change gets its
  own migration again (rule 14).
- Dated documents (research reports, specs and plans before 18 Oct 2026, skill reports) are
  not rewritten: "dispatcher" in them means `shift_supervisor`.

## Consequences

- A database made before the squash (alembic version 0001 to 0008) cannot be upgraded: delete
  it and run `mia migrate && mia seed`. Its events would keep the old `dispatcher.*` and
  `dispatcher_*` names anyway (append-only, rule 2), so rebuilding is the clean path.
- The data-preserving upgrade tests of the old steps (1.0 to 1.1, 1.2 to 1.3, 1.3 to 1.4) are
  gone with them; the schema test (migrations equal the models, triggers present) stays.
- A role model trained before the rename (`data/models/dispatcher/`, labels `dispatcher.*`) is
  not found under the new id: move the folder to `shift_supervisor/` and rewrite the labels in
  each `card.json`, or retrain. None existed when this was decided.
- Q20 (where timesheets live) is answered: core.
- New agents start with job ids: sales_supervisor, inventory_manager, bookkeeper, hr_officer,
  branch_manager.
