# Dispatcher skill data: review notes (Gate 1 package)

Date: 2026-10-12. Plan: role.yaml (13 intents, en and fi, cleaners 80% over WhatsApp,
supervisors 20% over the web). Teachers: `local/gemma4-mia` and `local/qwen3.5-mia` for train
(two families, nothing leaves the node). The test set comes from `local/gemma4-mia` again:
the rule asks a third model family, and this Mac has none that answers structured chat (its
`clef-flash` tag does not support chat). The test set is therefore provisional, usable to tune
nothing and to read the first report only, until a cloud teacher of another family regenerates
it (a Gate 1 decision; the spend is small, the data synthetic).

## Overlap review (one message, one label, D30)

Every role intent against the conversation catalogue (87 shared intents) and the other roles'
rows in docs/capabilities.md (no other role has a role.yaml yet). Rules from guidelines.md:
(1) questions about rules are kb_*, (2) doing stays with the role, (3) sender role does not
make a new intent.

| Pair | Decision | Rule, reason |
| --- | --- | --- |
| report_absence vs conversation.kb_sick_leave_rules | keep both | 1: "am I paid when sick" is a question; "I'm sick tomorrow" is the action |
| report_absence vs cover_reply (decline) | keep both, sharpen | 2: a decline answers a cover request, an absence drops a visit; descriptions name the difference, look-alike cells generate the boundary |
| report_absence vs absence_scope | keep both | follow-up with context; absence_scope only ever answers Mia's question |
| absence_scope vs conversation.affirm | keep both | a bare "yes" stays affirm; scope names the visits |
| cover_reply vs conversation.affirm / deny | keep both | the reply to a cover request is the role's write; affirm and deny carry no context of a request |
| my_visits vs visit_details | keep both | the list versus one visit's details (address, code) |
| my_visits vs who_is_working (phase 2) | keep my_visits | 3: a supervisor asking about someone else's visits is my_visits with a person; who_is_working is a staffing view, not built |
| find_cover vs assign | keep both | asking for candidates versus naming the person (the "same action?" test: different actions) |
| check_in vs check_out | keep both | arriving versus leaving |
| check_out vs checklist | keep both | the whole visit versus one item |
| check_out vs conversation.goodbye | keep both | "I'm done here" ends a visit; "bye" ends a chat |
| cannot_access_site vs admin.reset_login | keep both | a building versus Mia; the catalogue row says so |
| cannot_access_site vs visit_details | keep both | asking for the code versus reporting that it fails |
| site_problem vs purchaser.broken_equipment | keep both | the client's site versus the company's own machine |
| site_problem vs conversation.hazard_report | keep both | work stopped versus a danger to people |
| visit_details vs conversation.kb_cleaning_howto | keep both | 1: where and how to get in versus how to clean |
| send_photos vs conversation.media_without_text | keep both | words announcing photos versus a bare attachment (the channel path handles the bytes) |

Label count for the model: 13 role intents + 87 conversation intents + `other` = 101, within
the budget of about 150.

`uv run mia skills overlap dispatcher`: run after the data exists (section below).

## Data review

(filled in after generation: per-record statuses are in the generated files' `review` field,
the records that fit another intent better are listed here, then coverage notes and the
validator's warnings with a judgement on each.)
