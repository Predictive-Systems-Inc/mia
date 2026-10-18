# HR Officer v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Staff ask their hours, payday, 13th month and contributions, file leave that head staff approve with a tap, get payslips computed by code on payday; the owner gets a certificate text.

**Architecture:** The scaffolded package `mia/agents/hr_officer/` (the greeting turn) grows the inventory manager's shape: three agent-owned tables, pure `ph.py` and `calendar.py`, a `find_dates` addition to `mia/agents/parsing.py`, actions, decider, nine tools (leave through the approvals guard with the approve and reject registries), replies, due work. Reads only core data that is already shared (approved timesheets, people, branches). No money tool (Q57).

**Tech Stack:** as the inventory manager.

**Spec:** docs/superpowers/specs/2026-10-19-hr-officer-design.md

## Global Constraints

The sales supervisor plan's list applies (docs/superpowers/plans/2026-10-19-sales-supervisor.md), plus:
- Rule 7 above all: every peso and minute is Python with a unit test; `ph.py` tables are dated constants (`TABLES_AS_OF`) with Q61; nothing numeric from Jev.
- Rule 3 and the approvals: `request_leave` is `approval: always` with approvers supervisor, owner, admin; the guard stores the validated input in the evidence; the approve and reject registries apply the decision; the requester never approves (approvals core).
- No risky tool (money, external, delete) in this plan (Q57).
- Rule 15: ids from `MANIFEST.id`; the scaffold wired registry, label, policy `use` lines, schema, layout.
- The hours helpers come from `mia/templates/retail/hours.py` (opening hours, business date); the calendar module is new and country-level (`mia/agents/hr_officer/calendar.py`), not retail.

## Review Focus (from checklist.md, pinned)

1. A clerk never reads another person's hours, payslip or balance; a supervisor reads their branch only (Task 3, `test_a_clerk_reads_only_their_own_hours`, `test_a_supervisor_reads_their_branch_only`).
2. A leave approval executes exactly the requested leave and the requester cannot approve it (Task 3, `test_a_supervisor_cannot_approve_their_own_leave`, `test_the_approved_leave_is_the_one_requested`).
3. Payslips are issued once per cutoff and never recomputed after issue (Task 6, `test_payslips_are_issued_once_per_cutoff`, `test_an_issued_payslip_is_not_recomputed`).
4. The night differential and overtime split is computed from the timesheet's own times in the branch's zone, across midnight (Task 2, `test_night_minutes_across_midnight`).
5. Dates typed in Filipino weekday names and "next week" resolve by code to the right dates (Task 2, `test_find_dates_next_week_weekday_in_filipino`).
6. Every key in ten languages through the coverage test; replies assert through `t(...)` (Task 7).

---

### Task 1: Data and configuration

**Files:** `node/mia/agents/hr_officer/models.py` (`Contract`, `Payslip`, `Leave`), `node/migrations/versions/0000_initial.py`, `node/mia/core/orgconfig.py` (`OrgSettings.holidays: list[Holiday]` with `date`, `kind` in regular or special, `name`; `OrgSettings.payroll: Payroll(cutoffs="semi_monthly", pay_lag_days=5)`; loaded from `settings.yaml` with `holidays` either inline or from `holidays.yaml` next to it, your call, say which), `node/config/org/ferinos/settings.yaml` and `holidays.yaml` (the 2026 PH list, Q62), `node/mia/templates/retail/seed.py` (contracts per person, two approved leave rows, two issued payslips per clerk for the last two cutoffs, one "Counter shift" job and location per branch with two weeks of completed visits and approved timesheets through `store.insert`, noted as seed-only), `node/tests/templates/test_retail_seed.py`, `node/tests/test_orgconfig.py` (or where OrgSettings is tested).

**Interfaces (produces):** the three models with the spec's columns (`Payslip` unique on `person_id`, `cutoff_start`); `OrgSettings.holidays` and `.payroll`; seed constants `CONTRACTS`, `HOLIDAYS_2026`.

