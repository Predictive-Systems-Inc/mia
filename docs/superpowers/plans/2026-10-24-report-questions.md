# Report Questions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Goal:** a report question no existing read answers ("benta last week per item", "magkano gcash this month vs last month") is answered with figures computed by code: a hosted model fills a fixed report form or picks one clarifying question, code validates it, checks rbac, sums `day_sales` and words a text table; the answered form can be saved and the next identical message runs it with no model call. The owner's words (22 Oct): "we need a smart model to respond to this? cache the result... let agent collaborate and clarify what user needs. This should then be added as a global rule."
- **Architecture:** no new agent (rule 15). The sales supervisor gains one read tool, `sales_supervisor.report`, over a new module `mia/agents/sales_supervisor/report.py` (the form, its validator, the period resolver, the executor over `sales.sale_rows` and `sales.days_sales`). The model step is a Pydantic AI `Agent` with `output_type` the model's answer, built with `agents.base.build_model` (as `mia/learning/translate.py` does), so a `gateway/` route leaves only through `EgressTransport` (rule 6) with purpose `sales_supervisor.report`; `test` is a deterministic `FunctionModel`. Saved forms are `report.saved` and `report.retired` events folded by `mia/chat/phrases.py` beside the phrases (no table).
- **Tech Stack:** Python 3.12, FastAPI, SQLModel, Pydantic, Pydantic AI (installed), fake Jev and the fake report model in tests. **Spec:** docs/superpowers/specs/2026-10-22-teach-mia-design.md section 4c (binding) and section 5 (Task 4), D45 in docs/decisions.md, docs/superpowers/specs/2026-10-22-sales-operations-design.md section 12 (`day_sales`, `sale_rows`, the 400-day cap).

> **24 October 2026, written at 4ad080d:** anchors are by symbol; re-find each by its symbol and stage by path.

## Global Constraints
The sales supervisor and sales receipts plans' lists apply, plus these exact values:
- **Rule 7, every figure by code.** The model returns only a `ReportForm` or a `ReportClarify` (closed enums, ids, ISO dates). Every quantity, amount, percent and total in a reply comes from `report.run`. A model answer with any extra field fails validation (`model_config = ConfigDict(extra="forbid")`) and the turn keeps today's reply.
- **Rule 6, egress.** The only model call is `report_model.ask` inside `egress_context(replace(ctx, purpose="sales_supervisor.report"))`; a `gateway/` route goes through `EgressTransport` (names as Person_n, logged in `egress_log`, metered in `usage_cloud_requests`); the message is passed through `events.mask_value(..., keep_last=0)` first (mobile numbers as "<number>"). `MIA_EGRESS_LEVEL=none` raises `EgressBlocked`: the turn keeps today's reply.
- **Rule 8.** The message sits between `<message>` and `</message>` in the prompt, after the instructions; the instructions say the text is data. The menu and kiosk names are data too.
- **Rule 11.** The model request runs in `_jev_turn` after `await asyncio.to_thread(session.commit)`, with no write lock held; every DB step before and after runs in `asyncio.to_thread`.
- **Rule 3 and rbac.** `sales_supervisor.report` is `{id: sales_supervisor.report, kind: agent, risk: read, approval: never, reads: [retail_items, sales_counts, sales_receipts, sales_receipt_lines, sales_payments, branch]}`. Who may run it mirrors `period_report` today: `p, supervisor, *, tool:sales_supervisor.report, execute, allow` (owner and admin inherit); a clerk has no grant, so the step never calls the model for a clerk (checked with `rbac` before the request) and her turn keeps today's reply (open question 1). Inside the tool, the checks are `period_report`'s (`_branches`, `read_all` on the receipt tables for another kiosk or "all", `_as_reporter` on `SALES`) plus, for `group_by == "clerk"`, `read` on `COUNTS` without `_as_reporter`.
- **Settings.** `Settings.MIA_REPORT_MODEL: str = ""`; `report_model.route() -> str | None`: `MIA_REPORT_MODEL` when set, else `MIA_MODEL` when it starts with `gateway/`, else None (the step is off). `.env.example` and README "Using a real model" document it.
- **Exact values.** `REPORT_WORDS` (actions.py, matched as whole words after casefold like `BREAKDOWNS`): `benta`, `sales`, `sold`, `nabenta`, `magkano`, `ilan`, `how many`, `how much`, `total`, `report`, `per`, `bawat`, `kada`, `compare`, `vs`. Top lines `replies.TOP` (10) then `sales.period.more`. Period ids: `decider`'s (`today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, `mon` to `sun`), resolved by `actions._period`. Ferino's tests on `RS_TODAY = dt.date(2026, 10, 28)` (a Wednesday; `last_week` is 19 to 25 October).
- **No new dependency, no data standard change.** No table or column; the new events are `report.saved`, `report.retired` (Task 3) and, in Task 4's own plan, `intent.unrecognised`, `phrase.proposed`. Agent role grants: none new (the manifest already reads the four tables). **Stop rule:** a task that needs a table, a column or a human right beyond the policy line above stops and reports.
- **Ten languages** (`i18n.SUPPORTED`): every new key in en and fi, drafted in fil, ceb, ilo, hil, war, bcl, pam and pag, placeholders identical; tests assert through `t(...)` in English first (D44). Ids from `MANIFEST.id`; no em-dashes.
- **Tests run offline:** `MIA_MODEL=test`, `MIA_REPORT_MODEL=test` set by the tests that need the step (monkeypatched settings), model requests blocked; the gateway path is tested with a mock transport under `models.override_allow_model_requests(True)`, as the existing gateway tests do.
- **Checks per task:** `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && uv run pytest`; one commit per task, staged by path; `gh pr checks` after a push.

