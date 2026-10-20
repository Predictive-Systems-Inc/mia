# Questions from the coding agent

All questions below (Q1 to Q7) are answered in docs/decisions.md (D1 to D12).

Format for each entry:

## Q1: short title
- Where: file or spec section
- Question: what is unclear
- Assumed answer: what the code does now
- Blocking: yes or no

## Q1: What `MIA_MODEL=test` runs
- Where: brief, Environment; ADR 004
- Question: the brief says `test` uses Pydantic AI's `TestModel`, and also that the four demo
  conversations must work with `MIA_MODEL=test`. `TestModel` calls tools with generated
  arguments and cannot hold a conversation, so both cannot be true.
- Assumed answer: `test` runs the dispatcher's deterministic rules model (a `FunctionModel`
  driven by the rules classifier from the manifest). `TestModel` is used in unit tests.
- Blocking: no

## Q2: The demo supervisor cannot approve her own request
- Where: brief, demo conversation 3; spec, Approvals ("nobody approves a request they made or triggered")
- Question: in demo 3 the supervisor asks Mia to assign Mikael and then approves. The agent acts
  on her behalf, so she made the request and the spec rule forbids her approval. Which wins?
- Assumed answer: the spec rule. The seed adds an owner (Helena Hyppönen) who approves, so the
  seed has 7 persons instead of 6. Approving as the supervisor shows "nobody approves a request
  they made or triggered". If a supervisor's own chat choice should count as the decision, that
  changes a security rule and needs your decision.
- Blocking: no (the stricter rule is in place)

## Q3: Where Job and Visit live
- Where: brief layout lists Job and Visit in both `core/models.py` and `templates/cleaning/models.py`
- Question: which one owns the tables?
- Assumed answer: core owns location, job and visit (they are in the data standard). The
  cleaning template adds `cleaning_sites`, `cleaning_checklists`, `cleaning_availability` and
  `cleaning_work_limits`.
- Blocking: no

## Q4: Finding the visit for "Who can cover Kalasatama tomorrow at 6:30?"
- Where: brief, tools table (`find_replacements` input: visit id)
- Question: the supervisor names a site and time, not a visit id, and there is no visit search tool.
- Assumed answer: `find_replacements` also accepts `location_name`, `date` and `time` and
  resolves the visit (start within 30 minutes). `get_my_visits` also accepts `person_name` so a
  supervisor can ask about someone else, and a cleaner's attempt is denied and logged (demo 4).
- Blocking: no

## Q5: Evals command path
- Where: brief, commands (`uv run pytest tests/evals -m evals`)
- Question: tests live in `node/tests`, so `tests/evals` does not exist at the repository root.
- Assumed answer: `uv run pytest node/tests/evals -m evals` (or `uv run pytest -m evals`).
- Blocking: no

## Q6: Replacement ranking without travel data
- Where: plan, Replacement scoring ("shortest added travel")
- Question: the seed has no coordinates, so travel cannot be scored.
- Assumed answer: ranking is knows the site, has the skills, fewest hours this week, then name.
  Travel is added when locations have geofence coordinates.
- Blocking: no

## Q7: The existing marketing site in this repository
- Where: repository root (`index.html`, `netlify/`, `netlify.toml`)
- Question: the repository already held a Netlify site ("Mia, your clinic's AI secretary").
  Its `netlify.toml` publishes the whole repository root, so docs and code would be served too.
- Assumed answer: left unchanged. Suggest moving the site to its own repository or setting
  `publish` to a folder that holds only the site.
- Blocking: no

## Q8: Encrypting channel tokens at rest
- Where: spec, Channel rules ("channel tokens encrypted")
- Question: the node has no secret store or field encryption yet.
- Assumed answer: MIA_WA_TOKEN and MIA_WA_APP_SECRET live in `.env` (file permissions, ignored by
  git, excluded by detect-secrets) for Phase 1; they move to encrypted storage with field
  encryption.
- Blocking: no

## Q9: One conversation across app and WhatsApp
- Where: spec, Conversations; ADR 007
- Question: should WhatsApp messages get their own thread?
- Assumed answer: no. A person's latest thread with the agent is shared by the app and every
  channel, so history and approvals stay in one place; the app shows the whole conversation.
- Blocking: no

## Q10: Data standard 1.3 for authentication
- Where: docs/superpowers/specs/2026-10-05-authentication-design.md, section 12; ADR 011
- Question: authentication needs credentials, devices, sessions and clients tables, and one-time
  codes and attempt counts for logins. May the data standard add auth_credentials,
  auth_devices, auth_sessions and auth_clients, and rename channel_link_codes to auth_codes and
  channel_link_attempts to auth_attempts (one table for every one-time code and every attempt)?
- Assumed answer: yes, as proposed in section 12. person gets no new field: phone numbers stay
  in channel_identities and the login email lives on the password credential.
- Blocking: yes (changes the data standard; nothing is built until approved)
- Answered: D17.

## Q11: No email delivery for password resets
- Where: design section 9; spec, Authentication (email plus password)
- Question: email is the office login, but the node has no email service. Should the node send
  reset emails (a new external service), or do resets go through people and channels it has?
