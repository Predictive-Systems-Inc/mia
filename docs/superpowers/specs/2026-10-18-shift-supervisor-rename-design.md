# Shift supervisor rename and shared tables (design, 18 Oct 2026)

Part 0, before multi-agent routing (2026-10-18-multi-agent-routing-design.md). A refactor with
one migration and no behaviour change.

## Why

Agents are named after real jobs (D16). "Dispatcher" fits a cleaning company, not a shop; the
same work (rosters, absences, cover, check-in) is a shift supervisor's. Its tables carry the
agent prefix (rule 9) although other agents need them: HR reads absences and timesheets,
payroll reads timesheets, and a shop's "the oven is broken" is the same record as a cleaner's
site problem. The new agents (sales_supervisor, inventory_manager, bookkeeper, hr_officer,
branch_manager) start with job ids, so the oldest one should too.

## Decisions

- The agent id `dispatcher` becomes `shift_supervisor` everywhere: package
  `mia/agents/shift_supervisor/`, manifest id, agent role `agent.shift_supervisor`, tool ids
  (`shift_supervisor.record_absence`), intent ids (`shift_supervisor.report_absence`), event
  entity and purpose names, i18n keys, settings and docs that describe the current system.
- Shown name: "Shift Supervisor" (en, fil); "Vuoropäällikkö" (fi).
- Data standard 1.4: four tables become shared, one moves to the cleaning template.

| Before | After | Owner | RBAC resource |
| --- | --- | --- | --- |
| `dispatcher_absences` | `absences` | `core/models.py` | `data:core.absence` |
| `dispatcher_cover_requests` | `cover_requests` | `core/models.py` | `data:core.cover_request` |
| `dispatcher_timesheets` | `timesheets` | `core/models.py` | `data:core.timesheet` |
| `dispatcher_site_problems` | `incidents` | `core/models.py` | `data:core.incident` |
| `dispatcher_checklist_ticks` | `cleaning_checklist_ticks` | `templates/cleaning/models.py` | `data:cleaning_checklist_ticks` |

Columns do not change (`incidents.kind` keeps `cannot_access`, `site_problem`; `visit_id`
stays required until a non-visit agent needs an incident). Classes: `Absence`, `CoverRequest`,
`Timesheet`, `Incident` (was `SiteProblem`), `CleaningChecklistTick` (was `ChecklistTick`).
Services that write them move with them (`core/absences.py` and so on) when other agents will
call them; until then the shift supervisor's tools keep their write functions, which still emit
events (rule 1).

## Data and migration

- All data is seed and demo (confirmed 18 Oct). Migration 0008 renames the five tables and their
  indexes (`ALTER TABLE ... RENAME`, no copy) so an existing demo database upgrades; a fresh
  seed writes only new names.
- Events are append-only (rule 2): rows already written keep `dispatcher.*`. No compatibility
  map: a demo database is reseeded when its history matters.
- Training data and models: a one-off script rewrites intent ids in `intents.jsonl`, the role
  skill data (`skill/data/*.jsonl`), `intents_catalogue.yaml`, `capabilities.md` and the trained
  models' label lists, so no retraining. The script is run once and not kept.
- Not rewritten: dated records (docs/research, docs/superpowers specs and plans before this
  one, skill reports). ADR 014 says that "dispatcher" in them means `shift_supervisor`.

## Done when

- `grep -rw dispatcher node/mia node/tests node/config` finds nothing outside migrations 0001 to
  0007 (history), and `grep -r dispatcher_` finds the same.
- The full suite passes with no test logic changed (names only), lint, format and mypy pass.
- Migration 0008 upgrades a database made by 0007 with seed data, and downgrade restores it.
- The scenario evals (rules model) pass as before; the Jev eval is not rerun (no behaviour
  change).
- ADR 014 (rename, shared tables, data standard 1.4), `docs/layout.md`, README and
  `docs/capabilities.md` updated.
