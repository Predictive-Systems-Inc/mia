# Mia Phase 1 Build Plan

Sep 30, 2026 · @Allan Tan

## Goal and scope

Build the Mia platform structure and one fully configured agent, the dispatcher, and put it into daily use at Hype Siivous within 3 months. The plan lists all the work that is needed; hour estimates are not a constraint (D24).

**In scope (Phase 1)**

- Mia Node: FastAPI, SQLite, Alembic, Huey, Docker Compose install, Litestream backup
- Data standard v1.0 and the cleaning template: sites, jobs, visits, checklists, check-in and check-out, photos
- Authentication, RBAC (pycasbin), approvals service and inbox, append-only events log with hash chain
- Office web app (React, Vite, static files served by the node): clients, sites, staff, schedule board, supervisor view, approvals, exports
- Cleaners work over WhatsApp; the apps are a separate project (D20, D25): today's visits, site instructions, check-in and check-out by location share, checklists with interactive lists and buttons, photos as media, chat, absences and cover
- Chat: AG-UI endpoint, message model with text, quick replies, card, approval card, form and file blocks; web chat UI for the office
- Cloud egress policy (`none`, `pseudonymised`) and the gateway client; usage table
- Dispatcher agent v1 (Pydantic AI): absence reports, replacement suggestions, schedule questions, site instructions, alerts
- Billing summary export (CSV) in code
- Finnish and English UI

**Out of scope (deferred):** Mia Cloud UI and bundle sync (not built until decided otherwise, D13), catalogue and hiring, grading, subagents and variants, QA agent and audit reports, voice, QuickBooks and other connectors, custom fields UI, chart and table blocks, payroll and social media agents.

**Added to scope (D13):** outside channels, WhatsApp first; see docs/superpowers/specs/2026-10-02-channel-adapters-whatsapp-design.md.

**Designed in Phase 1, built in Phase 2:** A2A between agents (D14, ADR 008; needs real authentication first, and Phase 1 has one agent on one node) and skill distillation for small local models (needs real traffic from the pilot to train on).