## Review Focus (pinned)
1. **No figure from the model:** a fake that answers with a figure in any field fails validation and the reply has no figure from it (Task 2, `test_a_model_answer_with_extra_fields_is_ignored`); every reply figure equals `period_report`'s for the same period (Task 1, `test_report_sums_equal_period_report`).
2. **Rbac before the model:** a clerk's report question makes no model request and no egress row (Task 3, `test_a_clerks_report_question_calls_no_model`); a supervisor's `kiosk` grouping is refused, an owner's runs (Task 1, `test_kiosk_grouping_needs_read_all`); `clerk` grouping needs `read` (Task 1, `test_clerk_grouping_needs_read`).
3. **Egress:** the request carries purpose `sales_supervisor.report`, no person name and no mobile number (Task 2, `test_the_report_request_is_pseudonymised_and_logged`); egress `none` and an unset route keep today's reply (Task 3, `test_the_step_is_off_without_a_route`, `test_egress_none_keeps_todays_reply`).
4. **Bad forms:** over 400 days, end before start, a date after today, tender with pieces or with item or clerk grouping, an unknown item or kiosk id: refused, today's rephrase, `decision.failed` (Task 1, `test_bad_forms_are_refused`).
5. **Clarify buttons by code:** the options are the readable kiosks, the named periods or the two measures, never the model's words; one clarify per message (Task 2, `test_a_clarify_answer_gets_code_built_buttons`; Task 3, `test_a_second_clarify_is_a_rephrase`).
6. **Saved forms:** only a named period is saveable; the next identical key runs with no Jev and no model request and rbac is checked for the new asker (Task 3, `test_a_saved_report_runs_with_no_model_call`, `test_a_saved_report_checks_the_new_askers_rights`, `test_explicit_dates_offer_no_save`).
7. Counts messages and existing reads unchanged: "3 ube 2 classic cash" never reaches the step; the existing sales tests pass unedited.

