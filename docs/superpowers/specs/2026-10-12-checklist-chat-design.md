# The visit checklist over chat: design

Date: 2026-10-12. Status: built (plan item 5, Sprint 3; the Phase 1 intent
`dispatcher.checklist`). Builds on field work over chat and the scheduling core.

## Goal

A cleaner asks "Mikä on tarkistuslista?" and gets the current visit's items with their state;
"Tehty: roskat" ticks one off. Ticks are per visit (the checklist itself is per job).

## Data

`dispatcher_checklist_ticks` (agent-owned, migration 0006): visit_id, item (the item text as
on the job's checklist), ticked_by, ticked_at. One row per visit and item; ticking twice is a
no-op.

## Behaviour

| Message | Tool | Reply |
|---|---|---|
| "checklist", "tarkistuslista", "mitä pitää tehdä", "what do I need to do" | `dispatcher.checklist()` (read) on the current or next visit today | a card of items, done ones marked, plus quick replies "Done: <item>" for the open ones |
| "Done: <item>", "Tehty: <item>", "Valmis: <item>" (a quick reply or typed) | `dispatcher.checklist(item)` (write) | the item is ticked (prefix match, case-insensitive; the closest item when several match); the card again. An unknown item answers with the open items. |

Permissions: `data:core.visit read` and `data:dispatcher_checklist_ticks write_own` for the
acting person's own visit (staff). A visit without a checklist answers "no checklist".
Ticking the last item does not check the cleaner out; "I'm done here" still does.

## Tests

Classifier cases in both languages (and "Valmis, lähden nyt" staying check-out); the tool with
no visit, a visit without a checklist, show, tick, tick twice, unknown item; a chat demo with
the quick replies; eval scenarios.
