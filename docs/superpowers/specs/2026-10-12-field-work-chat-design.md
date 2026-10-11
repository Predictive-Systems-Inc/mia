# Field work over chat: check-in, check-out and visit details

Date: 2026-10-12. Status: built (plan item 5, Sprint 3, D20 and D25: field work stays over
WhatsApp and the in-app chat). Builds on the scheduling core (D34) and the capability
catalogue intents `dispatcher.check_in`, `dispatcher.check_out` and `dispatcher.visit_details`.

## Goal

A cleaner tells Mia "Olen perillä" or "I'm done here" and the visit's actual times are
recorded through `scheduling.check_in` and `check_out`; "Mikä on ovikoodi?" or "What's the
address?" answers with the visit's address, instructions, access notes and checklist. Rule 7:
which visit, whether the window is open and who may do it are code; the model only classifies.

## Behaviour

| Intent | Tool | Picks the visit | Reply |
|---|---|---|---|
| check_in | `dispatcher.check_in` (write) | today's planned visit of the acting person whose check-in window holds now (closest start first); a site name narrows it | "Checked in at {location} at {time}." or why not (no visit now, too early, too late, already started) |
| check_out | `dispatcher.check_out` (write) | the acting person's visit in progress today | "Checked out of {location} at {time}." or "You are not checked in anywhere." |
| visit_details | `dispatcher.visit_details` (read) | the named site's next visit, else the acting person's current or next visit today | a card: address, instructions, access notes, checklist items |

Permissions: the tools check `data:core.visit` `write` (check-in and check-out) and `read`
(details) with the acting person as owner, so staff act on their own visits only; supervisors
may do the same for themselves. Checking someone else in stays an API action
(`POST /visits/{id}/check-in`), not a chat one. Access notes are sensitive: on an outside
channel the message becomes a link to the app (the existing `sensitive` rendering), in the app
they show.

## Out of scope

Location sharing as a check-in (needs the channel's location message type), photos and ticking
checklist items (Phase 2 intents), the missed-check-in alert (plan item 6).

## Tests

Classifier cases in both languages; each tool's happy path, no visit, window edges and the
permission denial; a chat demo (Juha arrives, asks the door code, finishes) on the daytime
clock; eval scenarios for the three intents.