- [ ] Failing tests: seed counts (6 contracts: no, the owner has none, so 5; 2 leave rows; 2 payslips per clerk; approved timesheets for the last 14 days per clerk); `OrgSettings(holidays=[{"date": "2026-12-25", "kind": "regular", "name": "Christmas"}])` validates and a bad kind is refused; `test_migrations` green.
- [ ] Implement; `uv run pytest node/tests/templates/test_retail_seed.py node/tests/test_migrations.py --no-cov`; full checks; commit `hr: contracts, payslips and leave (agent-owned), the holiday calendar and payroll settings, the Ferino's seed with approved timesheets`.

---

### Task 2: Calendar, PH payroll rules, dates, actions and decider

**Files:** Create `node/mia/agents/hr_officer/calendar.py`, `ph.py`; modify `node/mia/agents/parsing.py` (`find_dates`), `node/mia/agents/hr_officer/actions.py`, `decider.py`; tests `node/tests/test_hr_calendar.py`, `test_hr_ph.py`, `test_parsing.py` (dates), `test_hr_actions.py`.

**Interfaces (produces):**
- `calendar.cutoff(day: dt.date) -> tuple[dt.date, dt.date]` (1st to 15th, 16th to month end); `previous_cutoff(day)`; `payday(cutoff_end, lag: int, holidays: Mapping[dt.date, str]) -> dt.date` (moved to the previous working day when it falls on a Sunday or a holiday); `working_days(start, end, rest_day: int, holidays) -> int`; `leave_days(start, end, rest_day, holidays) -> int`; `sil_balance(start_date: dt.date, today: dt.date, used: int) -> int` (five days a year after one year, pro rata by completed months in the current year of service, never negative).
- `ph.py`: `TABLES_AS_OF = "2026-01"`; `sss_employee(monthly_basic: int) -> int`, `philhealth_employee(monthly_basic: int) -> int`, `pagibig_employee(monthly_basic: int) -> int` (the 2026 tables as dated constants in minor units with a Q61 note; the mechanism tested at bracket boundaries); multipliers `OVERTIME = 1.25`, `NIGHT = 0.10`, `REST_DAY = 1.30`, `REGULAR_HOLIDAY = 2.00`, `SPECIAL_HOLIDAY = 1.30`; `split_minutes(start, end, tz, rest_day, holidays) -> Minutes(regular, overtime, night, rest_day, regular_holiday, special_holiday)` (8 hours regular per day, the rest overtime; night is the part between 22:00 and 06:00 local, counted alongside; a rest-day or holiday shift's minutes go to that bucket instead of regular); `payslip(minutes_by_day: Sequence[Minutes], daily_rate: int, monthly_basic: int) -> Payslip(lines, gross, deductions, net)` with integer arithmetic (hourly rate = daily rate / 8, rounded half up per line).
- `parsing.find_dates(text, today, lang) -> list[tuple[str, dt.date]]` ids `d0`, `d1` in text order: today, tomorrow, weekday names (en, fi, fil, ceb; the sales supervisor's constants), "next week <weekday>" / "sa susunod na linggo", "<d> <month>" and "<month> <d>" (en month names and the Filipino ones), ISO dates.
- `ACTIONS` as the spec's section 6 with label keys from `MANIFEST.id`; `Query` (message, previous_mia_message, role, today, dates, people (owner and admin only), periods, days); `build_request` (state with the message and the date candidates as a list; questions action, period, which, leave_kind, leave_start, leave_end, day, person (leads only), conversation; no message text in instructions); `_args` per action (`request_leave` -> `{"kind", "start", "end"}` ISO with `missing = "leave_start"` when none; `hours` -> `{"start", "end", "person_id": None}`; `certificate_text` -> `{"person_id"}` with `missing = "person"`; the rest `{}` or the slot).

- [ ] Failing tests: calendar (cutoffs at month ends incl. February; payday on a Sunday and on a holiday moves back; leave days skip the rest day and a holiday; balance pro rata and never negative); ph (each multiplier on a worked example; `split_minutes` for a 14:00 to 23:30 shift gives 480 regular, 90 overtime, 90 night; a 21:00 to 05:00 shift across midnight gives 480 regular and 420 night; a rest-day shift goes to rest_day; a full payslip example by hand with the table lookups at two brackets); `find_dates` ("next week Monday", "sa susunod na linggo Lunes", "Dec 25", "2026-12-25", "bukas"); actions (`file_leave` from "I want to file leave next week Monday to Wednesday" gives start and end; `my_hours` with "last cutoff"; `certificate` by a clerk has no `person` question).
- [ ] Implement; `uv run pytest node/tests/test_hr_calendar.py node/tests/test_hr_ph.py node/tests/test_parsing.py node/tests/test_hr_actions.py --no-cov`; full checks; two commits (`hr: the payroll calendar and the Philippine pay rules as pure code (dated contribution tables, Q61)`, `hr: actions and the Jev request (periods, leave dates, which contribution, the certificate person), the argument mapping; find_dates shared`).

---

### Task 3: Tools, manifest, policy, the leave approval

**Files:** `node/mia/agents/hr_officer/tools.py`, `calc.py` (glue: a person's minutes by day in a period from approved timesheets through `ph.split_minutes`), `manifest.yaml`, `node/config/policies/policy.csv`, `node/tests/conftest.py` (`CLOCK_USERS` if `utcnow` is imported), tests `node/tests/test_hr_tools.py`.

**Interfaces:** the nine tools of the spec with inputs and outputs (`HoursInput(start, end, person_id | None)` -> `HoursOutput(regular, overtime, night, rest_day, holiday minutes, days)`; `NextPaydayOutput(pay_date, cutoff_start, cutoff_end)`; `ThirteenthOutput(earned_basic, estimate, paid_in)`; `ContributionsOutput(sss, philhealth, pagibig, cutoff_end)`; `RequestLeaveInput(kind, start, end)` through the guard (`approval: always`, approvers supervisor, owner, admin) with `apply_leave_approval` and `apply_leave_rejection` registered (the leave row is written `requested` at request time? No: as the inventory order, the handler writes the row on approve from the evidence; a rejection writes nothing but notifies; say so); `BalanceOutput(total, used, left)`; `HolidayInput(day)` -> `HolidayOutput(kind, rate_percent, name)`; `resend_payslip` -> the last payslip's lines as output and a notification to self; `CertificateInput(person_id)` -> `CertificateOutput(text)` built from a template with the person's name, position, branch, start date, today, the owner's name; `set_contract` (owner, admin). `_check` before every read and write; own rows through the `_as_self` pattern, branch scoping through `read_all`/`write_all`. Manifest grants and rows; policy lines (staff: the own-data tools and `request_leave`; supervisor: plus `hours` for the branch and the leave approvals through the approvers list; admin: `read_all`/`write_all` and `certificate_text`, `set_contract`).

- [ ] Failing tests: the Review Focus tests named above; each tool's happy path on the seed; a clerk asking a certificate denied; `test_the_approved_leave_is_the_one_requested` (a forged later event ignored); `test_a_supervisor_cannot_approve_their_own_leave` (approvals.decide refuses the requester); the balance after an approval.
- [ ] Implement; focused tests; full checks; commit `hr: nine tools behind rbac (own rows, branch scoping), leave through the approvals guard with approve and reject handlers, the certificate text from a template`.

---

### Task 4: Turn and replies, scenarios 1 to 4

**Files:** `node/mia/agents/hr_officer/turn.py`, `replies.py`, `node/mia/i18n/strings.py` (en, fi); tests `node/tests/test_hr_officer_chat.py`.

- [ ] Failing tests through `run_turn` with the fake Jev: `test_a_clerk_asks_their_hours_this_cutoff`, `test_payday_is_the_next_one_after_the_cutoff`, `test_thirteenth_month_is_a_twelfth_of_basic_earned`, `test_contributions_come_from_the_last_payslip`, injection is data, the greeting with capabilities, a clerk asking another person's hours is refused in words.
- [ ] Implement (the inventory turn's shape; questions: none in this task beyond Did-you-mean); full checks; commit `hr: the HR officer answers in chat: hours this cutoff by kind, the next payday, the 13th month so far, the last contributions`.

---

### Task 5: Scenarios 5 to 8

**Files:** turn.py, replies.py, strings.py; tests.

- [ ] Failing tests: `test_a_leave_request_waits_for_head_staff` (an Approval, no leave row yet), `test_an_approved_leave_tells_the_requester_and_updates_the_balance` (through `approvals.decide`), `test_a_rejected_leave_tells_the_requester`, `test_leave_dates_are_asked_when_missing` (buttons with the date candidates), `test_holiday_pay_question_reads_the_calendar`, `test_a_payslip_is_resent`, `test_the_owner_gets_a_certificate_text`, `test_a_clerk_cannot_get_a_certificate`.
- [ ] Implement; full checks; commit `hr: leave requests approved by head staff on a card with the balance, holiday pay answers from the calendar, payslips resent, the certificate text for the owner`.

---

### Task 6: Due work

**Files:** `node/mia/agents/hr_officer/due.py`, turn.py (`run_due`), strings.py; tests `node/tests/test_hr_due.py`.

**Interfaces:** `run_due(session, now) -> int`; `payslips_due(now, branch tz, payroll, holidays) -> cutoff | None` at 09:00 local on a payday; `issue_payslips(session, branch, cutoff)`: one `Payslip` row per person with an active contract from `calc` and `ph.payslip`, event `hr.payslip_issued` each, a notification in the person's language with the lines, marker `hr.payslips_issued` (branch, cutoff) with message ids; `approval_reminder` at 09:00 two days before the cutoff ends to `alerts.supervisors` with the count of draft timesheets (marker `hr.approval_reminded`); the org gate.

- [ ] Failing tests at fixed clocks: `test_payslips_are_issued_once_per_cutoff`, `test_an_issued_payslip_is_not_recomputed` (a later timesheet correction does not change an issued row), `test_a_payday_on_a_sunday_pays_the_friday_before`, `test_head_staff_are_reminded_to_approve_timesheets`, the org gate, quiet hours (09:00 is outside them; assert no `send_after`).
- [ ] Implement; full checks; commit `hr: due work on the tick: payslips issued once per cutoff on payday, head staff reminded to approve timesheets before the cutoff closes`.

---

### Task 7: Ten languages

- [ ] Every `hr.*` and `intent.hr_officer.*` key in the eight modules (fil first), placeholders identical, no digits, the Q28 to Q35 note; chat and due tests assert through `t(...)`; full checks; commit `i18n: the HR officer's replies, questions and buttons in all ten languages (Philippine languages as machine drafts, Q28 to Q35)`.

---

### Task 8: Evals, gates and docs

- [ ] `node/tests/evals/hr_officer_cases.py` (ten messages per scenario 1 to 8 per gated language, tune and gate halves by seed), the scaffolded harness filled (scoring: right = action and, for leave, the dates; wrong; ask; other), the offline shape test; ten router seeds per gated language for the HR officer in `router_cases.py` and `PENDING` emptied (check whether the HR officer already has cases from the retail set; if so, add none and say so); run the decider gate once (tune once on the tune half, rerun once); the router gate is not rerun unless the HR description changed; reports under docs/research/; README, docs/layout.md, questions (Q57 to Q62 exist); the spec's Carried over line.
- [ ] Full checks; commit `hr: decider eval set and gate, report, README and layout`.

## Self-review

Every spec scenario has a test (1 to 4 in Task 4, 5 to 8 in Task 5, 9 and 10 in Task 6); every Review Focus line has a task and a test; no money tool; the data standard gate is satisfied (Q59 recorded); `find_dates` is added once and shared.
