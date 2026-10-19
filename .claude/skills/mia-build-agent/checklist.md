# Review checklist

What every review asks, from the findings parts 1 and 2 kept producing. Each line has the shape
"claim: source file (symbol), test file::test name", the proof in the built agents. A line with
no test says so. Pin each line to the plan task that owns it.

## Rule 15: names
- No bare agent id literal; ids from `MANIFEST.id`, label keys built from it: `mia/agents/sales_supervisor/actions.py` (`ACTIONS`), `node/tests/test_architecture.py::test_no_module_spells_an_agent_id`.

## Rules 8 and 6: data, not instructions
- The message and any list of its parts go to Jev as state, pseudonymised (lists item by item): `mia/agents/decider.py` (`pseudonymised`), `node/tests/test_jev_decider.py::test_pseudonymised_covers_lists_of_strings_in_the_state`.
- Nothing from the message in instructions: `mia/agents/sales_supervisor/actions.py`, `node/tests/test_sales_actions.py::test_item_instructions_carry_no_message_text`.
- Requests only inside the egress context: `mia/agents/decider.py` (`decide`), `node/tests/test_jev_decider.py::test_decide_goes_through_egress`.
- A message is data, an injected instruction is not followed: `mia/agents/sales_supervisor/turn.py`, `node/tests/test_sales_chat.py::test_injection_is_data`.

## Rule 7: code calculates
- Every number computed by code: `mia/agents/sales_supervisor/calc.py`, `node/tests/test_sales_calc.py::test_month_share_rounds_half_up`.
- Money typed in major units is converted once to minor units: `mia/agents/sales_supervisor/decider.py` (`_minor`), `node/tests/test_sales_actions.py::test_set_target_amount_from_total_and_periods`.
- Dates from the branch's local clock, never `now.date()` in UTC: `mia/templates/retail/hours.py` (`business_date`), `node/tests/test_sales_calc.py::test_business_date_uses_the_branch_time_zone`.

## Rule 4: permissions
- Branch scoping through casbin (`read_all`, `write_all`): `mia/agents/sales_supervisor/tools.py` (`_branch`), `node/config/policies/policy.csv`, `node/tests/test_sales_tools.py::test_a_clerk_reads_only_their_branch`.
- Every read and write `_check`ed; a denial is visible as an event or a `tool.called` refusal: `mia/agents/sales_supervisor/tools.py` (`_check`), `node/tests/test_sales_tools.py::test_a_supervisor_reading_another_branch_is_an_rbac_deny`.
- `read_own` gates by role only, so say so where it is used: `node/config/policies/policy.csv`, `node/tests/test_sales_tools.py::test_call_tool_refuses_a_clerk_the_report`.

