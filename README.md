# Mia

Local-first AI ERP for businesses that run on shifts. One Mia Node per client branch, agents built with Pydantic AI, data in SQLite on the client's own server.

## Documents
- docs/spec.md: Mia Agent Manifest Specification v0.1 (architecture, RBAC, approvals, chat, egress, tech stack)
- docs/plan.md: Phase 1 build plan (Hype Siivous)
- docs/brief.md: Initial build brief (this repository's first milestone)
- docs/layout.md: repository layout
- docs/adr/: architecture decision records
- docs/questions.md and docs/decisions.md: clarification loop between the coding agent and the product owner

## Quick start (target state, see docs/brief.md)
```
uv sync
cp .env.example .env        # MIA_MODEL=test needs no API key
uv run mia migrate
uv run mia seed
uv run mia serve            # chat page at http://localhost:8000/
uv run pytest
```

## Rules for coding agents
See CLAUDE.md. It is read automatically by Claude Code.
