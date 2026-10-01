# Decisions from the product owner

Answers to docs/questions.md. Reference the question number. Decisions that change the spec also get an ADR.

## D1: (answers Q1)
- Decision:
- Reason:

## D1: (answers Q2) An explicit instruction is the approval
- Decision: when a person with the required role explicitly instructs Mia (for example the
  supervisor says "Assign Mikael"), that instruction counts as the approval and the change is
  applied directly. Mia asks for approval only when it acts on its own decision, when no rule
  covers the case, or when payment or money is involved.
- Reason: the user already decided; a second approval step by the same person adds nothing.

## D2: (answers Q1) `MIA_MODEL=test` runs the rules model
- Decision: keep `test` as the deterministic rules model (FunctionModel plus the rules classifier
  named in the manifest). Pydantic AI's TestModel is used directly in unit tests only.
- Reason: no API key needed, deterministic, and the brief, CI and .env.example stay unchanged.

## D3: (answers Q3) Job and Visit live in core
- Decision: location, job and visit are core data standard tables. The cleaning template adds
  only industry extras (sites, checklists, availability, working-hour limits).
- Reason: other industries reuse jobs and visits.

## D4: (answers Q4) Visit lookup through optional tool inputs
- Decision: find_replacements also accepts location_name, date and time; get_my_visits also
  accepts person_name (permission checked). No separate search tool.
- Reason: keeps the tool set at four while supporting natural requests.

## D5: (answers Q5) Evals command
- Decision: `uv run pytest node/tests/evals -m evals` (or `uv run pytest -m evals`); tests stay
  under node/tests.
- Reason: matches the layout; README and CI already use it.

## D6: (answers Q6) Travel in ranking, home base, cleaner confirmation
- Decision: rank replacements by added travel (from the previous visit that day, or the
  cleaner's home base address). Coordinates come from geocoding addresses. Each cleaner has a
  home base address. After the supervisor picks a candidate, Mia asks that cleaner to confirm;
  the visit changes only when the cleaner accepts. On decline, the supervisor is told and the
  next candidate is offered.
- Open follow-ups: geocoding provider, where home base is stored, confirmation timeout.

## D7: (answers Q6a) Geocoding is a tool with pluggable providers
- Decision: geocoding is a core tool with one interface and swappable providers, chosen by
  configuration. First provider: Digitransit (Finland). Requests leave the node only through
  the egress layer and are logged; results are cached so each address is geocoded once.
- Reason: Finnish address quality now, other countries (Philippines) later without code changes.

## D8: (answers Q6b) Home base on the person, data standard 1.1
- Decision: home address and its coordinates are person fields in the core data standard
  (version 1.1, ADR to follow), encrypted with other contact details when field encryption lands.
- Principle (applies to all later choices): every design decision must fit the architecture so
  the system stays easy to maintain. Shared, industry-neutral data goes in the core standard;
  industry fields in templates; agent working data in agent tables; external services behind
  tools with pluggable providers and the egress layer.

## D9: Employee data is shared data
- Decision: all employee data lives in the core data standard (1.1): home base address and
  coordinates, skills, weekly availability and working-hour limits. The tables
  cleaning_availability and cleaning_work_limits move to core. The cleaning template keeps only
  industry data (sites, checklists).
- Reason: employee data is industry-neutral and reused by every shift business and agent.

## D10: (answers Q6c) Confirmation escalation: message, then call, then next candidate
- Decision: Mia messages the picked cleaner for confirmation; with no response it escalates to a
  phone call; with still no response it moves to the next candidate and tells the supervisor.
- Build note: voice is deferred (brief non-goal), so the call step goes behind a channel
  adapter interface with a stub that logs the call request; the real voice adapter plugs in
  later. Calls only to people who agreed to calls, respecting quiet hours (spec, Voice rules).
- Open: timings for each step.

## D11: (answers Q6d) Confirmation timings and quiet hours
- Decision: organisation settings with these defaults: wait 15 minutes after the message, then
  call; wait 10 minutes after the call, then move to the next candidate and tell the supervisor.
  If the visit starts within 60 minutes, call at once and move on after 5 minutes. Quiet hours
  (21:00 to 06:00): urgent cover (visit before 10:00 next morning) may message during quiet
  hours but never call before 06:00; other requests wait until quiet hours end.
