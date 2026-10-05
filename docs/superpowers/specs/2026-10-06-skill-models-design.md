# Role skill models: design

Date: 2026-10-06. Status: proposed, for review. Related decisions: D16 (agents are human roles),
D18 (local model answers), D22 (turn cap), D26 (language layer, refined here), D27 (local or
cloud learning). Related research: docs/research/model-comparison-2026-10-05.html,
docs/research/english-intents-2026-10-05.md, docs/research/conversation-topics.md,
docs/research/translation-models.md.

## 1. Goal

Make small, specialised language models a first-class, repeatable part of Mia. Every agent role
(dispatcher, client service, bookkeeper, recruiter and so on) gets its own multilingual intent
classifier, built the same way each time: from the role's job, to wide and realistic training
data, to a measured model that runs on the node, to a model that keeps learning from real use.

Success means:
- a new role gets a promoted model by running one Claude Code skill and one command, with two
  human approvals;
- the model reads Finnish, English and Filipino (including mixed language) directly, in about
  20 ms on the node's CPU;
- intents that change data are handled automatically only at precision of 99% or better; the
  rest are clarified with "Did you mean" options instead of guessed;
- every promoted model has a report that shows what data and settings produced it and how it
  scored, per intent and language;
- the defaults for how much data is needed are replaced by measured numbers as roles are
  trained.

Out of scope here: the apps (D25), translation of free-text replies (section 9), fine-tuning
LLMs (kept as a fallback tier, section 9).

## 2. Principles

- The role comes first: responsibilities, counterparts, then intents (D16).
- LLMs classify and code acts (rule 7): the model picks the intent; tools, permissions,
  approvals and events stay as they are (rules 1, 3, 4, 5).
- Creative, LLM-driven work (planning, writing and reviewing data) is a Claude Code skill;
  anything that must be deterministic or run on the node without Claude Code is ordinary code
  in the `mia.learning` package.
- Fewest steps: one skill, one training command, two approvals.
- Synthetic data only leaves the node. Real messages are used only on the node, or in the cloud
  if the owner opted in (D27).

## 3. Artefacts

Per role, in git, next to the agent:
```
node/mia/agents/<role>/skill/
  role.yaml            the approved plan
  data/
    generated.jsonl    raw teacher output, kept for audit and regeneration
    reviewed.jsonl     every record after review (labels fixed, drops marked)
    train.jsonl        fits the model
    dev.jsonl          tuning: hyperparameters, early stopping, calibration, thresholds
    test.jsonl         final held-out score only; written by a different model family
    review.md          the reviewer's coverage and quality notes
  reports/
    <version>.md       evaluation and promotion report with the sign-off
```
Built artefact, not in git, shipped in the role's skill package:
```
models/<role>/<version>/
  model.onnx           int8 for CPU
  labels.json          intents, languages, slot values
  thresholds.json      per-intent confidence thresholds, calibration temperature
  card.md              data hash, settings, metrics, gate result, sign-off
```
Shared:
- node/mia/learning/catalogue/conversation.yaml: the conversation intents every role inherits
  (greetings, help, safety, privacy, out of scope), from node/tests/evals/conversation_intents.yaml.
- docs/capabilities.md and the machine-readable intents catalogue are generated from all
  role.yaml files, not edited by hand.
- docs/research/skill-sizing.md: the sizing log (section 6).

### role.yaml
Sections: `role` (id, job summary, departments), `responsibilities`, `counterparts` (role,
share of traffic, typical channel), `languages` and `countries`, `intents` (id, description,
counterparts, trigger, risk read/write/money/external/delete, `label_en`, slots, handler, hard
look-alikes, volume normal/high, follow-up yes/no), `styles` and `channels` with shares,
`targets` (overrides of the guideline defaults), `base_model` (optional override).

### Record format (all data files)
`id, role, intent, lang (en|fi|fil|mixed), text, context (Mia's last question or empty),
counterpart, style (informal|terse|typo|indirect|formal|mixed|context), channel (whatsapp|web),
country, slots, negative_of, kind (normal|negative|other|injection|safety), split
(train|dev|test), source (teacher model id | reviewer | real-clarification), review (status,
note)`.

Splits are stratified per intent and language. Paraphrases of one message never sit on both
sides of a split. Real records (self-learning) are never written to git.

## 4. The Claude Code skill: `/mia-train-role <role>`

Location `.claude/skills/mia-train-role/`: `SKILL.md` (steps and gates), `guidelines.md`
(section 6 defaults, updated from the sizing log), `prompts/` (planner, generator and reviewer
prompts, versioned with the skill). Each step writes its files, so an interrupted run resumes.

1. Understand the role: read job.md, manifest.yaml, the shared conversation intents, D16 and
   the catalogue; ask the developer only what is missing (countries, languages, counterparts).
2. Plan (frontier model): responsibilities, counterparts, intents with descriptions, risk,
   labels and slots, hard look-alikes, coverage dimensions, targets. Writes role.yaml.
