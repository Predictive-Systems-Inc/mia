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
                            geocoding (pluggable providers), orgconfig (organisation settings),
                            keys (master key, HKDF, scrypt, TOTP), auth (sessions, codes,
                            credentials, devices, clients; ADR 011), scheduling (recurrence,
                            visit generation, assignment rules, check-in, inbox)
      templates/cleaning/   models (sites, checklists), seed
      agents/               base.py (manifest, guard, model factory)
        dispatcher/         manifest.yaml, job.md, prompts/, models.py, classifier.py,
                            scoring.py, cover.py (confirmation flow), rules.py, tools.py,
                            agent.py, tests/scenarios.yaml (and scenarios_en.yaml)
        <role>/skill/       role.yaml, public.yaml, data/, reports/ (ADR 013)
      learning/             offline pipeline for role skill models (ADR 013)
      skills/               classifier runtime and per-turn routing (ADR 013)
      chat/                 blocks.py, service.py, router.py, channels.py (notifications, calls),
                            runs.py (live AG-UI runs: reconnect, catch-up, stop)
      channels/             messaging channels (ADR 007): base.py (adapter protocol), registry.py,
                            render.py (fallback rendering), service.py (deliver), inbound.py,
                            outbox.py, linking.py (codes, invites), setup.py, transport.py (the only HTTP
                            exit for channels), router.py (webhooks), simulator.py ("sim" adapter)
        whatsapp/           adapter.py (Meta Cloud API), templates.py
      api/                  main.py, deps.py (session and auth dependencies), auth.py (login routes),
                            schedule.py (week view, assignment, check-in, inbox)
      i18n/                 Finnish and English strings
      static/index.html     dev chat page
    migrations/             alembic.ini, env.py, versions/
    config/                 policies/ (Casbin model.conf, policy.csv), org/demo/ (instructions, settings.yaml),
                            ollama/ (Modelfiles for local models, ADR 004)
    tests/                  unit tests; auth/ (login flows); evals/ (marker `evals`; intents.jsonl, intents_catalogue.yaml
                            and intents.py for intent classification)
  docs/                     spec, plan, brief, ADRs, questions, decisions, ideas, capabilities,
                            research/ (research notes and dated evaluation reports, ADR 012)
```

Files beyond the brief's layout, and why, are listed in docs/adr/001-stack.md, 005 and 010.
Add new folders only with a reason recorded in an ADR.
