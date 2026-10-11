# Local model measurements on the current build (12 Oct 2026)

Plan item 2 (local model to 95%, D18, D19, D26). The 5 Oct measurements
(model-comparison-2026-10-05.html, english-intents-2026-10-05.md) predate authentication,
scheduling, field work over chat, the turn cap (D22) and the role skill models. This note
re-measures Gemma 4 12B on the build of 12 Oct, on an Apple Silicon Mac with Ollama (the same
class of machine as the Mac mini of D19), and adds the first Finnish parallel intent suite
(`mia skills translate`, Q25).

Setup: `local/gemma4:12b` (Q4_K_M, Ollama, thinking off), `MIA_EVAL_RUNS=1`, the eval clock
pinned to 09:30 local (Juha's Kamppi visit current), real tools, permissions and approvals.

## 1. Dispatcher agentic suite (mixed languages, 48 scenarios)

`uv run pytest node/tests/evals/test_dispatcher_evals.py -m evals`: **37/48 runs passed
(77.1%)** on `local/gemma4-mia` (the project Modelfile, 16k context) and 38/48 (79.2%) on the
plain `local/gemma4:12b` tag (Ollama's 4k default), both under the 95% gate (the rules model
and Sonnet 5.5 pass 100%). The failures of the two runs overlap on 8 scenarios; the table
lists the 4k run, the 16k run adds fi_sick_tomorrow (no quick replies), fi_tick and
en_supervisor_asks_other_visits (output retries exhausted) and passes en_done_here:

| Scenario | What Gemma did | Reading |
| --- | --- | --- |
| scope_without_absence | recorded an absence the message did not report | acts before the clarifying question (format, extra tool call) |
| en_my_visits | output token limit exceeded before any response | long table reply; the reply contract (text, code builds blocks) should take this |
| en_shifts_tomorrow | exceeded the output retries | structured output format errors |
| cover_unknown_site | called find_replacements three times | retries a failed lookup instead of answering |
| cleaner_declines_cover | asked a clarifying question instead of respond_to_cover | reads "I cannot" as an absence, not a decline |
| assign_without_cover | ran find_replacements and assign_cover from a plain instruction | acts without the cover flow |
| fil_late_tomorrow | reason sick instead of late, no partial day | Filipino "late tomorrow" misread (language layer, D26) |
| en_done_here | replied in Finnish to an English message | reply language follows the thread, not the message |
| fi_door_code | no card block | answered in text where the details card is expected |

Pattern: 6 of 9 are format or extra-tool-call failures (the role skill model's clarifying
question and the reply contract address them), 2 are language (D26's translation layer), 1 is
a reasoning miss (declining a cover). With the 16k context 4 runs end in "exceeded maximum
output retries": Gemma answers with text or a malformed tool call where the structured reply
is expected; the reply contract (`text_reply`) catches plain text but not a broken tool call.
The turn cap (D22) ended no run in either measurement.

## 2. Intent classification, English (held-out split)

`MIA_EVAL_MODEL=local/gemma4-mia uv run pytest node/tests/evals/test_intent_classification.py
-m evals` on the held-out `test` split (1091 of 3664 English utterances, the catalogue after
D30 and D31):

| | Gemma 4 12B, 12 Oct | Gemma 4 12B, 5 Oct (older catalogue) |
| --- | --- | --- |
| Accuracy | **88.9%** (970/1091) | 91.9% (998/1086) |
| Right agent (routing) | 92.0% | 94.8% |
| Macro-F1 | 0.876 | 0.907 |
| Dispatcher intents (174 messages) | **92.0%** (160/174) | 86% built intents (43/50) |
| Hard negatives | 83.5% (of 79) | 91.4% (of 81) |
| Injection attempts labelled `other` | 72.7% (8/11) | 82% (9/11) |
| Ids not in the catalogue | 2 | 3 |
| Latency per message, mean / p50 / p95 | 0.97 / 0.95 / 1.19 s | 1.20 / 1.16 / 1.33 s |
| Messages with confidence >= 0.8, their accuracy | 97.8%, 89.8% | 98.6%, 92.9% |

The two runs are not the same test: D30 and D31 merged and renamed intents and the split was
regenerated, so the 3-point drop is within what the catalogue change moves. By area the
dispatcher (92%), sales (96%), client service (96%) and marketing (100%) are fine; recruiter
(75%), `other` (66%) and conversation (84%) are not.

Weakest intents (5 or more test messages): bookkeeper.annual_accounts 2/5 (to `other`),
purchaser.order_subcontract 2/5, recruiter.interview_notes 2/5 (to admin.update_employee),
recruiter.publish_job_ad 2/5 (to marketing.publish_post), conversation.hazard_report 3/7,
admin.agent_settings, admin.change_role, admin.reset_login (to dispatcher.cannot_access_site),
admin.staffing_forecast, conversation.kb_employment_terms, dispatcher.checklist 3/5 (to
site_problem and send_photos), hr.contribution_question, hr.performance_review,
recruiter.candidates (to dispatcher.find_cover). In the dispatcher's own area the confusions
are cover_reply read as report_absence (2) and absence_scope read as cover_reply or
report_absence: the same "a reply in a cover thread looks like an absence" weakness the
agentic suite shows (cleaner_declines_cover).

This is the list for the distilled classifier: the role skill models exist for every role
(spec 2026-10-06-skill-models); the dispatcher's should be trained first on cover_reply,
absence_scope and checklist, where Gemma confuses neighbours it should not.

## 3. Intent classification, Finnish (the parallel suite)

The first Finnish parallel suite: `uv run mia skills translate --lang fi --model
local/gemma4-mia --split test` translated the held-out English records with the same labels
(390 of 1091 in this run, the file's first intents: the dispatcher's 174 test messages and
parts of admin, bookkeeper, client service, conversation and sales; the rest is being
appended in later runs, the command resumes by `source_id`). Gemma classified its own
translations, so this measures understanding of Finnish, not the translation layer of D26 (the
Finnish message went to the classifier untranslated):

| | Finnish, 390 messages | English, the same 390 (from the run above) |
| --- | --- | --- |
| Accuracy | **82.6%** (322/390) | about 90% |
| Right agent (routing) | 92.0% | 92% |
| Macro-F1 | 0.756 | |
| Dispatcher intents (174) | **80.5%** (140/174) | 92.0% (160/174) |
| Hard negatives (22) | 86.4% | |
| Latency, mean / p95 | 0.99 / 1.35 s | 0.97 / 1.19 s |
| Confidence >= 0.8, their accuracy | 97.2%, 84.7% | 97.8%, 89.8% |

Finnish costs the dispatcher 11 points. The misses concentrate where English was already
weakest: absence_scope 2/8 (to report_absence and `other`), cover_reply 2/8 (to greeting and
report_absence), checklist 1/5, assign 2/5 (to `other`), find_cover read as who_is_working.
Routing to the right agent stays at 92%, so the loss is inside the dispatcher's own
neighbours, the case the role skill model (a classifier that knows cover_reply from
report_absence) is for, and the case D26's translation to English before the model would
remove if the translation holds the meaning.

## What this says for the pilot

- Gemma 4 12B alone is at 77 to 79% on the agentic suite and 89% (English) or 83% (Finnish)
  on intent classification; the 95% gate (D18) is not met by the model on its own.
- The gap is concentrated: structured-output format errors and extra tool calls (the suite),
  and three dispatcher intents confused with their neighbours (both suites). The dispatcher
  role skill model, trained first on cover_reply, absence_scope and checklist, plus the
  clarifying question when its confidence is low (D28), is the planned remedy for exactly
  these; the reply contract should also accept a broken tool call by retrying as plain text.
- The translation layer (D26) was not measured here; `mia skills translate` now gives it a
  parallel Finnish suite to be measured against the English numbers once the set is complete.
- Measuring took 10 min (agentic suite), 18 min (1091 English messages) and 7 min (390
  Finnish messages) on this Mac; the Mac mini of D19 is the same class of machine, so the
  suite can run on the node itself before each model change.