### Task 1: The form, the validator and the executor (no model)
- **Files:** `node/mia/agents/sales_supervisor/report.py` (new); `node/mia/agents/sales_supervisor/tools.py` (`ReportInput`, `report`); `node/mia/agents/sales_supervisor/replies.py` (`report_text`); `node/mia/agents/sales_supervisor/manifest.yaml` (grant `tool:sales_supervisor.report:execute`, the tool row above); `node/config/policies/policy.csv` (the supervisor line beside `period_report`); `node/mia/i18n/strings.py` and the eight modules; tests `node/tests/test_sales_report.py` (new).
- **Interfaces (produced):**
  - `report.Measure = Literal["pieces", "amount"]`; `report.GroupBy = Literal["none", "item", "day", "weekday", "kiosk", "tender", "clerk"]`; `report.Compare = Literal["none", "previous_period", "same_period_last_year"]`.
  - `report.ReportForm(BaseModel, extra="forbid")`: `measure: Measure`, `group_by: GroupBy = "none"`, `period: str | None = None` (a period id), `start: dt.date | None = None`, `end: dt.date | None = None`, `items: list[str] = []`, `kiosks: list[str] = []`, `tenders: list[Tender] = []`, `compare_to: Compare = "none"`. Exactly one of `period` or both dates (a model validator).
  - `report.resolve(form, today: dt.date, lang: str) -> tuple[dt.date, dt.date]`: `actions._period` for a period id, else the dates; raises `report.ReportError(code)` with codes `period` (unknown id, neither or both), `order` (end before start), `future` (end after today), `range` (more than `sales.MAX_SALES_DAYS` days, compared range included), `combo` (a tender grouping or filter with `pieces`, or with `item` or `clerk` grouping).
  - `report.compared(start, end, compare: Compare) -> tuple[dt.date, dt.date] | None`: the same length just before, or the same dates a year earlier (29 February to 28 February).
  - `report.Line(name: str, quantity: int, amount: int, before: int | None)`; `report.Result(head_measure: Measure, group_by: GroupBy, start, end, lines: list[Line], total: int, total_before: int | None, currency: str)`.
  - `report.run(session, branches: list[Branch], form, start, end, names: dict[str, RetailItem], clerks: dict[str, str]) -> Result`. Unchecked (the tool checks). Pieces and amounts from `sales.sale_rows(session, ids, start, end)` filtered by `items`; `tender` grouping or a tender filter from `sales.days_sales(...)[d].by_tender` per branch; groups keyed by item id (menu order with no compare, else largest first), ISO date (date order), weekday 0 to 6 (Monday first), branch name, tender (`TENDERS` order), clerk id (name from `clerks`, largest first); `before` and `total_before` from the same run over `compared(...)`. A group in the compared range only is shown with 0 now.
  - `tools.ReportInput(form: report.ReportForm)`; `tools.ReportOutput(result: report.Result)`; `tools.report(deps, args, tool_call_id) -> ReportOutput`: the rbac of the Global Constraints, `resolve` (a `ReportError` becomes `LookupError(code)`, so `call_tool` answers `invalid` and `range` maps to `sales.refused.range` in `_refusal`), unknown item or kiosk ids raise `LookupError("form")`, then `run`.
  - `replies.report_text(result, lang) -> list[Block]`: one `TextBlock`: `sales.report.head` then `sales.report.line` per line (top `TOP`, then `sales.period.more`), with a compare `sales.report.line_vs` and `sales.report.total_vs` (percent from `calc.compare`).
  - Keys (en): `sales.report.head` "{measure}, {start} to {end}{by}: {total}"; `sales.report.by` " per {group}"; `sales.report.measure.pieces` "Pieces sold"; `sales.report.measure.amount` "Sales"; `sales.report.group.<item|day|weekday|kiosk|tender|clerk>` "item", "day", "weekday", "kiosk", "payment", "clerk"; `sales.report.line` "{name}: {value}"; `sales.report.line_vs` "{name}: {value} ({percent}% vs {before})"; `sales.report.total_vs` "Total {total} ({percent}% vs {before})".
