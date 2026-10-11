# Timesheets, the payroll export and the attendance alerts: design

Date: 2026-10-12. Status: built (plan Sprint 2 "time and attendance chain", plan item 6
"missing check-out and overtime alerts, the payroll export"; Q20, Q24).

## Goal

Check-in and check-out produce timesheets; the office corrects them and a supervisor approves
them with separation of duties (whoever enters time never approves it); approved timesheets
are the only source for the payroll export. The ticker tells people about a missing check-out
and tells the supervisors about overtime.

## Where timesheets live

Q20 asked whether timesheets are a core entity; that answer changes the data standard, which
needs the owner's decision. Until then they are an agent-owned table, `dispatcher_timesheets`
(rule 9, migration 0007), with Q20's shape (person, visit, date, start, end, minutes, source,
status, entered_by, note, approved_by, approved_at), so moving them to core is a rename.

## Behaviour

- Drafts are built in code on the ticker (and by `timesheets.build_due`): one row per
  completed visit of the last 14 days and assigned person, once (unique visit and person). A
  visit that was checked in and out gives its actual times (source `check_out`); a completed
  visit without them gives its planned times (source `planned`). The enterer is the person
  themselves (their check-out is their entry). Event `timesheet.created`.
- Correction (`POST /timesheets/{id}/correct`, the person for their own row or the office for
  anyone's, `data:dispatcher_timesheets write` with the owner): new start and end (the end
  after the start, else 409), minutes recomputed, source `correction`, back to draft, the
  corrector becomes the enterer. Event `timesheet.corrected`.
- Approval (`POST /timesheets/{id}/approve`, supervisors and up, `write` without an owner):
  refused with 409 when the approver is the enterer (SeparationError) or the row is already
  approved. Event `timesheet.approved`. Staff get 403.
- `GET /timesheets?start=&end=&person_id=`: the period (default the last 14 days); staff see
  their own rows.
- Payroll export: `mia payroll export --from YYYY-MM-DD --to YYYY-MM-DD [--out file]` writes
  the approved rows of the period as CSV (timesheet id, person, date, site, local start and
  end, minutes, source, approver) and emits `payroll.exported`. A generic layout until Hype's
  payroll system is named (Q24). Drafts never leave.
- Alerts (the ticker, once each, markers as events): a visit in progress more than
  `alerts.check_out_grace_minutes` (30) past its planned end asks the cleaner to check out
  and tells the supervisors; a check-out timesheet more than `alerts.overtime_minutes` (30)
  past the planned length tells the supervisors that it waits for approval.

## Out of scope

Per-person times on a two-person visit (the visit's times are shared until check-in is per
person, D34); weekly hour limits and overtime pay rules (payroll's job, plan Sprint 2);
approving from the chat; the office screens (apps project).

## Tests

Drafts per completed visit and person, once, with actual or planned times; correction and
approval with the separation rule, staff refused; the API list for staff and the office,
approve 200, own entry 409, unknown 404; the payroll export takes approved rows only, the CLI
writes the file and the event and refuses a reversed period; the missing check-out and
overtime alerts fire once after their thresholds.
