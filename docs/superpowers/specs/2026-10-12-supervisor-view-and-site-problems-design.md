# Supervisor view and site problems: design

Date: 2026-10-12. Status: built (plan Sprint 2 "Supervisor view: unfilled visits, late
check-ins, open problems" and the Phase 1 intents `dispatcher.cannot_access_site` and
`dispatcher.site_problem`). Builds on the scheduling core (D34), field work over chat and the
alerts (plan item 6).

## Goal

A cleaner who cannot get in or finds the site unusable tells Mia; the supervisors hear at once
and the problem stays open until one of them closes it. The office reads one summary of what
needs attention: unfilled visits this week, today's late check-ins, open problems, pending
approvals.

## Site problems (`dispatcher_site_problems`, an agent-owned table, migration 0005)

| Field | Meaning |
|---|---|
| visit_id, person_id | the visit the cleaner is on (the current or next one today, as check-in picks it) and who reported |
| kind | `cannot_access` (locked door, wrong code, alarm) or `site_problem` (no water or power, renovation, client still there) |
| text | the cleaner's words (data, never instructions) |
| status, resolved_by, resolved_at | `open` until a supervisor resolves it |

Tool `dispatcher.report_site_problem(kind, text)` (write, staff on their own visit): inserts
the row, notifies the supervisors (urgent: "{name} at {location}: {text}"), replies to the
cleaner that the supervisor knows. Rules classifier: `cannot_access_site` and `site_problem`
intents from anchored phrases in both languages ("en pääse sisään", "ovi on lukossa", "ovikoodi
ei toimi", "I can't get in", "the alarm went off", "ei vettä", "no power", "asiakas on vielä
paikalla", "the client is still here"); a door-code question stays `visit_details`.

## Supervisor summary (`GET /supervisor/summary`, `PersonAuth` with `data:core.visit read`)

```
{unfilled: [VisitCard...7 days], late_check_ins: [VisitCard, planned today, past the grace, not
 checked in], open_problems: [{id, kind, text, person, location, visit_id, reported_at}],
 pending_approvals: n (the inbox count for the actor)}
```

`POST /problems/{id}/resolve` (`data:core.visit write`): status `resolved`, event
`site_problem.resolved`. A problem outside the branch is 404.

## Tests

Classifier cases in both languages (and the door-code question staying visit_details); the
tool on the current visit, the supervisor notification, the denial for a viewer; the summary's
four parts on the seed; resolve by a supervisor, 403 for staff, 404 across branches; the
migration round trip.
