# Repository layout

```
mia/
  CLAUDE.md
  README.md
  pyproject.toml            uv project; the package lives in node/mia
  uv.lock
  .env.example              every MIA_* variable with a comment
  .pre-commit-config.yaml   ruff, mypy, detect-secrets (.secrets.baseline)
  .github/workflows/ci.yml  jobs: lint, types, tests, evals
  node/
    mia/
      settings.py           MIA_DB_PATH, MIA_MODEL, MIA_GATEWAY_URL, MIA_GATEWAY_KEY, MIA_EGRESS_LEVEL, MIA_ORG
      schema.py             imports every table module (Alembic, tests)
      cli.py                mia migrate | seed | serve | chat | decide | inbox | tick | geocode
      core/                 models, db, ids, events, store, rbac, approvals, egress, usage,
                            geocoding (pluggable providers), orgconfig (organisation settings)
      templates/cleaning/   models (sites, checklists), seed
      agents/               base.py (manifest, guard, model factory)
        dispatcher/         manifest.yaml, job.md, prompts/, models.py, classifier.py,
                            scoring.py, cover.py (confirmation flow), rules.py, tools.py,
                            agent.py, tests/scenarios.yaml
      chat/                 blocks.py, service.py, router.py, channels.py (notifications, calls)
      api/                  main.py
      i18n/                 Finnish and English strings
      static/index.html     dev chat page
    migrations/             alembic.ini, env.py, versions/
    config/                 policies/ (Casbin model.conf, policy.csv), org/demo/ (instructions, settings.yaml)
    tests/                  unit tests; evals/ (marker `evals`)
  docs/                     spec, plan, brief, ADRs, questions, decisions, ideas
```

Files beyond the brief's layout, and why, are listed in docs/adr/001-stack.md and 005.
Add new folders only with a reason recorded in an ADR.
