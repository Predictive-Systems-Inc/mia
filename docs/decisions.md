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