- [ ] Failing tests first (`node/tests/test_sales_report.py`; `ss_deps` is `test_sales_tools.deps_for` with `today=RS_TODAY`, owner and supervisor from `rs`):
```python
def test_bad_forms_are_refused() -> None:
    bad = [
        ReportForm(measure="pieces", start=dt.date(2025, 1, 1), end=RS_TODAY),  # range
        ReportForm(measure="amount", start=RS_TODAY, end=RS_TODAY - dt.timedelta(days=1)),  # order
        ReportForm(measure="amount", start=RS_TODAY, end=RS_TODAY + dt.timedelta(days=1)),  # future
        ReportForm(measure="pieces", period="last_week", group_by="tender"),  # combo
        ReportForm(measure="amount", period="last_week", group_by="item", tenders=["gcash"]),  # combo
        ReportForm(measure="amount", period="next_year"),  # period
    ]
    codes = [_code(lambda f=f: resolve(f, RS_TODAY, "en")) for f in bad]
    assert codes == ["range", "order", "future", "combo", "combo", "period"]
    with pytest.raises(ValidationError):
        ReportForm.model_validate({"measure": "amount", "period": "last_week", "total": 5})
def test_compared_ranges() -> None:
    assert compared(dt.date(2026, 10, 19), dt.date(2026, 10, 25), "previous_period") == (dt.date(2026, 10, 12), dt.date(2026, 10, 18))
    assert compared(dt.date(2028, 2, 29), dt.date(2028, 2, 29), "same_period_last_year") == (dt.date(2027, 2, 28), dt.date(2027, 2, 28))
def test_report_sums_equal_period_report(session, rs) -> None:  # supervisor, last_week, per item: lines == period_report breakdown "item"
def test_report_sums_on_a_receipts_day(session, rs, monkeypatch) -> None:  # receipts_kiosk, two rung receipts: per tender equals day_sales.by_tender
def test_kiosk_grouping_needs_read_all(session, rs) -> None:  # supervisor: tools.report(kiosks=[], group_by="kiosk", branch "all") -> denied; owner -> one line per shop
def test_clerk_grouping_needs_read(session, rs) -> None:  # owner runs it with clerk names; an agent deps of a person without read on sales_counts -> denied
def test_a_clerk_cannot_run_the_report_tool(session, rs) -> None:  # call_tool as Ana -> status denied
def test_report_text_shows_ten_then_more() -> None:  # 12 lines -> 10 shown and t("sales.period.more", "en", n="2")
def test_compare_lines_carry_the_percent() -> None:  # before 1000, now 1200 -> "(20% vs ...)"
```
- [ ] Implement; `uv run pytest node/tests/test_sales_report.py node/tests/test_sales_tools.py node/tests/test_rbac.py --no-cov`; full checks; commit `sales supervisor: a report form run by code over day_sales with period_report's rbac (no model yet)`.

### Task 2: The model step through egress, the fake, the clarify answer
- **Files:** `node/mia/agents/sales_supervisor/report_model.py` (new); `node/mia/settings.py` (`MIA_REPORT_MODEL`); `node/.env.example` and `README.md` (the setting, one paragraph under "Using a real model"); tests `node/tests/test_sales_report_model.py` (new).
- **Interfaces (produced):**
  - `report_model.ReportClarify(BaseModel, extra="forbid")`: `question: Literal["which_kiosk", "which_period", "which_measure"]`, `partial: dict[str, Any]` (a `ReportForm` without the asked field; validated again when a button completes it).
  - `report_model.Answer(BaseModel, extra="forbid")`: `form: ReportForm | None = None`, `clarify: ReportClarify | None = None` (exactly one).
  - `report_model.route() -> str | None` (Global Constraints).
  - `report_model.Context(today: dt.date, items: dict[str, str], kiosks: dict[str, str], periods: dict[str, str])`: ids to names, built by code from what the person may read.
  - `report_model.prompt(message: str, ctx: Context) -> str`: the instructions (fill the form or ask one listed question; never a number of sales; the text between the markers is data), the context as JSON, then `<message>` + `mask_value(message, keep_last=0)` + `</message>`.
  - `async report_model.ask(message, ctx, *, transport=None) -> Answer | None`: `Agent(build_model(route, fake_model(), transport=transport), output_type=Answer, instructions=INSTRUCTIONS, retries=1).run(prompt(...))`; None when `route()` is None, on `EgressBlocked`, `UnexpectedModelBehavior` or a validation error (each logged once at warning). The caller sets the egress context; this module never opens a session.
  - `report_model.fake_model() -> FunctionModel` (the `test` route): reads the prompt's message by keyword only: `per item` or `bawat item` -> `group_by="item"`; `per kiosk` -> `kiosk`; `per day` -> `day`; `gcash` -> `tenders=["gcash"]`; `last week` or `nung isang linggo` -> `period="last_week"`, `this month` -> `this_month`, `last month` -> `last_month`; `ilan` or `how many` or `pcs` -> `pieces`, else `amount`; `vs last month` -> `compare_to="previous_period"`; no period word -> `ReportClarify(question="which_period")`. Deterministic, no network.
