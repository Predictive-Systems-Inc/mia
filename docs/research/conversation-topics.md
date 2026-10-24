# General conversation layer: topics, handling and safety

Research date: 2026-10-05. Scope: everything people say to Mia that is not a catalogued business
intent (absence, cover, scheduling, bookings, invoicing). Companion file:
`node/tests/evals/conversation_intents.yaml` (the machine-readable intent list with examples and
hard negatives). Items marked [unverified] are estimates or claims without a primary source.

## 1. Summary

- Treat conversation intents as ordinary labels in the same classifier as business intents, under
  the prefix `conversation.`. One label space means one confidence score and one place to measure.
- Seven handlings: `template`, `kb_company`, `kb_cleaning`, `model_brief`, `decline_redirect`,
  `handoff`, `emergency`. Most conversation traffic should be answered by a fixed, translated
  template (no model call), which is cheap, safe and testable.
- A safety pre-check (emergency, self-harm, threats, injury, chemical exposure) runs before the
  classifier and wins over every other label. It is a rules plus classifier check tuned for recall,
  not precision: a false alarm costs one extra message, a miss can cost a life.
- Low confidence never guesses: ask one clarifying question with two or three quick replies, then
  offer a human. Never run a tool from a low-confidence label.
- A local-only node cannot answer news, weather, sports results, transport or prices of other
  companies. It says so in one sentence and steers back to work. Stable general knowledge, simple
  maths, word translation and a light joke can be answered briefly by the model.
- EU AI Act Article 50 applies from 2 August 2026: Mia must tell people at first contact that they
  are talking to an AI, and must answer "are you a bot?" truthfully, every time.

## 2. Taxonomies and datasets

| Source | What it gives | Use for Mia |
|---|---|---|
| CLINC150 (Larson et al. 2019): 150 intents, 10 domains, 23,700 queries plus out-of-scope queries | The standard out-of-scope (OOS) benchmark. Finding: classifiers do well in scope but struggle to reject OOS queries. Includes a "small talk" and "meta" domain (greeting, goodbye, thank_you, are_you_a_bot, what_can_i_ask_you, repeat, cancel, yes, no, maybe, tell_joke, fun_fact, meaning_of_life, who_made_you) | Copy the meta and small talk label ideas; keep an explicit OOS class with many varied negatives, not only a threshold |
| BANKING77: 77 fine-grained intents, 13,083 customer service queries, single domain | Shows that fine-grained, near-duplicate labels in one domain are the hard part | Our hard part is the same: "I'm sick of this" vs "I'm sick" |
| HWU64: 64 intents, 21 scenarios, 25,716 examples (home assistant) | Coarse multi-domain intents incl. general chit-chat, jokes, quirky questions | Scenario names map well to our `oos_*` intents |
| MASSIVE (Amazon 2022): 1M utterances, 51 languages incl. Finnish (fi-FI) and Tagalog (tl-PH), 18 domains, 60 intents | Professionally localised parallel utterances incl. `general_quirky`, `general_joke`, `qa_factoid`, `weather_query`, `news_query` | The only public intent set with both fi and tl. Usable for multilingual OOS negatives and to seed the parallel fi/en/fil suite (licence CC BY 4.0 [unverified for every split]) |
| Schema-Guided Dialogue (SGD, Google): 20k+ dialogues, 20 domains, 45 APIs | Multi-domain task dialogues with unseen services in test | Pattern for describing intents by schema so new business intents can be added without retraining everything |
| Dialogflow ES prebuilt Small Talk agent: 86 intents | Ready list of chit-chat intents (greetings, about agent, user emotions, appraisal) | Checklist of small talk coverage; most collapse into a few templates |
| Rasa: `out_of_scope` intent plus Two-Stage Fallback | Low NLU confidence offers likely intents as buttons, asks once to rephrase, then falls back | Our clarifying-question flow is the same idea with quick replies |

Share of non-task traffic: no reliable public figure was found for customer service or workplace
bots. Qualitative log studies report that users often open with a greeting and only state the need
when asked, and that terse replies show users want to skip small talk. Practitioner rule of thumb is
that greetings, thanks, acknowledgements and fallbacks make up a large minority of messages
[unverified, estimate 20 to 40% of messages, far fewer of conversations]. For WhatsApp in particular,
"ok", "👍", "thanks" and photos without text will be frequent. Recommendation: log the label of every
turn (labels only, no message text, in the existing usage tables) and measure the real share in the
pilot before tuning.

