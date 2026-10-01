# 005: Data standard 1.1, geocoding, and cover confirmation

## Status
Accepted (decisions D1 and D6 to D11 in docs/decisions.md). Supersedes the approval flow for
assignments in ADR 003 and extends ADR 002.

## Context
The product owner decided that an explicit instruction is the approval (D1), that replacement
ranking uses travel from a home base (D6), that geocoding is a tool with pluggable providers
(D7), that all employee data is shared data (D8, D9), and that the picked cleaner must confirm,
with escalation from message to call to the next candidate (D10, D11).

## Decision
Data standard 1.1 (core, `mia/core/models.py`):
- `person`: `home_address`, `home_lat`, `home_lon`, `accepts_calls`. The address becomes an
  encrypted field when field encryption lands.
- `location`: `lat`, `lon`.
- `availability` and `work_limits` move from the cleaning template to core (migration 0002
  renames the tables and keeps their rows). The cleaning template keeps only sites and checklists.
- `geocode_cache`: one row per geocoded address, so an address leaves the node once.

Geocoding (`mia/core/geocoding.py`): a `GeocodeProvider` interface with a registry chosen by
`MIA_GEOCODER`. Providers: `digitransit` (default, needs `MIA_GEOCODER_KEY`) and `static`
(offline, tests). Requests go through `EgressTransport` with `pseudonymise=False` (an address must
leave as it is; name pseudonymisation would corrupt street names such as Mikaelinkatu), are
logged in `egress_log` with purpose `geocoding`, and are blocked at level `none`. The demo seed
stores coordinates directly (provider `demo`); `uv run mia geocode` fills missing coordinates.

Scoring: rank by knows the site, has the skills, least added travel (straight line from the
previous visit that day or the home base, including the detour to the next visit), fewest
hours, name. Unknown coordinates rank after known ones.

Assignment (replaces `propose_assignment`):
- `dispatcher.assign_cover` (write_internal, approval never) acts on a person's explicit
  instruction. It records `assignment.instructed` with the instructor as approver. When the
  choice breaks a hard rule (availability, double booking, hour limits) or the instructor is the
  person being replaced, it requests a `dispatcher.cover_override` approval from admin or owner
  instead (no rule covers it, so a second person decides). Absent candidates are refused.
- The visit changes only when the candidate accepts (`dispatcher.respond_to_cover`).

Confirmation (`mia/agents/dispatcher/cover.py`, table `dispatcher_cover_requests`):
- Ask by in-app notification, wait 15 minutes, call, wait 10 minutes, then ask the next ranked
  candidate and tell the instructor. Visits within 60 minutes: call at once, move on after 5.
- Quiet hours 21:00 to 06:00: messages wait unless the visit is before 10:00 the next morning;
  calls never happen in quiet hours. People with `accepts_calls = false` are never called.
- A new instruction or an acceptance cancels other open asks for the visit.
- Timings and quiet hours are organisation settings in `config/org/<org>/settings.yaml`.
- Calls go through a `CallAdapter`; until voice exists a stub logs `call.requested`.
- Due steps run every `MIA_TICK_SECONDS` inside `mia serve` (stand-in for the Huey worker) or
  with `uv run mia tick`.

## Consequences
- Supervisors no longer see an approval card for ordinary cover; they get notifications when the
  cleaner accepts, declines or does not answer.
- Until the voice channel exists, the call step only notifies through the log; a cleaner who
  never opens the app is moved past after the call wait.
- Demo seed has home bases and site coordinates; real data needs a Digitransit key.