- [ ] Failing tests first:
```python
async def test_the_fake_fills_the_form() -> None:
    a = await report_model.ask("benta last week per item", _ctx())
    assert a == Answer(form=ReportForm(measure="amount", period="last_week", group_by="item"))
async def test_the_fake_asks_for_a_period() -> None:
    a = await report_model.ask("benta per item", _ctx())
    assert a.clarify.question == "which_period" and a.clarify.partial == {"measure": "amount", "group_by": "item"}
async def test_no_route_means_no_request(monkeypatch) -> None:  # MIA_REPORT_MODEL "" and MIA_MODEL "test" -> route() None, ask() None
def test_route_falls_back_to_a_gateway_mia_model(monkeypatch) -> None:  # MIA_MODEL "gateway/x" -> "gateway/x"; "local/y" -> None
async def test_the_report_request_is_pseudonymised_and_logged(session, rs, monkeypatch) -> None:
    # MIA_REPORT_MODEL "gateway/report", httpx.MockTransport answering a valid Answer, override_allow_model_requests(True),
    # message "Ana, benta last week per item, call 09171234567": one egress_log row, purpose "sales_supervisor.report";
    # the request body has "Person_" and "<number>", no "Ana", no "09171234567"; one usage_cloud_requests row
async def test_a_model_answer_with_extra_fields_is_ignored(...) -> None:  # the mock answers form + {"total": 999} -> None
async def test_egress_none_blocks_the_request(...) -> None:  # MIA_EGRESS_LEVEL none -> None, no egress_log row
```
- [ ] Implement; `uv run pytest node/tests/test_sales_report_model.py --no-cov`; full checks; commit `sales supervisor: report questions go to a hosted model through egress for a form or one clarifying question (fake for tests)`.

