# Repository layout

```
mia/
  CLAUDE.md
  README.md
  pyproject.toml            uv project, one workspace for node/
  .github/workflows/ci.yml
  node/
    mia/
      settings.py           MIA_DB_PATH, MIA_MODEL, MIA_GATEWAY_URL, MIA_GATEWAY_KEY, MIA_EGRESS_LEVEL
      core/                 models, db, events, rbac, approvals, egress, usage, ids
      templates/cleaning/   models, seed
      agents/               base.py, dispatcher/ (manifest.yaml, job.md, prompts/, tools.py, agent.py, tests/)
      chat/                 blocks.py, router.py
      api/                  main.py
      static/index.html
    migrations/             alembic
    config/                 policies/, org/
    tests/                  unit tests and evals/
  docs/
```

Add new folders only with a reason recorded in an ADR.