3. Generate: Sonnet plus a second teacher model, through the development egress, synthetic only.
   Fills every intent by language by counterpart by style cell to its quota, written natively
   per language (Finnish puhekieli, Taglish), with `context` for follow-up intents. The test
   split is generated by a third model family. Writes generated.jsonl.
4. Review (a stronger model than the generator): checks each record's label, language,
   naturalness and slots; fixes or drops it; judges completeness against the role and generates
   what is missing (reviewed again); runs the mechanical checks (duplicates and near-duplicates,
   split leakage, quotas, wrong language, contradicting labels). Writes reviewed.jsonl, the three
   splits and review.md.
5. Gate 1: shows role.yaml, about 20 sample records per language and the coverage notes; waits
   for approval.
6. Train: runs `mia skills train <role>` (section 5).
7. Explain the report: learning curves, weak cells, confused pairs. If targets are not met,
   proposes a targeted top-up (back to step 3 for those cells only).
8. Gate 2: sign-off of the model card; runs `mia skills promote`; adds a line to the sizing log.

Rules: no example in the prompts repeats a test message; the test split is never used for
tuning and is regenerated only when role.yaml changes; nothing is promoted without gate 2.

## 5. The package: `mia.learning`

Deterministic code, the same on a laptop, a cloud GPU or the node. Training dependencies live
in an optional `learning` dependency group that nodes install only if they retrain locally
(D27); the node runtime needs only `onnxruntime`. Both need approval before the build.

### `mia skills train <role> [--base-model M] [--with-real]`
1. Validate role.yaml and the splits (schema, known labels, leakage, quotas); stop with a clear
   message on failure.
2. Train a multilingual encoder with three heads: intent (role intents plus shared conversation
   intents plus `other`), language (fi, en, fil, mixed), and slot classifiers for the role's
   simple details. Input: the message, plus Mia's last question when present, joined by a
   separator token. Learning rate swept 2e-5 to 8e-5, batch 16 to 32, warm-up ratio 0.06, up to
   20 epochs with early stopping on dev, label smoothing; three seeds, best on dev kept.
   Plain Hugging Face Transformers; no Unsloth (it pays off only for large LLMs).
3. Calibrate: temperature scaling on dev; choose per-intent thresholds on dev that meet each
   intent's risk target.
4. Evaluate on test once: the gate metrics (section 6), the learning curve on 25/50/75/100% of
   train, the weakest intent by language by style cells, the most-confused pairs, CPU latency.
5. Package into models/<role>/<version>/ and write reports/<version>.md.

The base model is a setting. The first role runs a bake-off between mmBERT-small, mmBERT-base,
XLM-R base and multilingual-e5-base on the same splits; the winner on per-language accuracy,
calibration and CPU latency becomes the default and is recorded in the sizing log.

### `mia skills promote <role> <version> --signed-by <name>`
Refuses if the gate failed or the sign-off is missing; marks the version active; keeps the
previous version for rollback; emits an event.

### `mia skills harvest <role>`
Turns clarification, correction, undo and handoff events into candidate records (section 8).

### Runtime: `mia.skills.runtime`
- Loads each role's active package at startup and runs it on the CPU with onnxruntime.
- `classify(role, text, context) -> Classification(intent, confidence, band, alternatives,
  lang, slots)`, a Pydantic model; band is high, medium or low from the per-intent thresholds.
- No active package: every message is band low and the agent behaves as it does today.

## 6. Sizing, distribution and accuracy (defaults, learned as we go)

Per intent, per language:

| | Train | Dev | Test |
|---|---|---|---|
| Normal | 30 minimum, 60 target | 10 | 20 |
| High-volume or leads to a write | 100 | 15 | 30 |
| Follow-up replies (with context) | 60 | 15 | 30 |

Evidence: BERT on Banking77 reaches about 91% at 30 examples per intent and about 94% with the
full set (about 130); XLM-R trained on English only reaches about 80% in Finnish but about 64% in
Tagalog, so every language gets native data; LLM-generated data helps most in low-data settings
but does not fully match real data (sources in section 13).

Within each intent: counterparts in proportion to who says it; styles informal 30%, terse 15%,
typos 15%, indirect 15%, formal 10%, mixed language 10%, context 5% (more for follow-ups);
mostly WhatsApp style; languages equal at first. Across the dataset: hard look-alikes at least
15%, `other` 5 to 10%, injection 1 to 2%, safety cases always present. Data from at least two
teacher models; test from a third family.

Promotion gate (gate 2 defaults, risk per intent from role.yaml):
- intents that lead to a write, money or an external message: precision at least 99% at the
  chosen threshold; read intents at least 95%;
- share handled without asking at least 70%;
- each language within 3 points of the best language and meeting the intent targets;
- safety intents: recall at least 99%;
- injection and `other`: never classified as an action;
- calibration error (ECE) at most 0.05;
- no intent or language worse than the current version.

Learning as we go: the learning curve shows per intent whether more data still helps (more than
1 point from 75% to 100% means yes); the report drives targeted top-ups; every promoted role
logs the counts it actually needed in docs/research/skill-sizing.md, and guidelines.md is
updated from that log.

## 7. How agents use the model (per turn, web chat and WhatsApp)

