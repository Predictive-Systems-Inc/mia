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
