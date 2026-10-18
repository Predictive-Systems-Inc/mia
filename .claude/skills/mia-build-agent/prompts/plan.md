# Plan skeleton

Write `docs/superpowers/plans/<date>-<agent_id>.md` in the shape of
docs/superpowers/plans/2026-10-19-sales-supervisor.md. Each task: Files, Interfaces, a failing
test first, the run, the commit. Test names come from the spec's scenarios, one behaviour each,
in the pattern `test_<who>_<does>_<result>`.

## Review Focus
Pre-filled from `checklist.md`: copy the lines that apply to this agent and pin each to the task
that owns it, as "N. rule sentence (Task K, test `test_name`)". A line without a task and a test
name is not done.

## Tasks (the eight standard ones)
1. Data: tables, template, migration (0000_initial in place before the first candidate), seed,
   org config. Tests: schema, downgrade order, FKs, nullable branch_id.
2. Actions and decider: ACTIONS, Query, build_query, build_request, the parse. Tests:
   `test_<id>_actions.py`, the fake Jev through `test_jev_decider.py` shapes.
3. Tools and policy: BINDINGS with risk and roles, policy lines, `_check` before every read and
   write, branch scoping. Tests: `test_<id>_tools.py` with a negative test per tool.
4. Turn and replies: the Jev turn, commit before the await, taps, one reply per turn. Tests:
   `test_<id>_chat.py` through `run_turn`.
5. The rest of the scenarios: each remaining acceptance item, one test each.
6. Due work: windows, markers with sends, urgent flags, per-branch commits. Tests:
   `test_<id>_due.py` with clocks across midnight.
7. Ten languages: every key through the coverage test, placeholders, assert through `t(...)`.
8. Evals and docs: seeds per gated language in `router_cases.py`, `PENDING` emptied, both gates
   at the Q40 bar on fresh halves, the reports, README, layout, ADR, questions.

## Self-review
Every Review Focus line has a task and a test; every spec scenario has a test; no placeholder
left.