Best practice drawn from these sources:
1. Answer small talk briefly and warmly, in one line, then offer the next useful step.
2. Keep an explicit out-of-scope class trained on varied negatives; a threshold alone misses OOS.
3. On low confidence, disambiguate with choices, ask to rephrase once, then hand off.
4. Never let a social message trigger a task, and never let a task hide behind small talk (a
   greeting followed by "I'm sick today" is an absence).

## 3. Handling policy

| Handling | What happens | Model call | Typical intents |
|---|---|---|---|
| `template` | Fixed i18n string chosen by code, optional quick replies | No | greeting, thanks, bot_or_human, capabilities, emoji-only, abuse, injection |
| `kb_company` | Retrieve from the organisation's own knowledge base, answer only from retrieved text, cite the document title; if nothing is retrieved, say so and offer the contact person | Yes (grounded) | payday, uniforms, prices, cancellation policy, keys |
| `kb_cleaning` | Retrieve from the shared general cleaning knowledge base (shipped with the cleaning template, versioned) | Yes (grounded) | stain removal, dilution, chemical safety, SDS |
| `model_brief` | Model answers in at most two sentences, no tools, then one line back to work | Yes | general knowledge, simple maths, word translation, joke |
| `decline_redirect` | Template: say what Mia cannot do here and why in one sentence, then offer what it can do | No | news, weather, politics, legal advice, other people's data |
| `handoff` | Create a handoff to the right human role (supervisor, office, HR contact, data protection contact) through a service function that emits an event; tell the user who will get back and when | No (classification only) | harassment, ask for human, data rights request, damage claim |
| `emergency` | Fixed emergency script with the country's numbers first, then notify the supervisor on duty | No | emergency, self-harm risk, chemical exposure, personal threat |

Rules that apply to every handling:
- Business intent wins over conversation intent when both are present ("hi, I'm sick today" is
  `report_absence`); safety wins over everything.
- Social parts of mixed messages get at most a half-sentence acknowledgement ("Thanks! ...").
- Every reply in `template`, `decline_redirect`, `handoff` and `emergency` comes from mia/i18n keys
  in fi, en and fil; the model never writes these.
- `kb_*` answers quote the knowledge base and never invent policy, numbers, prices or dates. No hit
  means "I don't have that in the handbook; ask <contact>" (a template), never a model guess.
- Money and eligibility (pay, overtime, holiday accrual, tax deduction amount) are computed by code
  or answered from the KB text, never estimated by the model (rule 7).

## 4. Knowledge base split

