# Location sharing as check-in and check-out: design

Date: 2026-10-12. Status: built (plan item 5, Sprint 3; D20 "check-in and check-out by
location share"; plan.md Sprint 3 "matched to the site's geofence in code; a check-in outside
the fence is flagged, not rejected"). Builds on field work over chat and photos as proof.

## Goal

A cleaner shares their location on WhatsApp when they arrive and again when they leave. The
node checks them in to (or out of) their current visit, compares the shared point with the
site's coordinates in code (rule 7), and flags an arrival or departure outside the site's
geofence for the supervisors without rejecting it.

## Behaviour

- `InboundMessage` carries `lat` and `lon` when the channel delivered a location message (both
  finite and in range, else neither: a crafted payload becomes a plain empty message) and
  `picked_place` when the person sent a chosen place (WhatsApp adds `name` or `address`) rather
  than where they are; the simulator takes `location: [lat, lon]` and `place`.
- Trust: the point is the person's claim, like a text "Olen perillä" is. WhatsApp lets anyone
  send any place, so a point inside the fence is not proof of presence; it is one more signal
  for the supervisor, never a gate. A picked place is flagged like a point outside the fence.
- Privacy: the coordinates are used once and kept nowhere. `channel_inbound.body` is redacted
  from events (the append-only log never holds them) and the row's copy is dropped when the
  message is handled; the fence event holds the distance, the radius and the reason only.
- Inbound handling: a location message from a linked person is attendance, not a chat turn
  and not media. The visit is the person's current one today (`scheduling.current_visit`: in
  progress, else the nearest ahead), after `rbac.require(data:core.visit, write)` with the
  person as owner (rule 4, the same check as the chat tools).
  - No visit: the existing "I found no visit of yours to check in to right now" reply.
  - A planned visit: `scheduling.check_in` (the same window as the chat tool: two hours
    before the start to four hours after the end); outside it the existing too early or too
    late reply. Reply: the existing "Checked in at {location} at {time}" text.
  - A visit in progress: `scheduling.check_out`. Reply: the existing "Checked out of
    {location} at {time}" text. A second share during a visit therefore means "I am leaving"
    (D20 names both by location share; Q23).
- The fence: when the site has coordinates, the great-circle distance from the shared point
  to the site is compared with `location.geofence["radius_m"]` (100 m when unset). Beyond it,
  the node appends one event `visit.attendance_outside_fence` on the visit (kind check_in or
  check_out, reason outside or picked_place, person_id, distance_m, radius_m, date; never
  the shared coordinates) and adds to the reply "You seem to be {distance} m from {location}. I
  recorded that for your supervisor." The check-in or check-out itself stands. A site without
  coordinates is never flagged; an unusable `radius_m` falls back to 100 m rather than failing
  the check-in. On a two-person visit the second arrival hears "already checked in" (the chat
  tool's answer, D34) instead of checking the visit out.
- `GET /supervisor/summary` gains `outside_fence`: today's flagged check-ins and check-outs
  of the branch (visit card, person, kind, reason, distance).

## Out of scope

Location sharing from the in-app chat (no location input there), live location updates
(WhatsApp sends only the first point), a per-branch default radius (per site is enough),
alerting supervisors at once (the summary shows it; the missed check-in alert path can carry
it when timesheets land).

## Tests

WhatsApp: coordinates from the location sample. Simulator end to end: a share at the site
during the window checks in without a flag and runs no chat turn; a share 2 km away checks in,
emits the event with the distance (no coordinates) and the summary lists it; a share while in
progress checks out; a share without a visit replies and marks the row done.
