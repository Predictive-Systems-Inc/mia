# shift_supervisor retail copy: design

Date: 21 October 2026. Catalogue row: docs/agents-catalogue.md (shift_supervisor, "built; retail
copy needed"). Shape followed: docs/superpowers/specs/2026-10-20-bookkeeper-design.md. Builds on
D1 (an instruction is the approval), D3 (job and visit in core), D34 (scheduling core), Q20
(timesheets in core). Filipino first, never "Tagalog". Questions Q101 to Q111 are open.

## 1. Goal

The same shift supervisor, for a kiosk chain: who opens and who closes each kiosk this week,
check-in and check-out at the counter, "may sakit ako bukas" and the cover from the other kiosk,
a swap between two clerks, a corrected time, a broken stove or a delivery that never came, the
week's roster to staff, and a kiosk closed for a holiday. Shifts follow the branch's hours
(opening, closing, split shifts, a second clerk on weekends). Timesheets keep feeding the HR
officer's pay, which already reads approved rows. Proof shop: Ferino's Bibingka (Mall kiosk
09:00 to 21:00, Street stall 06:00 to 19:00).

Package (Q101): recommend (a), the same package with a template switch
(`orgconfig.load().template == "retail"` picks the shift words and rules), not (b) a sibling id:
rule 15 gives one id per job, and only words and three rules differ (no skills, no travel, the
kiosk instead of a site).

Out of scope for v1: checklists and rider dispatch (Q109), photos, geocoding (a kiosk is its
branch), the schedule board (Q19), pay (the HR officer's), counts reminders (the sales supervisor's).

## 2. Data standard check (gate 1, the owner)

The retail seed already models a kiosk shift as a core `visit` (`_seed_hr`: one Client and one
Location per branch, a Job "Counter shift", one completed visit and one approved timesheet per
clerk and day), the HR officer's pay reads those timesheets (`hr_officer/calc._approved`) and the
sales supervisor's `_clerks` (due.py) reads visits to know who is on shift. So the assumed answer
to Q102 is: a kiosk shift is a Visit, the branch's single Location is "the kiosk", one Job per
shift pattern (Opening, Closing, Weekend second clerk, each split part its own Job), one visit
per clerk so per-person check-in works (D34's two-person limit never applies). No new core
table. The question to the owner (Q102): Visit as the shift, or a new core `shifts` table; and
the incident kinds `equipment`, `no_delivery`, `customer` added to the code list (data standard
1.7, a code list change only). Stop rule: if the owner wants `shifts`, or says no to the kinds,
stop scenario work until a yes, then one migration edit (0000_initial, rule 14) and ADR 019.

Reads: core `visit`, `job`, `location`, `person`, `availability`, `work_limits`, `absences`,
`leave` (approved leave counts as absent, new), `cover_requests`, `timesheets`, `incidents`,
`supplier_orders` (no_delivery names the open order), template `retail_branch_hours`. Writes:
`job` and `visit` (through mia/core/scheduling), `absences`, `cover_requests`, `timesheets`
(drafts and corrections), `incidents`. Other readers: visits (sales supervisor), timesheets and
leave (HR officer), supplier_orders (inventory manager, bookkeeper), all already core. Closed
days (Q105): template table `retail_closures` beside `retail_branch_hours`, read by every agent
that works to the hours. Cross-kiosk cover (Q103) puts a person of one branch on another
branch's visit: no schema change, a security rule change, so that part waits for the answer.

## 3. Who talks to it

Clerk (staff by inheritance): own shifts, check-in and check-out, absences, answering a cover
ask, asking a swap, own timesheet correction while draft, reporting an incident; own branch.
Head staff (supervisor): the branch's roster, cover, swaps, corrections, incidents, closing a
day. Owner and admin: every branch, the roster pattern, cover overrides (app only, D34).
Languages: ten; Ferino's runs fil, ceb, en. Channels: the existing chat and outside channels.

## 4. Scenarios (the acceptance list)

1. Roster from the owner's pattern: "Ana opening Martes hanggang Linggo 9 to 5, Liza closing 1 to
   9, Sabado at Linggo dagdag si Liza 9 to 1 sa umaga" makes Jobs with RRULEs and assigns them;
   generation keeps 28 days ahead; a clash with hours or limits is listed, never saved silently.
   `test_a_roster_pattern_makes_the_weeks_shifts`, `test_a_pattern_outside_opening_hours_is_refused`.
2. Check-in at the kiosk: "nandito na ako" checks Ana in at the Mall kiosk (her visit today, no
   location asked, no geocoding); two clerks on Saturday each check in on their own visit; "uwi
   na ako" checks out and drafts the timesheet. `test_two_clerks_check_in_on_a_weekend`.
3. Late: "malelate ako 30 minutes" records a late absence for today's shift; no message and no
   check-in 15 minutes after the start tells head staff (alerts.missed_check_ins).
   `test_a_late_check_in_tells_head_staff`.
4. No-show and cover: Pao is sick tomorrow; head staff asks "sino pwede sa Street stall bukas?";
   candidates from both kiosks under the same rules minus skills (available, not absent or on
   leave, not double-booked, within hour limits; ranked by has worked this kiosk, fewest week
   hours, name); "si Liza" asks Liza (message, then call, then the next). Breaking a rule is the
   cover override approval. `test_a_no_show_gets_cover_from_the_other_kiosk`.
5. Swap: "palit kami ni Liza sa Sabado" from Ana asks Liza, then head staff confirms with a quick
   reply; both visits change in one write; either breaking a rule is the override (Q104).
   `test_a_swap_needs_the_other_clerk_and_head_staff`.
6. Timesheet correction: "nakalimutan kong mag-check out, 9pm ako umalis" corrects Ana's draft
   (timesheets.correct, back to draft, she can never approve it); after approval only head staff
   corrects. `test_a_clerk_corrects_her_draft_timesheet`, `test_an_approved_timesheet_needs_head_staff`.
7. Retail incident: "sira ang kalan" is `equipment`, "walang dumating na delivery ng itlog" is
   `no_delivery` (names the open supplier order), "may nagwala na customer" is `customer`; head
   staff and the owner are told. "kulang ang cash" is the bookkeeper's, "ubos na ang LPG" the
   inventory manager's (Q108). `test_a_broken_stove_is_an_equipment_incident`,
   `test_short_cash_routes_to_the_bookkeeper`.
8. Weekly roster to staff: Sunday 17:00 (Q110) each clerk gets their own week, head staff the
   branch's; the daily plan then goes only when tomorrow changed. `test_the_weekly_roster_goes_out_once`.
9. Holiday closing: "sarado ang Mall kiosk sa Nov 1" by head staff or the owner writes a closure,
   cancels that day's visits, tells the clerks; the sales and inventory reminders skip the day.
   `test_a_closed_day_cancels_its_shifts`.
10. Security: a clerk sees only her shifts; a supervisor only their branch (cross-kiosk cover as
    Q103 decides); the override needs admin or owner; a retail clerk is a candidate through role
    inheritance. `test_a_clerk_reads_only_her_shifts`, `test_a_cover_override_needs_the_owner`.

## 5. Data

No new core table under the assumed Q102. Template: `retail_closures` (branch, date, reason,
set_by; ULID, aware times), Q105. Seed-level fixes: Availability rows for retail clerks (their
working days, the branch's open hours) and WorkLimit rows (Q106), since without them every clerk
is "outside availability". Incident kinds gain equipment, no_delivery, customer. Money is not
touched. Migration: `0000_initial` edited in place for `retail_closures` (rule 14).

## 6. The agent

Same tools, same ids (tool and intent ids are stable even where they say visit or site); new
tools: `set_roster` (write, supervisor and owner; writes jobs and assignments through a new
`scheduling.upsert_job`), `swap_shifts` (write; asks the other clerk, then head staff),
`correct_timesheet` (write, own draft or supervisor), `close_day` (write, supervisor and owner),
`roster` (read, the week). Actions add set_roster, swap, correct_time, close_day, week_roster.
Due work: cover escalation, missed check-in and check-out, overtime, unstaffed tomorrow at 15:00,
the weekly roster (marker `notification.weekly_roster`, once per branch and week), the daily plan
only on a change. Events: `visit.*`, `timesheet.*`, `incident.*`, `retail.closure_set`.

Messages that stay theirs, not duplicated: the sales supervisor's closing reminder, missing list,
owner report and morning message; the inventory manager's closing summary and bake plan; the
bookkeeper's closing-count reminder; the HR officer's draft-timesheet reminder and payslips. The
shift supervisor's own end-of-shift messages are only the missed check-out and overtime alerts.

Where cleaning leaks today (each switched by the template, or made neutral):
- scoring.py: English reason literals ("knows the site", "has the required skills", travel km)
  shown in the cover card; retail drops skills and travel and words "has worked this kiosk".
- core/scheduling.candidate_data: `"staff" in p.roles` is a literal check, so a retail clerk
  (roles [clerk], staff only by inheritance) is never a candidate; use the role graph. Candidates
  are branch-only (Q103). Approved `leave` is not read.
- actions.py: "lost its cleaner", "the shift supervisor of a cleaning", "cleaners: {who}", and an
  unconditional `CleaningChecklist` import (line 179).
- tools.py: visit_details (address, access notes, cleaning checklist), checklist (cleaning
  tables), report_site_problem kinds (cannot_access, site_problem), VisitInfo.job.
- manifest.yaml: `data:cleaning_checklist_ticks:write`; the checklist tool off for retail.
- i18n: visits.*, plan.intro, alert.unstaffed_intro ("without a cleaner"), cover.*, cover.call_script
  ("cover {location}"), problem.*, check_in.* and check_out.*, field.*, fallback.quick_visits.
- turn.py router_description ("a site", "cleaning checklists"); prompts/base.md and job.md
  ("cleaning visit", "cleaner"); skill/role.yaml seeds (cleaning, mostly Finnish).
The switch: one helper in replies.py, `word_key(key)`, returns `retail.<key>` when the template
is retail and the English table has it, else the key; logic reads the template through one
function, `is_retail()` in rules.py, so no second module is needed.

## 7. Parsing

Code (rule 7): times ("9 to 5", "1-9pm"), weekday ranges ("Martes hanggang Linggo") into RRULE
BYDAY, `parsing.find_dates`, roster expansion, eligibility, swaps, minutes, closures. Jev picks the action,
the person among the branch's people (or both branches', Q103), the kiosk among branches, the
shift among the branch's Jobs (opening, closing), the incident kind among the code list. A
negation is a correction ("hindi Sabado, Linggo"); an unlisted day is asked, never assumed.

## 8. i18n

Keys `retail.visits.*` and the rest above (shift words: "shift", "pasok", "kiosk"), new
`shift.roster.*`, `shift.swap.*`, `shift.closed.*`, `intent.shift_supervisor.*` for the new
intents; en, fi, fil and ceb by the build, six modules as drafts (Q28 to Q35); same label.

## 9. Seed and configuration

Ferino's: Availability per clerk (Ana and Liza Tuesday to Sunday at the mall, Pao Wednesday to
Monday at the stall, the branch hours), WorkLimit rows (Q106), the existing Counter shift Job
split into Opening and Closing Jobs with the seeded clerks' times (SHIFTS), a Weekend second
clerk Job at the Mall kiosk, the existing completed visits and approved timesheets kept, planned
visits generated from today, one open equipment incident, one closure on the next holiday in
`orgconfig.holidays`. Settings: `shift_supervisor.weekly_roster_time` (Sunday 17:00). Policy:
staff the clerk's new tools, supervisor the new write tools, owner and admin on every branch.

## 10. Testing and gates

Pure-code tests: the pattern parser, RRULE expansion against hours and closures, eligibility
without skills and with leave, swap validation. Chat tests through run_turn for scenarios 1 to
10 in fil and ceb; due tests at fixed Manila clocks (weekly roster once, the daily plan only on a
change, a closed day silent). Cleaning regression: the whole existing shift supervisor suite
passes unchanged with `template: cleaning`. The decider gate at the Q40 bar; router seeds with
the contrast "shifts, attendance, cover, kiosk problems; not counts, stock, cash or pay".

## 11. Open questions

- Q101. Where: catalogue, rule 15. Question: same package with a template switch, or a sibling
  id? Assumed answer: the same package (a). Blocking: no.
- Q102. Where: data standard (visit, incident). Question: is a kiosk shift a Visit (the branch's
  one Location, a Job per shift pattern, one visit per clerk) or a new core `shifts` table; and
  may incidents gain equipment, no_delivery, customer (1.7)? Assumed answer: Visit, kinds yes.
  Blocking: yes (gate 1, the stop rule in section 2).
- Q103. Where: scheduling.candidate_data, rbac branch scoping. Question: may a clerk of one kiosk
  cover the other's shift (a person on another branch's visit, read_own there)? Assumed answer:
  yes within one organisation, head staff of the shift's branch instructs. Blocking: yes for the
  cross-kiosk part of scenario 4 (a security rule).
