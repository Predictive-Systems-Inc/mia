# Overlap calibration, 6 Oct 2026: not calibrated (recall below 0.80 within budget)

Dataset: `git show 8fee0ac:node/tests/evals/intents.jsonl` (3643 records, 185 intents) plus the
conversation examples. Expected pairs: `docs/research/intent-overlap-review-2026-10-06.md`
(40 pairs, none unfindable).

## Result

`mia skills overlap --calibrate` printed `recall 1.00 (40/40)` for both models, but the number is
vacuous: no grid point kept the flagged pairs within the budget (3 x 40 = 120), so `calibrate`
returned the default thresholds, which flag nearly everything (e5: 17k report lines; bge-m3: 18k
rows). Nothing was pinned.

Probe of the dataset alone (13 expected pairs findable in it), wider grid, same `analyse`:

| model | centroid cosine, all 17020 intent pairs (p5 / p50 / p95 / max) | expected pairs (min / median / max) | best recall with at most 120 flagged | flags at recall 1.00 |
|---|---|---|---|---|
| intfloat/multilingual-e5-small | 0.915 / 0.940 / 0.963 / 0.987 | 0.962 / 0.974 / 0.981 | 0.15 (close_pair 0.98) | 1269 |
| BAAI/bge-m3 | 0.824 / 0.872 / 0.920 / 0.977 | 0.913 / 0.933 / 0.955 | 0.23 (close_pair 0.95) | 899 |

Reading: the reviewed pairs sit only 0.02 to 0.04 above the median intent pair, and the top of the
distribution is crowded with unreviewed pairs (book_cleaning vs change_booking 0.987,
update_contact vs hr.update_details 0.987, ...), so a centroid threshold cannot separate them.
Neither model reaches recall 0.80 at a usable precision. Status: BLOCKED, thresholds unchanged.

## Owner judgement of the top 10 unreviewed pairs (e5-small, centred centroid)

Real overlap (6): conversation.compliment / conversation.thanks; conversation.goodbye /
conversation.thanks; conversation.confusion / conversation.rephrase_simpler;
conversation.emergency / conversation.hazard_report (differ in handling: sharpen, do not merge);
site_manager.report_damage / site_manager.report_injury; admin.update_client / hr.update_details.
Not an overlap (4): dispatcher.add_visit / dispatcher.reschedule_visit;
client_service.book_cleaning / client_service.change_booking; admin.add_site / admin.update_site;
conversation.kb_cleaning_howto / chemical exposure. The four misses share a topic but name a
different action, which embeddings do not separate: the reviewer applies a "same action?" test
to every flagged pair. Precision at top 10, owner-judged: 0.6. Decision: the tool is a ranked
review aid, not a gate (plan amendment A1); the trained classifier's confusion list stays the
authoritative overlap signal.

## Rerun with the centred, ranked report (A3)

Dataset: pre-review intents (8fee0ac, 3643 records) plus the conversation.yaml examples, against
docs/research/intent-overlap-reference.md (46 findable pairs, no unfindable). Reference numbers,
not a bar (the list is not exhaustive). Full e5 report: docs/research/overlap-report-pre-d30-e5.md
(Paraphrases trimmed to 30 of 45 rows by hand; bge-m3 report not kept).

| Model | recall@40 | recall@80 | recall@120 |
|---|---|---|---|
| e5-small (default) | 0.39 | 0.46 | 0.57 |
| bge-m3 | 0.30 | 0.43 | 0.54 |

Link threshold (e5-small): 0.283 (p75 of within-intent similarity).

Top 10 ranked pairs (e5-small):

| Rank | Pair | Similarity | In reference |
|---|---|---|---|
| 1 | conversation.kb_payday / hr.payday | 0.856 | yes |
| 2 | conversation.kb_prices / sales.price_question | 0.841 | yes |
| 3 | conversation.kb_household_tax_deduction / sales.household_deduction | 0.818 | yes |
| 4 | conversation.kb_cleaning_howto / conversation.kb_surface_care | 0.812 | yes |
| 5 | conversation.kb_chemical_safety / site_manager.chemical_safety | 0.756 | yes |
| 6 | conversation.compliment / conversation.thanks | 0.731 | yes (owner confirmed) |
| 7 | conversation.injury_minor / site_manager.report_injury | 0.725 | yes |
| 8 | conversation.goodbye / conversation.thanks | 0.72 | yes (owner confirmed) |
| 9 | conversation.emergency / conversation.hazard_report | 0.717 | yes (owner confirmed) |
| 10 | client_service.update_contact / hr.update_details | 0.717 | no (reference has it only via admin.update_client) |

Candidates: the report lists one, not five. other (merge) with conversation.emoji_only,
kb_chemical_safety, oos_other_companies, oos_sports, oos_weather (5 sub-clusters overlap other).
Reading the Paraphrases rows, this is duplicate text, not a real merge: other/en/023 equals an
oos_sports example, other/en/025 an oos_joke example, other/en/039 a laughter example,
other/en/032 an oos_general_knowledge example, other/en/062 an emoji_only example. Judgement:
narrow, not merge; drop or relabel the `other` records that copy a conversation example.

## Conversation intents: pairs for the owner

Run on the 294 pre-review records labelled conversation.* plus the conversation.yaml examples
(report: docs/research/overlap-report-conversation.md; link threshold 0.308). The top 15 ranked
pairs are all conversation.* on both sides. Example texts are the first conversation.yaml example
per intent. Decisions are the owner's; conversation.emergency / hazard_report is sharpened, not merged.

| # | Pair | similarity | A example | B example |
|---|---|---|---|---|
| 1 | conversation.kb_cleaning_howto / conversation.kb_surface_care | 0.815 | "how do I get red wine out of a carpet" | "how to clean oiled parquet" |
| 2 | conversation.emergency / conversation.hazard_report | 0.75 | "there's a fire in the building" | "the ladder at the office is broken" |
| 3 | conversation.kb_household_tax_deduction / conversation.tax_personal_advice | 0.662 | "can I get the household deduction" | "how should I fill my tax card" |
| 4 | conversation.compliment / conversation.thanks | 0.661 | "you're really helpful" | "thanks" |
| 5 | conversation.goodbye / conversation.thanks | 0.65 | "bye" | "thanks" |
| 6 | conversation.distress / conversation.self_harm_risk | 0.623 | "I'm so stressed I can't sleep" | "I don't want to live anymore" |
| 7 | conversation.kb_chemical_safety / conversation.kb_cleaning_howto | 0.62 | "can I mix bleach with the toilet cleaner" | "how do I get red wine out of a carpet" |
| 8 | conversation.harassment_report / conversation.personal_threat | 0.598 | "my supervisor keeps touching me" | "a man is following me from the bus stop" |
| 9 | conversation.kb_expenses_travel / conversation.kb_payment_invoicing | 0.591 | "do I get money for the bus" | "can I pay by card" |
| 10 | conversation.goodbye / conversation.greeting | 0.587 | "bye" | "hi" |
| 11 | conversation.affirm / conversation.laughter | 0.585 | "ok" | "haha" |
| 12 | conversation.greeting / conversation.laughter | 0.578 | "hi" | "haha" |
| 13 | conversation.emergency / conversation.personal_threat | 0.576 | "there's a fire in the building" | "a man is following me from the bus stop" |
| 14 | conversation.confusion / conversation.rephrase_simpler | 0.575 | "???" | "I don't understand" |
| 15 | conversation.kb_chemical_safety / conversation.kb_surface_care | 0.573 | "can I mix bleach with the toilet cleaner" | "how to clean oiled parquet" |
