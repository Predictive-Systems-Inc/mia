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
