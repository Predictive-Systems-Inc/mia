# Scheduling core and approvals inbox: design

Date: 2026-10-12. Status: built from assumptions Q19 to Q22 (docs/questions.md); the schedule
board UI and timesheets are not in this build. Plan item 4 (docs/plan.md, "Status and revised
order"), Sprint 2; spec.md "Data standard" (job, visit, approval) and "Approvals".

## 1. Goal

A branch's visits exist weeks ahead, are assigned by the office with the same rules the
dispatcher uses for cover, and the office sees what needs a decision. Concretely:

- Visits are generated from each job's recurrence rule for the next 28 days, every day,
  without duplicates; a visit nobody is assigned to is `unfilled`.
- The office assigns and unassigns people to visits. The eligibility rules are code: available
  on that weekday and time, not absent, not double-booked, within daily and weekly hour limits,
  holding the required skills. Breaking a rule needs an approval (`schedule.assignment_override`,
  approver roles admin and owner, app only), like the dispatcher's cover override.
- A cleaner checks in and out of a visit (actual times, status `in_progress` then `completed`);
  a supervisor can do it for them. Check-in is refused more than 2 hours before the planned
  start or on another person's visit.
- The approvals inbox: the pending approvals the acting person may decide, with what an
  approval card needs; deciding stays `POST /approvals/{id}/decide`.
- A week view per person or per site, as JSON, for the office page and the apps.

Done when (Sprint 2): the seeded branch's next four weeks are generated and assigned through
the API, a rule-breaking assignment lands in the inbox and a supervisor cannot decide it but
an admin with a PIN can, and a check-in from the cleaner marks the visit in progress.

## 2. Non-goals (and where they go)

- The drag-and-drop schedule board and the supervisor dashboard: the office web app is a
  separate project (D25); this build exposes the data it needs.
- Timesheets, corrections and the payroll export: a new core entity, which changes the data
  standard; proposed in Q20 and waiting for the answer.
- Swap requests, extra-shift offers, route planning, client bookings: Phase 2 intents in
  docs/capabilities.md.
- A job's default assignee: no new job field (Q21); generation copies the assignment of the
  job's most recent visit on the same weekday when that person is still eligible.

## 3. Recurrence rules (code, no dependency)

`job.recurrence` is an RFC 5545 RRULE string. Supported: `FREQ=DAILY`, `FREQ=WEEKLY;BYDAY=MO,TU`,
optional `INTERVAL=n` (every n days or weeks, anchored on the job's creation date in the branch
time zone), optional `UNTIL=YYYYMMDD`. Anything else raises `ValueError` at job validation and
at generation (the job is skipped with a warning, the others still generate). `occurs_on(rule,
anchor, day)` is a pure function; the seed uses it.

## 4. Services (`mia/core/scheduling.py`, every write through `store`)

| Function | Guarantees |
|---|---|
| `generate(session, actor, branch, *, days=28, today=None) -> list[Visit]` | One visit per (job, date) at most: existing dates are skipped. New visits are `planned` with the copied assignee when eligible, else `unfilled`. Returns the new rows. Event `visit.generated` per row. |
| `assign(session, actor, visit, person, *, override_approved=False) -> Assignment` | Checks eligibility with `scoring.ineligibility` on the person's `CandidateData` (built by `candidate_data` moved from the dispatcher tools into scheduling). Eligible: the visit gets the person (replacing the current assignees unless `add=True`), status `planned`, event `visit.assigned`. Not eligible and not approved: an approval `schedule.assignment_override` (subject the visit, evidence the reasons and the person) and the visit is unchanged; the result carries `approval_id`. A registered approval handler applies the assignment on approval. |
| `unassign(session, actor, visit, person) -> Visit` | Removes the person; an empty visit becomes `unfilled`. |
| `check_in(session, actor, visit, person, now) -> Visit` | Person must be assigned; `now` within 2 hours before `planned_start` and before `planned_end + 4 h`; status `planned` only. Sets `actual_start`, status `in_progress`; event `visit.checked_in`. |
| `check_out(session, actor, visit, person, now) -> Visit` | Status `in_progress`, same person; sets `actual_end`, status `completed`; event `visit.checked_out`. |
| `week(session, branch_id, start: date, *, person_id=None, location_id=None) -> list[Visit]` | The seven days from `start`, filtered, ordered by planned start. |
| `inbox(session, actor) -> list[Approval]` | Pending and escalated approvals of the branch whose `approver_roles` (or `escalate_to` when escalated) meet the actor's roles, oldest first. |

`ScheduleError(RuntimeError)` for refused operations; its message is the reason.
`Assignment(visit, approval_id: str | None, reasons: list[str])` is the result of `assign`.

## 5. API (`mia/api/schedule.py`, all `PersonAuth`, `rbac.require` on each)

| Route | Permission | Does |
|---|---|---|
| `GET /schedule?start=YYYY-MM-DD&person_id=&location_id=` | `data:core.visit read` (`read_own` for one's own) | Seven days of visits as cards: id, job name, site, address, start, end, assignees (id, name), status. |
| `POST /visits/{id}/assign {person_id, add?}` | `data:core.visit write` | `assign`; 200 with `approval_id` when an override is needed. |
| `POST /visits/{id}/unassign {person_id}` | `data:core.visit write` | `unassign`. |
| `POST /visits/{id}/check-in`, `/check-out` `{person_id?}` | `data:core.visit write_own`; supervisors `write` for others | Acting person by default. |
| `GET /approvals` | signed in | `inbox` for the actor: id, type, summary, evidence, requester, created, expires, status. |

Errors: 404 outside the branch, 403 from RBAC, 409 with the reason for a refused schedule
operation. Policy: `supervisor` gets `data:core.visit write`; `staff` gets `data:core.visit
write_own` (check-in and check-out on own visits).

## 6. Generation on the node

`mia schedule generate [--days N]` runs it once; the ticker runs it once a day (first tick
after 03:00 local, remembered in process) so visits always exist four weeks ahead. The seed keeps
creating its demo visits.

## 7. Office page

The dev chat page gets a "Week" panel: a table of the next seven days for the signed-in
person (staff) or the whole branch (office roles), read from `GET /schedule`; no editing.

## 8. Tests

Recurrence (daily, weekly with BYDAY, INTERVAL anchor, UNTIL, unsupported); generation
(idempotent, copies the assignee, unfilled when nobody eligible, skips a bad rule); assign
(eligible, each ineligibility reason, override approval then handler applies, add vs replace,
rbac denies staff); unassign; check-in windows and wrong person; check-out; week filters;
inbox filtered by role and escalation; API routes including 404 across branches and 409 texts;
the daily generation on the ticker; the CLI.
