# HR officer v1: hours, pay, leave, contributions, payslips

19 Oct 2026. Built with `/mia-build-agent hr_officer` (docs/agents-catalogue.md row). Proof
shop: Ferino's Bibingka. **Status: in execution** under the owner's "build all" (the
developer's three answers of step 1 are recorded assumptions: proof shop Ferino's; roles
staff and clerk (their own data), supervisor (the branch, leave approvals), owner and admin
(everything, contracts, payslips); the first five scenarios are 1 to 5 below).

## 1. Goal

A clerk asks how many hours they worked this cutoff, when payday is, how much their 13th
month is so far and what was deducted for SSS, PhilHealth and Pag-IBIG; files a leave request
that head staff approve with a tap; gets a payslip on payday computed by code from approved
timesheets and their contract; the owner gets a certificate of employment text to sign. All
Philippine labour arithmetic is Python with unit tests (rule 7); Jev only picks the action and
the period.

Out of scope: cash advances (a money tool; CLAUDE.md says ask before adding a risky tool: Q57,
owner's call); withholding tax (Q58); remittance to SSS, PhilHealth and Pag-IBIG (the
bookkeeper, later); hiring posts, interview scheduling, contracts drafting, SOP answers,
exits beyond the certificate (next phase or follow-up); reading sales or stock data (none).

## 2. Data standard check (gate 1, the owner)

| Table | Written by | Read by now | Read by later | Verdict |
| --- | --- | --- | --- | --- |
| `timesheets`, `person`, `branch`, `visit` (core) | shift_supervisor, people | hr_officer reads | | core, no change |
| `hr_officer_contracts` | hr_officer (owner, admin) | hr_officer | bookkeeper (payroll cost) | agent-owned now |
| `hr_officer_payslips` | hr_officer (due work) | hr_officer | bookkeeper | agent-owned now |
| `hr_officer_leave` | hr_officer | hr_officer | shift_supervisor (rosters) | agent-owned now |
| `config/org/<org>/holidays.yaml` | config | hr_officer | shift_supervisor later | config, not a table |

No core change, so no owner gate now. Promotion of the three tables is recorded as blocking
before the bookkeeper or the roster reads them (Q59, with Q39 and Q53).

## 3. Who talks to it

| Role | May | Scope |
| --- | --- | --- |
| staff, clerk | ask their hours, payday, 13th month, contributions, holiday pay; request leave; ask for their payslip again | own rows (`read_own`) |
| supervisor | the same, plus the branch's hours summary and approving leave (approver) | own branch; `read_all` denied |
| owner, admin | everything for every branch; set and change contracts; the certificate text; approve leave | `read_all`, `write_all`; approvers |

Policy: `agent:hr_officer, use` for staff (clerk inherits), supervisor, owner (admin inherits
through the hierarchy; check the `g` lines). Tool and data lines in the plan's Task 3.

## 4. Scenarios (the acceptance list)

