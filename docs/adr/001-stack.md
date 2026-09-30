# 001: Stack for the initial build

## Status
Accepted (initial build, 2026-09-30).

## Context
The brief fixes the stack: Python 3.12 with uv, Pydantic AI 2.x, FastAPI, SQLModel on SQLAlchemy 2,
Alembic, pycasbin and pytest. A few details were left open.

## Decision
- One uv project at the repository root; the package lives in `node/mia` (hatchling build),
  so `uv run mia ...` and `uv run pytest` work from the root. `node/` is the only workspace member
  for now; `apps/` and `cloud/` join later as separate packages.
- Pydantic AI `>=2.52,<3` with the `openai` and `ag-ui` extras.
- SQLite in WAL mode, `busy_timeout=5000`, foreign keys on. Times are stored as ISO 8601 strings
  with offset through a `TZDateTime` column type that refuses naive datetimes.
- IDs are ULIDs generated monotonically within the process, so ordering by id follows insert
  order (the events hash chain relies on this).
- The acting person comes from the `X-Mia-Actor` header (a person id) until real authentication
  lands in Sprint 1. This is documented as temporary and must not ship to a client.
- `tzdata` is a dependency so `zoneinfo` works on machines without a system time zone database.
- Files added beyond the brief's layout (see docs/layout.md): `core/store.py` (generic write
  services that always emit an event), `schema.py` (imports every table module for Alembic and
  tests), `cli.py`, `i18n/`, `chat/service.py` (one chat turn, shared by HTTP and CLI), and in
  the dispatcher `models.py`, `classifier.py`, `scoring.py` and `rules.py`.

## Consequences
- Background jobs (Huey), Docker Compose, Litestream and the web and mobile apps are not in this
  build; they arrive in their sprints without changing this layout.
- Pydantic AI 2.52 warns that `httpx.AsyncClient` support for OpenAI-compatible providers moves to
  `httpx2` in v3. The egress transport must be ported when we upgrade.
