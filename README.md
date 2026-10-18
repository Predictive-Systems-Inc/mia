# Mia

Local-first AI ERP for businesses that run on shifts. One Mia Node per client branch, agents
built with Pydantic AI, data in SQLite on the client's own server.

This repository holds the first milestone (docs/brief.md): the node skeleton, the coding
harness, and a basic shift supervisor agent you can chat with.

## Quick start

Needs [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 if it is missing.

```
uv sync
cp .env.example .env        # MIA_MODEL=test needs no API key
uv run mia migrate          # creates data/mia.db
uv run mia seed             # demo cleaning company in Helsinki
uv run mia serve            # chat page at http://localhost:8000/
uv run pytest               # unit tests, no network, 80% coverage floor on mia/core
```

## Try the demo

In the chat page pick who you are acting as (top left), then:

1. As **Juha Laine** (cleaner): `Olen kipeä huomenna.` Mia records the absence, lists the
   affected visits and offers **Kaikki** or **Vain aamu**.
2. As **Sanna Virtanen** (supervisor): `Who can cover Kalasatama tomorrow at 6:30?` Mia shows the
   top candidates with reasons (site knowledge, skills, added travel, hours this week).
3. Still as Sanna: `Assign Mikael.` Her instruction is the approval. Mia asks Mikael to confirm;
   the visit does not change yet.
4. As **Mikael Nieminen**: Mia's question appears with **Hyväksyn** and **En pysty**. Press
   Hyväksyn: the visit is reassigned and Sanna is told. (No answer: after 15 minutes Mia calls,
   after 10 more it asks the next candidate.)
5. As Sanna: `Assign Liisa` after asking about Kamppi at 9:00. Liisa starts at 10:00, so the
   choice breaks a rule and an approval card goes to admin or owner; **Helena Hyppönen** (owner)
   can approve it, Sanna cannot.
6. As Juha: `Show me Maria's visits.` Mia refuses politely and the denial is logged.

The same from the terminal:

```
uv run mia chat "Olen kipeä huomenna." --as Juha
uv run mia chat "Who can cover Kalasatama tomorrow at 6:30?" --as Sanna
uv run mia chat "Assign Mikael." --as Sanna --thread <thread id printed above>
uv run mia inbox --as Mikael            # what Mia asked Mikael
uv run mia chat "Hyväksyn" --as Mikael
uv run mia inbox --as Sanna             # Mikael accepted
uv run mia chat "Show me Maria's visits." --as Juha
```

## Commands

| Command | Does |
| --- | --- |
| `uv run mia migrate` | Create or upgrade the SQLite database (Alembic) |
| `uv run mia seed` | Load demo data (once, on an empty database) |
| `uv run mia import FILE.yaml` | Real master data (people, clients, sites, jobs) from a YAML file; re-runnable, names are the key (docs/rollout.md) |
| `uv run mia serve` | FastAPI on port 8000: chat page `/`, `/health`, `/chat`, `/chat/stream`, `/ag-ui` (plus `/ag-ui/connect` to catch up and `/ag-ui/stop`), `/notifications`, `/approvals/{id}/decide`, `/channels/{id}/webhook` |
| `uv run mia chat "..." [--as NAME] [--thread ID]` | One chat turn from the terminal |
| `uv run mia decide ID approved\|rejected --as NAME` | Decide an approval (stand-in for the inbox) |
| `uv run mia billing export --month YYYY-MM [--out FILE]` | Completed work per client and site for a month, as CSV |
| `uv run mia schedule generate [--days N]` | Create the missing visits from the job recurrences (the node also does this daily) |
| `uv run mia keys init [PATH]` | Create the master key file (ADR 011) |
| `uv run mia auth bootstrap --email EMAIL` | First owner: prints an enrolment link (password and TOTP) |
| `uv run mia auth reset NAME` / `unlock LOGIN` / `link NAME` | Recovery: new enrolment link, clear a lockout, send a login link over WhatsApp |
| `uv run mia auth client add NAME --role ROLE` / `revoke ID` | Client credentials for outside agents and services |
| `uv run mia inbox --as NAME` | Show messages Mia sent to a person |
| `uv run mia tick` | Run each agent's due work, retry deferred turns and send the channel outbox once (`mia serve` does this every 30 s; a turn is claimed under the write lock, so running both is safe) |
| `uv run mia person add NAME --role staff [--lang fi]` | Add a person |
| `uv run mia invite NAME [--as SUPERVISOR]` | One-time WhatsApp invite link for a person (needs `MIA_NODE_SECRET`) |
| `uv run mia channels sim "..." --from NUMBER` | Message Mia as a phone on the simulated channel (try `LINK <code>` first) |
| `uv run mia geocode` | Geocode home bases and sites without coordinates (needs `MIA_GEOCODER_KEY`) |
| `uv run mia backup FILE` | Consistent copy of the database to a new file (safe while serving) |
| `uv run mia verify-db FILE` | Check a restored copy: integrity, events hash chain, row counts |
| `uv run mia skills generate ROLE --model ROUTE --split train\|test` | Teacher-model generation per coverage cell (role skill models) |
| `uv run mia skills translate --lang fi\|fil --model ROUTE [--limit N]` | The intent eval set in another language, translated from the English records (a `local/` model sends nothing off the node) |
| `uv run pytest` | Unit tests |
| `uv run pytest node/tests/evals -m evals` | Shift supervisor evaluation suite (41 scenarios, 5 runs each; `MIA_EVAL_SUITE=tests/scenarios_en.yaml` for English only) |
| `MIA_EVAL_MODEL=local/<model> uv run pytest node/tests/evals/test_intent_classification.py -m evals -s` | English intent classification over docs/capabilities.md (held-out split; `MIA_EVAL_INTENT_SPLIT=all`, `MIA_EVAL_REPORT=file.json`) |
| `MIA_DECIDER=jev MIA_EVAL_RUNS=1 uv run pytest node/tests/evals/test_shift_supervisor_evals.py -m evals -s` | The shift supervisor suite through Jev (spec docs/superpowers/specs/2026-10-17-jev-decider-design.md; needs `MIA_TYPESAFE_KEY`, demo data only) |
| `uv run pytest node/tests/evals/test_jev_action_eval.py -m evals -s` | Jev's action choice on the intent set (`MIA_EVAL_INTENT_SPLIT`, `MIA_EVAL_INTENT_LANG`, `MIA_EVAL_REPORT`; skips without `MIA_TYPESAFE_KEY`) |
| `MIA_TYPESAFE_KEY=... uv run pytest node/tests/evals/test_router_eval.py -m evals -s` | The agent router through real Jev over six agents and nine languages, plus a deferral check (synthetic data; prints the table, writes `docs/research/router-<date>.raw.json`; skips without `MIA_TYPESAFE_KEY`) |
| `uv run ruff check . && uv run ruff format --check . && uv run mypy node/mia` | Lint and types |
| `uv run pre-commit install` | Run ruff, mypy and detect-secrets on every commit |

The actor for HTTP calls is the `X-Mia-Actor: <person id>` header. There is no real login yet;
do not expose a node built from this milestone to a network.

## Role skill models

Each agent role can have its own multilingual intent classifier (docs/superpowers/specs/2026-10-06-skill-models-design.md).
In Claude Code run `/mia-train-role <role>`; it plans the role, researches public data, generates and reviews
messages, then runs:

    uv run mia skills validate <role>    # data checks
    uv run mia skills split <role>       # train and dev from reviewed.jsonl
    uv sync --group learning && uv run mia skills train <role>   # train, calibrate, evaluate, package
    uv run mia skills promote <role> <version> --signed-by "Name"
    uv run mia skills harvest <role>     # on the node: clarification choices to candidates
    uv run mia skills generate <role> --model ROUTE --split train|test   # teacher generation
    uv run mia skills overlap <role>     # ranked overlap review of intents (learning group)
    uv run mia skills bakeoff <role>     # train encoder, knn, contrastive; compare; promotes nothing

Harvested candidates stay in `MIA_LEARNING_DIR/<role>/candidates.jsonl` on the node. If a stale
Hugging Face token gives 401 errors when training, set `HF_HUB_DISABLE_IMPLICIT_TOKEN=1`.

## Messaging channels

People can talk to Mia on WhatsApp as well as in the app (ADR 007). Try it without a Meta
account on the simulated channel:

```
uv run mia invite Juha                       # prints a link and "LINK 123456"
uv run mia channels sim "LINK 123456" --from 358401234567
uv run mia channels sim "Olen kipeä huomenna." --from 358401234567
```

For the real WhatsApp number, follow docs/whatsapp-setup.md.

## Authentication

Every request carries a verified actor (ADR 011, docs/superpowers/specs/2026-10-05-authentication-design.md).
`MIA_AUTH_MODE=dev` (the `.env.example` default) keeps the `X-Mia-Actor` header for local
development and the chat page's actor picker; it works only from localhost and the node refuses
to start in dev mode with a public URL. A server runs `required`.

- Office users: `POST /auth/login` (email, password), then `POST /auth/mfa` with a TOTP or
  recovery code. Owner, admin and accountant must enrol an authenticator (`/auth/mfa/enrol`,
  `/auth/mfa/confirm`) before they get past the enrolment session. Web clients send
  `X-Mia-Client: web` and get HttpOnly cookies; others get bearer tokens with a rotating refresh
  token (`/auth/refresh`).
- Staff: `POST /auth/otp/start` sends a 6-digit code to the linked WhatsApp number;
  `POST /auth/otp/verify` binds the phone (a device secret, shown once) and signs in;
  `POST /auth/device` signs in again on that phone. A one-time login link (`mia auth link`)
  opens the web app from WhatsApp.
- Risky approvals (money, external, delete) need a 6-digit PIN entered in the last five minutes:
  `POST /auth/pin` to set it, `POST /auth/stepup` before deciding; the API answers 403
  `step_up_required` otherwise.
- Outside agents and services: `mia auth client add` and `POST /auth/token`
  (client credentials, one-hour bearer tokens); clients never hold `approve`.
- Keys: `mia keys init` writes the master key (mode 400); subkeys come from HKDF. Without a key
  file, `MIA_NODE_SECRET` keys the one-time codes, so old invites keep working.

## Scheduling

Visits come from each job's recurrence rule (`FREQ=DAILY` or `FREQ=WEEKLY;BYDAY=..`, optional
`INTERVAL` and `UNTIL`), generated 28 days ahead once a day and by `mia schedule generate`.
A new visit copies the last assignment on the same weekday when that person is still eligible,
otherwise it is `unfilled`. Eligibility is code, the same rules the shift supervisor uses for cover:
availability, absences, double booking, daily and weekly hour limits, skills.

