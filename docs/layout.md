# Repository layout

```
mia/
  CLAUDE.md
  README.md
  pyproject.toml            uv project; the package lives in node/mia
  uv.lock
  .env.example              every MIA_* variable with a comment
  .pre-commit-config.yaml   ruff, mypy, detect-secrets (.secrets.baseline)
  .github/workflows/ci.yml  jobs: lint, types, tests, evals, docker (build, smoke and restore test)
  Dockerfile                the node image (ADR 010); .dockerignore beside it
  deploy/                   docker-compose.yml (node, litestream, tunnel), litestream.yml,
                            install.md, restore-test.sh (ADR 010)
  node/
    mia/
      settings.py           MIA_DB_PATH, MIA_MODEL, MIA_GATEWAY_URL, MIA_GATEWAY_KEY, MIA_EGRESS_LEVEL, MIA_ORG
      schema.py             imports every table module (Alembic, tests)
      cli.py                mia migrate | seed | serve | chat | decide | inbox | tick | geocode |
                            backup | verify-db | ...
      core/                 models, db, ids, events, store, rbac, approvals, egress, usage, people,
                            geocoding (pluggable providers), orgconfig (organisation settings)
      templates/cleaning/   models (sites, checklists), seed
      agents/               base.py (manifest, guard, model factory)
        dispatcher/         manifest.yaml, job.md, prompts/, models.py, classifier.py,
                            scoring.py, cover.py (confirmation flow), rules.py, tools.py,
                            agent.py, tests/scenarios.yaml
      chat/                 blocks.py, service.py, router.py, channels.py (notifications, calls)
      channels/             messaging channels (ADR 007): base.py (adapter protocol), registry.py,
                            render.py (fallback rendering), service.py (deliver), inbound.py,
                            outbox.py, linking.py (codes, invites), setup.py, transport.py (the only HTTP
                            exit for channels), router.py (webhooks), simulator.py ("sim" adapter)
        whatsapp/           adapter.py (Meta Cloud API), templates.py
      api/                  main.py
      i18n/                 Finnish and English strings
      static/index.html     dev chat page
    migrations/             alembic.ini, env.py, versions/
    config/                 policies/ (Casbin model.conf, policy.csv), org/demo/ (instructions, settings.yaml)
    tests/                  unit tests; evals/ (marker `evals`)
  docs/                     spec, plan, brief, ADRs, questions, decisions, ideas
```

Files beyond the brief's layout, and why, are listed in docs/adr/001-stack.md, 005 and 010.
Add new folders only with a reason recorded in an ADR.