- Q104. Where: D1, scenario 5. Question: who approves a swap two clerks agree on? Assumed answer:
  head staff's yes is the instruction; a rule break is the cover override. Blocking: no.
- Q105. Where: templates/retail/hours.py. Question: where does a closed day live? Assumed answer:
  template `retail_closures`, read by hours.open_days, written by the shift supervisor's
  close_day (supervisor, owner). Blocking: yes for scenario 9 only (a table several agents read).
- Q106. Where: core work_limits, Availability. Question: Ferino's hour limits and availability?
  Assumed answer: daily 600 minutes, weekly 3,240 (six 9-hour shifts with the meal hour),
  availability the contract days and branch hours; placeholders the owner corrects. Blocking: no.
- Q107. Where: core incident (visit_id required). Question: an incident when the reporter has no
  shift (head staff)? Assumed answer: it attaches to the branch's first open visit today; on a
  closed day head staff and the owner get the message, no row. Blocking: no.
- Q108. Where: catalogue. Question: whose are "LPG out" and a missed delivery? Assumed answer:
  LPG out is the inventory manager's stock event; a missed delivery is an incident. Blocking: no.
- Q109. Where: catalogue row. Question: opening and closing checklists and rider dispatch in v1?
  Assumed answer: no; later, with quality_officer and customer_service delivery. Blocking: no.