## Rules 11 and 12: transactions and threads
- Commit before the Jev await: `mia/agents/sales_supervisor/turn.py` (`_jev_turn`); no dedicated test, the reviewer reads the order.
- Sync DB work in threads, one Session per thread: `mia/agents/sales_supervisor/turn.py` (`asyncio.to_thread`); no dedicated test for the turn, the reviewer reads it (`node/tests/test_egress.py::test_egress_db_work_is_off_the_event_loop` covers egress's own DB work only).
- Per-branch commits in due work: `mia/agents/shift_supervisor/alerts.py` (`_each_branch`); no dedicated test, the reviewer reads it.

## Taps
- A button value is a stored decision, validated against the agent's own ACTIONS: `mia/agents/sales_supervisor/turn.py` (`_tapped`), `node/tests/test_sales_chat.py::test_a_tapped_decision_of_another_agent_asks_to_rephrase`.
- Stale after a notification: `mia/chat/service.py` (`_route_tapped`, `_last_mia`), `node/tests/test_agent_router.py::test_a_notification_after_the_route_question_makes_its_buttons_stale`.
- Never replayed across a date: `mia/agents/sales_supervisor/turn.py` (`_tapped`, the asked-today check), `node/tests/test_jev_chat.py::test_a_clarify_button_from_another_day_goes_to_jev`.

## Due work
- Windows as datetimes that may cross midnight: `mia/templates/retail/hours.py` (`window_end`), `node/tests/test_sales_due.py::test_a_late_closing_reports_after_midnight_under_its_own_date`.
- Business date from the closing's day: `mia/templates/retail/hours.py` (`after_close`), `node/tests/test_sales_due.py::test_after_close_window_ends_at_the_next_opening`.
- Markers per branch and date, written with the send: `mia/agents/sales_supervisor/due.py` (`_branch_due`), `node/tests/test_sales_due.py::test_reminder_once_per_branch_and_day`.
- End-of-shift messages urgent, reminders and morning messages not: `mia/agents/sales_supervisor/due.py` (`_send`), `node/tests/test_sales_due.py::test_end_of_shift_messages_are_not_held_by_quiet_hours`.
- Reminders wait for quiet hours: `mia/agents/sales_supervisor/due.py`, `node/tests/test_sales_due.py::test_reminder_waits_for_quiet_hours`.
- Nothing sent when there is nothing to say: `mia/agents/sales_supervisor/due.py` (`_morning_text`), `node/tests/test_sales_due.py::test_morning_with_neither_yesterday_nor_a_target_says_nothing`.

## Business dates
- A late count is yesterday's only before opening and within two hours of a late close, never ask: `mia/templates/retail/hours.py` (`business_date`), `node/tests/test_sales_calc.py::test_just_after_midnight_after_a_late_closing_is_yesterday`.

## Parsing
- Both orientations scored by menu tokens: `mia/agents/parsing.py` (`pre_parse`), `node/tests/test_parsing.py::test_number_then_words_and_words_then_number`.
- Negation is a correction: the negation drops the next number and makes the message a correction by rule: `mia/agents/parsing.py` (`was_corrected`), `node/tests/test_parsing.py::test_a_negation_drops_the_old_number`, `node/tests/test_sales_chat.py::test_a_negation_correction_is_a_correction_even_when_jev_says_report`.
- Leading stray words dropped: `mia/agents/parsing.py`, `node/tests/test_parsing.py::test_a_leading_verb_is_not_an_item`.
- Currency symbols stripped: `mia/agents/parsing.py`, `node/tests/test_parsing.py::test_currency_symbols_are_stripped`.
- A clock time with a space ("3 pm", "alas 2") is no count group: `mia/agents/parsing.py` (`strip_times`), `node/tests/test_parsing.py::test_times_with_a_space_are_not_count_groups`.

## Harvest and learning
- Sensitive skip depends on an active role model: `mia/learning/harvest.py` (`_sensitive`), `node/tests/learning/test_harvest.py::test_route_taps_on_sensitive_or_injected_messages_are_not_harvested`.
- Records are pending review (D27): `mia/learning/harvest.py`, `node/tests/learning/test_harvest.py::test_clarified_choice_becomes_a_pending_pseudonymised_candidate`.

## i18n
- Every key in ten languages through the coverage test: `node/mia/i18n/strings.py`, `node/tests/test_i18n_languages.py::test_every_new_key_exists_in_every_language`.
- Placeholders identical across languages: `node/mia/i18n/strings.py`, `node/tests/test_i18n_variants.py::test_variants_share_their_placeholders_across_languages`.
- Filipino (fil), never Tagalog, in labels, comments, docs and cases: `node/mia/i18n/fil.py`, `node/tests/evals/test_router_cases.py::test_no_case_names_tagalog`.
- Tests assert through `t(...)`: `mia/agents/sales_supervisor/replies.py`, `node/tests/test_sales_chat.py::test_greeting_is_answered_in_filipino`.

## Evals
- A fresh gate half per run, split by seed, ten cases per language, scenario and half: `node/tests/evals/sales_cases.py`, `node/tests/evals/test_sales_cases.py::test_ten_cases_per_language_scenario_and_half`.
- No text in both halves: `node/tests/evals/router_cases.py`, `node/tests/evals/test_router_cases.py::test_no_text_appears_in_both_halves`.
- The router shape test skips an id in `PENDING`, so the gates step empties it: `node/tests/evals/router_cases.py` (`PENDING`), `node/tests/evals/test_router_cases.py::test_every_gated_language_covers_every_agent_and_group`.
- The raw file named by local time, never overwritten: `node/tests/evals/test_sales_supervisor_evals.py` (`_report_path`), `node/tests/evals/test_router_cases.py::test_the_raw_report_is_named_by_local_minute_and_never_overwritten`.
- The gate bar is Q40: `node/tests/evals/gate.py` (`gate_failures`), `node/tests/evals/test_router_cases.py::test_the_gate_is_the_q40_bar`.
- The report in the research shape with the gate stated as it is, numbers recomputed from the raw file: `docs/research/*.md`; no test, the reviewer recomputes.

## Tests
- Through `run_turn` with the fake Jev: `node/tests/jev_fake.py`, `node/tests/test_sales_chat.py::test_a_count_is_recorded_and_echoed`.
- Negative tests for permissions: `node/tests/test_sales_tools.py::test_a_clerk_cannot_set_a_target`.
- Negative tests for egress: `node/tests/test_architecture.py::test_no_provider_sdk_outside_egress_and_model_factory`.
- The plan's Review Focus list pinned to tasks, each with a named test: `docs/superpowers/plans/2026-10-19-sales-supervisor.md`.

## Pay, leave and seeded money
- Pay and leave stay off the chain on the whole chat path: a `run_turn` test asserts that no amount, minute total or leave kind appears in any event (chat_messages.created, decision.made, decision.clarify_asked): `node/mia/chat/replies.py` (`_store`), `node/tests/test_hr_officer_chat.py::test_pay_and_leave_stay_off_the_chain_through_chat`.
- Seeded pay or money rows come from the same pure functions as the live path: `node/mia/templates/retail/seed.py` (`calc.cutoff_pay`), `node/tests/test_hr_officer_chat.py::test_contributions_come_from_the_last_payslip`.
- A computed payslip never nets negative: `node/mia/agents/hr_officer/ph.py` (`payslip`), `node/tests/test_hr_ph.py::test_one_approved_day_never_nets_below_zero`.
- Every pay rule a reply promises (holiday pay when not working, paid leave) is paid by the payslip, or the reply and the spec say it is not: `node/mia/agents/hr_officer/calendar.py` (`unworked_regular_holidays`), `node/tests/test_hr_calc.py::test_an_unworked_regular_holiday_pays_when_the_day_before_was_worked`.
- The plan's Review Focus test names exist (a grep in the reviewer pass); a renamed test gets a dated note at the top of the plan: `docs/superpowers/plans/2026-10-19-hr-officer.md`; no test, the reviewer greps.

## Public senders (customer_service, whole-branch review 20 Oct 2026)
- Exception text never reaches an event on a public path (SQL parameters carry the row); the inbound failure carries the class name only, and a read-then-insert keyed by an outside address takes the write lock first: `mia/channels/inbound.py` (`handle_inbound`, `_fail`), `mia/agents/customer_service/public.py` (`_arrive`), `node/tests/channels/test_customer_service.py::test_a_failed_customer_step_writes_the_exception_class_only`, `::test_two_first_messages_at_once_make_one_customer`.
- Payload digests on the chain are keyed (HMAC), never a plain hash of a body that holds an address: `mia/channels/outbox.py` (`_digest`), `node/tests/channels/test_outbox.py::test_the_payload_hash_is_keyed_never_a_plain_sha256`.
- Names of non-Person parties (customers) are scrubbed from staff text before Jev, and a reply that names one is sensitive: `mia/agents/customer_service/actions.py` (`build_query`, `_without`), the manifest, `node/tests/test_customer_service_chat.py::test_staff_text_reaches_jev_without_the_customer_name`, `::test_the_picked_up_reply_is_redacted_on_the_chain`.
- Every approval-backed row has an end when nobody decides (TTL or a passed date), with the requester told: `mia/agents/customer_service/tools.py` (`close_undecided`), `mia/core/approvals.py` (`expire`), `node/tests/test_customer_service_due.py::test_a_waiting_order_whose_pickup_passed_is_closed_and_the_customer_told`, `::test_a_waiting_order_past_its_approval_ttl_is_closed`.
- A public sender's writes that notify staff are capped per sender (open orders) and per node (a Jev budget per hour): `mia/agents/customer_service/tools.py` (`_order_precheck`), `mia/agents/customer_service/public.py` (`_public_calls`), `node/tests/test_customer_service_tools.py::test_a_second_order_while_one_waits_is_refused`, `node/tests/channels/test_customer_service.py::test_the_public_jev_budget_holds_a_message_without_a_jev_call`.
- "Reminders wait for quiet hours" says whether a reminder waits or is dropped, per agent: `mia/agents/customer_service/due.py` (module docstring: waits inside its hour, dropped when the whole hour is quiet), `node/tests/test_customer_service_due.py::test_a_pickup_reminder_waits_for_quiet_hours`.