- `GET /schedule?start=&person_id=&location_id=`: seven days of visits (staff see their own);
  `GET /schedule/people` lists the branch's people for the office. The dev page's "Schedule
  board" assigns and unassigns from the week table, and its "Supervisor summary" panel shows
  the summary, resolves site problems and approves timesheet drafts.
- `POST /visits/{id}/assign {person_id, add}` and `/unassign`: the office assigns; a
  rule-breaking assignment creates an approval (`schedule.assignment_override`, admin or owner,
  app only with a PIN) and the visit changes only when it is approved.
- `POST /visits/{id}/check-in` and `/check-out`: the cleaner on their own visit (from two
  hours before the start), or the office for them.
- `GET /approvals`: the inbox, the approvals the signed-in person may decide.
- `GET /timesheets`, `POST /timesheets/{id}/correct` and `/approve`: drafts built from completed
  visits (actual times after a check-out), corrected by the person or the office, approved by a
  supervisor who did not enter them. `mia payroll export --from --to` writes the approved rows
  as CSV; the ticker alerts a missing check-out and overtime.
- Over chat, a cleaner checks in ("Olen perillä"), asks the door code, gets the checklist
  ("Mikä on tarkistuslista?") and ticks items with the quick replies ("Tehty: Empty bins"),
  reports a problem ("En pääse sisään"), sends a photo as proof of work (saved under
  `MIA_MEDIA_DIR`, referenced on the visit) and checks out ("Valmis, lähden nyt"). A shared
  location checks in (or out, during the visit); one outside the site's geofence, or a chosen
  place rather than the phone's position, is flagged for the supervisors, not rejected. The
  coordinates are used once and never stored.