- Q110. Where: alerts.daily_plan. Question: when does the weekly roster go out? Assumed answer:
  Sunday 17:00 for Monday to Sunday, the daily plan only on a change. Blocking: no.
- Q111. Where: customer_service complaints. Question: a clerk's report of a customer at the
  counter: incident or complaint? Assumed answer: an incident; the public's stays a complaint.
  Blocking: no.

## 12. Order of work

1. Gate 1: Q102 to the owner; stop until a yes. 2. Neutral fixes that keep cleaning green: role
inheritance in candidate_data, approved leave as absent, the CleaningChecklist import behind the
template, the reason literals to i18n. 3. The template switch (word_key, rules switch) and retail
keys. 4. Seed: availability, limits, the shift Jobs. 5. Pure code: pattern parser, roster,
swap, closures. 6. New tools and actions, the decider. 7. Chat turn, scenarios 1 to 8 and 10.
8. Closures and scenario 9 (after Q105). 9. Due work: weekly roster, daily plan on change.
10. Ten languages. 11. Evals, gates, router seeds, docs (layout.md, agents-catalogue row).

## Carried over

- The scoring reasons are English literals in a user-facing card (an i18n bug in cleaning too);
  owned by shift_supervisor/scoring.py.
- sales_supervisor `_clerks` falls back to every clerk when a branch has no visits that day; once
  retail visits are generated it narrows to the shift; owned by sales_supervisor/due.py.