1. Safety check first (catch-all): an emergency gets the fixed script and a supervisor notice
   before anything else.
2. `classify` with Mia's last question as context; conversation and role intents share one
   label space.
3. By band:
   - high, intent with a tool handler: code runs the handler through the registered tools with
     `rbac.require`, approvals and events; slots from the classifier, dates from code parsers,
     names from matching; the reply from i18n templates or the LLM wording the tool result;
   - high, template intent: a fixed i18n reply, no model call;
   - high, intent that needs judgement (open questions, knowledge-base answers): the LLM agent
     runs with the intent as context (replacing today's regex hint);
   - medium: "Did you mean" buttons from the top alternatives with catalogue labels in the
     person's language, plus "Something else"; the choice is recorded;
   - low or `other`: the LLM agent as today, or a request to rephrase, then a handoff.
4. Reply in the detected language.

Each role.yaml intent declares its handler: `tool` (with argument mapping), `template` or
`agent`. A2A: the role's intents are the AgentSkills on its Agent Card (ADR 008), and incoming
A2A tasks go through the same `classify`. Each classification emits an event (version, intent,
band, latency; no message text); the health page shows each role's active version and
clarification rate.

## 8. Self-learning loop

1. Capture: medium-band clarifications, corrections, undos, "Something else" and handoffs are
   events with the classification and the choice.
2. Harvest (`mia skills harvest`, nightly): candidate records with `source:
   real-clarification`, `review: pending`; kept only if the task completed and was not undone
   and similar messages agree; pseudonymised; special category data dropped; stored in the node
   database, never in git.
3. Review: a reviewer model (local, or cloud if the owner opted in, D27) checks candidates; the
   data owner approves batches (office web app, a CLI listing until then).
4. Retrain: `mia skills train <role> --with-real`; approved real records go to train and dev
   only. The synthetic test set stays fixed, plus a growing real test set (about 20% of approved
   real records, never trained on).
5. Promote: same gate, owner sign-off, rollback kept. Retraining is suggested at about 200 new
   approved records or monthly, never automatic without sign-off.

## 9. Relation to other parts of the plan

- Language (D26): understanding is handled by the multilingual encoder directly; the
  translation layer is needed only for free-text replies, and fixed replies come from i18n.
  D26 is to be updated after the bake-off confirms this.
- Small LLMs: the local LLM (Gemma 4 12B, D18) still words replies and handles low-band and
  judgement intents; LoRA fine-tuning of Qwen or Gemma (with Unsloth on a cloud GPU) stays a
  fallback tier if the encoder cannot reach a role's targets.
- Knowledge base: if multilingual-e5 wins the bake-off, the same encoder family also produces
  the knowledge-base embeddings.

## 10. Error handling

- Missing or corrupt package: fall back to the agent; health shows an alert.
- Training interrupted: resumable; nothing is written to models/ until packaging.
- Gate failure: a normal result with a report, not an exception.
- Cloud job failure: nothing promoted; the local version stays active.
- Classifier slower than its budget: logged; the turn continues with the agent.

## 11. Testing

- Unit tests without models: schema, split leakage, quotas, metrics (precision at threshold,
  ECE, gates), threshold selection, band logic, harvest rules, pseudonymisation, promotion
  refusals.
- Tiny model in CI: a fixture role with 3 intents and about 60 records, one CPU epoch, export to
  ONNX, load in the runtime, check shapes and bands (behind a marker if slow).
- Runtime: no package means today's behaviour; medium band gives buttons; a high-confidence
  intent still passes `rbac.require` (negative test: a cleaner's "assign cover" is denied);
  injection classified as `other` runs no tool; a safety message triggers the emergency script
  before classification.
- Evals: the dispatcher suites (all languages and English) and the classification eval run under
  the `evals` marker against the trained package.

## 12. Open items for the plan

- Approve the `learning` dependency group and `onnxruntime` (CLAUDE.md, dependencies).
- Q18: the extra roles in the catalogue (quality, office, platform chat) and the `applicant`
  counterpart.
- Native-speaker review of the Finnish and Filipino test splits, if available, in addition to
  the reviewer models.
- Office web app screen for approving harvested batches (Phase 2; CLI until then).

## 13. Sources
- BERT few-shot and full-data intent results (Banking77, CLINC150): https://arxiv.org/html/2109.05782v2 ,
  https://arxiv.org/pdf/2109.10126 , SetFit https://arxiv.org/abs/2209.11055
- MASSIVE (XLM-R per language, English-only transfer): https://ar5iv.labs.arxiv.org/html/2204.08582
- LLM-generated data for intent classifiers: https://www.tandfonline.com/doi/full/10.1080/08839514.2024.2414483
- Fine-tuning stability: https://arxiv.org/pdf/2006.04884 ; calibration: https://arxiv.org/pdf/2003.07892
- mmBERT: https://arxiv.org/html/2509.06888v1 , https://github.com/jhu-clsp/mmBERT
- Unsloth with Sentence Transformers: https://sbert.net/examples/sentence_transformer/training/unsloth/
