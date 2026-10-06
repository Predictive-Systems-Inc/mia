# Sizing, distribution and accuracy guidelines

Defaults, learned as we go. Source: spec section 6 (docs/superpowers/specs/2026-10-06-skill-models-design.md).
Per intent, per language:

| | Train | Dev | Test |
|---|---|---|---|
| Normal | 30 minimum, 60 target | 10 | 20 |
| High-volume or leads to a write | 100 | 15 | 30 |
| Follow-up replies (with context) | 60 | 15 | 30 |

Evidence: BERT on Banking77 reaches about 91% at 30 examples per intent and about 94% with the
full set (about 130); XLM-R trained on English only reaches about 80% in Finnish but about 64% in
Filipino, so every language gets native data; LLM-generated data helps most in low-data settings
but does not fully match real data.

## Distribution
Within each intent: counterparts in proportion to who says it; styles informal 30%, terse 15%,
typos 15%, indirect 15%, formal 10%, mixed language 10%, context 5% (more for follow-ups);
mostly WhatsApp style; languages equal at first. Across the dataset: hard look-alikes at least
15%, `other` 5 to 10%, injection 1 to 2%, safety cases always present. Data from at least two
teacher models; test from a third family.

## One message, one label (D30)
The classifier sees text, not the sender, so a message gets exactly one intent.
1. Questions about rules or company knowledge belong to the shared conversation kb_* intents.
   Example: "can I mix bleach with the descaler?" is a conversation.kb_* question, not a role intent.
2. Doing something stays with the role intent, whose records must be actions; questions go to
   kb_*. Example: "log the damaged mirror at Aalto school" is an action, "how do I report damage?"
   is a question.
3. A message that differs only by sender role is one intent, and code routes by sender. Example:
   "change the client's invoice address" is admin.update_client whoever writes it.
Keep two close intents only with a written reason (the planner lists them).

## Public data rules
- Allowed: licences that permit commercial use without share-alike (for example CC BY, MIT,
  Apache 2.0, CC0); attribution is recorded in public.yaml and the model card.
- Needs Allan's approval: share-alike licences (CC BY-SA), custom commercial terms, or terms
  that restrict model training.
- Never: non-commercial licences (CC BY-NC and similar), data with real personal data that was
  not published for this use, and anything whose licence cannot be confirmed.
- Typical uses: intermediate training for general intent sense in every language (for example
  MASSIVE, 60 intents in 51 languages including Finnish and Filipino), out-of-scope examples
  mapped to `other` (for example CLINC150), natural phrasing to compare against generated data,
  and real-world safety and injection attacks.
- Public data fills a share of train and dev, never more than the role's own data per intent,
  so the role's own intents dominate. It never goes into test. Each public record keeps its
  origin in `source` (for example `public:massive-1.1`).

## Promotion gate (Gate 2 defaults, risk per intent from role.yaml)
- Intents that lead to a write, money or an external message: precision at least 99% at the
  chosen threshold; read intents at least 95%.
- Share handled without asking at least 70%.
- Each language within 3 points of the best language and meeting the intent targets.
- Safety intents: recall at least 99%.
- Injection and `other`: never classified as an action.
- Calibration error (ECE) at most 0.05.
- No intent or language worse than the current version.

## Learning as we go
The learning curve shows per intent whether more data still helps (more than 1 point from 75% to
100% means yes). The report drives targeted top-ups. Every promoted role logs the counts it
actually needed in docs/research/skill-sizing.md, and this file is updated from that log.

## Measured so far
(empty; filled from docs/research/skill-sizing.md)
