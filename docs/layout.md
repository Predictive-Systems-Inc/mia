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
                            sales counts, targets and notes, stock events (data standard 1.5),
                            sales tenders, supplier orders, contracts, payslips and leave (1.6),
                            the kiosk incident kinds (1.7), customer orders (1.8), sales
                            (1.9: sessions, receipts, lines and payments, their services and
                            day_sales over a kiosk's one source; ADR 022),
                            geocoding (pluggable providers), orgconfig (organisation settings),
                            keys (master key, HKDF, scrypt, TOTP), auth (sessions, codes,
                            credentials, devices, clients; ADR 011), scheduling (recurrence,
                            visit generation, assignment rules, check-in, inbox), billing
                            (the monthly summary export), jev.py (one TypeSafe Jev request)
      templates/cleaning/   models (sites, checklists, checklist ticks), seed, importer (master data from YAML)
      templates/retail/     models (items with short codes, prices, bundle components and cost, dated
                            branch prices, branch hours, closed days as retail_closures), items
                            (dated prices per branch,
                            short codes), hours (opening hours helpers, closed days and the business
                            date), seed
                            (Ferino's demo)
      learning/             role skill data: generate, translate (the eval set by language), train, bakeoff
      agents/               base.py (manifest, guard, model factory, AgentSpec), registry.py
                            (every agent by id), stubs.py (roster agents not built yet),
                            decider.py (the shared Jev decider), scaffold.py and _template/
                            (`mia agent scaffold`: a new agent package, wired in)
        shift_supervisor/   manifest.yaml, job.md, prompts/, classifier.py,
                            scoring.py, cover.py (confirmation flow), alerts.py (missed
                            check-in and check-out, overtime, unstaffed visits, daily plan),
                            timesheets.py (drafts, corrections, approval, payroll rows),
                            rules.py (is_retail, the template switch), roster.py (pure: the
                            weekly pattern, shift ranges and days, swap checks), actions.py
                            and decider.py (Jev; the retail actions beside the cleaning ones),
                            tools.py (incl. incidents),
                            agent.py, turn.py (its chat turn and AgentSpec),
                            tests/scenarios.yaml (and scenarios_en.yaml)
        sales_supervisor/   manifest.yaml, job.md, prompts/, actions.py and decider.py (Jev),
                            tools.py, calc.py, due.py, replies.py, turn.py,
                            tests/scenarios.yaml (chat scenarios); its tables are core (1.5);
                            the chat till on a receipts kiosk: record, void, refund and read
                            receipts; report.py and report_model.py: report questions
                            (teach-Mia 4c)
        inventory_manager/  Inventory Manager: the mia agent scaffold shape (turn.py, actions.py, ...);
                            its tables are core (1.5, 1.6)
        hr_officer/         HR Officer: the mia agent scaffold shape (turn.py, actions.py, ...);
                            its tables are core (1.6)
        customer_service/   Customer Service: the scaffold shape plus models.py (three agent-owned
                            tables; its orders are core, 1.8), public.py (the customer turn
                            for unlinked senders, the 24-hour window, send_direct), actions.py
                            and decider.py (Jev, a customer side and a staff side), calc.py,
                            tools.py, replies.py
        branch_manager/     Branch Manager: the mia agent scaffold shape (turn.py, actions.py, ...)
                            plus models.py (experiments, strategies, tips, coaching), tips.py
                            (data only: the seeded tips, encouragement lines and pricing strategies),
                            experiments.py (pure: baseline, score, the strategy proposals and
                            guard rails) and calc.py (pure: tip rotation, nudge, best day,
                            pairing); its prices go through templates/retail/items.py
        bookkeeper/         Bookkeeper: the mia agent scaffold shape (turn.py, actions.py, ...)
                            plus models.py (cash counts, settlements, payouts, expenses,
                            deposits, the tax figure), calc.py (pure: matching with fees and
                            commissions, balances, profit), tax.py (the dated VAT and percentage
                            tax table) and words.py (the fixed lists, the amount, receipt, VAT,
                            period and bank readers); the four tables it reads from the HR
                            officer and the inventory manager are core (1.6)
        production_planner/ Production Planner: the mia agent scaffold shape (turn.py, actions.py, ...)
                            plus models.py (recipes, plans, batches, dispatches), forecast.py
                            (pure: the same-weekday forecast, demand, whole batches and the
                            split per kiosk), capacity.py (pure: free oven minutes and pieces
                            for a day) and words.py (the number, batch report and recipe
                            readers); the customer orders it counts are core (1.8)
        <role>/skill/       role.yaml, public.yaml, data/, reports/ (ADR 013)
      skills/               classifier runtime and per-turn routing (ADR 013)
      chat/                 blocks.py, service.py, router.py, channels.py (notifications, calls),
                            runs.py (live AG-UI runs: reconnect, catch-up, stop), replies.py
                            (stored replies), access.py (a person's agents), agent_router.py
                            (the Jev router, ADR 015), language.py (the reply language, ADR 016),
                            deferred.py (turns waiting while Jev is unreachable),
                            route_memory.py (what people chose when Mia asked),
                            phrases.py (the phrasebook: taught phrases and learned Did you mean
                            taps), features.py (feature requests), help_menu.py (what Mia can do)
      channels/             messaging channels (ADR 007): base.py (adapter protocol), registry.py,
                            render.py (fallback rendering), service.py (deliver), inbound.py,
                            outbox.py, linking.py (codes, invites), setup.py, transport.py (the only HTTP
                            exit for channels), router.py (webhooks), simulator.py ("sim" adapter)
        whatsapp/           adapter.py (Meta Cloud API), templates.py
      api/                  main.py, deps.py (session and auth dependencies), auth.py (login routes),
                            schedule.py (week view, assignment, check-in, inbox), supervisor.py
                            (the summary, resolving site problems), timesheets.py (list, correct,
                            approve), sim.py (the phones page routes, dev and loopback only)
      i18n/                 strings.py (Finnish and English), <code>.py (one module per further
                            language: fil, ceb, ilo, hil, war, bcl, pam, pag)
      static/index.html     dev chat page
      static/sim.html       phones on screen: one simulated phone per person (/sim, dev only)
    migrations/             alembic.ini, env.py, versions/
    config/                 policies/ (Casbin model.conf, policy.csv), org/demo/ and org/ferinos/ (instructions, settings.yaml),
                            ollama/ (Modelfiles for local models, ADR 004)
    tests/                  unit tests (test_data_standard_<n>.py pins each data standard change,
                            test_data_standard_1_9.py the sales operations tables;
                            test_sales_receipts.py the chat till, test_day_sales_reads.py the
                            other agents' receipts-day reads); auth/ (login flows); evals/ (marker `evals`; intents.jsonl, intents_catalogue.yaml
                            and intents.py for intent classification; cases/ (one CSV of test
                            messages per agent, <agent_id>.csv, and router.csv, with the shared
                            loader the <id>_cases.py modules build their cases with, and a
                            README of the columns); router_cases.py and
                            test_router_eval.py for the real-Jev router eval; sales_cases.py,
                            test_sales_cases.py (offline shape check) and
                            test_sales_supervisor_evals.py for the real-Jev sales decider eval;
                            test_sales_supervisor_scenarios.py runs the sales scenarios.yaml;
                            inventory_manager_cases.py, test_inventory_cases.py (offline shape
                            and scoring check) and test_inventory_manager_evals.py for the
                            real-Jev inventory decider eval; hr_officer_cases.py,
                            test_hr_cases.py (offline shape and scoring check) and
                            test_hr_officer_evals.py for the real-Jev hr decider eval;
                            customer_service_cases.py, test_customer_service_cases.py
                            (offline shape and scoring check) and
                            test_customer_service_evals.py for the real-Jev customer service
                            decider eval; bookkeeper_cases.py, test_bookkeeper_cases.py
                            and test_bookkeeper_evals.py for the bookkeeper's;
                            shift_retail_cases.py, test_shift_retail_cases.py and
                            test_shift_retail_evals.py for the retail shift supervisor's;
                            production_planner_cases.py, test_production_planner_cases.py and
                            test_production_planner_evals.py for the production planner's;
                            <id>_cases.py and
                            test_<id>_evals.py from the scaffold);
                            affected.py (the tests a change affects, from a reverse import
                            graph; ALL for shared foundations) and test_affected.py
  docs/                     spec, plan, brief, ADRs, questions, decisions, ideas, capabilities,
                            research/ (research notes and dated evaluation reports, ADR 012),
                            testing-ferinos.md (the local test and staff phone test runbook)
```

Files beyond the brief's layout, and why, are listed in docs/adr/001-stack.md, 005 and 010.
Add new folders only with a reason recorded in an ADR.
