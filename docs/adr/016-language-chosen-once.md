# ADR 016: The reply language is chosen once

## Status

Accepted.

## Context

Mia took the reply language from the message. The language spike
(docs/research/jev-languages-2026-10-18.md) showed that detection cannot tell the Philippine
languages apart: Jev read the messages well in most of them, but named the language right only
for English, Filipino and part of Cebuano, and called most of the others Filipino. Menu names
stay in English in every language, so short messages carry little to detect. A wrong guess
answers a person in a language they did not choose.

## Decision

- Nothing detects the language of a message. Every reply uses `person.language`
  (`mia/chat/language.py`).
- When the organisation offers two or more languages, Mia asks once, with one button per
  offered language, each named in itself. With one language nobody is asked.
- A person changes it by writing `language`, `wika`, `pinulongan` or `lengguahe`, which asks
  the question again.
- Seeded and imported people have already chosen (their language comes with the record).

## Consequences

- A person who writes in another language still gets the one they chose, until they change it.
- The router and the agents read messages in any language; only the reply language is fixed.
- Eight languages (`fil`, `ceb`, `ilo`, `hil`, `war`, `bcl`, `pam`, `pag`) ship as machine
  drafts in `mia/i18n/<code>.py`; a native speaker reviews each before a client uses it
  (docs/questions.md).