- Assumed answer: no email in Phase 1. An admin or owner resets a user and hands over a one-time
  enrolment link (on screen or to the person's linked WhatsApp); a locked-out owner uses
  `mia auth reset` on the node host; MFA users also get ten recovery codes.
- Blocking: no
- Answered: D17.

## Q12: on_behalf_of from outside agents over A2A
- Where: design section 6; ADR 008 (Mia actor extension)
- Question: an outside agent may claim it acts for a person. Is that claim used for RBAC?
- Assumed answer: no. Outside clients act only as themselves with their registered roles; the
  claim is written to the event as claimed_on_behalf_of. Agents on the same node pass the real
  actor in process. Trusted delegation (for example node to node in one organisation) is a
  later decision.
- Blocking: no (changes a security rule only if the answer is yes)
- Answered: D17.

## Q13: One PIN as the step-up for risky approvals
- Where: design section 8; spec, Approvals and Voice rules; plan, Sprint 2
- Question: should office users with TOTP or a passkey use that factor for the step-up instead
  of a PIN?
- Assumed answer: one 6-digit PIN for everyone, re-entered within 5 minutes before deciding a
  money, external or delete approval, on an aal2 session. The same PIN serves voice later.
- Blocking: no
- Answered: D17.

## Q14: Staff login codes through WhatsApp, no SMS provider yet
- Where: design sections 4.4 and 13; spec, Authentication (phone number with one-time code)
- Question: the spec says a one-time code to the phone; it does not say SMS. Can the code go
  through the WhatsApp channel (a Meta authentication template) to the person's linked number?
- Assumed answer: yes. No SMS provider until a pilot user has no WhatsApp; then an SMS channel
  adapter (46elks first for Finland), which is a new external service needing approval.
- Blocking: no
- Answered: D17.

## Q15: Dependencies for authentication
- Where: design section 13
- Question: stdlib scrypt or argon2-cffi for passwords; passkeys now or later?
- Assumed answer: stdlib only for the first build (scrypt, secrets, hmac for TOTP and HKDF, no
  JWT). Passkeys come as a later step with `webauthn` (py_webauthn, BSD-3), after approval.
- Blocking: no for the first build; yes for passkeys
- Answered: D17.

## Q16: Supervisor MFA and session lifetimes
- Where: design sections 4.1 and 5; spec, Authentication (MFA for owner, admin, accountant)
- Question: should supervisors need MFA too, and are the session lifetimes right?
- Assumed answer: MFA offered but not required for supervisors, as the spec says. Access tokens
  15 minutes; office refresh 12 hours idle and 7 days absolute; staff on a bound device 30 days
  idle and 90 days absolute.
- Answered: D17.

## Q17: AG-UI thread ids
- Where: spec, Chat ("the AG-UI stream reconnects and resumes"); rule 10 (IDs are ULIDs)
- Question: AG-UI clients name the thread (`threadId`), and stock clients such as CopilotKit use
  UUIDs. Should Mia accept any client-chosen id?
- Assumed answer: no. A new thread's `threadId` must be a ULID (422 otherwise) and becomes the
  chat_threads id; an existing thread must belong to the acting person (404 otherwise). Mia's own
  apps generate ULIDs. Mapping outside ids would need a column on chat_threads (data standard).
- Answered: D15 (thread ids stay ULIDs).
- Blocking: no

## Q18: Roles for quality, master data and reporting in the capability catalogue
- Where: docs/plan.md roster ("Agents, processes and capabilities beyond Phase 1"); docs/capabilities.md
- Question: the roster has no role for site quality, safety and compliance work, or for master
  data, user administration and management reports. Which agent owns them?
- Assumed answer: two proposed roles, `quality` (quality, safety and compliance coordinator) and
  `office` (office manager: master data, administration, management reporting), plus `chat`
  for platform-wide intents (greeting, help, talk to a person) that belong to no hired role.
  The QA platform agent keeps watching processes; it does not take site inspections.
- Answered: D30 (`quality` is renamed `site_manager` and `office` is renamed `admin`; no chat
  role, generic conversation is the shared conversation catalogue).
- Blocking: no

## Q19: Scope of the scheduling build (plan item 4)
- Where: docs/plan.md Sprint 2; D25 (apps are a separate project)
- Question: Sprint 2 lists a drag-and-drop schedule board and a supervisor dashboard. Are they
  part of the node build or of the separate apps project?
- Assumed answer: the node exposes the schedule, assignment, check-in and inbox API and a
  read-only week table on the dev page; the board and dashboard belong to the apps project.
- Blocking: no

## Q20: Timesheets in the data standard
- Where: docs/plan.md Sprint 2 (time and attendance chain)
- Question: timesheets are a new core entity: `timesheet` (id, branch_id, person_id, visit_id,
  start, end, minutes, source: check_in | correction, status: draft | approved, entered_by,
  approved_by) with separation of duties (the approver is never the person who entered it).
  Is that the shape, and is it core or the cleaning template? Note: until timesheets exist,
  check-in and check-out are per visit, so a two-person visit records one pair of times.
- Assumed answer (updated 2026-10-12): built as an agent-owned table `dispatcher_timesheets`
  with the shape above (rule 9), so the data standard is untouched; when the answer is "core",
  the table moves with a migration and the service stays. The enterer of a check-out row is
  the cleaner; a correction makes the corrector the enterer.
- Blocking: no (the placement is open, the behaviour is built)
- Answered 18 Oct 2026 (ADR 014): timesheets are a core table (data standard 1.4).

## Q21: A job's default assignee
- Where: spec.md data standard (job has no assignee field); the seed assigns by name
- Question: should `job` get `default_person_ids` so generated visits come assigned?
- Assumed answer: no new field. Generation copies the assignment of the job's most recent
  visit on the same weekday when that person is still eligible, else the visit is unfilled.
- Blocking: no

## Q22: Approval for a rule-breaking assignment by the office
- Where: spec.md Approvals; D1 (an instruction is the approval) covers the dispatcher's cover
- Question: when the office assigns someone outside their availability or hour limits, is that
  an approval (like the dispatcher's cover override) or the office's own call?
- Assumed answer: an approval `schedule.assignment_override`, approver roles admin and owner,
  app only, same as the cover override; the supervisor's instruction alone is not enough.
- Blocking: no

## Q23: A second location share during a visit
- Where: D20 (check-in and check-out by location share); spec 2026-10-12-location-check-in
- Question: when a cleaner shares their location while their visit is in progress, is that the
  check-out, or should the node ask first (a share by mistake would end the visit)?
- Assumed answer: it is the check-out, as D20 names both by location share; a wrong one is
  corrected by the office (`POST /visits/{id}/check-in` again is not possible, so a timesheet
  correction once Q20 lands). The site's geofence radius comes from `location.geofence`
  (`radius_m`, 100 m when unset); the shared coordinates are never stored, only the distance.
  A shared point is the cleaner's claim (WhatsApp lets anyone send a chosen place), so a chosen
  place is flagged like a point outside the fence and a point inside it proves nothing.
- Blocking: no

## Q24: The payroll export format
- Where: docs/plan.md Sprint 5 (payroll export in the format of Hype's payroll system)
- Question: which payroll or accounting system does Hype use, and what file does it import?
- Assumed answer: a generic CSV of approved timesheets (person, date, site, start, end,
  minutes) from `mia payroll export`; the system-specific layout is a second writer once the
  system is named. Mia never runs payroll (plan Sprint 5).
- Blocking: no

## Q25: The parallel intent suite by language
- Where: docs/plan.md item 2 (a parallel intent by language suite); D26 (the core is measured in
  English, translation on its own)
- Question: the English intent suite has 3664 utterances. A Finnish and Filipino parallel suite
  is generated with the cloud teacher from synthetic data (D18 allows it), which costs model
  calls; and its purpose, measuring the translation layer and Gemma on the node, needs the Mac
  mini (D19). Generate it now with the teacher, or once the node hardware is in place?
- Assumed answer: once the hardware is in place, so the suite and the measurement land together
  and the spend is approved with the pilot. The chat scenarios already exist in both languages
  (tests/scenarios.yaml, scenarios_en.yaml) and run on every model route.
- Blocking: no

## Q26: The dispatcher skill model's gates and teachers
- Where: .claude/skills/mia-train-role (Gate 1 before training, Gate 2 before promotion); spec
  2026-10-06-skill-models-design.md (test set from a third model family); D18, D27
- Question: the training skill makes Gate 1 and Gate 2 human decisions. The data package exists
  (two local teachers for train, every record reviewed, 12 Oct 2026) but the Mac has no third
  model family that answers structured chat, and the local Qwen 3.5 writes Finnish a reviewer
  drops two times out of three. May the session train on the package as it is, and may the
  Finnish cells and the test set be regenerated by a cloud teacher (synthetic data only)?
- Assumed answer: no training before the developer's Gate 1, as the skill says; the package is
  presented with the test set marked provisional (same family as a train teacher, so it can
  read the first report and tune nothing). The cloud teacher for the Finnish cells and the test
  set is a spend decision taken at Gate 1; D18 allows it (no real data), the egress layer
  already carries gateway routes.
- Blocking: yes for training and promotion; no for the package itself.
- Addendum (same day): the train step takes the conversation and `other` rows from the intent
  evaluation set (tests/evals/intents.jsonl; the dispatcher's own rows stay out, it is the
  benchmark), so the shared labels no longer train on nothing. Assumed acceptable: the set is
  the project's own labelled data, synthetic, already in git.

## Q27: TypeSafe as a processor of real data
- Where: spec 2026-10-17-jev-decider-design.md (Scope and data); docs/research/jev-2026-10-18.md; D18
- Question: Jev mode is measured on synthetic data only. TypeSafe's docs say nothing about
  retention, region or processing terms. May Jev ever see real Hype messages?
- Assumed answer: no, until the terms are read and an ADR amends D18; real traffic stays on
  MIA_DECIDER=agent.
- Blocking: yes for real data; no for the measurement.

## Q28: Review of the Filipino strings
- Where: node/mia/i18n/fil.py; spec 2026-10-18-multi-agent-routing-design.md
- Question: Who reviews the Filipino strings in mia/i18n/fil.py?
- Assumed answer: they ship as machine drafts and a native speaker reviews them before a client uses that language.
- Blocking: no for the package; yes before a client uses Filipino.
- The sales supervisor's Filipino keys (`sales.*`, `intent.sales_supervisor.*`, `conversation.greeting`, `conversation.thanks`, `conversation.goodbye`, `clarify.*`, `denied.generic`) are drafts under the same note.
- The inventory manager's Filipino keys (`stock.*`, `intent.inventory_manager.*`) are drafts under the same note.
- The HR officer's Filipino keys (`hr.*`, `intent.hr_officer.*`) are drafts under the same note.

## Q29: Review of the Cebuano strings
- Where: node/mia/i18n/ceb.py; spec 2026-10-18-multi-agent-routing-design.md
- Question: Who reviews the Cebuano strings in mia/i18n/ceb.py?
- Assumed answer: they ship as machine drafts and a native speaker reviews them before a client uses that language.
- Blocking: no for the package; yes before a client uses Cebuano.
- The sales supervisor's Cebuano keys (`sales.*`, `intent.sales_supervisor.*`, `conversation.greeting`, `conversation.thanks`, `conversation.goodbye`, `clarify.*`, `denied.generic`) are drafts under the same note.
- The inventory manager's Cebuano keys (`stock.*`, `intent.inventory_manager.*`) are drafts under the same note.
- The HR officer's Cebuano keys (`hr.*`, `intent.hr_officer.*`) are drafts under the same note.

## Q30: Review of the Ilocano strings
- Where: node/mia/i18n/ilo.py; spec 2026-10-18-multi-agent-routing-design.md
- Question: Who reviews the Ilocano strings in mia/i18n/ilo.py?
- Assumed answer: they ship as machine drafts and a native speaker reviews them before a client uses that language.
- Blocking: no for the package; yes before a client uses Ilocano.
- The sales supervisor's Ilocano keys (`sales.*`, `intent.sales_supervisor.*`, `conversation.greeting`, `conversation.thanks`, `conversation.goodbye`, `clarify.*`, `denied.generic`) are drafts under the same note.
- The inventory manager's Ilocano keys (`stock.*`, `intent.inventory_manager.*`) are drafts under the same note.
- The HR officer's Ilocano keys (`hr.*`, `intent.hr_officer.*`) are drafts under the same note.

## Q31: Review of the Hiligaynon strings
- Where: node/mia/i18n/hil.py; spec 2026-10-18-multi-agent-routing-design.md
- Question: Who reviews the Hiligaynon strings in mia/i18n/hil.py?
- Assumed answer: they ship as machine drafts and a native speaker reviews them before a client uses that language.
- Blocking: no for the package; yes before a client uses Hiligaynon.
- The sales supervisor's Hiligaynon keys (`sales.*`, `intent.sales_supervisor.*`, `conversation.greeting`, `conversation.thanks`, `conversation.goodbye`, `clarify.*`, `denied.generic`) are drafts under the same note.
- The inventory manager's Hiligaynon keys (`stock.*`, `intent.inventory_manager.*`) are drafts under the same note.
- The HR officer's Hiligaynon keys (`hr.*`, `intent.hr_officer.*`) are drafts under the same note.

## Q32: Review of the Waray strings
- Where: node/mia/i18n/war.py; spec 2026-10-18-multi-agent-routing-design.md
- Question: Who reviews the Waray strings in mia/i18n/war.py?
- Assumed answer: they ship as machine drafts and a native speaker reviews them before a client uses that language.
- Blocking: no for the package; yes before a client uses Waray.
- The sales supervisor's Waray keys (`sales.*`, `intent.sales_supervisor.*`, `conversation.greeting`, `conversation.thanks`, `conversation.goodbye`, `clarify.*`, `denied.generic`) are drafts under the same note.
- The inventory manager's Waray keys (`stock.*`, `intent.inventory_manager.*`) are drafts under the same note.
- The HR officer's Waray keys (`hr.*`, `intent.hr_officer.*`) are drafts under the same note.

## Q33: Review of the Bikol strings
- Where: node/mia/i18n/bcl.py; spec 2026-10-18-multi-agent-routing-design.md
- Question: Who reviews the Bikol strings in mia/i18n/bcl.py?
- Assumed answer: they ship as machine drafts and a native speaker reviews them before a client uses that language.
- Blocking: no for the package; yes before a client uses Bikol.
- The sales supervisor's Bikol keys (`sales.*`, `intent.sales_supervisor.*`, `conversation.greeting`, `conversation.thanks`, `conversation.goodbye`, `clarify.*`, `denied.generic`) are drafts under the same note.
- The inventory manager's Bikol keys (`stock.*`, `intent.inventory_manager.*`) are drafts under the same note.
- The HR officer's Bikol keys (`hr.*`, `intent.hr_officer.*`) are drafts under the same note.

## Q34: Review of the Kapampangan strings
- Where: node/mia/i18n/pam.py; spec 2026-10-18-multi-agent-routing-design.md
- Question: Who reviews the Kapampangan strings in mia/i18n/pam.py?
- Assumed answer: they ship as machine drafts and a native speaker reviews them before a client uses that language.
- Blocking: no for the package; yes before a client uses Kapampangan.
- The sales supervisor's Kapampangan keys (`sales.*`, `intent.sales_supervisor.*`, `conversation.greeting`, `conversation.thanks`, `conversation.goodbye`, `clarify.*`, `denied.generic`) are drafts under the same note.
- The inventory manager's Kapampangan keys (`stock.*`, `intent.inventory_manager.*`) are drafts under the same note.
- The HR officer's Kapampangan keys (`hr.*`, `intent.hr_officer.*`) are drafts under the same note.

## Q35: Review of the Pangasinan strings
- Where: node/mia/i18n/pag.py; spec 2026-10-18-multi-agent-routing-design.md
- Question: Who reviews the Pangasinan strings in mia/i18n/pag.py?
- Assumed answer: they ship as machine drafts and a native speaker reviews them before a client uses that language.
- Blocking: no for the package; yes before a client uses Pangasinan.
- The sales supervisor's Pangasinan keys (`sales.*`, `intent.sales_supervisor.*`, `conversation.greeting`, `conversation.thanks`, `conversation.goodbye`, `clarify.*`, `denied.generic`) are drafts under the same note.
- The inventory manager's Pangasinan keys (`stock.*`, `intent.inventory_manager.*`) are drafts under the same note.
- The HR officer's Pangasinan keys (`hr.*`, `intent.hr_officer.*`) are drafts under the same note.

## Q36: Accountants and viewers have no agent
- Where: node/config/policies/policy.csv (no `agent:*` line for `accountant` or `viewer`); node/mia/chat/access.py
- Question: Should accountants and viewers reach an agent? Before multi-agent routing they could talk to the shift supervisor; now they get `reply.no_agent`.
- Assumed answer: intended until their agents exist (bookkeeper for accountants, branch_manager for viewers); their `agent:*` lines are added with those agents.
- Blocking: no.

## Q37: Learned keys are per branch or per person
- Where: docs/superpowers/specs/2026-10-18-router-follow-up-design.md (decision 4); mia/chat/route_memory.py
- Question: Should a learned key be per person or per branch?
- Assumed answer: per branch: clerks share the shop's words and one clerk's confirmation helps the next.
- Blocking: no.

## Q38: Tell the owner when Mia learns a key
- Where: docs/superpowers/specs/2026-10-18-router-follow-up-design.md (decision 5); `mia learned`
- Question: Should the owner be told when Mia learns a key?
- Assumed answer: no; `mia learned` is enough until the owner page exists.
- Blocking: no.

## Q39: Sales tables are agent-owned until a second agent reads them
- Where: docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (section 4); mia/agents/sales_supervisor/models.py
- Question: Should sales counts, targets and notes be core tables now (data standard 1.5), since the branch_manager, inventory_manager and bookkeeper will read them, or agent-owned until one of them exists?
- Assumed answer: agent-owned (`sales_supervisor_*`) now, because rule 9 makes a table shared only once a second agent reads it and changing the data standard needs the owner's explicit yes; promoted to core with an ADR when the branch_manager is built, by an in-place edit of `0000_initial` before the first candidate release (rule 14). Column names are chosen so the move is a table rename.
- Blocking: no now; yes before part 3 starts.
- Answered 19 Oct 2026 (D36, ADR 017): core tables `sales_counts`, `sales_targets`, `sales_notes` (data standard 1.5).

## Q40: Router gate decisions after the 19 Oct run
- Where: docs/superpowers/specs/2026-10-18-router-follow-up-design.md (carried-over section); docs/research/router-2026-10-19.md
- Question: Who owns "add a person to a branch" (branch manager or HR)? When Jev's top pick differs from the active agent below the threshold, keep the active agent or ask with buttons? Is 90% right per language the bar, given asks are safe?
- Assumed answer: the branch manager owns adding people, HR owns pay, leave, contributions and hiring campaigns; ask instead of keep on a low-confidence switch (no silent misroute, every tap teaches the memory); the gate is wrong at most 2% (hard), right at least 80% per language, ask at most 15%, measured on a fresh gate half.
- Blocking: no; the gate stays a merge condition.

## Q41: A count stores the selling price at the time
- Where: docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (section 10); mia/agents/sales_supervisor/models.py
- Question: Do counts need the selling price at the time, or is quantity enough and the amount derived at read time from the price history?
- Assumed answer: store both at write time; a price change never rewrites history.
- Blocking: no.

## Q42: Who may set a branch target
- Where: docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (section 10); mia/agents/sales_supervisor/tools.py (set_target)
- Question: Who may set a branch target: the supervisor of that branch, or only the owner?
- Assumed answer: both; the owner's target wins when both exist for a day.
- Blocking: no.

## Q43: The owner does not get the why question
- Where: docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (section 10); mia/agents/sales_supervisor/due.py
- Question: The why question goes to everyone who reported that day; should the owner get it too?
- Assumed answer: no, owners read the notes.
- Blocking: no.

## Q44: A stated day total is not stored
- Where: docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (section 3, scenario 1); mia/agents/sales_supervisor/tools.py (record_counts)
- Question: Scenario 1 says the amount is quantity times price "unless the clerk states a total". Should a stated total be stored (on the counts or as its own event) and shown instead of the computed sum?
- Assumed answer: not in v1. Rows keep quantity times price and the reply shows the branch's running total; the stated total is parsed but dropped. Revisit when the bookkeeper reconciles cash.
- Blocking: no.

## Q45: "Box of 4" carries a number in its name
- Where: mia/templates/retail/seed.py (ITEMS); mia/agents/sales_supervisor/actions.py (pre_parse)
- Question: "2 box of 4 3 sp" pre-parses into three groups, one a "4" with no words. Rename the item ("Box (4 pcs)") or let pre_parse protect menu phrases?
- Assumed answer: rename the demo item when the seed is next touched; protect menu phrases only if a real menu needs numbers in names.
- Blocking: no.

## Q46: Units glued to a number and money with centavos
- Where: mia/agents/sales_supervisor/actions.py (pre_parse)
- Question: "3pcs", "x3", "3x" and "1,450.50" become words and lose the number. Split the known suffixes and accept a decimal total?
- Assumed answer: yes, in the next pre_parse change, with the seed phrasings measured again.
- Blocking: no.

## Q47: "Cancel the last one" and head staff correcting a clerk
- Where: docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (scenario 2, tool table); mia/agents/sales_supervisor/tools.py (correct_count)
- Question: Scenario 2 names "Cancel the last one", and the tool table lets supervisors, owners and admins correct counts. Neither exists: correct_count only replaces the reporter's own latest count.
- Assumed answer: a follow-up adds a cancel action (supersede the reporter's last count) and a correction on behalf of a named clerk for head staff.
- Blocking: no.

## Q48: One end-of-day report per branch, not per owner
- Where: docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (scenario 5); mia/agents/sales_supervisor/due.py (_report)
- Question: Scenario 5 says one notification per owner and admin; the due work sends one per branch, an hour after each branch closes.
- Assumed answer: one per branch while the branches close at different times (19:00 and 21:00 at Ferino's); combine the reports when both windows are open at once.
- Blocking: no.

## Q49: Period replies show ISO dates and no line per branch for "all"
- Where: mia/agents/sales_supervisor/replies.py (tool_reply, period_report)
- Question: Period replies read "2026-10-01 to 2026-10-31; best day 2026-10-15", and "all" without an item gives one grand total, though the rows per branch are there.
- Assumed answer: word the dates in the person's language and add one line per branch in the next replies change.
- Blocking: no.

## Q50: Nothing in a count message is recorded until every group has an item
- Where: docs/superpowers/specs/2026-10-19-sales-supervisor-design.md (section 3, scenario 1); mia/agents/sales_supervisor/turn.py (_act)
- Question: The spec says the other groups are recorded while one group's item is asked. The turn records nothing until every group has an item, so a clerk who ignores the which-item question loses the whole message.
- Assumed answer: keep the whole-message hold in v1 (one reply, no half-recorded message); the closing reminder catches clerks with no count at all.
- Blocking: no.

## Q51: Should the scaffold write the eight-language label drafts?
- Where: docs/superpowers/specs/2026-10-19-mia-build-agent-design.md (section 8); mia/agents/scaffold.py
- Question: should the scaffold also write the eight-language label drafts, or leave them to the i18n task?
- Assumed answer: write the English label into the eight modules with the review note, so the coverage test is green from the first commit.
- Blocking: no.

## Q52: Does /mia-build-agent run the real-Jev gates itself?
- Where: .claude/skills/mia-build-agent/SKILL.md (step 7)
- Question: does `/mia-build-agent` run the real-Jev gates itself, or hand the command to the developer?
- Assumed answer: it runs them when `MIA_TYPESAFE_KEY` is set and reports; the developer decides on tuning.
- Blocking: no.

## Q53: Inventory tables move to core with the sales tables
- Where: docs/superpowers/specs/2026-10-19-inventory-manager-design.md (section 2); mia/agents/inventory_manager/models.py
- Question: `inventory_manager_stock_events` and `inventory_manager_orders` are agent-owned today; the bookkeeper (expenses from orders) and the branch manager (stock in the weekly summary) will read them. Promote them with the sales tables as data standard 1.5?
- Assumed answer: yes, in the same promotion (Q39), by an in-place edit of `0000_initial` before the first candidate and one ADR.
- Blocking: no now; yes before the bookkeeper or the branch manager is built.
- Answered 19 Oct 2026 (D36, ADR 017): `inventory_manager_stock_events` became the core table `stock_events` (data standard 1.5); `inventory_manager_orders` stays agent-owned (one reader so far).

## Q54: The bake plan without the sales counts
- Where: docs/superpowers/specs/2026-10-19-inventory-manager-design.md (section 7); mia/agents/inventory_manager/calc.py
- Question: until the sales counts are readable (1.5), the bake plan is a heuristic on this agent's sell-outs and leftovers over the last four same weekdays. Acceptable for v1?
- Assumed answer: yes; the message says it is a suggestion.
- Blocking: no.

## Q55: An order without prices
- Where: docs/superpowers/specs/2026-10-19-inventory-manager-design.md (section 6); the approval card
- Question: pack prices are optional seed data; without one the approval card shows the lines and no total.
- Assumed answer: acceptable; the owner approves the lines.
- Blocking: no.

## Q56: A delivery is matched to an order by ingredient only
- Where: mia/agents/inventory_manager/tools.py (receive_delivery)
- Question: a delivery closes the branch's oldest approved order line of the ingredient, whatever the supplier; two open egg orders from two suppliers can be closed out of order.
- Assumed answer: acceptable for v1 (one supplier per ingredient at Ferino's); match by supplier when the delivery names one, later.
- Blocking: no.

## Q57: Cash advances are a money tool
- Where: docs/superpowers/specs/2026-10-19-hr-officer-design.md (section 1); CLAUDE.md "Ask before: adding a risky tool"
- Question: Staff cash advances (deducted from the next payslip) need a money-risk tool. May the HR officer have one? The inventory manager's `draft_order` is a money tool added without asking (it executes only on the owner's approval tap); should it stay?
- Assumed answer: cash advances stay out of v1 until the owner answers; `draft_order` stays, behind the owner's approval, unless the owner says otherwise.
- Blocking: for cash advances, yes.

## Q58: Withholding tax
- Where: docs/superpowers/specs/2026-10-19-hr-officer-design.md (section 1); mia/agents/hr_officer/ph.py
- Question: Payslips in v1 deduct SSS, PhilHealth and Pag-IBIG only. Withholding tax needs the BIR table and each person's status; the accountant's call.
- Assumed answer: out of v1; the payslip says "before tax".
- Blocking: no.

## Q59: HR tables move to core with the sales and inventory tables
- Where: docs/superpowers/specs/2026-10-19-hr-officer-design.md (section 2)
- Question: `hr_officer_contracts`, `hr_officer_payslips`, `hr_officer_leave` are agent-owned; the bookkeeper (payroll cost) and the shift supervisor (leave in rosters) will read them.
- Assumed answer: promoted with Q39 and Q53 as data standard 1.5.
- Blocking: no now; yes before the bookkeeper reads payroll or rosters read leave.
- Answered in part 19 Oct 2026 (D36, ADR 017): the HR tables were not part of data standard 1.5 and stay agent-owned; their promotion still waits for the owner, before the bookkeeper reads payroll or rosters read leave.

## Q60: The cutoff and payday rule
- Where: node/mia/agents/hr_officer/calendar.py; config/org/ferinos/settings.yaml `payroll`
- Question: Ferino's pays how and when?
- Assumed answer: semi-monthly cutoffs (1st to 15th, 16th to month end), paid five days after the cutoff, moved to the previous working day when payday falls on a Sunday or a holiday.
- Blocking: no.

## Q61: SSS, PhilHealth and Pag-IBIG tables
- Where: node/mia/agents/hr_officer/ph.py (`TABLES_AS_OF`)
- Question: The employee contribution tables are dated constants written from memory of the 2026 schedules.
- Assumed answer: verify every bracket with the accountant before a real payslip is issued; the mechanism is tested, the figures are not authoritative.
- Blocking: yes before real payslips.

## Q62: The 2026 holiday list
- Where: config/org/ferinos/holidays.yaml
- Question: Regular holidays and special non-working days for 2026 as published by proclamation.
- Assumed answer: the list is a draft to verify; the owner can edit the file.
- Blocking: no.

## Q63: The service incentive leave balance
- Where: node/mia/agents/hr_officer/calendar.py (`sil_balance`)
- Question: How do the five service incentive leave days a year build up?
- Assumed answer: 0 before one year of service; five days credited in full at each service anniversary, less the days used in the current service year, never negative. The owner may prefer monthly accrual.
- Blocking: no.

## Q64: The user's own pay and leave words in the event log
- Where: node/mia/chat/service.py (the user message row and its chat_messages.created event); node/mia/chat/replies.py (`_store`)
- Question: Should a user message that carries pay or leave words ("sick today", "my SSS is 400") be redacted from the hash chain, like the agent's sensitive answers now are?
- Assumed answer: no. The user's own words stay in their event; Mia's answers of a sensitive tool (pay, hours, leave) and buttons that carry a leave kind are redacted (text and blocks kept in the row only).
- Blocking: no.

## Q65: Contributions on a short cutoff
- Where: node/mia/agents/hr_officer/ph.py (`payslip`)
- Question: The contributions read the monthly basic as the daily rate times 26, whatever was worked, so a cutoff with one approved day would net below zero. Should they read the month's actual earnings instead?
- Assumed answer: for v1 the deductions are taken in order (SSS, PhilHealth, Pag-IBIG) while the gross lasts, so the net is never below zero. Contributions on the month's actual earnings is the fuller rule, to settle with the accountant (Q61).
- Blocking: no.

## Q66: The approver's free-text reason in approval.decided
- Where: node/mia/core/approvals.py (`decide`), node/mia/core/models.py (`Approval.__redact__`)
- Question: The hr officer's hr.leave_rejected event no longer logs the approver's reason, but the core approval.decided event still snapshots `Approval.reason`. Should approval.decided redact that free-text reason?
- Assumed answer: no for v1; the reason stays in the core event.
- Blocking: no.

## Q67: customer_service, a public sender
- Where: node/mia/channels/inbound.py (only linked people get a chat turn), node/mia/core/rbac.py, docs/agents-catalogue.md (customer_service)
- Question: The customer_service agent serves the public on Messenger, Viber and WhatsApp, so a sender who is not a linked Person must get a turn. Who is a customer in the data standard, what may that turn do, and which channel numbers are public?
- Assumed answer: a customer is not a Person: an agent-owned table customer_service_customers keyed by the channel address (platform and id) with the name the customer gives, language and the branch of the public number; the agent runs as its own actor on behalf of the address and may call only customer_service.* tools with risk none, except place_order (money), which drafts an order and asks the branch's clerk or supervisor to confirm through approvals; orders live in customer_service_orders until the production_planner or the sales_supervisor reads them (then promotion with an ADR, the Q39 precedent); every customer message is data (rule 8), no staff tool ever runs for a customer, no linking to a Person from the customer flow; the auth.py address limits apply; the customer reads only the menu, prices, hours, delivery areas and their own order status; one public number per branch; deposits for large orders are out of v1 (staff ask by hand).
- Blocking: yes, before any customer_service code: a public sender is a new security boundary and a new place for customer data.

## Q68: Customer messages outside WhatsApp's 24-hour window
- Where: node/mia/agents/customer_service/public.py (`window_open`, `send_pending`)
- Question: WhatsApp lets a business message a customer freely only within 24 hours of the customer's last message; after that it needs a registered template. Should Mia register templates for the pickup reminder and the order-ready message?
- Assumed answer: not in v1. A message outside the window is skipped and logged (`customer_service.reminder_skipped`); templates are their own work.
- Blocking: no.

## Q69: Customer data retention
- Where: node/mia/agents/customer_service/models.py (the four customer_service_* tables)
- Question: How long are a customer's rows (the address, name, messages, orders and complaints) kept?
- Assumed answer: 12 months after the customer's last message; then a `mia customers prune` command deletes the customer, message and complaint rows, and the customer's `channel_inbound` rows (their body holds the text, the profile name, the address and any shared point). The events stay, redacted (the identity never reaches the chain).
- Blocking: no.

## Q70: Customer channels in v1
- Where: node/mia/channels/ (whatsapp/, simulator.py), docs/agents-catalogue.md (customer_service)
- Question: The catalogue names Messenger, Viber and WhatsApp. Which channels does customer_service serve first?
- Assumed answer: WhatsApp and the simulator in v1; the Messenger and Viber adapters are their own work.
- Blocking: no.

## Q71: Customer text sent to the decider
- Where: node/mia/agents/customer_service/actions.py (`build_request`), node/mia/core/egress.py
- Question: May a customer's message text go to Jev (TypeSafe) to pick the action?
- Assumed answer: yes, pseudonymised like staff text, as data in the request's state only; the customer's address and stored name never leave the node.
- Blocking: no.

## Q72: What staff see of a customer
- Where: node/mia/agents/customer_service/tools.py (the order card, the staff order list), calc.py (`last_four`)
- Question: How much of a customer's identity do clerks and supervisors see on an order card and in the day's list?
- Assumed answer: the first name the customer gave and the last four digits of the number, nothing more.
- Blocking: no.

## Q76: Which branch a node's public number serves
- Where: node/mia/agents/customer_service/public.py (the customer row's branch)
- Question: A customer writing to the node's number is a customer of which branch, when the organisation has several?
- Assumed answer: the organisation's first branch (by id). One public number per branch (D35) needs a per-branch number setting in the channel configuration; until then the first branch serves them all.
- Blocking: no.

## Q78: Customer names a staff member types in their own chat
- Where: node/mia/chat/service.py (the user message row, its chat_messages.created event and chat_threads.created), node/mia/agents/customer_service/actions.py (`build_query`), manifest.yaml (`mark_picked_up`)
- Question: A clerk writes "ready na yung kay Mila": the customer's first name is in the staff member's own message row and its event. Should it be redacted from the hash chain, as a customer's own identity is?
- Assumed answer: no, as Q64 says for a user's own words: what the staff member typed stays in their event. The name never leaves the node (build_query scrubs the branch customers' first names before Jev), and Mia's replies that name a customer (orders_today, mark_ready, mark_picked_up) are sensitive, so their text and blocks stay in the row only.
- Blocking: no.

## Q73: Price history and bundles in the retail template
- Where: node/mia/templates/retail/models.py, node/migrations/versions/0000_initial.py, node/mia/agents/sales_supervisor/tools.py (counts priced on their business date)
- Question: Experiments and dated price changes need a price history; may the template gain `retail_item_prices` (per branch) and `retail_items.components`?
- Answer (20 Oct 2026, D37): yes, dated prices per branch; `retail_items.price` stays the default; counts keep the price of their day.
- Blocking: no (answered).

## Q74: Who may propose an experiment
- Where: node/mia/agents/branch_manager (propose_experiment)
- Question: May a supervisor propose a price or promo experiment, and how often may the agent propose one itself?
- Assumed answer: a supervisor proposes and the owner decides; the agent proposes at most one a month per branch, always from the strategy catalogue (D37).
- Blocking: no.

## Q75: Sources of the quotes and tips
- Where: node/mia/agents/branch_manager/tips.py (seed data)
- Question: Where do the motivational quotes and sales tips come from?
- Assumed answer: public-domain quotes and the owner's own lines, each row with its source; no scraping, no model-invented quote.
- Blocking: no.

## Q77: The owner's own price change
- Where: node/mia/core/approvals.py (decide)
- Question: The approvals core never lets a requester decide their own request. When the owner types a price change, who approves it?
- Answer (20 Oct 2026, D37): the owner's own typed request is the decision: the approval row exists, the owner decides it themselves with the PIN step-up, only for the owner role in their own branch; everyone else waits for another approver.
- Blocking: no (answered).

## Q80: The business date under hours that close after midnight
- Where: node/mia/templates/retail/hours.py (`business_date`, `business_date_at`); node/mia/agents/sales_supervisor/tools.py:254 and node/mia/agents/inventory_manager/tools.py:90 call it; node/mia/agents/customer_service/calc.py (`hours_span`) already handles it on its own
- Question: Under 16:00 to 02:00 hours, a report at 01:00 should belong to the day before, but `business_date` returns today: it compares against yesterday's closing time on yesterday's date plus two hours (02:00 yesterday plus two hours is long past). Should the shared function take the closing on the next day when the closing is at or before the opening?
- Assumed answer: yes, fix the shared function the way calc.hours_span does (a closing at or before the opening is the next calendar day's), in a follow-up with the three agents' tests; the customer service keeps its own until then.
- Blocking: no.

## Q82: A late-day markdown under prices dated per day
- Where: node/mia/agents/branch_manager/experiments.py (`_markdown`), node/mia/templates/retail/items.py (`retail_item_prices.effective_on` is a date)
- Question: The markdown strategy (spec section 13, 5) is a late-day cut on an item that is often left over, but a branch's price changes by the day, not by the hour. Should the template gain a time-of-day price?
- Assumed answer: not in v1; the markdown is proposed as an all-day price for the 14 days and the owner's card says "all day" until a time-of-day price exists.
- Blocking: no.