**References:** the [Mia Agent Manifest Specification v0.1](https://claude.ai/code/artifact/36ffddd5-462a-46cc-b582-5dbcbf46720b) (architecture, RBAC, approvals, chat, egress, tech stack) and the Hype Siivous proposal (scope and timeline commitments).

**Team:** one senior full-stack developer (Python and TypeScript), with Allan as product owner and reviewer. Hour estimates are not used as a limit; the plan includes all necessary work (D24).

## Status and revised order (Oct 5, 2026)

Built so far, ahead of the sprint order below: the initial build (docs/brief.md), core data and
events, RBAC and approvals records, chat with blocks and AG-UI, the dispatcher with instructed
cover and the confirmation flow (D1, D6 to D11), channel adapters with WhatsApp (D13), local
and cloud model routes with the evaluation suite. Not built: real authentication (the actor
still comes from the unverified X-Mia-Actor header), the office web app, Huey workers, Docker Compose and Litestream.

Remaining work in this order, because each step unblocks the next:

1. **Authentication and identity** (Sprint 1 item, moved first): office login, staff phone
   OTP, sessions, and channel identities linked to real accounts. Blocks the pilot with real
   people, WhatsApp in production and A2A.
2. **Local model to 95%** (D18, D19, D26): the full intent list in English, measured on
   Qwen3.5 9B and Gemma 4 12B; translation (Finnish, Filipino to and from English) as a
   separate layer measured on its own. Then: Gemma 4 12B on Ollama on an Apple Silicon Mac mini, no
   cloud route for real data. It passes 85% today (Oct 5 evaluation: Sonnet 5.5 100%, Haiku 4.5
   88%, Gemma 4 12B 85%, Qwen3.5 9B on llama.cpp 76%), so before the pilot: the turn cap (D22),
   the reply contract for small models (the model writes text, code builds the blocks), a
   parallel intent by language suite, and a distilled intent classifier where Gemma is weak.
   Cloud models are used only for development and as the distillation teacher, with synthetic
   or demo data.
3. **Install and backup** (Sprint 0 items still open): Docker Compose, Litestream, health page,
   install guide; needed before anything runs at Hype.
4. **Scheduling and approvals inbox** (Sprint 2), then the **office web app** screens it needs.
5. **Field work over WhatsApp** (Sprint 3, D20): check-in and check-out, checklists and photos
   over WhatsApp; no mobile app. Needs Hype's agreement, since the proposal promised an app.
6. **Alerts, billing export, rollout** (Sprint 5).

Sprint numbers keep their order and milestones; hour figures are removed (D24).

## Repository structure and conventions

One monorepo; the node is Python, the apps are TypeScript.

```
mia/
  node/
    mia/
      core/          data standard models, auth, rbac, approvals, events, egress, usage
      templates/cleaning/   sites, jobs, visits, checklists
      agents/dispatcher/    manifest.yaml, job.md, prompts/, tools/, tests/
      chat/          AG-UI endpoint, message model, blocks
      api/           FastAPI routers (OpenAPI is the contract for the apps)
      workers/       Huey tasks: visit generation, alerts, exports, backups
    migrations/      Alembic (core, cleaning, dispatcher folders)
    config/          standard/, roles/, policies/ (Casbin), agents/, org/ (Hype)
    tests/
  apps/
    web/             React + Vite, built to node/static
    shared/          generated API types, chat block components
  deploy/            docker-compose.yml, litestream.yml, install.md
  docs/              spec links, ADRs (architecture decision records)
```

**Conventions**

- Python 3.12, `uv` for dependencies, Ruff for lint and format, mypy strict on `core/`.
- Every table has `id` (ULID), `branch_id`, `created_at`, `updated_at`; money in integer minor units; times in ISO 8601 with time zone.
- All writes go through service functions that emit events; no direct table writes from API routes or tools.
- Agent tools are typed Pydantic functions with `reads`, `writes`, `risk` and `approval` declared; the node registers them from the manifest.
- Frontend types are generated from the OpenAPI schema; no hand-written API types.
- Secrets only in environment variables; encrypted fields use the node master key.
- Every pull request runs lint, type checks, unit tests and the dispatcher evaluation suite in GitHub Actions.
- Decisions that change the spec are recorded as short ADRs in `docs/adr/`.

## Sprint plan

Six two-week sprints; each ends with a demo to Hype and a working build. Months in brackets match the proposal milestones.

### Sprint 0: foundations (weeks 1 to 2 alongside Sprint 1)

- Monorepo, GitHub Actions, `uv`, Ruff, mypy, pytest
- Docker Compose for the node (API, worker, static files), Litestream config
- SQLite with WAL, Alembic set up with core, cleaning and dispatcher migration folders
- ADR 001 (stack) and ADR 002 (data standard v1.0 field list)

**Done when:** `docker compose up` starts an empty node with a health page and a passing CI pipeline.

### Sprint 1: core data and access (month 1)

- Data standard v1.0 tables: organisation, branch, person, client, location, job, visit, approval, thread, message, event
- Events service: append-only, hash chain, `actor` and `on_behalf_of` on every event
- Auth (D17, ADR 011): email, password and TOTP for office users (MFA required for owner, admin and accountant), sessions and refresh tokens, PIN step-up for risky approvals; staff are identified by their linked WhatsApp number, with a WhatsApp login code only if they open the web app
- RBAC: standard roles, Casbin model and policies, permission check middleware
- Office web app: login, and create, edit and list screens for clients, sites, staff and jobs
- CSV import for clients, sites and staff with column mapping and preview
- Master data owners: who may create or change clients, sites, staff, service agreements and price lists, and which changes need approval (a price or a site's access notes are not free text anyone can edit). Service agreements (scope, frequency, price per visit or m2, index clause) are a data standard addition and need approval first.

**Done when:** Hype's clients, sites and staff are imported, and an admin and a supervisor can log in with the right rights.

### Sprint 2: scheduling and approvals (month 1 to 2)

- Visit generation from jobs (recurrence rules), assignment, availability and skills, working-hour limits
- Schedule board by cleaner and by site, drag and drop, week view
- Supervisor view: unfilled visits, late check-ins, open problems
- Approvals service and inbox (record, approver roles, expiry, escalation, no self-approval, PIN for money and external types)
- Time and attendance chain: check-in and check-out produce timesheets; corrections and supervisor approval with separation of duties (whoever enters time does not approve it). Approved timesheets are the only source for the payroll export.

**Done when:** a full week for Hype is planned in the app and a supervisor approves a change from the inbox.

### Sprint 3: field work over WhatsApp (month 2)

- Check-in and check-out by WhatsApp location share, matched to the site's geofence in code; a check-in outside the fence is flagged, not rejected
- Today's visits and route, site instructions (access notes only during the visit, never in a message that stays on the phone longer than needed)
- Checklists as WhatsApp interactive lists and reply buttons; photos and problem reports as media messages stored on the node
- Quiet hours and templates for messages outside the 24-hour window (ADR 007); everything also visible in the office web app
- Finnish and English; Filipino measured for later clients

**Done when:** one supervisor and a first group of cleaners work a full week over WhatsApp (proposal month 2 milestone, changed from an app with Hype's agreement).

### Sprint 4: chat and the dispatcher agent (month 2 to 3)

- Chat message model and blocks; AG-UI endpoint on FastAPI; chat UI on web and mobile with streaming and reconnect
- Model routing: one cloud route through the gateway for the dispatcher (chosen by the evaluation suite), `local/` routes for models on the node, and the egress component with `none` and `pseudonymised` levels; gateway client and `usage_cloud_requests`. Distilled local skills replace the cloud route intent by intent in Phase 2.
- Dispatcher agent v1 with its tools (see below), running through the permission and approval checks
- Absence flow end to end: cleaner reports sick in chat, replacement suggested, supervisor approves if needed, everyone notified
- Dispatcher evaluation suite in CI
- Knowledge base (see "Knowledge base (RAG)"): document tables (after the data standard is approved), ingestion with review before publish, hybrid search with permission filtering, `core.search_knowledge` with cited answers, and its evaluation set

**Done when:** a sick report in chat is covered within two minutes in a demo with Hype data, and the evaluation suite passes at the agreed rate.

### Sprint 5: alerts, billing export and rollout (month 3)

- Alerts: unfilled visits, late check-ins, missing check-outs, overtime risk
- Billing summary export: completed visits and extras per client per month (CSV); extras count only when approved (by the client where the agreement requires it)
- Payroll export from approved timesheets in the format of Hype's payroll or accounting system. Mia does not run payroll or report to the Incomes Register (tulorekisteri) itself in Phase 1; the payroll system does.
- Backups verified with a restore test; install guide; update procedure
- Whole Hype team onboarded; two weeks of supported use; fixes from feedback

**Done when:** Hype runs a full month in the app, the billing summary is exported, and the Phase 1 release is accepted (proposal month 3 milestone).

### Rollout support

Feedback from demos, Finnish-language edge cases and rollout support, as needed.

## Dispatcher agent v1

The one fully configured agent in Phase 1, built with Pydantic AI on the manifest format from the spec; the model understands messages, code makes every scheduling decision.

**Job description:** keeps every visit staffed. Handles absence reports and shift questions from cleaners, suggests replacements, keeps supervisors informed, and never changes pay or client commitments on its own.

### Intents it handles

| Intent | From | Result |
| --- | --- | --- |
| Report absence (sick, late, leaving early) | Cleaner | Absence recorded, affected visits found, replacement suggested |
| Ask my schedule | Cleaner | Today's or this week's visits |
| Ask site instructions | Cleaner | Instructions for a visit they are assigned to (access notes only during the visit) |
| Find cover for a visit | Supervisor | Ranked replacement candidates |
| Approve or reject a suggestion | Supervisor | Assignment updated, people notified |
| Accept or decline a cover request | Cleaner | Visit reassigned, or the next candidate asked (built, D10) |
| Change or end an absence ("back tomorrow", "only the morning") | Cleaner | Absence updated, cover requests adjusted |
| Running late to a visit, with ETA | Cleaner | Supervisor told; client told only with approval |
| Can't get in (keys, alarm, locked) | Cleaner | Organisation instructions shown, supervisor alerted |
| Set availability or ask for time off | Cleaner | Availability updated; time off waits for supervisor approval |
| Anything else | Anyone | Polite redirect or handoff to a supervisor |

Started by events, not by a message: a missed check-in, a declined or unanswered cover request, a visit still unfilled close to its start. These are alerts (Sprint 5) that open a task for the dispatcher.

### Tools

| Tool | Kind | Risk | Approval |
| --- | --- | --- | --- |
| `core.read_person`, `core.read_visits`, `core.read_location` | Core | Read | Never |
| `dispatcher.record_absence` | Agent | Write internal | Never |
| `dispatcher.find_replacements` | Agent (code: scoring) | Read | Never |
| `dispatcher.propose_assignment` | Agent | Write internal | Never (creates a proposal) |
| `dispatcher.apply_assignment` | Agent | Write internal | Supervisor approval when the change adds overtime, moves a visit outside its window, or assigns someone new to the site; otherwise auto |
| `core.notify_person`, `core.notify_client` | Core | External | Client notifications always need supervisor approval in v1 |
| `core.request_approval`, `core.ask_supervisor` | Core | Internal | Never |

### Replacement scoring (code, not the model)

Candidates must be available, within daily and weekly hour limits, and not already assigned at that time. Ranking: knows the site (has done it before), has the required skills, shortest added travel, fewest hours this week, then preferred cleaners for the site. The top three are shown with reasons.

### Permissions

- Role `agent.dispatcher`; grants listed one by one as above; `denies: tool:*:approve`.
- Approvers: supervisor, admin, owner. Client notifications: supervisor.
- Separation of duties: the person who reported the absence cannot approve their own replacement.

### Instructions and models

- Base instructions in `prompts/base.md`; organisation instructions for Hype in `config/org/hype/dispatcher.md` (for example who to call for keys, quiet hours).
- Models: Gemma 4 12B on Ollama on the node only (D18); nothing goes to a cloud model with real data. Turns stop after 8 model calls with a polite translated fallback (D22). Where Gemma is weak (mostly format errors and extra tool calls), skills distilled from a cloud teacher (Sonnet 5.5, 100% on the suite) into small local classifiers run when their confidence is high, with a clarifying question (quick replies) when it is not.
- Languages: Finnish and English in and out; Filipino is measured in the evaluation suite for later Philippine clients.

### Data requirements and onboarding

- Requires: persons with skills and availability, locations with instructions and geofence, jobs with recurrence and required skills, visits generated.
- On missing availability: ask the supervisor; on missing skills: default to "general cleaning" and flag.
- Readiness: blocked without persons and jobs; ready with gaps when some availability is missing.

### Tests (evaluation suite)

At least 30 scenarios in Finnish and English (41 as of Oct 5, with Filipino), run 3 to 5 times each against the seeded database with real tools, reported per language: sick report at 05:40 with three visits, late arrival, absence with no available replacement (must escalate), request for instructions on a visit the cleaner is not assigned to (must refuse), a message that tries to instruct the agent to reassign someone (must ignore), and supervisor approval and rejection paths. Target pass rate 95% in Phase 1, overall and for each of Finnish and English.

## Knowledge base (RAG)

Answers questions from approved documents instead of from the model's memory: the company's
handbook and policies, site instructions, and cleaning knowledge. Mia never invents a policy,
price or rule; if no approved document answers the question, it says so and offers a person.

**Collections and access.** Every document has an owner, an audience (roles), a language, a
version, valid-from and valid-until dates, and a sensitivity level.

| Collection | Examples | Who can read |
| --- | --- | --- |
| Company handbook | payday, holidays, sick leave rules, uniforms, safety, who to contact, how to use Mia | staff of the organisation |
| Site instructions | what to clean, products, alarms; access notes (codes, key boxes) | the cleaner assigned to the visit; access notes only during the visit (spec) |
| Cleaning knowledge | safety data sheets, product dilution, stain removal, equipment care | all staff |
| Client FAQ (Phase 2) | services, what is included, cancellation policy, pets, insurance, household tax deduction | clients and leads |

**Ingestion.** Office users add documents (PDF, Word, Markdown, pasted text) in the web app or
with a CLI command. Text is extracted on the node, split by headings into passages of a few
hundred words, and stored with its metadata. A document is answerable only after its owner
publishes it (review before publish); every add, publish, replace and retire is an event
(rule 1). Documents never contain other people's personal data.

**Storage and search, all on the node.** Documents and passages are tables in the node database
(a data standard addition, needs approval first), with SQLite FTS5 for keyword search and
passage embeddings from a multilingual encoder (multilingual-e5, the same family as the intent
classifier, so one model serves both). Search is hybrid: keyword and meaning, merged.
Brute-force similarity is enough for tens of thousands of passages; a vector index comes only
when that is measured to be slow. Cross-language search works: a Finnish question finds an
English passage.

**Permissions before retrieval (rule 4).** `rbac.require` runs before search, and passages the
person may not read (another site's access notes, a visit outside its time window, client-only
material) are filtered out before anything reaches the model, never after.

**Answering.** The agent calls a registered read-only tool, `core.search_knowledge` (rule 3),
gets the top passages with their document, section and version, and answers only from them,
citing the source (shown as a card). Below a relevance threshold it answers "I don't have that
in the handbook" and offers the supervisor. Passages are data, never instructions (rule 8):
text inside a document cannot change Mia's behaviour. Answers are given in the user's language;
a passage in the user's language is preferred when both exist.

**Freshness and conflicts.** Only published, currently valid versions are searched; a newer
version replaces the older one. Organisation instructions (config/org) keep shaping how agents
behave; the knowledge base holds facts.

**Learning loop.** Questions the knowledge base could not answer, and answers people marked as
wrong, are collected for the document owner as suggested additions (review before publish),
the first rung of skill distillation.

**Evaluation.** A question set per collection and language: questions with the passage that
answers them, questions with no answer (Mia must say so), and questions the asker may not see
(must be filtered). Measured: retrieval hit rate in the top results, answers that stay faithful
to the passages (checked offline by a strong model on synthetic documents), correct refusals,
permission leaks (must be zero), and latency.

**Phase 1 scope.** Company handbook, site instructions and cleaning knowledge for Hype; the
client FAQ in Phase 2 with the client service agent. New dependencies to approve before the
build: a local runtime for the embedding model (for example onnxruntime) and text extraction for
PDF and Word files.

## Self-learning from clarifications

When Mia is not sure what a message means, it asks instead of guessing, and the person's answer
becomes a labelled example for the next version of the intent classifier.

**In the conversation.** The intent classifier returns its top intents with calibrated
confidence (high, medium, low):
- high: code acts;
- medium: Mia asks "Did you mean:" with the two or three most likely intents as buttons plus
  "Something else" (WhatsApp allows 3 reply buttons, or a list of up to 10). Option labels come
  from the intent catalogue as i18n strings in the person's language, never written by a model;
- low or "Something else": Mia asks the person to say it in other words, then hands over to a
  supervisor if it is still unclear. It asks once, never in a loop.
Writes still go through their normal confirmation and approval: choosing "Report I'm sick" leads
to the usual absence flow, so a wrong click cannot change data on its own.

**What is recorded.** An event per clarification with the message, its language, the options
shown with their scores, the choice, the classifier version, and the outcome: whether the
person finished the task, undid it or corrected it ("no, I meant"). Corrections, undos and
supervisor handoffs are recorded the same way as negative or corrected labels.

**Turning choices into training data, with care.**
- A choice is a weak label. It becomes training data only when the task it started was
  completed and not undone, and identical or near-identical messages agree.
- People can only pick what they were shown, so "Something else" answers and handoffs are kept
  and reviewed; they are where new intents and phrasings appear.
- Before training, a reviewer model checks each candidate label (a local model, or a stronger
  cloud model if the owner chose cloud) and a person (the data owner) approves batches of new
  examples. Special category data (health details beyond "sick", ID numbers) is dropped.
- Users are told in the privacy notice that messages may improve Mia; organisations can switch
  it off.

**Where training runs is the owner's choice** (organisation setting, D27):
- **Local (default):** the classifier retrains on the node, so real messages never leave the
  branch. Works with every egress level, including `none`.
- **Cloud:** for better review and training (stronger reviewer models, GPUs for larger
  students). Only when the organisation has agreed to it in its data processing agreement and
  its egress level allows it. The training set leaves through the egress component (rule 6):
  names, places, phone numbers, IDs, dates and amounts are replaced by tokens, free text that
  could still identify someone (incidents, health details, complaints about a named person) is
  dropped, and the export is logged. This is pseudonymised data, not anonymous data, and is
  described that way to the client. Processing happens in the EU, nothing is kept after the
  job, and only the trained model comes back.
In both cases a new version replaces the old one only if it passes the evaluation suite with no
drop in any language and no new permission or injection failures; the previous version is kept
for rollback, and each version's score is logged. Sharing learned patterns across organisations
is opt-in and pattern-level only (spec, QA); real messages are never pooled.

**What is measured.** Clarification rate (target under 10% per intent and language), how often
the top option is chosen, how often a choice is later undone, new phrasings learned per month,
and accuracy before and after each retrain.

## Agents, processes and capabilities beyond Phase 1

Phase 1 builds one agent. The rest of a cleaning company's work is mapped now so that Phase 1's
data and hand-offs do not have to be redone. The full list lives in docs/capabilities.md (to be
written): process, capability, intents, owning agent, trigger, system of record, risk and
sensitivity, approval and separation of duties, legal effect, country variant, phase.

**Agents are hired roles that mirror the client's departments** (spec: job description, own
role, approvers, onboarding, per-agent price). A small company hires a few and adds more as it
grows, the way it hires people. Planned roster:

| Agent (role) | Department | Main capabilities | Phase |
| --- | --- | --- | --- |
| Dispatcher | Operations | Absences, cover, schedule questions, field exceptions | 1 |
| Client service | Customer service | Bookings, changes, complaints, re-cleans, client notices (approval) | 2 |
| Sales | Sales | Leads, site surveys, quotes (code calculates), contracts, renewals and index increases | 2 |
| HR and payroll administrator | HR | Onboarding documents, time off, timesheet approval support, payroll export, offboarding | 2 |
| Bookkeeper | Finance | Invoicing, reminders, credit notes, supplier invoices, VAT and contribution reports via the accounting system | 2 to 3 |
| Purchaser | Operations | Supplies, equipment, suppliers and subcontractors | 3 |
| Recruiter | HR | Job ads, screening, interviews, offers | 3 |
| Marketing assistant | Sales | Posts, campaigns, reviews (drafts only, approval to publish) | 3 |
| QA (built in) | All | Watches every process end to end | platform |

**Processes are how workflows are designed and tested, never agents themselves.** They run
across agents, and each has a named process owner (a person in the client's
organisation) and an end-to-end test: Lead-to-Contract, Contract-to-Service, Service-to-Cash,
Hire-to-Retire, Procure-to-Pay, Record-to-Report. Agents hand work to each other as A2A tasks
(ADR 008) or events, never by writing each other's tables.

**Triggers:** a message from a person, an event (missed check-in, invoice received), or a schedule
(month-end invoicing, payroll cut-off, certificate expiry, contract renewal).

**Every capability declares how it is handled:** system of record (Mia, or an integrated system
such as the accounting or payroll system; Mia does not rebuild a general ledger), data owner,
validations in code (rule 7), approval and separation-of-duties pairs, sensitivity (special
category data such as health or ID documents never goes to a cloud model, even pseudonymised),
legal effect (terminations, contract changes and statutory filings are decided by a person; the
agent drafts), how it is reversed (credit note, reassignment; events are append-only), who is
notified and how fast, and the country variant.

**Country rules to design for:** Finland: Working Hours Act, Annual Holidays Act, the cleaning
sector collective agreement, tax cards, Incomes Register within five days of payment, occupational
health care, Contractor's Liability Act checks for subcontractors, Finvoice e-invoicing, household
tax deduction details. Philippines: BIR invoices, SSS, PhilHealth and Pag-IBIG, 13th-month pay,
DOLE rules on hours, rest days, holidays and night differential, Data Privacy Act.

**Local models:** the high-volume, language-heavy entry intents (absence, running late, can't get
in, supplies low, book or cancel, cover answers, schedule questions) are the first candidates for
distilled local classifiers. Rare, high-risk capabilities (payroll, terminations, contracts) stay
with a strong model and human approval.

## Definition of done, inputs and risks

### Definition of done (Phase 1 release)

- Hype Siivous has run one full month of operations in Mia: all visits planned, checked in and out, checklists completed.
- At least five real absence reports handled through chat, with replacements accepted by the supervisor.
- The billing summary for that month is exported and matches Hype's own records.
- The dispatcher evaluation suite passes at 95% or better in CI.
- A backup restore test has passed on Hype's server.
- The install guide lets a second node be set up in under two hours.
- Every action is visible in the events log with actor and on\_behalf\_of; no direct table writes exist outside service functions.

### Inputs needed from Hype Siivous

| Input | Needed by |
| --- | --- |
| Client, site and staff lists (Excel or CSV), site instructions and access notes | Sprint 1 |
| Cleaner skills and weekly availability | Sprint 2 |
| Checklist templates per site type | Sprint 3 |
| A supervisor and a first group of cleaners as pilot users, with phones | Sprint 3 |
| An Apple Silicon Mac mini (24 GB or more) on site, with the owner present at install (D19) | Sprint 3 |
| Agreement to WhatsApp-only field work instead of a mobile app (D20) | Before Sprint 3 |
| Organisation instructions for the dispatcher (contacts, quiet hours, escalation) | Sprint 4 |
| Hype's own WhatsApp Business account and number, completed business profile and Meta business verification (can take days to weeks), and a public HTTPS address for the node | Before the pilot uses WhatsApp |
| Last month's invoicing data to check the billing export against | Sprint 5 |
| Service agreements and price lists per client (scope, frequency, price, index clause) | Sprint 1 |
| Employee handbook and policies, site instructions, the safety data sheets of the products Hype uses, and the questions staff ask most | Sprint 4 |
| Names and import formats of Hype's payroll and accounting systems | Sprint 2 |

### Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| The local model (Gemma 4 12B, 85% today) does not reach 95% before the pilot | Turn cap, reply contract for small models, parallel intent by language suite, distilled classifier where Gemma is weak; the pilot starts only when the suite passes |
| Gemma is slow (about 10 s per turn on an M5 Pro) | Mac mini with 24 GB or more; shorter replies; test the QAT checkpoint and MTP speculative decoding |
| Meta approval for Hype's WhatsApp (business verification, display name, message templates) is slow | Start the Meta setup in Sprint 1; the in-app chat works without it |
| Check-in over WhatsApp is weaker than an app (no geofence trigger, no offline queue) | Location share matched to the site in code, flagged when outside; supervisor view of missing check-ins; revisit an app in Phase 2 if needed |
| Cleaners do not adopt the WhatsApp flows | Minimal-tap buttons and lists, Finnish and English, supervisor onboarding in Sprint 3, feedback loop every two weeks |
| Scope creep from demos | Anything beyond the plan goes to Phase 2 with Allan's sign-off |
| Hype expected an app (proposal) | Agree the WhatsApp-only change with Hype before Sprint 3 |
| Server at Hype is unreliable | Litestream backup from day one, health page, and a rented-server fallback |
| Statutory errors once Mia feeds payroll and invoicing (Working Hours Act limits, supplements, Incomes Register deadlines) | Phase 1 only exports; payroll and filing stay in Hype's payroll system. Limits and supplements are code with unit tests, checked against Hype's last month |
| The knowledge base answers from outdated or wrong documents, or shows access notes to the wrong person | Owner publishes each version, validity dates, permission filter before search with a zero-leak test, citations on every answer |
| The capability map turns into scope creep | Only Phase 1 rows are built; everything else is mapped so Phase 1 data does not block it later |
| Model gateway not ready | Sprint 4 can run with a single provider key on the node behind the same egress component; switch to the gateway when available |

### Weekly rhythm

- Monday: 30-minute planning with Allan; Friday: demo build and short written status (done, next, blockers).
- Every second Friday: demo to Hype.
- All decisions and scope changes recorded in `docs/adr/` or the issue tracker, never only in chat.
