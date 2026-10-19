# Repository layout

```
mia/
  CLAUDE.md
  README.md
  pyproject.toml            uv project; the package lives in node/mia
  uv.lock
  .env.example              every MIA_* variable with a comment
  .pre-commit-config.yaml   ruff, mypy, detect-secrets (.secrets.baseline)
  .claude/skills/mia-build-agent/  SKILL.md, checklist.md, prompts/ (spec, plan, reviewer): /mia-build-agent
  .github/workflows/ci.yml  jobs: lint, types, tests, evals, docker (build, smoke and restore test)
  Dockerfile                the node image (ADR 010); .dockerignore beside it
  deploy/                   docker-compose.yml (node, litestream, tunnel), litestream.yml,
                            install.md, restore-test.sh (ADR 010)
  node/
    mia/
      settings.py           MIA_DB_PATH, MIA_MODEL, MIA_GATEWAY_URL, MIA_GATEWAY_KEY, MIA_EGRESS_LEVEL, MIA_ORG
      schema.py             imports every table module (Alembic, tests)
      cli.py                mia migrate | seed | serve | chat | decide | inbox | tick | geocode | learned | forget |
                            backup | verify-db | ...
      core/                 models, db, ids, events, store, rbac, approvals, egress, usage, people,
                            absences, cover requests, timesheets, incidents (data standard 1.4),
                            geocoding (pluggable providers), orgconfig (organisation settings),
                            keys (master key, HKDF, scrypt, TOTP), auth (sessions, codes,
                            credentials, devices, clients; ADR 011), scheduling (recurrence,
                            visit generation, assignment rules, check-in, inbox), billing
                            (the monthly summary export), jev.py (one TypeSafe Jev request)
      templates/cleaning/   models (sites, checklists, checklist ticks), seed, importer (master data from YAML)
      templates/retail/     models (items with short codes and prices, branch hours), hours (opening
                            hours helpers and the business date), seed (Ferino's demo)
      learning/             role skill data: generate, translate (the eval set by language), train, bakeoff
      agents/               base.py (manifest, guard, model factory, AgentSpec), registry.py
                            (every agent by id), stubs.py (roster agents not built yet),
                            decider.py (the shared Jev decider), scaffold.py and _template/
                            (`mia agent scaffold`: a new agent package, wired in)
        shift_supervisor/   manifest.yaml, job.md, prompts/, classifier.py,
                            scoring.py, cover.py (confirmation flow), alerts.py (missed
                            check-in and check-out, overtime, unstaffed visits, daily plan),
                            timesheets.py (drafts, corrections, approval, payroll rows),
                            rules.py, tools.py (incl. incidents),
                            agent.py, turn.py (its chat turn and AgentSpec),
                            tests/scenarios.yaml (and scenarios_en.yaml)
        sales_supervisor/   manifest.yaml, job.md, prompts/, models.py (counts, targets, notes),
                            actions.py and decider.py (Jev), tools.py, calc.py, due.py,
                            replies.py, turn.py, tests/scenarios.yaml (chat scenarios)
        inventory_manager/  Inventory Manager: the mia agent scaffold shape (turn.py, actions.py, ...)
        hr_officer/         HR Officer: the mia agent scaffold shape (turn.py, actions.py, ...)
        <role>/skill/       role.yaml, public.yaml, data/, reports/ (ADR 013)
      skills/               classifier runtime and per-turn routing (ADR 013)
      chat/                 blocks.py, service.py, router.py, channels.py (notifications, calls),
                            runs.py (live AG-UI runs: reconnect, catch-up, stop), replies.py
                            (stored replies), access.py (a person's agents), agent_router.py
                            (the Jev router, ADR 015), language.py (the reply language, ADR 016),
                            deferred.py (turns waiting while Jev is unreachable),
                            route_memory.py (what people chose when Mia asked)
      channels/             messaging channels (ADR 007): base.py (adapter protocol), registry.py,
                            render.py (fallback rendering), service.py (deliver), inbound.py,
                            outbox.py, linking.py (codes, invites), setup.py, transport.py (the only HTTP
                            exit for channels), router.py (webhooks), simulator.py ("sim" adapter)
        whatsapp/           adapter.py (Meta Cloud API), templates.py
      api/                  main.py, deps.py (session and auth dependencies), auth.py (login routes),
                            schedule.py (week view, assignment, check-in, inbox), supervisor.py
                            (the summary, resolving site problems), timesheets.py (list, correct,
                            approve)
      i18n/                 strings.py (Finnish and English), <code>.py (one module per further
                            language: fil, ceb, ilo, hil, war, bcl, pam, pag)
      static/index.html     dev chat page
    migrations/             alembic.ini, env.py, versions/
    config/                 policies/ (Casbin model.conf, policy.csv), org/demo/ and org/ferinos/ (instructions, settings.yaml),
                            ollama/ (Modelfiles for local models, ADR 004)
    tests/                  unit tests; auth/ (login flows); evals/ (marker `evals`; intents.jsonl, intents_catalogue.yaml
                            and intents.py for intent classification; router_cases.py and
                            test_router_eval.py for the real-Jev router eval; sales_cases.py,
                            test_sales_cases.py (offline shape check) and
                            test_sales_supervisor_evals.py for the real-Jev sales decider eval;
                            test_sales_supervisor_scenarios.py runs the sales scenarios.yaml;
                            inventory_manager_cases.py, test_inventory_cases.py (offline shape
                            and scoring check) and test_inventory_manager_evals.py for the
                            real-Jev inventory decider eval; hr_officer_cases.py,
                            test_hr_cases.py (offline shape and scoring check) and
                            test_hr_officer_evals.py for the real-Jev hr decider eval;
                            <id>_cases.py and
                            test_<id>_evals.py from the scaffold)
  docs/                     spec, plan, brief, ADRs, questions, decisions, ideas, capabilities,
                            research/ (research notes and dated evaluation reports, ADR 012)
```

Files beyond the brief's layout, and why, are listed in docs/adr/001-stack.md, 005 and 010.
Add new folders only with a reason recorded in an ADR.