1. **Hours this cutoff.** "how many hours did I work this cutoff" (and "last cutoff", "this
   month"): approved timesheet minutes in the period, regular, overtime, night and rest-day
   minutes split by code, in one line each. Test `test_a_clerk_asks_their_hours_this_cutoff`.
2. **Payday.** "when is payday": the next payday from the cutoff rule (the 15th and the last day
   of the month, paid five days later, moved to the previous working day when it falls on a
   holiday or Sunday; Q60). Test `test_payday_is_the_next_one_after_the_cutoff`.
3. **13th month so far.** "how much is my 13th month": one twelfth of the basic pay earned this
   calendar year from issued payslips, with the month it is paid (December). Test
   `test_thirteenth_month_is_a_twelfth_of_basic_earned`.
4. **Contributions.** "is my SSS paid", "magkano ang PhilHealth ko": the employee shares from
   the last issued payslip, from the dated tables in code (`ph.py`, `TABLES_AS_OF`, Q61 to
   verify with the accountant); remittance status is out (bookkeeper). Test
   `test_contributions_come_from_the_last_payslip`.
5. **Leave.** "I want to file leave next week Monday to Wednesday", "sick today": a leave row
   `requested` and an approval card to the branch's supervisors (fallback owners and admins);
   the tap approves or rejects, the requester is told, the balance (five service incentive
   leave days a year after one year of service, pro rata) is shown; "how many leave days do I
   have left". Tests `test_a_leave_request_waits_for_head_staff`,
   `test_an_approved_leave_tells_the_requester_and_updates_the_balance`,
   `test_a_supervisor_cannot_approve_their_own_leave`.
6. **Holiday pay.** "do we get holiday pay on Monday": from `holidays.yaml` the kind (regular,
   special non-working, none) and the rate rule (200% or 130%, 100% when not working on a
   regular holiday after a worked day before). Test `test_holiday_pay_question_reads_the_calendar`.
7. **Payslip again.** "my payslip is missing", "send my payslip": the last issued payslip's
   breakdown resent as a notification. Test `test_a_payslip_is_resent`.
8. **Certificate of employment.** The owner asks "COE for Ana": a fixed-format text (name,
   position from roles, branch, start date from the contract, today's date, the owner's
   name) for the owner to copy and sign; no model writes it. Test
   `test_the_owner_gets_a_certificate_text`.
9. **Payslips on payday (due).** On each payday at 09:00 local, one payslip per person with an
   active contract: regular, overtime, night differential, rest day and holiday pay, less SSS,
   PhilHealth, Pag-IBIG; issued once per cutoff (a row), delivered as a notification in the
   person's language; marker `hr.payslips_issued` per branch and cutoff. Test
   `test_payslips_are_issued_once_per_cutoff`.
10. **Timesheet approval reminder (due).** Two days before the cutoff closes, head staff get the
    count of draft timesheets to approve (the shift supervisor's approval flow does the
    approving). Test `test_head_staff_are_reminded_to_approve_timesheets`.

## 5. Data

Agent-owned, `mia/agents/hr_officer/models.py`:

| Table | Row |
| --- | --- |
| `hr_officer_contracts` | `person_id` FK, `employment_type` (regular, probationary, part_time), `daily_rate: int` (minor units), `currency`, `rest_day: int` (weekday), `start_date`, `end_date: date | None`, `position: str`, `set_by` |
| `hr_officer_payslips` | `person_id`, `cutoff_start`, `cutoff_end`, `pay_date`, `lines: list[dict]` JSON (kind, minutes or days, rate, amount), `gross: int`, `deductions: list[dict]` JSON, `net: int`, `currency`, `issued_at` TZDateTime, `message_id: str | None`; unique (`person_id`, `cutoff_start`) |
| `hr_officer_leave` | `person_id`, `kind` (vacation, sick, unpaid), `start_date`, `end_date`, `days: int`, `status` (requested, approved, rejected), `approval_id`, `reason: str` (free text stored as data) |

Config: `config/org/<org>/holidays.yaml` as a list of `{date, kind: regular | special, name}`
read by `orgconfig` into `OrgSettings.holidays` (validated dates); Ferino's gets the 2026 PH
list (regular holidays and special non-working days as published; Q62 to verify). The cutoff
rule lives in `OrgSettings.payroll` (`cutoffs: semi_monthly`, `pay_lag_days: 5`).

Core read only: `timesheets` with `status == "approved"`, `person`, `branch`, `visit`.
Rule 14: `0000_initial` edited in place.

## 6. The agent

**Actions:** `my_hours` (tool `hours`; slot `period`: this_cutoff, last_cutoff, this_month,
last_month, not_stated), `payday` (`next_payday`), `thirteenth` (`thirteenth_month`),
`contributions` (`last_contributions`; slot `which`: sss, philhealth, pagibig, all),
`file_leave` (`request_leave`; slots `leave_kind`, `leave_start` and `leave_end` over
pre-parsed date candidates: today, tomorrow, weekday names, "next week" plus explicit dates
found by code), `leave_balance` (`balance`), `holiday_pay` (`holiday`; slot `day` over the
next 14 days' candidates), `my_payslip` (`resend_payslip`), `certificate` (`certificate_text`;
slot `person` over the branch's people, owner and admin only), `reply_only`, `clarify`.

**Tools:**

| Tool | Risk | Writes | Who |
| --- | --- | --- | --- |
| `hr_officer.hours` | read | | all; supervisor and leads for others |
| `hr_officer.next_payday` | read | | all |
| `hr_officer.thirteenth_month` | read | | all (own); leads for others |
| `hr_officer.last_contributions` | read | | all (own) |
| `hr_officer.request_leave` | write_internal, `approval: always`, approvers supervisor, owner, admin | leave, approvals | staff, clerk, supervisor |
| `hr_officer.balance` | read | | all (own); leads for others |
| `hr_officer.holiday` | read | | all |
| `hr_officer.resend_payslip` | read (sends a notification to self) | | all (own) |
| `hr_officer.certificate_text` | read | | owner, admin |
| `hr_officer.set_contract` | write_internal | contracts | owner, admin (chat v2; v1 seeds and the importer) |

The leave approval uses the approvals guard (`approval: always`, the validated input in the
evidence) with the approve and reject registries; whoever requested never approves (the
approvals core already refuses the requester); a supervisor approving their own leave is
refused by that rule. Payslips are issued by the due work, never by a chat tool.

**Pure modules:** `ph.py` (contribution tables with `TABLES_AS_OF`, the rate multipliers,
night window 22:00 to 06:00, `payslip(minutes_by_kind, daily_rate, ...) -> lines and
deductions`), `calendar.py` (cutoffs, paydays, holidays, working days, leave days between two
dates skipping rest days and holidays), `calc.py` glue (split a timesheet's minutes into
regular, overtime, night, rest day, holiday by the contract and the calendar).

**Due work:** payslips at 09:00 local on a payday (not urgent; quiet hours end before); the
approval reminder at 09:00 two days before a cutoff ends (not urgent). Markers
`hr.payslips_issued` (branch, cutoff) and `hr.approval_reminded` (branch, cutoff).

**Events:** `hr.contract_set`, `hr.leave_requested`, `hr.leave_approved`, `hr.leave_rejected`,
`hr.payslip_issued` (one per payslip), `hr.payslips_issued`, `hr.approval_reminded`,
`hr.certificate_issued`.

## 7. Parsing

The shared parser is not needed for counts. Dates by code (`parsing.find_dates`): "today",
"tomorrow", weekday names in the person's language (reuse the sales supervisor's weekday
constants), "next week <weekday>", "<d> <month>" and "<month> <d>", ISO; Jev picks among the
candidate ids. Period ids as fixed criteria. Numbers never from Jev; money formatted by code.

## 8. i18n

Keys `hr.*` (hours lines, payday, 13th month, contributions, leave question texts and buttons,
leave approved and rejected, balance, holiday answers, payslip lines and the resent payslip,
the certificate text, capabilities, not allowed) and `intent.hr_officer.*` in ten languages
(eight as machine drafts, Q28 to Q35).

## 9. Seed and configuration

Ferino's seed: a contract per person (daily rates in PHP: clerks 61000 centavos, supervisors
80000, the owner none; rest day Monday for the mall, Tuesday for the stall; start dates in
2025 and 2026 so one clerk has under a year of service), two approved leave rows, two issued
payslips for the last two cutoffs per clerk (so questions have data), and
`config/org/ferinos/holidays.yaml` with the 2026 list; `settings.yaml` gains `payroll:` and
`hr_officer` in `agents`. Approved timesheets for the retail org: the retail seed has no
visits today; the seed adds, per clerk, two weeks of visits with check-in and check-out times
through the existing core models (visits need a job and a location: one "Counter shift" job
per branch) and approved timesheets through `shift_supervisor.timesheets` (built then
approved by the owner), so hours have data. If that is heavy, the plan may seed timesheet
rows directly through `store.insert` with a note.

