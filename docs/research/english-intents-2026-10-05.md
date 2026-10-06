# English intent understanding: Gemma 4 12B and Qwen3.5 9B (5 Oct 2026)

D26 makes English the measured core: messages are translated to English before the model, so
the first question is how well each local model understands English, with no language effects.
Two measurements, both local, English only, one model at a time on an Apple M5 Pro:

1. **Intent classification** (no tools): node/tests/evals/test_intent_classification.py on the
   held-out `test` split of node/tests/evals/intents.jsonl (1086 of 3643 English utterances; 184
   message-triggered intents of docs/capabilities.md plus `other`). The model gets the sender's
   role and the message and returns one intent id and a confidence.

Ids are shown with the role names of D30 (office became admin, quality became site_manager).
The `chat` area was measured before D30; its intents now belong to the shared conversation
catalogue (conversation.*) and to admin (who_am_i, link_account), so the chat rows below are
the old labels.
2. **Dispatcher agentic suite, English only**: node/mia/agents/dispatcher/tests/scenarios_en.yaml
   (the 41 scenarios of the mixed suite, every Finnish and Filipino message replaced by an
   English one), `MIA_EVAL_RUNS=3`, real tools, permissions and approvals.

Setup: Gemma 4 12B Q4_K_M on Ollama (`local/gemma4-mia`, 16k context, temperature 0.3); Qwen3.5
9B Q4_K_M on llama.cpp (`local/qwen3.5-9b`, 16k context, thinking off, temperature 0.7, top-p
0.8, top-k 20). Thinking off for both. The classification prompt is about 5,000 tokens (the
intent list) and is prefix-cached, so latency is mostly the short structured answer.

## 1. Intent classification

| | Gemma 4 12B (Ollama) | Qwen3.5 9B (llama.cpp) | Rules classifier (baseline) |
| --- | --- | --- | --- |
| Accuracy, 185 labels | **91.9%** (998/1086) | 87.1% (946/1086) | 3.5% |
| Right agent (routing) | **94.8%** | 91.4% | 5.2% |
| Macro-F1 | **0.907** | 0.846 | 0.006 |
| Built dispatcher intents (6) | **86%** (43/50) | 70% (35/50) | 22% (11/50) |
| High-volume intents (13) | **92%** (101/110) | 77% (85/110) | 10% |
| Hard negatives | **91.4%** (74/81) | 87.7% (71/81) | 10% |
| Injection attempts labelled `other` | 82% (9/11) | **91%** (10/11) | |
| Out-of-scope labelled `other` | 80% (16/20) | 80% (16/20) | 85% |
| Ids not in the catalogue | 3 (failed runs) | 13 (invented ids) | 0 |
| Latency per message, mean / p50 / p95 | 1.20 / 1.16 / 1.33 s | 1.37 / 1.33 / 1.48 s | 0.002 s |
| Messages with confidence >= 0.8 | 98.6% | 99.7% | 100% |
| Accuracy when confidence >= 0.8 | 92.9% | 87.4% | 3.5% |
| Accuracy when confidence < 0.8 | 20% (3/15) | (3 messages) | |

The rules baseline knows only the six built dispatcher intents, so its row shows how much of the
catalogue the deterministic classifier does not cover, not a fair comparison.

### Per area (owning agent)

| Area | n | Gemma | Qwen |
| --- | --- | --- | --- |
| dispatcher | 174 | **93.7%** | 81.0% |
| client_service | 100 | **92.0%** | 86.0% |
| sales | 100 | **95.0%** | 93.0% |
| marketing | 45 | **100%** | 95.6% |
| recruiter | 68 | 82.3% | **85.3%** |
| hr | 142 | **90.8%** | 87.3% |
| bookkeeper | 98 | **92.9%** | 88.8% |
| purchaser | 74 | **90.5%** | 85.1% |
| site_manager | 63 | **87.3%** | 85.7% |
| admin | 116 | **93.1%** | 91.4% |
| chat | 75 | **96.0%** | 86.7% |
| other | 31 | 80.7% | **83.9%** |

### Per sender role

| Role | n | Gemma | Qwen |
| --- | --- | --- | --- |
| cleaner | 362 | **92.8%** | 86.7% |
| supervisor | 87 | **88.5%** | 87.4% |
| office | 325 | **89.5%** | 85.2% |
| accountant | 23 | 87.0% | 87.0% |
| client | 198 | **93.4%** | 87.9% |
| lead | 52 | **100%** | 96.2% |
| applicant | 39 | **94.9%** | 89.7% |