- `GET /supervisor/summary`: unfilled visits this week, today's late check-ins, today's
  check-ins and check-outs outside the site's geofence, open site
  problems (a cleaner's "en pääse sisään" or "no water" over chat tells the supervisors at
  once) and the number of pending approvals; `POST /problems/{id}/resolve` closes a problem.

The schedule board belongs to the office app (Q19); timesheets wait for Q20.

The ticker also sends three alerts, each once (the marker is an event): a cleaner who has not
checked in 15 minutes after the planned start is asked, and the supervisors told; from 15:00
local the supervisors get a card of tomorrow's visits without a cleaner; from 17:00 each cleaner
gets a card of tomorrow's visits. The times are organisation settings (`alerts:` in
`node/config/org/<org>/settings.yaml`).

## Installing on a server

Docker Compose runs the node with Litestream backup (and optionally a Cloudflare Tunnel) on one
server. Install, backups, restore test and updates: deploy/install.md.

```
cp .env.example deploy/.env      # then edit; secrets stay in this file
cd deploy && docker compose build && docker compose up -d --wait
./restore-test.sh                # restores the latest backup and verifies it
```

## Using a real model

Two kinds of model, chosen with `MIA_MODEL` in `.env`; no code changes:
- Cloud: `MIA_MODEL=gateway/<route>` with `MIA_GATEWAY_URL` and `MIA_GATEWAY_KEY` (any
  OpenAI-compatible endpoint, for example OpenRouter `https://openrouter.ai/api/v1`). Requests go
  through the egress component, which pseudonymises person names, writes `egress_log` and meters
  `usage_cloud_requests`. `MIA_EGRESS_LEVEL=none` blocks them.
