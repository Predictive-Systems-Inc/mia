# Mia Phase 1 Build Plan

Sep 30, 2026 · @Allan Tan

## Goal and scope

Build the Mia platform structure and one fully configured agent, the dispatcher, and put it into daily use at Hype Siivous within 3 months (about 450 hours).

**In scope (Phase 1)**

- Mia Node: FastAPI, SQLite, Alembic, Huey, Docker Compose install, Litestream backup
- Data standard v1.0 and the cleaning template: sites, jobs, visits, checklists, check-in and check-out, photos
- Authentication, RBAC (pycasbin), approvals service and inbox, append-only events log with hash chain
- Office web app (React, Vite, static files served by the node): clients, sites, staff, schedule board, supervisor view, approvals, exports
- Cleaner mobile app (Expo): today's visits, instructions, check-in and check-out, checklists with photos, chat, offline queue
- Chat: AG-UI endpoint, message model with text, quick replies, card, approval card, form and file blocks; web and mobile chat UI
- Cloud egress policy (`none`, `pseudonymised`) and the gateway client; usage table
- Dispatcher agent v1 (Pydantic AI): absence reports, replacement suggestions, schedule questions, site instructions, alerts
- Billing summary export (CSV) in code
- Finnish and English UI

**Out of scope (deferred):** Mia Cloud UI and bundle sync (not built until decided otherwise, D13), catalogue and hiring, grading, subagents and variants, QA agent and audit reports, voice, QuickBooks and other connectors, custom fields UI, chart and table blocks, payroll and social media agents.

**Added to scope (D13):** outside channels, WhatsApp first; see docs/superpowers/specs/2026-10-02-channel-adapters-whatsapp-design.md.

**Designed in Phase 1, built in Phase 2:** A2A between agents (D14, ADR 008; needs real authentication first, and Phase 1 has one agent on one node) and skill distillation for small local models (needs real traffic from the pilot to train on).