### Task 3: The chat wiring, the reply, save and reuse
- **Files:** `node/mia/agents/sales_supervisor/actions.py` (`REPORT_WORDS`, `report_like`); `node/mia/agents/sales_supervisor/turn.py` (`_jev_turn`, `_act`, `_did_you_mean`, `_report_step`, `_report_reply`); `node/mia/chat/phrases.py` (`REPORT_SAVED`, `REPORT_RETIRED` in `ALL`, `save_report`, `retire_report`, `saved_report`, the fold, `export_rows`, `import_rows`); `node/mia/chat/router.py` or wherever the taught-phrase exact-key route sits (a saved report key routes to the sales supervisor as a taught phrase does); `node/mia/api/sim.py` and the Phrases drawer (lists saved reports, Retire for owner or admin); `node/tests/evals/cases/sales_supervisor_reports.csv` (new, header only) and a test that validates every row; strings; `docs/layout.md` (the sales_supervisor line gains "report.py and report_model.py: report questions (teach-Mia 4c)"); tests `node/tests/test_sales_report_chat.py` (new), `node/tests/test_phrases.py`.
- **Interfaces (produced):**
  - `actions.report_like(message: str, q: Query) -> bool`: a `REPORT_WORDS` phrase as whole words and not `q.counts_only`.
  - `turn._wants_report(deps, decision, query_or_text) -> str | None`: the message text when the step should run: `route()` set, `rbac` allows `tool:sales_supervisor.report:execute` for the person, and either the decision is `clarify` with no offerable alternative or `reply_only` of kind `other` or `capabilities` on a `report_like` message, or the decision is a tapped Something else (`Decision(action="clarify", args={"asked": <message id>})`, `_did_you_mean` now stores the asked message id in its Something else option) whose message is `report_like`.
  - `_jev_turn`: after the decision, `text = await asyncio.to_thread(_wants_report, ...)`; when set, `await asyncio.to_thread(session.commit)`, then inside `egress_context(replace(ctx, purpose=f"{MANIFEST.id}.report"))` `answer = await report_model.ask(text, rctx)`; `await asyncio.to_thread(_report_reply, session, deps, thread, answer, text)`; None keeps `_act`'s reply.
  - Internal action `REPORT = "report"`, never in `actions.ACTIONS` (Jev never sees it, never teachable): `_act` handles `decision.action == REPORT` first, validating `decision.args["form"]` with `ReportInput` and calling the tool through `call_tool` (the guard, rule 4).
  - `_report_reply`: a form runs as `REPORT`; the reply is `replies.report_text` plus, when `form.period` is set and the message key has a letter, a `QuickRepliesBlock` with `sales.report.save` whose option is `{"action": "report_save", "args": {"form": ..., "message_id": ...}}`; a clarify answer asks with `_ask` and code-built options (`which_kiosk`: the readable branches by name plus `sales.report.all_kiosks` for an owner or admin; `which_period`: the period ids labelled `sales.report.period.<id>`; `which_measure`: `sales.report.measure.pieces` and `.amount`), each option `Decision(action=REPORT, args={"form": completed})`; a second clarify on the same message id gets `clarify.rephrase`.
  - `phrases.save_report(session, actor, branch_id, message: Message, form: dict) -> Event`: emits `report.saved` `{"key": key_of(message.text), "agent_id": MANIFEST.id, "form": form, "message_id": message.id, "person_id": actor.person_id}`, entity `("report", key)`; refuses a key without a letter. `phrases.retire_report(...)` emits `report.retired`. `phrases.saved_report(session, branch_id, key) -> dict | None` (the latest unretired form). `version()` counts both.
  - `_query`: after the tapped, injection and slot steps and before Jev, `saved_report(...)` for the message key returns `Decision(action=REPORT, args={"form": form})` (no Jev request, no model request).
  - Export: `export_rows` also writes `node/tests/evals/cases/sales_supervisor_reports.csv` (`text,key,form`), `import_rows` replays it as `report.saved` by the system actor.
  - Keys (en): `sales.report.save` "Save as a report"; `sales.report.saved` "Saved. Ask the same way and I will answer it at once."; `sales.report.ask.which_kiosk` "Which kiosk?"; `sales.report.ask.which_period` "For which period?"; `sales.report.ask.which_measure` "Pieces or sales amount?"; `sales.report.all_kiosks` "All kiosks"; `sales.report.period.<id>` for the six named periods (weekdays reuse the day names).
- [ ] Failing tests first (`node/tests/test_sales_report_chat.py`; fake Jev as `test_sales_chat.jev_on`, `MIA_REPORT_MODEL=test`, English, the owner unless named):
```python
def test_the_step_is_off_without_a_route(...) -> None:  # MIA_REPORT_MODEL "" and MIA_MODEL "test": Jev clarify with no alternative on "benta last week per item" -> t("clarify.rephrase", "en")
def test_egress_none_keeps_todays_reply(...) -> None:  # MIA_REPORT_MODEL "gateway/x", MIA_EGRESS_LEVEL none -> rephrase, no egress_log row
def test_a_report_question_gets_the_table(...) -> None:  # reply equals replies.report_text(tools.report(... last_week, item ...)), plus the Save button
def test_a_clerks_report_question_calls_no_model(...) -> None:  # Ana: rephrase, no egress_log row with purpose "sales_supervisor.report"
def test_a_counts_message_never_reaches_the_step(...) -> None:  # "3 ube 2 classic cash" with Jev clarify -> today's reply, no model request
def test_something_else_after_a_report_like_message_runs_the_step(...) -> None:  # Did you mean (sales_today, sales_period) -> tap Something else -> the table
def test_a_clarify_answer_gets_code_built_buttons(...) -> None:  # "benta per item" -> t("sales.report.ask.which_period") with the period labels; tapping last week -> the table
def test_a_second_clarify_is_a_rephrase(...) -> None
def test_a_saved_report_runs_with_no_model_call(...) -> None:  # tap Save -> report.saved; "Benta last week per item!" again -> same table, no new egress_log row, no Jev request (fake Jev asserts not called)
def test_a_saved_report_checks_the_new_askers_rights(...) -> None:  # saved by the owner with group_by kiosk; the supervisor asks the same -> t("denied.generic", "en")
def test_explicit_dates_offer_no_save(...) -> None:  # a form with start and end -> no Save button
def test_saved_reports_export_and_import(...) -> None:  # tmp folder round trip, version counts report.saved
```
- [ ] Implement; `uv run pytest node/tests/test_sales_report_chat.py node/tests/test_phrases.py node/tests/test_sales_chat.py node/tests/evals/test_sales_cases.py --no-cov`; full checks; commit `sales supervisor: report questions answered in the chat with a save button; a saved form runs again with no model call (teach-Mia 4c)`.

