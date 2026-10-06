# Embedding review and embedding classifiers (addition to the skill models spec)

Date: 2026-10-06. Extends docs/superpowers/specs/2026-10-06-skill-models-design.md sections 4, 5
and 6. Status: proposed, for the owner's review.

## 1. Goal
Measure intent overlap instead of finding it by reading (the D30 review found about 25
overlapping pairs by hand), and test whether a classifier built on sentence embeddings can match
or replace the fine-tuned encoder for some roles, or serve as the starting classifier before a
role has a trained package.

## 2. Embedding model
- Default: multilingual-e5-small (MIT, about 118M parameters, 384 dimensions, covers Finnish and
  Filipino). Alternatives measured in the bake-off: bge-m3 (larger, stronger), LaBSE.
- Runs with the libraries already in the `learning` group (transformers, mean pooling, the model's
  required "query: " prefix). No new dependency. On the node it runs on onnxruntime and tokenizers
  like the role classifier.
- Embeddings of harvested real messages are computed and kept on the node only (D18).

## 3. Overlap report: `mia skills overlap <role>`
Learning group command; reads the role's records, the other roles' records and the conversation
catalogue examples; writes `<role>/skill/reports/overlap-<UTC>.md`; changes nothing.

1. Close intents: per-intent centroid, cosine similarity between centroids; pairs above a
   threshold are listed.
2. Suspect labels: for each record, its k nearest neighbours (k = 10); a record whose neighbours
   mostly carry another label is listed with that label.
3. Paraphrases across intents: record pairs with cosine at or above 0.95 and different labels
   (the exact-text check in `mia skills validate` misses these).
4. Clusters inside each intent: the intent's records are clustered (cosine threshold, union-find
   as in splits.py, numpy only, no scikit-learn). For each sub-cluster the nearest other intent is
   found.
   - Merge candidate: an intent with two or more sub-clusters that each overlap other intents, or
     several sub-clusters overlapping the same other intent. Shown with the overlapping intents
     and example records.
   - Split candidate: sub-clusters far from each other that overlap nothing.
   - Narrow candidate: one sub-cluster overlaps a narrower intent (the D30 rule "narrower intent
     wins").
5. Output: one table (pair or intent, signal, strength, examples, suggested decision using the
   D30 rules). The skill shows it at Gate 1 and again after the data review; the developer
   decides; nothing is relabelled automatically.

Thresholds start as defaults and are calibrated once on the pre-review dataset
(node/tests/evals/intents.jsonl at commit 8fee0ac, before the D30 review): the report must find
most pairs in docs/research/intent-overlap-review-2026-10-06.md. That recall is the acceptance
test for the report and is written into the skill's guidelines.

## 4. Classifier contenders (bake-off, Task 19)
All three are trained on the same train and dev splits, scored on the same test split and judged
by the same promotion gate; the winner per role is promoted. The model card records the kind.

| Contender | How | Strength | Weakness |
|---|---|---|---|
| A. Fine-tuned encoder (built) | Encoder plus intent, language and slot heads | Best on fine-grained look-alikes | Needs training per change |
| B. Nearest examples | Frozen embeddings of the reviewed examples; similarity to the k nearest per intent, calibrated to probabilities with the existing temperature fit | No training; adding an intent is adding examples; cross-lingual | Usually a few points lower on look-alikes; no slot head |
| C. Contrastive fine-tune (SetFit method) | Short contrastive fine-tune of the embedding model plus a logistic head, written with torch and transformers | Strong with few examples per intent | One more training path |

- Runtime: B and C produce intent scores that go through ScoredClassifier, so bands, thresholds,
  "Did you mean", routing and safety work unchanged. B ships the embedding model and an example
  matrix (hashed in `artifacts` like model.onnx). Slots stay with A; a role that needs slots
  either keeps A or runs A's slot head alongside.
- Starting classifier: before a role has a promoted package, B built from the reviewed synthetic
  data can be promoted through the same gate and replaces the regex hint fallback (D28 A) for that
  role.

## 5. Out of scope
- The SetFit library (C is written directly; adding the library would need approval).
- Automatic relabelling or merging.
- Clustering libraries (HDBSCAN, scikit-learn).

## 6. Open items
- Embedding model choice after the bake-off (e5-small vs bge-m3 vs LaBSE: size against accuracy
  on Finnish and Filipino).
- Overlap thresholds after calibration.
