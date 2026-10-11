# Alerts and the billing summary export: design

Date: 2026-10-12. Status: built (plan item 6, Sprint 5, first slice). Builds on the scheduling
core (D34) and field work over chat; the capability catalogue rows `dispatcher.missed_check_in`,
`dispatcher.unstaffed_visits` and `dispatcher.daily_plan`; spec.md "Billing summary export
(CSV) done in code".

## Goal

The node tells people what they need to act on without being asked, and the office gets the
month's completed work per client as a CSV. All of it is code on the ticker (rule 7); the
messages go through `chat.channels.notify`, so the app keeps a copy and channels get it under
the quiet-hours rules.

## Alerts (`agents/dispatcher/alerts.py`, run by `run_due_work` and `mia tick`)

| Alert | When | Who | Once |
|---|---|---|---|
| missed check-in | a `planned` visit whose planned start is more than `check_in_grace_minutes` (15) ago has no check-in | the assigned cleaner ("Are you at {location}? Reply 'I'm here' when you arrive."), urgent; then every supervisor of the branch ("{name} has not checked in at {location}, planned {time}.") | one `visit.missed_check_in` event per visit; the handler skips visits that already have one |
| unstaffed visits | once a day from `unstaffed_check_time` (15:00 local): tomorrow's `unfilled` visits | every supervisor, a card listing them | one `alert.unstaffed_visits` event per branch and date (none when there is nothing to report) |
| daily plan | once a day from `daily_plan_time` (17:00 local): each cleaner's visits tomorrow | the cleaner, a card of tomorrow's visits; people without visits get nothing | one `notification.daily_plan` event per person and date |

Settings in `OrgSettings.alerts`: `check_in_grace_minutes=15`, `unstaffed_check_time=15:00`,
`daily_plan_time=17:00`. The once-markers are events, so a restart never repeats an alert.
Overtime risk and missing check-outs stay open (they need timesheets, Q20).

## Billing summary export (`core/billing.py`, `mia billing export`)

`summary(session, branch_id, year, month) -> list[BillingRow]` with one row per client and
site: completed visits, planned minutes, actual minutes (from check-in to check-out, planned
when a visit has no actual times), and the visit ids. `mia billing export --month YYYY-MM
[--out PATH]` writes it as CSV (standard library `csv`) or to stdout; the export is an event
(`billing.exported`, with the month and the row count, never the rows). Prices, extras and
approvals wait for service agreements (D21, Sprint 1 item not yet built), so the CSV carries
work done, not amounts. Shell access is the permission (as every `mia` command).

## Tests

Each alert: fires once, not twice; respects its time of day; nothing to report sends nothing;
the right recipients. The billing summary on the seed (completed visits exist for the past two
weeks); the CSV columns; the CLI.