### Task 4: Phase 2, the nightly phrase proposals (a separate later plan)
Large enough for its own plan (the tick's due work, a new approval type and its app card, the backlog export), written after Tasks 1 to 3 ship and the owner has seen report questions on real phones. Scope from spec section 5, recorded here so nothing is lost:
- **Files (expected):** `node/mia/chat/phrases.py` (`intent.unrecognised`, `phrase.proposed`, `propose`, `accept_proposal`); `node/mia/chat/proposals.py` or a due step of the node's tick (the nightly run per branch after closing); the agents' rephrase and Something else paths (write `intent.unrecognised` with the message id); `node/mia/core/approvals.py` callers (approval type `phrase.proposal`, approvers `[admin, owner]`, channel any, risk none); the app's approvals inbox card; strings; tests `node/tests/test_phrase_proposals.py`.
- **Interfaces (expected):** `phrases.unrecognised(session, branch_id, day) -> list[Message]` (distinct keys, at most 50, keys in the phrasebook skipped); `async proposals.ask(messages, teachable: dict[str, dict[str, str]]) -> list[Proposal]` through `report_model`'s route with purpose `phrases.propose`; `Proposal(key, agent_id, verdict: action id | "report" | "capability_gap" | "none")`; code drops any action not in `phrases.teachable(agent_id)`.
- **Tests (expected, negative first):** a money action proposed is dropped; nothing is taught without an approval; a declined proposal writes no phrase; the egress row carries purpose `phrases.propose` and no name; off with no route or egress `none`.
- **Commit (expected):** `teach Mia phase 2: nightly phrase proposals through the hosted model, approved by the owner or an admin`.

## Open questions (for docs/questions.md; the plan runs on the assumptions)
1. Clerks and report questions: a clerk cannot run `period_report` today (only supervisors, admins and owners hold the tool). Assumed: the same for `report`, so a clerk's report question keeps today's reply and costs nothing. Should a clerk get reports of her own kiosk?
2. Which hosted route (a small fast model on the Better Labs gateway or OpenRouter) and a monthly cost cap. Assumed: none configured, the step stays off until `MIA_REPORT_MODEL` or a `gateway/` `MIA_MODEL` is set; no cap in code (usage is metered in `usage_cloud_requests`).
3. Who may save a report: assumed anyone who got the answer at that branch (it only reads; rbac is checked per run); owners and admins retire.

## Self-review
- **Spec coverage:** the trigger (4c "When the step runs"; Task 3), what leaves the node (Task 2), the form and the combinations refused (Task 1), the clarify list with buttons by code (Tasks 2 and 3), rbac as today (Tasks 1 and 3), the reply table top 10 (Task 1), save and reuse with export and import (Task 3), the model setting and the fake (Task 2), phase 2 (Task 4, its own plan).
- **Placeholders:** the fil and seven draft wordings are written at implementation as drafts; the router file in Task 3 is named by where the taught-phrase route sits (re-find by `phrasebook(`).
- **Type consistency:** `ReportForm` is the tool input, the model output and the saved form; `Tender` and `TENDERS` from `core.models`; dates are `dt.date`; money is `int` minor units with `currency`.
