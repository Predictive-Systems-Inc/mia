# Review checklist

What every review asks, from the findings parts 1 and 2 kept producing. Each line ends with the
file or test that proves the point in the built agents. Pin each line to the plan task that
owns it.

## Rule 15: names
- No bare agent id literal; ids from `MANIFEST.id`; label keys built from it: `sales_supervisor/__init__.py`, `tests/test_architecture.py`.

## Rules 8 and 6: data, not instructions
- The message and any list of its parts go to Jev as state, pseudonymised (lists item by item); nothing from the message in instructions: `mia.agents.decider.pseudonymised`, `test_jev_decider.py`.
- Requests only inside the egress context: `mia.agents.decider`, `tests/test_architecture.py`.

## Rule 7: code calculates
- Every number computed by code: `sales_supervisor/calc.py`, `test_sales_calc.py`.
- Money typed in major units is converted once to minor units: `sales_supervisor/actions.py`, `test_sales_calc.py`.
- Dates from the branch's local clock, never `now.date()` in UTC; business date: `calc.business_date`, `test_sales_calc.py`.

## Rule 4: permissions
- Branch scoping through casbin (`read_all`, `write_all`): `sales_supervisor/tools._branch`, `policy.csv`, `test_sales_tools.py`.
- Every read and write `_check`ed; a denial is visible as an event or a `tool.called` refusal: `sales_supervisor/tools.py`, `test_sales_tools.py`.
- `read_own` gates by role only; say so where it is used: `policy.csv`, `test_sales_tools.py`.

## Rules 11 and 12: transactions and threads
- Commit before the Jev await: `sales_supervisor/turn.py`, `test_sales_chat.py`.
- Sync DB work in threads, one Session per thread: `sales_supervisor/turn.py`, `test_sales_chat.py`.
- Per-branch commits in due work: `sales_supervisor/due.py`, `test_sales_due.py`.

## Taps
- A button value is a stored decision, validated against the agent's own ACTIONS: `sales_supervisor/actions.py`, `test_sales_chat.py`.
- Stale after a notification, never replayed across a date: `sales_supervisor/turn.py`, `test_sales_chat.py`.

## Due work
- Windows as datetimes that may cross midnight (midnight windows): `sales_supervisor/due.py`, `test_sales_due.py`.
- Business date from the closing's day: `sales_supervisor/due.py`, `test_sales_due.py`.
- Markers per branch and date, written with the send: `sales_supervisor/due.py`, `test_sales_due.py`.
- End-of-shift messages urgent, reminders and morning messages not: `sales_supervisor/due.py`, `test_sales_due.py`.
- Nothing sent when there is nothing to say: `sales_supervisor/due.py`, `test_sales_due.py`.

## Business dates
- A late count is yesterday's only before opening and within two hours of a late close; never ask: `calc.business_date`, `test_sales_calc.py`.

## Parsing
- Both orientations scored by menu tokens: `sales_supervisor/actions.py`, `test_sales_actions.py`.
- Negation is a correction: the negation drops the next number and the message is a correction by rule: `actions.was_corrected`, `sales_supervisor/decider._parse`.
- Leading stray words dropped, currency symbols stripped: `sales_supervisor/actions.py`, `test_sales_actions.py`.

## Harvest and learning
- Sensitive skip depends on an active role model; records pending review (D27): `mia/learning`, `test_learning_harvest.py`.

## i18n
- Every key in ten languages through the coverage test, placeholders identical, no digits: `mia/i18n`, `test_i18n.py`.
- Filipino (fil), never Tagalog, in labels, comments and docs: `mia/i18n/fil.py`.
- Tests assert through `t(...)`: `test_sales_chat.py`.

## Evals
- A fresh gate half per run, split by seed, no text in both halves: `tests/evals/gate.py`, `router_cases.PENDING`.
- The raw file named by local time, never overwritten: `tests/evals/gate.py`, `test_sales_supervisor_evals.py`.
- The report in the research shape with the gate stated as it is: `docs/research/*.md`.
- The gate bar is Q40: `tests/evals/gate.py`, `docs/questions.md` Q40.

## Tests
- Through `run_turn` with the fake Jev: `test_sales_chat.py`.
- Negative tests for permissions, approvals and egress: `test_sales_tools.py`, `test_architecture.py`.
- The plan's Review Focus list pinned to tasks, each with a named test: `docs/superpowers/plans/2026-10-19-sales-supervisor.md`.
