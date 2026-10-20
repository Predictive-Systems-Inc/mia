# ADR 019: Data standard 1.7, the kiosk incident kinds and customer orders in core

## Status

Accepted (21 Oct 2026, the owner, D39).

## Context

The shift supervisor runs at Ferino's kiosks as well as for the cleaning company (D39: the same
package with a template switch, rule 15). A kiosk shift is a core Visit with the branch as the
site, so a clerk's problem at the counter is an Incident on that visit. The incident kinds
were the cleaning ones only (cannot_access, site_problem, a comment on a `str` column), while a
kiosk reports a broken stove or freezer, a delivery that never came and a customer making
trouble at the counter (Q108, Q111). The incidents table is shared (rule 9), so its code list
is part of the data standard. The production planner adds the customer orders section to this
ADR when it builds.

## Decision

- Data standard 1.7, in mia/core/models.py:
  - `IncidentKind`, the code list `INCIDENT_KINDS`: cannot_access, site_problem, equipment,
    no_delivery, customer. `Incident.kind` keeps its `str` column; the shift supervisor's
    `ReportProblemInput.kind` is the Literal, so an unknown kind is refused at the tool
    boundary.
  - `STANDARD_VERSION = "1.7"`; the shift supervisor's manifest declares 1.7.
- Retail offers equipment, no_delivery, customer and site_problem; cleaning keeps
  cannot_access and site_problem. A short till ("kulang ang cash") stays the bookkeeper's and
  an empty LPG tank the inventory manager's (Q108).
- Not data standard: the template table `retail_closures` (a branch's closed local dates, one
  row per branch and date, `set_by` the person) lives in mia/templates/retail/models.py; no
  core table, field or foreign key is added.

## Consequences

- An in-place edit of `0000_initial` for `retail_closures` (no new migration), since there is
  no candidate release yet (rule 14). Dev databases are rebuilt: `rm data/mia.db &&
  uv run mia migrate && uv run mia seed`. The incident kinds need no schema change.
- Existing incident rows keep their kinds; no event row changes (rule 2).
- Cover eligibility reads the role graph (`scheduling.is_staff`): a role that is or inherits
  staff, never one that is or inherits supervisor, so a retail clerk is a cover candidate and
  head staff never. No rbac line is widened for a person.
