# Mia

Local-first AI ERP for businesses that run on shifts. One Mia Node per client branch, agents
built with Pydantic AI, data in SQLite on the client's own server.

This repository holds the first milestone (docs/brief.md): the node skeleton, the coding
harness, and a basic dispatcher agent you can chat with.

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
| `uv run mia serve` | FastAPI on port 8000: chat page `/`, `/health`, `/chat`, `/chat/stream`, `/ag-ui`, `/notifications`, `/approvals/{id}/decide` |
| `uv run mia chat "..." [--as NAME] [--thread ID]` | One chat turn from the terminal |
| `uv run mia decide ID approved\|rejected --as NAME` | Decide an approval (stand-in for the inbox) |
| `uv run mia inbox --as NAME` | Show messages Mia sent to a person |
| `uv run mia tick` | Advance due cover confirmations once (`mia serve` does this every 30 s) |
| `uv run mia geocode` | Geocode home bases and sites without coordinates (needs `MIA_GEOCODER_KEY`) |
| `uv run pytest` | Unit tests |
| `uv run pytest node/tests/evals -m evals` | Dispatcher evaluation suite (33 scenarios, 5 runs each) |
| `uv run ruff check . && uv run ruff format --check . && uv run mypy node/mia` | Lint and types |
| `uv run pre-commit install` | Run ruff, mypy and detect-secrets on every commit |

The actor for HTTP calls is the `X-Mia-Actor: <person id>` header. There is no real login yet;
do not expose a node built from this milestone to a network.

## Using a real model

Set `MIA_MODEL=gateway/<route>`, `MIA_GATEWAY_URL` and `MIA_GATEWAY_KEY` in `.env`. No code
changes: requests go through the egress component, which pseudonymises person names, writes
`egress_log` and meters `usage_cloud_requests`. `MIA_EGRESS_LEVEL=none` blocks cloud requests.
To evaluate a real model: `MIA_EVAL_MODEL=gateway/<route> uv run pytest node/tests/evals -m evals`.

## Documents
- docs/spec.md: Mia Agent Manifest Specification v0.1
- docs/plan.md: Phase 1 build plan (Hype Siivous)
- docs/brief.md: initial build brief (this milestone)
- docs/layout.md: repository layout
- docs/adr/: architecture decision records (001 stack, 002 data standard, 003 tool risk and approval, 004 model routing and egress, 005 data standard 1.1 and cover confirmation)
- docs/questions.md and docs/decisions.md: clarification loop between the coding agent and the product owner
- docs/ideas.md: ideas outside this milestone's scope

## Rules for coding agents
See CLAUDE.md. It is read automatically by Claude Code.