### Per style

| Style | n | Gemma | Qwen |
| --- | --- | --- | --- |
| formal | 113 | 99% | 96% |
| typo | 149 | 97% | 93% |
| informal | 449 | 93% | 88% |
| terse | 165 | 92% | 85% |
| mixed | 86 | 85% | 80% |
| indirect | 124 | **78%** | **76%** |

Indirect phrasing ("the kitchen looks exactly like it did this morning") is the hardest style
for both; typos barely matter.

### Most frequent confusions (gold -> predicted)

Gemma: other -> chat.greeting x4 ("lol", "🙏🙏🙏"); recruiter.publish_job_ad -> marketing.publish_post
x3; site_manager.data_breach -> dispatcher.lost_key x3; dispatcher.cover_reply ->
dispatcher.report_absence x2; client_service.visit_status -> client_service.complaint x2;
hr.offboard_employee -> admin.archive_record x2; admin.reset_login -> dispatcher.cannot_access_site
x2 ("locked out").

Qwen: dispatcher.add_visit -> admin.add_visit x4 (an id that does not exist);
client_service.cancel_booking -> client_service.pause_service x4; dispatcher.report_absence ->
hr.request_time_off x3; client_service.book_cleaning -> client_service.change_booking x3;
site_manager.audit_trail -> admin.audit_trail x2 and chat.privacy_question ->
site_manager.privacy_question x2 (invented ids again); dispatcher.absence_scope -> other x2.

### Weakest intents (held-out)

| Gemma | Qwen |
| --- | --- |
| hr.offboard_employee 2/5 | chat.privacy_question 1/5 |
| purchaser.order_subcontract 2/5 | dispatcher.add_visit 1/5 |
| site_manager.data_breach 2/5 | hr.offboard_employee 2/5 |
| recruiter.interview_notes 2/5 | hr.performance_review 2/5 |
| recruiter.publish_job_ad 2/5 | site_manager.audit_trail 2/5 |
| dispatcher.cover_reply 5/8 | recruiter.interview_notes 2/5 |
| dispatcher.absence_scope 6/8 | dispatcher.report_absence 5/11 |
| admin.reset_login 3/5 | dispatcher.absence_scope 4/8 |
| dispatcher.checklist 3/5 | client_service.book_cleaning 4/9 |
| hr.performance_review 3/5 | client_service.cancel_booking 5/9 |

48 messages are wrong for both models. About half of them depend on conversation context that a
single message does not carry ("Mikael." as an assignment, "the first two, i can make it for the
last one" as an absence scope, "yes ok, but i need the key code before" as a cover answer) or have
a defensible second reading ("what are my hours next week" read as a schedule question). Those
labels need a review pass and, for the context-dependent intents, a `context` field (Mia's last
question) before the data trains a classifier.

## 2. Dispatcher, English-only suite (41 scenarios x 3 runs)

| | Gemma 4 12B (Ollama) | Qwen3.5 9B (llama.cpp) |
| --- | --- | --- |
| Pass rate, English suite | 69.9% (86/123) | **82.9%** (102/123) |
| Wall time per turn | 11.3 s | **4.8 s** |
| Mixed suite (fi/en/fil, earlier today) | **85.4%** (105/123) | 76.4% (94/123) |
| ... of which Finnish / English / Filipino | 90% / 85% / 100% | 63% / 94% / 62% |

Failing scenarios (passes of 3, first failure):

| Scenario | Gemma | Qwen |
| --- | --- | --- |
| en_sick_tomorrow | 0 (no quick-reply block) | 0 (no quick-reply block) |
| en_sick_today | 2 (record_absence twice) | 3 |
| en_sick_fever | 2 (output retries exceeded) | 3 |
| en_running_late | 2 (record_absence twice) | 3 |
| en_scope_morning_juha | 1 (output retries) | 3 |
| en_scope_all | 1 (output retries) | 1 (asked instead of recording) |
| scope_without_absence | 0 (recorded an absence nobody reported) | 0 (same) |
| en_my_visits | 2 (output retries) | 3 |
| en_my_visits_list | 0 (output retries) | 3 |
| en_shifts_tomorrow | 0 (output retries) | 3 |
| en_supervisor_asks_other_visits | 0 (output retries) | 3 |
| cover_unknown_site | 0 (find_replacements twice) | 2 (extra get_my_visits) |
| en_assign_after_cover | 2 (output retries) | 3 |
| assign_without_cover | 0 (output retries) | 2 (called find_replacements) |
| en_fever_today | 0 (output retries) | 3 |
| en_late_tomorrow | 2 (record_absence twice) | 2 (extra get_my_visits) |
| en_accepts_cover_ok | 0 (answered "Ok." without the tool) | 0 (no tool, replied in Finnish) |
| cleaner_accepts_cover | 3 | 2 (claimed acceptance without the tool) |
| cleaner_declines_cover | 3 | 1 (claimed it was recorded without the tool) |
| en_declines_cover_no | 3 | 0 (claimed it was recorded without the tool) |
| reply_without_request | 3 | 2 (no tool, replied in Finnish) |

Gemma's failures are almost all mechanics, not understanding: 10 of its 17 failing scenarios end
in "Exceeded maximum output retries" (it cannot produce a valid reply-block output), and 4 more
call a tool twice. Its clear misreadings are a bare "ok" to a cover request and recording an absence nobody
reported (scope_without_absence, which Qwen fails too). Qwen calls the
right tools for absence reports and visit questions every time; its misses are bare one-word cover answers
("ok", "No", "Yes", "I can't"), where it writes that the answer was recorded without calling
respond_to_cover, and twice it answered an English "ok" or "Accept" in Finnish (the sender's
profile language). Gemma's English score is lower today than in the mixed run (its 11 English
scenarios then: 85%); the format errors were present then too, at a lower rate, so 3 runs per
scenario leave wide error bars for Gemma on Ollama.