## 10. Testing and gates

Unit: `ph.py` (each multiplier, each table lookup at the boundaries, a full payslip example
worked by hand), `calendar.py` (cutoffs across month ends, paydays moved off a Sunday and a
holiday, leave days skipping rest days and holidays, pro rata balance), `find_dates`; tools
with mocked deps and a negative test per tool (another person's hours by a clerk, a clerk
asking a certificate, a supervisor approving their own leave); chat through `run_turn` for
every scenario; due tests at fixed clocks (payday morning, the day after, the reminder day);
the decider gate at the Q40 bar on a fresh gate half; ten router seeds per gated language and
`PENDING` emptied.

## 11. Open questions

- Q57: cash advances are a money tool; CLAUDE.md says ask before adding a risky tool. Out of
  v1; the owner decides. (The inventory manager's `draft_order` is a money tool added without
  asking, executed only on the owner's approval tap; the owner may want it disabled.)
- Q58: withholding tax is out of v1; the accountant's call.
- Q59: the three hr tables move to core with the sales and inventory tables (1.5).
- Q60: the cutoff and payday rule assumed: semi-monthly, paid five days after the cutoff, moved
  to the previous working day.
- Q61: the SSS, PhilHealth and Pag-IBIG tables in `ph.py` are dated constants to be verified
  with the accountant before real payslips.
- Q62: the 2026 holiday list in `holidays.yaml` to be verified.

## 12. Order of work

1. Data (tables, migration, config fields, holidays, seed). 2. `calendar.py`, `ph.py`,
`parsing.find_dates`, actions and decider. 3. Tools, manifest, policy, the leave approval.
4. Turn and replies for scenarios 1 to 4. 5. Scenarios 5 to 8. 6. Due work (9, 10). 7. Ten
languages. 8. Evals, gates, docs.

## Carried over
- Decider gate (19 Oct, docs/research/hr-officer-2026-10-19.md): passes at the Q40 bar on the
  gate half after one tuning edit (wrong 0.0%; right en 94%, fil 94%, ceb 92%, hil 90%, war
  90%, bcl 90%; ask 6% to 10%). Leave requests are the ask cost (63% right, every miss a
  clarify with the right dates); "next week" and today or tomorrow words in ceb, hil, war and
  bcl are not in `find_dates` yet. The router gate was not rerun (description unchanged).
