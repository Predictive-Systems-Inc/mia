# 008: ERP builder agent and JEV decision rules

## Status
Proposed. Design: docs/superpowers/specs/2026-10-22-erp-builder-and-jev-design.md. The decision
record table changes the data standard and waits for the product owner (Q11).

## Context
Mia must cover common business processes (purchasing, inventory, billing, staff) for many
businesses. Writing every table, service and tool by hand does not scale. Running a large model
for every decision is slow, costly and breaks rule 7 (LLMs classify, code calculates). The spec
already says tools are built and certified by developers and agents are instructions on top of
them, so any generated code must go through the same review and signing.

## Decision
- A build-time architect agent (Claude Code with a Mia `erp-builder` skill, scaffolding scripts
  and the repository checks) turns a confirmed business brief into a package: tables,
  Alembic migration, service functions, tools, manifest entries, decision rules and tests.
  Its output is a pull request. It never runs on a client node and never changes a live schema.
- Business decisions are JEV rules: versioned JSON documents with typed inputs, organisation
  parameters within bounds, a closed operator set and test vectors. `mia/core/rules.py`
  evaluates them with no model, no I/O and integer money.
- Every evaluation is saved as a decision record with the rule hash, inputs, parameters and
  output, and emits `rule.decided`, so decisions can be looked up and replayed.
- Facts for a rule are loaded by tool code from the database; the model supplies only what the
  person said.
- A JEV outcome can add an approval but never remove one required by the tool's risk.

## Consequences
- Runtime cost drops to classification and wording on small models; decisions are free and
  repeatable.
- New package folder `rules/` and new docs folder `docs/erp/` (ERP catalogue). docs/layout.md
  is updated when the first package lands.
- Data standard change for decision records (Q11); industry-neutral ERP areas may need standard
  modules (Q12).
- Review effort moves from writing code to reading mapping reports and rule tables; the
  architect's quality is tracked with an eval set of briefs.
- The JEV operator set is versioned (`"jev": "1"`); adding operators needs a new version and an
  interpreter release.