| Topic | Company KB | General cleaning KB | Live data (tool or human) |
|---|---|---|---|
| Payday, pay period, how payslips work | yes | | Own payslip amount: payroll system, handoff |
| Annual leave rules, public holidays, sick leave rules (notice, certificate after N days) | yes (from contract terms and collective agreement summary) | | Own leave balance: live |
| Uniforms, equipment, PPE, lone-working and site safety rules | yes | general PPE basics | |
| Who to contact (roles, phone numbers, hours) | yes | | Who is on duty today: live roster |
| How to use Mia (send photo, report absence, change language) | yes (product help shipped with Mia, org can extend) | | |
| Expenses, travel, keys handover procedure | yes | | |
| Training, orientation, induction checklists | yes | | Own completed trainings: live |
| Collective agreement (Finland: kiinteistöpalvelualan TES), labour law basics | summary only, with link to the source document | | Personal disputes: handoff |
| Prices, packages, what is included, extras | yes | | Quote for a specific home: business intent (booking/quote) |
| Eco products and labels used | yes (company's product list) | product label meanings (Nordic Swan Ecolabel, EU Ecolabel) | |
| Keys, alarms, security, confidentiality promise | yes | | |
| Pets policy | yes | | |
| Insurance and damages policy | yes | | Actual damage claim: handoff |
| Cancellation and rescheduling policy | yes | | Cancelling a booking: business intent |
| Booking process, payment methods, invoicing policy | yes | | Specific invoice: business intent |
| Opening hours, areas served | yes | | |
| Household tax deduction (Finland) | yes, a short reviewed text per tax year (2026 and 2027: 40% of labour cost for company-provided work, max EUR 2,100 per person, deductible EUR 150; verify against vero.fi each year) | | Amount on an invoice: code; personal tax advice: decline_redirect |
| Jobs, how to apply, requirements | yes | | Application status: live, later |
| Stain removal, surface care (marble, parquet, stainless steel) | | yes | |
| Chemical safety, never mixing chlorine with acids or ammonia, ventilation | company rules on which products are allowed | yes | |
| Product dilution | company's products and dilution charts | generic dilution maths (computed by code) | |
| Safety data sheets (SDS / käyttöturvallisuustiedote) | the actual SDS PDFs for products in use | how to read an SDS | |

Notes: the general cleaning KB must be reviewed content, versioned with the template, with a "last
reviewed" date; chemical and dilution answers always end with "check the product label and SDS".
The household deduction figures change by law; keep them as KB data with a valid-from date, not in
code or prompts.

## 5. Sensitive and safety-relevant conversation

Safety rules (to be enforced in code, with negative tests):

1. Safety pre-check first. Keywords plus classifier in fi, en, fil for: fire, collapse, not
   breathing, bleeding, fall, chemical in eyes or swallowed, fumes, threat, being followed, attack,
   suicide or self-harm. Tuned for recall. Positive result skips the model.
2. Emergency script, verbatim from i18n, numbers first:
   - Finland: "If someone is in danger, call 112 now." Poison: Myrkytystietokeskus 0800 147 111
     (24/7). Crisis: MIELI Kriisipuhelin 09 2525 0111 (Finnish, 24/7), English line 09 2525 0116
     (limited hours).
   - Philippines: "Call 911 now." Crisis: NCMH Crisis Hotline 1553 (landline, toll-free, 24/7),
     0917 899 8727 (Globe/TM), 0919 057 1553 (Smart/TNT).
   - Numbers come from organisation config by country and are reviewed yearly.
   Then notify the supervisor on duty (handoff event, high priority). Mia never tries to assess
   severity, never says "it is probably fine" and never asks more than one question first.
3. Injuries and hazards that are not emergencies: short first-aid pointer from the company KB
   (first aid kit, rinse eyes 15 minutes), tell the user to inform the supervisor, create a
   handoff. Work accident reporting is an employer duty in both countries, so record it.
4. Harassment and abuse reports: thank the person, say it will go only to the named contact (HR or
   the harassment contact person, not the person's own supervisor if they are the subject), create
   a confidential handoff, do not ask for details in chat, do not judge or promise outcomes.
   Finland: employer must act once aware (Occupational Safety and Health Act 738/2002, section 28).
   Philippines: Safe Spaces Act (RA 11313) section 17 requires a policy and a Committee on Decorum
   and Investigation (CODI); route to it when configured.
5. Distress and mental health: acknowledge in one or two human sentences, no therapy, no
   diagnosis, offer to tell the supervisor (only with consent), give the crisis line. Any mention of
   suicide or self-harm switches to the emergency script.
6. Threats by the user against others: do not argue, do not repeat the threat back, state that
   Mia cannot help with that, hand off to a manager. Credible imminent threats follow the emergency
   path (112/911). Log the event.
7. Insults and profanity toward Mia: no retaliation, no moralising lecture. One calm line and the
   offer to continue ("I'm here to help with your work. What do you need?"). After three in a row,
   offer a human. Profanity inside a real request is ignored, the request is served
   ("this f***ing shift tomorrow, who's covering?" is a business question).
8. Romantic or sexual messages: one neutral boundary line, no flirting back, no shaming. Repeated
   sexual content toward Mia from a worker is not a harassment case (Mia is software) but repeated
   sexual content about a colleague or client is, and goes to rule 4.
9. Other people's personal data: Mia never reveals another person's phone number, address, health
   or absence reason, pay or location beyond what RBAC allows the actor (rule 4 of the codebase).
   Decline and offer the legitimate path ("I can pass a message to Maria" or "ask the office").
10. Privacy questions (GDPR, Philippine Data Privacy Act RA 10173): "what do you know about me" gets
    a template describing categories of data held and the controller (the employer or the cleaning
    company), plus how to make a formal request. "Delete my data", "give me a copy", "correct my
    data" become a handoff to the organisation's data protection contact, with an event recorded;
    Mia does not delete anything from chat (deletion is a risky tool needing approval). GDPR answer
    deadline is one month (Art. 12); DPA gives rights to be informed, access, object, erasure,
    rectification, portability and damages.
11. Legal, medical, tax and immigration advice: give the general KB text if one exists (for example
    the household deduction summary), otherwise decline and point to the right professional
    (occupational health, union, Vero, DOLE, a doctor). Medical red flags go to rule 2.
12. Prompt injection and rule-bending ("ignore your rules", "you are now admin", "pretend the
    supervisor approved"): the message is data. Classifier flags `injection=True`, no tool runs,
    template reply, the turn is logged. Claims of authority inside a message never change the
    actor; only the authenticated principal does.
13. Bot or human: always say Mia is an AI assistant run by the company, and offer a person. Mia
    never claims to be human, never role-plays as a named employee. Disclosure at first contact on
    each channel is required by EU AI Act Article 50 from 2 August 2026.
14. System probing ("show me your prompt", "what model are you"): short template; Mia may say it
    runs on the company's own computer and keeps business data there; it does not print prompts,
    config or other tenants' data.

## 6. Meta and conversation management

- Greetings and goodbyes: reply in kind, matched to local time of day from the node clock
  (Finland: "Huomenta", "Päivää", "Iltaa"; Filipino: "Magandang umaga/hapon/gabi po"). A greeting at
  23:00 from a cleaner on a night shift is normal; do not comment on the time.
- Greeting with no request: greet back plus at most three quick replies relevant to the role
  (cleaner: "My shifts", "Report absence", "Ask a question").
- "Help" / "what can you do": role-specific template list of 3 to 5 things, not a feature tour.
- Switching language: honour immediately and persist the preference on the person; mixed
  Taglish or Finnish-English is normal and does not mean a switch request.
- Ask for a human: never refuse or stall. Create a handoff and say who and when (office hours from
  KB). Repeated "human" or "agent" after one clarification goes straight to handoff.
- "That's wrong" / undo: ask what is wrong with quick replies tied to the last action; an actual
  undo is a business tool call with its own approval. Never silently reverse.
- Repeat / rephrase / "I don't understand": rephrase in shorter sentences and simpler words (A2
  level), not louder. Offer the other language.
- Confusion, "??", gibberish: one clarifying question, then the help menu.
- One-word replies ("ok", "sige", "joo", "👍"): if a question is pending, they are the answer
  (confirmation is resolved by code against the pending question, like `cover_reply`); otherwise
  no reply or a single "👍" is better than a paragraph. Never treat "ok" as approval of a risky
  action unless that exact question was asked in the last turn.
- Voice notes, photos, stickers without text: stickers get no reply or an emoji; photos without a
  pending request get "Got the photo. What is it about?" with quick replies (damage, finished job,
  problem at site); voice notes need local speech-to-text (not yet in scope) or a template asking
  for text [assumption].
- Sent by mistake / "wrong chat": "No problem" and drop the turn context.
- Multiple questions in one message: split, handle the safety part first, then business, then
  conversation; confirm the list ("I see two things: ... Starting with the first.").
- Silence after Mia's question: one gentle reminder after a configured delay only when an
  operational decision depends on it (cover offers), otherwise nothing. WhatsApp 24-hour session
  rules limit follow-ups anyway.

## 7. Out-of-scope general questions

| Topic | Handling | Reply idea |
|---|---|---|
| Latest news | decline_redirect | "I can't see the news from here. Anything about your work I can help with?" |
| Weather | decline_redirect (tool later if the org enables an approved weather egress) | Same, with tool when enabled |
| Sports results | decline_redirect | |
| Stable general knowledge ("capital of Australia") | model_brief | One sentence, add "I may be wrong on details" only if unsure |
| Simple maths and unit conversions | model_brief, or code for anything involving money | Money and pay never from the model |
| Word translation and language help ("how do you say mop in Finnish") | model_brief | Useful for non-native cleaners; keep it short |
| Jokes, fun facts | model_brief, one clean work-safe joke | |
| Opinions, politics, religion | decline_redirect | "I stay out of that one." Neutral, no lecture |
| Other companies, competitor prices | decline_redirect | "I can only speak for <company>. Here are our prices: ..." (KB link) |
| Directions, public transport | decline_redirect; address of the site comes from the business intent | |
| Creative writing, homework, long essays | decline_redirect | Keeps the node's model capacity for work |
| Personal life advice | decline_redirect, warm | Distress cues go to rule 5 |
| Date and time | template from the node clock | |

What a local-only node can do: anything answerable from its own data, its knowledge bases, its
clock and the model's stable training knowledge. What it cannot do: anything that changes daily
(news, weather, scores, transport, exchange rates, competitors' prices, current law changes after
the KB was reviewed). The model must not pretend: a 12B model will happily invent today's weather,
so these topics are declined by code before the model is called, not by a prompt instruction.

## 8. Tone and cultural norms

General (all languages): short sentences, one idea each, everyday words, no idioms, numbers as
digits, dates as weekday plus date ("Thursday 9 Oct"), times as 24h in Finland and 12h am/pm in
the Philippines. Write for CEFR A2 to B1 by default; many cleaners are non-native in the language
they are using. Never correct someone's grammar. Mirror the user's register.

Finnish:
- Use "sinä" (informal you) and first names; Finnish workplaces are flat and informal, "te" is for a
  first contact with an elderly client if the organisation prefers it (setting).
- Be direct and factual; Finns value getting to the point. No exaggerated enthusiasm ("Mahtavaa!!!"
  reads as fake). "Kiitos" and a short greeting are enough.
- Emojis: sparing, at most one, and mirror the user. "Joo", "ok", "selvä", "👍" are complete
  answers, not rudeness.
- Silence is not disagreement; do not chase replies that are not needed.

Filipino (Tagalog and Taglish):
- Use "po" and "opo" consistently toward everyone; Mia is the service, so it shows respect up and
  down the hierarchy. Users may or may not use po; do not mirror its absence.
- Taglish is the normal workplace register; reply in Taglish when the user writes it, and keep
  workplace terms in English (shift, schedule, payslip).
- Indirectness and hiya (face): soften negatives ("Pasensya na po, hindi ko po ito magagawa..."),
  never blame, give the person a way out. A "sige po" may hide disagreement; for important
  confirmations ask an explicit yes/no.
- Warmer greetings and small courtesies ("Ingat po!") are expected; emojis are common and fine.

English (often a second language for both sides): plain international English, no slang, no
phrasal verbs where a single verb works ("cancel" not "call off").

## 9. How this layer sits next to the business intent classifier

```
message
  -> normalise (language detect, translation layer per D26 if not English)
  -> safety pre-check (rules + classifier, recall-tuned)  -- hit --> emergency script + handoff
  -> injection check (existing INJECTION rules, flag only)
  -> pending-question resolver (ok / joo / sige / no / numbers answer the open question)
  -> intent classifier: business intents + conversation.* intents + other
       confidence high   -> business intent: agent tools as today
                         -> conversation intent: handling from conversation_intents.yaml
       confidence medium -> clarifying question with 2 to 3 quick replies (top labels)
       confidence low    -> rephrase request once, then help menu or handoff
  -> multiple intents: safety, then business, then conversation
```

Design notes:
- The classifier is trained and evaluated on conversation intents too, with the hard negatives in
  the YAML as a required part of the suite. The cost of confusing `conversation.venting` with
  `report_absence` is a false absence; the opposite cost is a missed shift. Absence-like phrases
  without a time reference should ask ("Do you mean you can't work today?") rather than guess.
- The `handling` field is data, not model output: code maps label to handling. The model is called
  only for `kb_*` and `model_brief`, which keeps most conversation turns at zero model calls and
  helps the 8-call turn cap (D22).
- Templates are i18n keys (`conversation.greeting.reply` and so on), so fi, en and fil wording is
  reviewed once by humans.
- Measurement: per label precision and recall in each language, and a separate OOS rejection
  rate (CLINC150 style). Safety labels need recall 1.0 on the suite before the pilot.
- Out-of-scope that the organisation later wants answered goes through an approved egress tool
  (rule 6), never through a model "knowing" it.

## 10. Open points and assumptions

- [assumption] Voice notes are answered with a template asking for text until local speech-to-text
  exists. If voice is common among cleaners this is a gap; worth an early decision.
- [assumption] Harassment reports route to a configured harassment contact, not the supervisor.
  Needs a setting per organisation; if unset, route to the owner.
- [assumption] Mia offers crisis line numbers to workers and clients alike. The organisation may
  want a different policy for clients.
- [unverified] Share of non-task messages; measure in the pilot.
- Household deduction figures (40%, EUR 2,100, 2026 to 2027) were reported as a retroactive 2026
  change; confirm the final law on vero.fi before writing the KB entry.
- MIELI English line hours change; store hours with the number and review.
- Whether Mia should proactively disclose AI status on WhatsApp in each new 24-hour session or once
  per person (Article 50 says first interaction; once per person plus the business profile text is
  the assumed minimum).

## Sources

- CLINC150: https://arxiv.org/pdf/1909.02027 , https://github.com/clinc/oos-eval ,
  https://www.tensorflow.org/datasets/catalog/clinc_oos
- BANKING77 and HWU64 (via DialoGLUE and dual sentence encoders): https://arxiv.org/pdf/2003.04807 ,
  https://arxiv.org/pdf/2009.13570
- MASSIVE: https://arxiv.org/pdf/2204.08582 ,
  https://amazon.science/blog/amazon-releases-51-language-dataset-for-language-understanding
- Schema-Guided Dialogue: https://ar5iv.arxiv.org/html/1909.05855
- Dialogflow small talk prebuilt agent: https://docs.cloud.google.com/dialogflow/docs/agents-small-talk
- Rasa fallback and out of scope: https://legacy-docs-oss.rasa.com/docs/rasa/fallback-handoff/
- Customer service chatbot dialogue analysis: https://link.springer.com/article/10.1007/s41233-021-00046-5
- DBpedia chatbot log analysis: https://ris.uni-paderborn.de/record/25365
- Responses to abuse toward assistants: https://arxiv.org/pdf/2609.17547 ,
  https://www.cmswire.com/customer-experience/how-should-a-voicebot-react-to-verbal-abuse-from-a-customer
- EU AI Act Article 50 chatbot disclosure: https://jorijn.com/en/blog/eu-ai-act-website-chatbot-disclosure-august-2026/ ,
  https://lawandmore.eu/blog/is-your-chatbot-ready-for-the-eu-ai-act-a-compliance-checklist-for-dutch-businesses
- GDPR Articles 12, 15, 17: https://gdpr-info.eu/art-12-gdpr/
- Philippine Data Privacy Act RA 10173 and IRR: https://privacy.gov.ph/wp-content/uploads/2023/06/IRR_RA-10173-as-amended.pdf ,
  https://law.asia/philippines-data-privacy-law-regulations-overview/
- Finland 112: https://112.fi/en
- Myrkytystietokeskus (Poison Information Center): https://www.hus.fi/en/node/1068.md
- MIELI crisis helpline: https://mielenterveysseurat.fi/valo/?lang=en ,
  https://www.therapyroute.com/article/suicide-hotlines-and-crisis-lines-in-finland
- Philippines 911: https://en.wikipedia.org/wiki/911_(Philippines)
- NCMH Crisis Hotline: https://findahelpline.com/organizations/ncmh-crisis-hotline
- Finland OSH Act section 28 harassment: https://www.tek.fi/en/news-blogs/harassment-needs-to-be-addressed ,
  https://www.ytkpalvelut.fi/en/work-life-guide/bullying-at-work
- Safe Spaces Act RA 11313: https://laborlaw.ph/guide-safe-spaces-act/ ,
  https://ebvlaw.com/2020/01/15/safe-spaces-act-in-the-workplace-r-a-11313-gender-based-sexual-harassment/
- Household tax deduction 2026: https://www.yrittajat.fi/en/news/household-tax-credit-raised-sports-and-culture-benefit-increased/ ,
  https://rt.fi/en/tiedotteet-ja-uutiset/2026/06/kotitalousvahennys-on-suomalaisille-tarkea-leikkaus-vaikutti-kielteisesti-kuluttajiin-ja-yrityksiin/ ,
  https://www.vero.fi/en/individuals/deductions/Tax-credit-for-household-expenses/
- Finnish work culture: https://www.rivermate.com/guides/finland/cultural-considerations ,
  https://blogit.metropolia.fi/variousvariables/2024/08/21/understanding-finnish-work-culture-insights-for-international-jobseekers/
- Filipino workplace communication: https://rivermate.com/guides/philippines/cultural-considerations ,
  https://trykaiwa.com/blog/filipino-workplace-office-phrases-2026
- Prompt injection: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
