# Jev on Philippine languages (spike, 18 Oct 2026)

Question: can Jev (`jev-1.13.0`) read a store clerk's free text in Filipino, English and the
top Philippine languages, for the store clerk agent (sales reports at a bibingka shop)? A
throwaway probe, no product code. Synthetic data only (D18).

Setup: 30 messages per language, the same 30 meanings in each: 10 sales reports ("8 ube
bibingcute sold"), 5 stock messages ("the puto bumbong is sold out"), 5 questions and other
messages, and 10 answers to Mia's "You beat today's target! What do you think worked?". The
menu is Ferino's Bibingka (17 items). Four choice questions per message: kind (report, stock,
question, other), item (17 items or not stated), reason (technique, busy day or event, big
order, weather, other) and language. 270 requests, 0 errors, 0.26 s p50, under $0.05.

## Results (second round)

Kind is asked for the 20 messages that do not answer "what worked?" (code knows from the
thread when a message answers Mia's question); reason only for the 10 that do. "Acted right" is
a correct pick at confidence 0.6 or more (the dispatcher's threshold); below it Mia asks back.

| Language | Kind | Item | Reason | Acted right at 0.6 | Confident and wrong | Language named |
| --- | --- | --- | --- | --- | --- | --- |
| English (`en`) | 20/20 | 14/15 | 10/10 | 43/45 | 0 | 26/30 |
| Filipino (`fil`) | 19/20 | 15/15 | 10/10 | 43/45 | 0 | 30/30 |
| Cebuano (`ceb`) | 20/20 | 15/15 | 10/10 | 40/45 | 0 | 19/30 |
| Hiligaynon (`hil`) | 20/20 | 15/15 | 10/10 | 42/45 | 0 | 5/30 |
| Waray (`war`) | 20/20 | 15/15 | 8/10 | 41/45 | 1 | 3/30 |
| Central Bikol (`bcl`) | 19/20 | 14/15 | 9/10 | 42/45 | 0 | 7/30 |
| Kapampangan (`pam`) | 19/20 | 14/15 | 7/10 | 38/45 | 1 | 3/30 |
| Ilocano (`ilo`) | 15/20 | 15/15 | 8/10 | 30/45 | 0 | 9/30 |
| Pangasinan (`pag`) | 15/20 | 14/15 | 6/10 | 24/45 | 4 | 0/30 |

The first round asked kind and reason for every message and offered both "other" and "not
stated" as reasons. Answers to "what worked?" were then often read as reports ("an office
ordered 20 boxes") and "I don't know, maybe luck" went to not stated; all three tasks together
scored 93% (en) down to 62% (pag). The second round fixed those two probe faults and sharpened
two reason descriptions (suggesting a box of four is a technique, not a big order).

## Reading

- **Items are easy in every language** (14 or 15 of 15). Menu names stay in English or
  Taglish in all of them. The one shared miss is a bare "ube" (not stated, about 0.5): short
  codes and aliases matched in code cover it.
- **Kind and reason hold up in Filipino, Cebuano, Hiligaynon, Waray and Bikol.** Ilocano
  misses are safe (report read as stock at low confidence, so Mia asks). Pangasinan is the
  weak one: 4 confident wrong answers out of 45.
- **Jev does not name the language.** Everything outside English and Cebuano is mostly called
  Filipino. Mia takes the reply language from the person's profile, never from Jev.

## Recommendation for the store clerk agent

| Languages | Free text through Jev |
| --- | --- |
| `en`, `fil`, `ceb`, `hil`, `war`, `bcl` | yes, threshold 0.6 |
| `pam`, `ilo` | yes; low confidence asks back, which is what happened here |
| `pag` | short codes only for now; free text asks in Filipino or English. Retest with native text |

Short codes (`cbc 5`) are read by code in every language and are the main path anyway.

## Caveats

- Claude wrote every message; none was checked by a native speaker. Real clerks write
  shorter, mix in Filipino and English, and misspell. Expect lower numbers on real text.
- 30 messages per language: one message is 2 to 3 points, so differences of under about 15
  points between languages mean little.
- The second round's reason descriptions were adjusted on these same messages. A held-out set
  (ideally native written) is needed before the agent's threshold is set.