**References:** the [Mia Agent Manifest Specification v0.1](https://claude.ai/code/artifact/36ffddd5-462a-46cc-b582-5dbcbf46720b) (architecture, RBAC, approvals, chat, egress, tech stack) and the Hype Siivous proposal (scope and timeline commitments).

**Team and budget:** one senior full-stack developer (Python and TypeScript) at about 150 hours a month, with Allan as product owner and reviewer. Hours below total 450 including a 60-hour buffer.

## Status and revised order (Oct 5, 2026)

Built so far, ahead of the sprint order below: the initial build (docs/brief.md), core data and
events, RBAC and approvals records, chat with blocks and AG-UI, the dispatcher with instructed
cover and the confirmation flow (D1, D6 to D11), channel adapters with WhatsApp (D13), local
and cloud model routes with the evaluation suite. Not built: real authentication (the actor
still comes from the unverified X-Mia-Actor header), the office web app, the cleaner mobile
app, Huey workers, Docker Compose and Litestream.

Remaining work in this order, because each step unblocks the next:

1. **Authentication and identity** (Sprint 1 item, moved first): office login, staff phone
   OTP, sessions, and channel identities linked to real accounts. Blocks the pilot with real
   people, WhatsApp in production and A2A.
2. **Production model route**: the EU gateway (or the organisation's own key) behind egress,
   and a model chosen by the evaluation suite. Evaluation on Oct 5 (41 scenarios, 3 runs):
   Claude Sonnet 5.5 100%, Claude Haiku 4.5 87%, Qwen3.5 27B 86%, Qwen3.5 9B on llama.cpp 77%
   (Ollama 64%). Real staff data must not go to a model route without the EU, no-retention
   terms (spec, egress).
3. **Install and backup** (Sprint 0 items still open): Docker Compose, Litestream, health page,
   install guide; needed before anything runs at Hype.
4. **Scheduling and approvals inbox** (Sprint 2), then the **office web app** screens it needs.
5. **Cleaner mobile app** (Sprint 3): scope to confirm with Hype, since WhatsApp now covers
   chat, absence reports and cover requests; check-in, checklists and photos still need the
   app unless done over WhatsApp.
6. **Alerts, billing export, rollout** (Sprint 5).

The hours below are the original estimate; the channel work (D13) was not in it, so the buffer
is partly used. Re-estimate the remaining sprints at the next planning meeting.

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
    mobile/          Expo
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

### Sprint 0: foundations (20 h, weeks 1 to 2 alongside Sprint 1)

- Monorepo, GitHub Actions, `uv`, Ruff, mypy, pytest
- Docker Compose for the node (API, worker, static files), Litestream config
- SQLite with WAL, Alembic set up with core, cleaning and dispatcher migration folders
- ADR 001 (stack) and ADR 002 (data standard v1.0 field list)

**Done when:** `docker compose up` starts an empty node with a health page and a passing CI pipeline.

### Sprint 1: core data and access (70 h, month 1)

- Data standard v1.0 tables: organisation, branch, person, client, location, job, visit, approval, thread, message, event
- Events service: append-only, hash chain, `actor` and `on_behalf_of` on every event
- Auth: email plus password or passkey for office users with MFA, phone OTP with device binding for staff, sessions and refresh tokens
- RBAC: standard roles, Casbin model and policies, permission check middleware
- Office web app: login, and create, edit and list screens for clients, sites, staff and jobs
- CSV import for clients, sites and staff with column mapping and preview

**Done when:** Hype's clients, sites and staff are imported, and an admin and a supervisor can log in with the right rights.

### Sprint 2: scheduling and approvals (75 h, month 1 to 2)

- Visit generation from jobs (recurrence rules), assignment, availability and skills, working-hour limits
- Schedule board by cleaner and by site, drag and drop, week view
- Supervisor view: unfilled visits, late check-ins, open problems
- Approvals service and inbox (record, approver roles, expiry, escalation, no self-approval, PIN for money and external types)

**Done when:** a full week for Hype is planned in the app and a supervisor approves a change from the inbox.

### Sprint 3: cleaner mobile app (75 h, month 2)

- Expo app: phone OTP login, today's visits and route, site instructions (access notes shown only during the visit)
- Geofenced check-in and check-out, photo capture and upload, checklist completion, problem reports
- Offline queue for check-ins, checklist results and photos; push notifications without personal data
- Finnish and English

**Done when:** one supervisor and a first group of cleaners use the app for a full week (proposal month 2 milestone).

### Sprint 4: chat and the dispatcher agent (80 h, month 2 to 3)

- Chat message model and blocks; AG-UI endpoint on FastAPI; chat UI on web and mobile with streaming and reconnect
- Model routing: one cloud route through the gateway for the dispatcher (chosen by the evaluation suite), `local/` routes for models on the node, and the egress component with `none` and `pseudonymised` levels; gateway client and `usage_cloud_requests`. Distilled local skills replace the cloud route intent by intent in Phase 2.
- Dispatcher agent v1 with its tools (see below), running through the permission and approval checks
- Absence flow end to end: cleaner reports sick in chat, replacement suggested, supervisor approves if needed, everyone notified
- Dispatcher evaluation suite in CI

**Done when:** a sick report in chat is covered within two minutes in a demo with Hype data, and the evaluation suite passes at the agreed rate.

### Sprint 5: alerts, billing export and rollout (70 h, month 3)

- Alerts: unfilled visits, late check-ins, missing check-outs, overtime risk
- Billing summary export: completed visits and extras per client per month (CSV)
- Backups verified with a restore test; install guide; update procedure
- Whole Hype team onboarded; two weeks of supported use; fixes from feedback

**Done when:** Hype runs a full month in the app, the billing summary is exported, and the Phase 1 release is accepted (proposal month 3 milestone).

### Buffer (60 h)

Reserved for feedback from demos, Finnish-language edge cases and rollout support. Not planned in advance.

| Sprint | Hours |
| --- | --- |
| 0 Foundations | 20 |
| 1 Core data and access | 70 |
| 2 Scheduling and approvals | 75 |
| 3 Cleaner mobile app | 75 |
| 4 Chat and dispatcher | 80 |
| 5 Alerts, export, rollout | 70 |
| Buffer | 60 |
| **Total** | **450** |

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
| Anything else | Anyone | Polite redirect or handoff to a supervisor |

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
- Models: one cloud model route via the Better Labs gateway with egress level `pseudonymised` for Phase 1. A local model on llama.cpp (Qwen3.5 9B passes 77%, short of the 95% target) is the fallback when the gateway is unreachable, and only for reads and clarifying questions. Phase 2: skills distilled from the cloud model into small local classifiers, run automatically when their confidence is high, with a clarifying question (quick replies) when it is not.
- Languages: Finnish and English in and out; Filipino is measured in the evaluation suite for later Philippine clients.

### Data requirements and onboarding

- Requires: persons with skills and availability, locations with instructions and geofence, jobs with recurrence and required skills, visits generated.
- On missing availability: ask the supervisor; on missing skills: default to "general cleaning" and flag.
- Readiness: blocked without persons and jobs; ready with gaps when some availability is missing.

### Tests (evaluation suite)

At least 30 scenarios in Finnish and English (41 as of Oct 5, with Filipino), run 3 to 5 times each against the seeded database with real tools, reported per language: sick report at 05:40 with three visits, late arrival, absence with no available replacement (must escalate), request for instructions on a visit the cleaner is not assigned to (must refuse), a message that tries to instruct the agent to reassign someone (must ignore), and supervisor approval and rejection paths. Target pass rate 95% in Phase 1, overall and for each of Finnish and English.

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
| A server or mini PC on site, or a rented server, with the owner present at install | Sprint 3 |
| Organisation instructions for the dispatcher (contacts, quiet hours, escalation) | Sprint 4 |
| Hype's own WhatsApp Business account and number, completed business profile and Meta business verification (can take days to weeks), and a public HTTPS address for the node | Before the pilot uses WhatsApp |
| Last month's invoicing data to check the billing export against | Sprint 5 |

### Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Finnish understanding by small local models is weak (confirmed Oct 5: most local failures are short Finnish messages) | Cloud model route for Phase 1; Finnish scenarios measured separately; local small models only for distilled, high-confidence skills in Phase 2 |
| Meta approval for Hype's WhatsApp (business verification, display name, message templates) is slow | Start the Meta setup in Sprint 1; the in-app chat works without it |
| No EU model route with no-retention terms when the pilot starts | Gateway work is step 2 of the revised order; until then pilot data stays on the node (local route or egress level `none`) |
| Cleaners do not adopt the app | Minimal-tap flows, voice notes, Finnish and English, supervisor onboarding in Sprint 3, feedback loop every two weeks |
| Scope creep from demos | Buffer of 60 hours; anything larger goes to Phase 2 with Allan's sign-off |
| Mobile release delays (app store review) | Submit a test build in Sprint 3 week 1; use internal test tracks until the store release |
| Server at Hype is unreliable | Litestream backup from day one, health page, and a rented-server fallback |
| Model gateway not ready | Sprint 4 can run with a single provider key on the node behind the same egress component; switch to the gateway when available |

### Weekly rhythm

- Monday: 30-minute planning with Allan; Friday: demo build and short written status (done, next, blockers).
- Every second Friday: demo to Hype.
- All decisions and scope changes recorded in `docs/adr/` or the issue tracker, never only in chat.