- Local: `MIA_MODEL=local/<model>` with `MIA_LOCAL_URL` (default Ollama,
  `http://localhost:11434/v1`). Nothing leaves the node, so egress is skipped and it works with
  `MIA_EGRESS_LEVEL=none`. The URL must be localhost or a private IP address.

Jev (TypeSafe, `MIA_TYPESAFE_KEY`): `MIA_DECIDER=jev` turns on both the shift supervisor's Jev
decider and the agent router; otherwise a person with several agents stays on the active one or
is asked.

To evaluate a model: `MIA_EVAL_MODEL=gateway/<route>` or `local/<model>`, then
`uv run pytest node/tests/evals -m evals`.

Rolling out at a client: docs/rollout.md (install, keys, master data import, linking the phones, the first week).

## Documents
- docs/spec.md: Mia Agent Manifest Specification v0.1
- docs/plan.md: Phase 1 build plan (Hype Siivous)
- docs/brief.md: initial build brief (this milestone)
- docs/layout.md: repository layout
- docs/adr/: architecture decision records (001 stack, 002 data standard, 003 tool risk and approval, 004 model routing and egress, 005 data standard 1.1 and cover confirmation, 010 install and backup)
- deploy/install.md: install, backup, restore and update a node
- docs/questions.md and docs/decisions.md: clarification loop between the coding agent and the product owner
- docs/ideas.md: ideas outside this milestone's scope

## Rules for coding agents
See CLAUDE.md. It is read automatically by Claude Code.