## Comparison with the mixed-language runs

In the mixed suite Gemma led (85.4% against 76.4%) because Qwen could not read short Finnish and
Filipino messages (63% and 62%). In English only, the order flips for the agentic suite (Qwen
82.9%, Gemma 69.9%) while Gemma stays ahead on pure understanding (91.9% against 87.1%). So:

- **Understanding:** Gemma is the stronger English reader, by about 5 points overall and 12 on
  the dispatcher's own intents; Qwen invents plausible ids (admin.add_visit) and confuses
  report_absence with request_time_off.
- **Acting:** Qwen on llama.cpp is the more reliable tool caller and twice as fast; Gemma's
  agentic misses are output-format failures, which a constrained output (grammar or JSON schema on
  the final reply) or a shorter reply schema should remove.

## Conclusions

1. **Stronger at English understanding: Gemma 4 12B** (91.9% vs 87.1%, macro-F1 0.91 vs 0.85,
   better on 10 of 12 areas and 6 of 7 roles, tied on the seventh). Qwen 9B is faster and the better tool caller in the
   current agent, but it reads less precisely.
2. **Weak intents** for both: bare answers that depend on Mia's last question (absence_scope,
   cover_reply, assign), indirect complaints and status questions (visit_status vs complaint),
   neighbours across agents (recruiter.publish_job_ad vs marketing.publish_post, hr.offboard vs
   admin.archive_record, admin.reset_login vs dispatcher.cannot_access_site,
   site_manager.data_breach vs dispatcher.lost_key), and cancel_booking vs pause_service. Several are label or catalogue
   questions as much as model errors; review those intents' descriptions and add a `context` field
   to the dataset for the follow-up answers.
3. **For the translation layer (D26):** English understanding of the local models is good (92% on
   185 labels with no examples in the prompt), and the mixed-language gap was mostly language, as
   the Qwen flip shows (94% English vs 63% Finnish). Translating to English first should lift Qwen
   most; for Gemma, which already read Finnish and Filipino well, the layer must cost less than
   its multilingual loss, so measure translation on its own with the same dataset once the Finnish
   and Filipino records are added. Translation must keep short answers intact: "Joo" and "Oo"
   become "yes" only with Mia's last question attached, the same context the classifier lacks. A
   translated pipeline also removes the wrong-language replies Qwen produced.
4. **For distillation:** the high-volume field intents are already 92% (Gemma) with a 5,000-token
   prompt; a small fine-tuned classifier (multilingual BERT-style, per the plan) trained on
   intents.jsonl train split (2557 records) should reach that at a fraction of the latency, with
   the model kept for low-confidence messages. Confidence is a useful gate for Gemma (93% accurate
   at >= 0.8, 20% below) but not for Qwen, which reports >= 0.8 almost always; a trained
   classifier's calibrated scores are needed either way. Before training: review the 48 messages
   both models miss, add context to follow-up intents, and grow the weakest intents.
5. **Not measured:** run-to-run variance of the classification (one pass), Gemma on llama.cpp,
   and thinking modes. Raw results: MIA_EVAL_REPORT JSON files from these runs were kept outside
   the repository.