- Task 2 (roster and cover): approved leave now counts as absent for cleaning orgs too (no
  cleaning seed has leave); `roster.job_name` may repeat for one clerk, so Task 4 must not rely
  on it being unique; `scheduling.ineligibility` stays branch-only (fails closed) until Task 4
  passes `org_wide=is_retail()`; owned by shift_supervisor/roster.py and core/scheduling.py.
- Task 8 (evals and docs): the cleaning scoring reasons stay English literals, so the cleaning
  tests stay unchanged (retail words them through `roster.REASON_KEYS`); owned by
  shift_supervisor/scoring.py. The Weekend second clerk Job comes from the owner's pattern
  (set_roster), not the seed; owned by templates/retail/seed.py. A Street stall override waits
  for an owner or admin of the stall under `approvals.decide` (it matches the decider's branch,
  and Ferino's has none at the stall); owned by core/approvals.py. Code reads shift and day
  ranges with "-", "to", "hanggang", "hangtod", "until" and "through" only, so a Hiligaynon,
  Waray or Bikol pattern with "tubtob" or "sagkod" is asked again (the eval set writes "-");
  owned by shift_supervisor/roster.py.
- Task 8 gates (docs/research/2026-10-21-shift-supervisor-retail-gate.md): the decider gate and
  the router gate failed and are reported as they are. Open for the developer: a
  find_replacements with a site and no understood date passes `date: None` instead of asking,
  and a cover ask that names the absent clerk but no kiosk asks for the visit (owned by
  shift_supervisor/decider.py); "ran out of LPG" read as a missed delivery and a corrected time
  read as a check-out (owned by shift_supervisor/actions.py, a tuning round needs a fresh decider
  gate half); a customer at the counter routed to customer_service in ceb and hil (owned by
  shift_supervisor/turn.py and customer_service/turn.py, a rerun needs a fresh router gate half).
- Fix wave B (21 Oct): `timesheets.py` `entered_by` records the person who entered a time, never
  the agent, for cleaning too. A deliberate change outside `is_retail()` (separation of duties:
  the person who entered a correction cannot approve it); owned by shift_supervisor/timesheets.py.
- Fix wave B (21 Oct), the open items above now guarded in code (rule 7): a find_replacements at
  the kiosk with a site and no understood date asks for the date; a no_delivery pick whose text
  names LPG or stock (`decider.STOCK_WORDS`) asks; a retail check_out whose text has a time and a
  correction word (`decider.CORRECTION_WORDS`) asks; "tubtob" and "sagkod" read as "hanggang".
  The router description names both worlds again (cleaning checklists). None of this was in the
  gate runs; a rerun needs fresh gate halves.
