# Dispatcher skill data: per-cell reviewer notes (12 Oct 2026)

One section per intent and language, written by the reviewer model (Claude Fable 5.1) over the
generated files (two local teachers for train, one for test). Per-record decisions are in the
records' review field (data/reviewed.jsonl, data/test.jsonl); review.md has the summary.

---

## dispatcher.absence_scope, en (62 records, all train, all counterpart cleaner)

### 1. Counts

| Teacher | Records | Kept | Fixed | Dropped |
|---|---|---|---|---|
| teacher:local/gemma4-mia | 9 | 8 | 0 | 1 |
| teacher:local/qwen3.5-mia | 53 | 0 | 40 | 13 |
| Total | 62 | 8 | 40 | 14 |

Main fix reason (40, all Qwen): follow-up intent with no `context` (32 records) or a context
carrying a "Mia:" prefix and robotic wording, "Can you tell me the scope of the absence you just
reported?" (8 records). A short natural Mia question was added or substituted; text untouched.

Main drop reasons:
- Wrong speaker, 5 (Qwen formal 0214 to 0218): system or office voice ("the absence has been
  updated", "we have verified", "will be recorded as"), not a cleaner replying.
- Machine-sounding or unnatural, 3 (0183, 0208, 0211).
- Ambiguous scope or self-contradictory, 3 (gemma 0206, 0184, 0202).
- Implausible context plus text meaningless without it, 2 (0219, 0220, Qwen "context" style).
- Question back to Mia, not an answer, 1 (0204).

### 2. Overlap suspects

Same-action test applied: all three below would not be "set the absence to whole day / morning /
afternoon"; they are a different action (withdraw, correct, ask) or no action.

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.absence_scope/en/local-gemma4-mia/0206 | conversation.undo | "free for the whole day after all" withdraws the absence (available all day); ambiguous with a whole-day scope, two labels |
| dispatcher.absence_scope/en/local-qwen3.5-mia/0211 | conversation.correction | "the initial report doesn't match what's happening" says Mia's record is wrong; two labels (also machine-sounding) |
| dispatcher.absence_scope/en/local-qwen3.5-mia/0204 | none (question back to Mia) | cleaner asks "does this cover the full day or just morning?"; not an answer, no dispatcher intent fits |

No record copies a conversation.yaml example; no bare affirm/deny; no kb_* questions.

### 3. Coverage: what a top-up should add (en, absence_scope)

Situations and phrasings missing:
- Afternoon-only answers are thin (about 8 of 48 surviving); most say morning only or whole day.
- Named visits or sites as the scope ("just the Aalto school one", "the 7 o'clock visit, I'll do
  the rest", "both the office and the gym", "only the first one"). role.yaml says "which visits";
  nothing here names a visit, every answer is morning / afternoon / whole day.
- Time-based scope ("back by 1", "from 11 on I'm fine", "until lunch", "the evening shift too").
- Multi-day scope ("today and tomorrow", "rest of the week", "just today, tomorrow I'm back").
- Scope with a correction of a previous answer ("no wait, the whole day"), still one action.
- Replies to differently worded Mia questions (quick-reply style "Whole day / Morning / Afternoon?",
  "Which of your visits does this affect?").
- Hard negatives nearby (to generate under their own intents, not here): bare "yes" / "no" to
  the scope question (conversation.affirm / deny), "how many days can I be off without a note"
  (kb_sick_leave_rules), "I'm sick today" with no prior question (report_absence).

Counterparts and styles:
- Counterpart is cleaner only, as role.yaml declares; fine.
- `mixed` style: 0 records (target 10%). `context` style survived 0 of 2. `formal` survived 2 of 7.
- Terse answers are all two-word; add one-word ("Morning", "Afternoon", "Both") and emoji-tailed
  variants if wanted.
- Every surviving Qwen record now carries one of three reviewer-written contexts; a top-up should
  generate its own varied contexts so the model does not key on those three strings.

Systematic teacher issues:
- Qwen 3.5: omitted `context` on 32 of 53 records of a follow-up intent; where present, prefixed
  it with "Mia:" and used robotic wording. Its `formal` style writes as the system or the office
  ("has been updated", "we have verified") instead of a polite cleaner; 5 of 7 dropped. Its
  `context` style invented an implausible Mia question and wrote text that only makes sense
  against it.
- Gemma 4: only 9 records, all `indirect`, all with the same context "Will you be off for the
  whole day?"; quality good (8 of 9 kept) but no style or context variety.

---

## dispatcher.absence_scope, fi (50 records, all split train)

### 1. Counts

| Teacher | kept | fixed | dropped | total |
|---|---|---|---|---|
| teacher:local/gemma4-mia | 0 | 4 | 5 | 9 |
| teacher:local/qwen3.5-mia | 0 | 10 | 31 | 41 |
| all | 0 | 14 | 36 | 50 |

No record is `kept` as is: every surviving record needed a context fix. Gemma's nine records all
carry the same context, "Miten pitäis ilmoittaa sun poissaolo tänään?", which is not a scope
question (it asks how to report, not whole day or part); rewritten on the four kept. Qwen's 41
records have no context at all; a Finnish Mia question was added to the ten kept. Four Qwen texts
also got a one-word grammar fix (0249, 0251, 0253, 0254, 0260, 0261 listed in the jsonl).

Main drop reasons:
- Garbled or invented Finnish, mostly Qwen (0221, 0222, 0224, 0225, 0226, 0228, 0230, 0232, 0236,
  0238, 0239, 0247, 0248, 0257, 0258, 0259): 16.
- Not a scope answer: past-tense arrivals or task reports, a question, Mia's own turn (0227, 0229,
  0233, 0234, 0240, 0241, 0242, 0255, 0256): 9.
- Unclear meaning (Gemma 0211, 0215, 0216; Qwen 0223, 0243): 5.
- Duplicates (0235 of 0222; 0244 and 0246 of 0242): 3.
- Overlap with report_absence (0212, 0217, 0252): 3, listed below.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.absence_scope/fi/local-gemma4-mia/0212 | dispatcher.report_absence | "Ei pääse tänään": text alone is a first absence report; no scope word; two labels (role.yaml look-alike: the first report, not the follow-up answer) |
| dispatcher.absence_scope/fi/local-gemma4-mia/0217 | dispatcher.report_absence | "Tänään ei onnistu": same as 0212, two labels |
| dispatcher.absence_scope/fi/local-qwen3.5-mia/0252 | dispatcher.report_absence | "Joululahjan vuoksi en pysty tulemaan töihin tänään": a first report with a reason slot, fits report_absence better (role.yaml look-alike); reason is also nonsense |

Same-action test: 0212 and 0217 do name the same action as a whole-day scope answer when the
context is present, so the developer may decide the context field makes them safe; they are
dropped here because the text carries no scope word and would train the model to read any
"can't today" as a scope answer. Kept records with "tänään" plus a scope marker (0210 "mitään",
0254 "vasta huomenna") are not listed. No record copies a conversation.yaml example and none is
a bare affirm, deny or greeting.

### 3. Coverage (what a top-up should generate)

Surviving cells: 14 records, all counterpart cleaner. Styles among them: indirect 5 (Gemma 4,
Qwen 1), informal 2, formal 5, mixed 2 (with no English words). Scopes covered: whole day 6,
morning only 5, afternoon only 3.

Missing:
- Styles `terse` (0 records: "koko päivä", "vaan aamu", "iltapäivä", "molemmat") and `typo`
  (0 records). `informal` puhekieli with scope words is nearly empty ("koko päivä pois", "pelkkä
  aamu", "ihan koko päivä", "aamun jutut vaan").
- `mixed` style with real English words ("whole day", "morning only", "aamu only").
- Visit-named scopes: answers that name the visits instead of a half day ("vaan se Kampin
  toimisto", "ekat kaks käyntiä", "kaikki paitsi koulu"), and counts ("molemmat", "kaikki kolme").
- Multi-day scopes ("tänään ja huomenna", "loppuviikon", "huomiseen asti") and the morning-late
  case ("tuun vasta iltapäivän käynteihin", "myöhästyn aamusta, iltapäivä onnistuu").
- Scope answers to a context that lists Mia's candidate visits ("1) Aalto 8.00 2) Kamppi 12.00,
  kummatkin?" answered with "ekaa vaan", "kakkonen").
- Varied Mia questions in context: the two surviving contexts are mine; a top-up should vary
  them (koko päivä vai osa, mitkä käynnit, aamu vai iltapäivä, listed visits).
- Hard negatives for this intent: bare "joo" / "ei" (conversation.affirm, deny) and re-reports
  without scope (dispatcher.report_absence) so the model learns the boundary.

Systematic teacher issues:
- Qwen 3.5: no context on any record for a follow-up intent; about 40% of texts are not Finnish a
  person would write (invented words: aamupäivystä, aamunpuute, aamupolua, osaamoin; "siisti" used
  as a verb); several records are Mia's turn (0255, 0256) or address "äiti"; the `mixed` cell has
  no English; three exact duplicates. The Finnish output of this teacher for this cell is not
  usable without review; prefer Gemma or a stronger model for the fi top-up.
- Gemma 4: one identical, off-target context on all nine records, and all nine are `indirect`
  (no other style survived the generation run); the texts themselves are natural puhekieli but
  several are too vague to carry a scope (0211, 0215, 0216).

---

## dispatcher.assign, en (113 records)

### 1. Counts

| Teacher | Split | Kept | Fixed | Dropped | Total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 0 | 0 | 15 | 15 |
| teacher:local/gemma4-mia | test | 5 | 0 | 0 | 5 |
| teacher:local/qwen3.5-mia | train | 51 | 14 | 28 | 93 |
| **All** | | **56** | **14** | **43** | **113** |

Main drop reasons:
- No named person, so the message asks for candidates: fits dispatcher.find_cover (24: all 15 gemma train records, 9 qwen).
- Stilted third-person Mia ("please have Mia get Clara to...", "tell Mia to have her...") while writing to Mia, often with off-domain vocabulary (patients, doctors, deliveries, drivers): 9 qwen.
- Ambiguous or not an assignment at all (status updates to a colleague, a yes to Mia's proposal, reordering visits, "mark the notes pending"): 10.

Fixes: 7 off-domain nouns swapped for a visit (audit, client demo, safety inspection, fire alarm drill, client call, patient, doctor); 3 third-person-Mia rewordings; 2 machine-sounding phrasings ("update his profile", "arrange for Emily to assign to cover"); 1 context aligned with the text (0398); 1 "warehouse shift with kate" reworded.

No slots declared for this intent and none in the records. No safety or real-person issues; names are common first names, places fictional.

### 2. Overlap suspects

| id (suffix) | Other intent | Rule or reason |
|---|---|---|
| 0358, 0359, 0360, 0361, 0362, 0363, 0364, 0365, 0366, 0367, 0368, 0369, 0371, 0372 (gemma train) | dispatcher.find_cover | Asks who can take the visit, no name given; role.yaml look-alike. Same action? No: searching for a candidate vs assigning a named one (rule 2, the narrower intent wins). |
| 0370 | dispatcher.find_cover (closest) | "Give me a heads up when someone agrees": a notification request, no name, no assignment. |
| 0404, 0410, 0418, 0425, 0460, 0464, 0466, 0469 | dispatcher.find_cover | "anyone free", "check with the team", "anyone else can cover", "pull someone off the other line", "the next person": no named person. |
| 0470 | dispatcher.find_cover (at best) | "want to reassign the field team?": no person, no visit. |
| 0447 | conversation.affirm | "yes lisa is in so roger is out for that one visit thanks mia" answers Mia's yes/no proposal; two labels possible. Context was also the supervisor's own earlier message, not a Mia question. |
| 0428, 0437, 0432 | dispatcher.cover_reply | "Mark, covering for Lisa?", "Dan, covering for Paul.", "Chris, taking over for Elena.": read as a cleaner's own reply as easily as a supervisor's assignment. |
| 0488 | dispatcher.find_cover | "Looks like Jordan's the only option left, right?": a question about options, not an instruction. |
| 0461 | none (other) | Swapping the order of two visits so Tom gets the morning: a schedule change, not assigning cover. |
| 0468 | none (other) | "make sure the notes say Pending until Chris answers": not an assignment. |

No record copies a conversation.yaml example; the catalogue has no assignment-like intent.

### 3. Coverage: what a top-up should add (dispatcher.assign, en)

Kept distribution after review: informal 16, terse 11, typo 13, indirect 8 (3 of them test), formal 10, mixed 7. Counterpart: supervisor only (correct per role.yaml).

Missing situations and phrasings:
- **Cleaning-company context.** Almost no record names a Finnish site or client type the dispatcher actually serves (school, office, stairwell, daycare, shop, "Aalto school", "Kamppi office"). Sites are "the Smith shift", "the Johnson family", "the downtown drop", "the community center run". Top-up should use fictional Finnish sites and cleaner names (Mikko, Aino, Jere, Sanna) alongside international ones.
- **Assign after a find_cover answer (context style).** Only 3 records carry context and one was dropped. Wanted: Mia lists candidates ("Mia: Aino and Jere are free at 14:00, who should I ask?") and the supervisor replies "Aino", "ask Jere", "the first one", "send it to Sanna". These short follow-ups are the realistic path to this intent and are absent.
- **Assign by reference, not by time.** Most records identify the visit by clock time ("the 2 PM slot"). Need: "Tiina's Tuesday visits", "the visit Mikko dropped", "the open one at Kamppi", "all of Anna's visits this week".
- **Multi-visit and whole-day assignment.** "Put Jere on all of Mikko's visits today", "Sanna takes the morning, Aino the afternoon".
- **Reassign / replace explicitly.** "Replace Mikko with Jere on the Lauttasaari job", "move the daycare from Anna to Sanna".
- **Assign with a question mark (polite instruction).** "Could Aino take it?" after Mia proposed options. Short, named.
- **Terse without the "Name, ..." template.** All 15 terse records used the pattern "Name, <slot>." (addressed to the cleaner). Wanted: "Jere → Kamppi 14", "assign Aino", "give it to Sanna", "Mikko takes it".
- **Mixed style with actual Finnish words**, since `mixed` for en should contain some Finnish: "put Aino on the Kamppi keikka", "assign Jere, hän on vapaa".
- **Indirect, named.** The kept indirect set is small (8). Wanted phrasings that imply the assignment: "Sanna said she can do it", "Jere's free after 3, that solves the Espoo one", "Aino offered to take Mikko's shift".
- **Web channel tone.** Supervisor writes on the web, so fewer "Hey Mia" openers and more dashboard-style one-liners.
- **Negative-space look-alikes for training the boundary**: a few hard find_cover messages that mention a name but still ask for candidates ("besides Jere, who else is free?") should be generated for find_cover, not here.

Systematic issues per teacher:
- **gemma4-mia (train, indirect cell):** all 15 records are find_cover, not assign. The indirect style was interpreted as "do not name the person", which removes the only feature that separates assign from find_cover. The gemma test records (0167-0171) got it right: indirect wording but a name. Regenerate the gemma indirect train cell with an explicit instruction that a named person is required.
- **qwen3.5-mia:** (a) frequent third-person Mia ("please have Mia...", "tell Mia to have her...") in the informal cell, 11 of 29 records; (b) domain drift to healthcare and logistics (patient, doctor, delivery route, driver, drop-off, audit, client demo, fire drill) in about 15 records; (c) the `mixed` cell has no mixed language and several records are status updates rather than instructions; (d) the `typo` cell mostly lacks typos (only missing apostrophes and lowercase). Fixes above restored 14; the top-up prompt should state the company cleans buildings in Finland and that the supervisor is writing to Mia.

---

## dispatcher.assign, fi (84 records)

### 1. Counts

| teacher | kept | fixed | dropped | total |
|---|---|---|---|---|
| teacher:local/gemma4-mia | 0 | 0 | 37 | 37 (30 train, 7 test) |
| teacher:local/qwen3.5-mia | 5 | 8 | 34 | 47 (all train) |
| all | 5 | 8 | 71 | 84 |

Survivors (13, all qwen): 0498, 0499, 0504, 0509, 0514 kept; 0490, 0494, 0496, 0502, 0503, 0506, 0522, 0528 fixed (text only, the name and the visit kept).
The whole test split (gemma 0172 to 0178) is dropped; the intent has no fi test rows left.

Main drop reasons:
- No named person, Mia is asked to pick someone: fits dispatcher.find_cover (29 records, all gemma except qwen 0536). Every gemma record either names nobody or is vague about tomorrow.
- Garbled or non-Finnish text (qwen 0491, 0495, 0500, 0507, 0511, 0516, 0519 to 0521, 0523, 0525, 0529, 0531, 0532, 0535; gemma 0388, 0392, 0399 and most of the test split: "katsely", "hoivattua", "Mekaannetaanpa", "annosta", "läsnäolohetki").
- Not an assignment: a time change (0493, 0497, 0510), an absence (0501, 0518), a room booking (0533), a statement of an existing schedule (0526, 0534), or nothing stated at all (0505, 0508, 0512, 0513, 0517).
- Template series and near-duplicates: gemma 0373 to 0387 are 15 variants of "voitko vaihtaa/laittaa tähän joku toisen"; qwen 0522 to 0531 are 10 variants of "Jarkko 15.5 klo 10" (two kept after fixing); 0514 = 0515; 0508/0513/0517.
- Vague indirect texts with no action (gemma 0393 to 0398, 0401): "Miten se huominen hoituu?", "Suunnitellaanpa se huominen reitti".

### 2. Overlap suspects

"Same action?" test applied: assign = tell Mia whom to put on the visit; find_cover = ask Mia to find someone. All rows below ask Mia to find or pick the person (no name, or the absent person's name only), which is the search, not the assignment. Role.yaml look-alike for dispatcher.assign: "dispatcher.find_cover (asking for candidates, no name yet)". None copies a catalogue example (the catalogue examples are English).

| id | other intent | rule or reason |
|---|---|---|
| local-gemma4-mia/0373 | dispatcher.find_cover | no name ("joku"), asks who fits; look-alike |
| local-gemma4-mia/0374 | dispatcher.find_cover | "jonkun toisen", no name; look-alike |
| local-gemma4-mia/0375 | dispatcher.find_cover | "joku toisen", no name; look-alike |
| local-gemma4-mia/0376 | dispatcher.find_cover | "joku toisen", no name; look-alike |
| local-gemma4-mia/0377 | dispatcher.find_cover | "joku toinen", no name; look-alike |
| local-gemma4-mia/0378 | dispatcher.find_cover | "joku nimen", no name; look-alike |
| local-gemma4-mia/0379 | dispatcher.find_cover | "toinen joku", no name; look-alike |
| local-gemma4-mia/0380 | dispatcher.find_cover | "joku toisen henkilon", no name; look-alike |
| local-gemma4-mia/0381 | dispatcher.find_cover | "joku toisen", no name; look-alike |
| local-gemma4-mia/0382 | dispatcher.find_cover | "joku toisen", no name; look-alike |
| local-gemma4-mia/0383 | dispatcher.find_cover | "joku toinen", no name; look-alike |
| local-gemma4-mia/0384 | dispatcher.find_cover | "joku toisen tyypin", no name; look-alike |
| local-gemma4-mia/0385 | dispatcher.find_cover | "joku toisen nimen", no name; look-alike |
| local-gemma4-mia/0386 | dispatcher.find_cover | "jonkun", no name; look-alike |
| local-gemma4-mia/0387 | dispatcher.find_cover | asks for a suggestion ("ehdotas"); look-alike |
| local-gemma4-mia/0389 | dispatcher.find_cover | "kuka pystyis hoitamaan", who could; look-alike |
| local-gemma4-mia/0390 | dispatcher.find_cover | "onko kenelläkö aikaa", who has time; look-alike |
| local-gemma4-mia/0391 | dispatcher.find_cover | "pitäisi saada joku", no name; look-alike |
| local-gemma4-mia/0396 | dispatcher.find_cover | "varata joku", no name; look-alike |
| local-gemma4-mia/0400 | dispatcher.find_cover | "kuka ottaa", who takes it; look-alike |
| local-gemma4-mia/0402 | dispatcher.find_cover | "jonkun sopivan", no name; look-alike |
| local-gemma4-mia/0172 (test) | dispatcher.find_cover | "joku muu", no name; look-alike |
| local-gemma4-mia/0173 (test) | dispatcher.find_cover | "sopiiko joku", no name; look-alike |
| local-gemma4-mia/0174 (test) | dispatcher.find_cover | visit still open, no name; look-alike |
| local-gemma4-mia/0175 (test) | dispatcher.find_cover | "jos joku saisi", no name; look-alike |
| local-gemma4-mia/0176 (test) | dispatcher.find_cover | "kun joku sopuu", no name; look-alike |
| local-gemma4-mia/0177 (test) | dispatcher.find_cover | "kuka siinä voisi olla", no name; look-alike |
| local-gemma4-mia/0178 (test) | dispatcher.find_cover | replacement for Pekka (the absent one), cover not named; also paraphrases the role.yaml description ("muuttuu heti kun hän hyväksyy") |
| local-qwen3.5-mia/0536 | dispatcher.find_cover | "mikä heistä on vapaampi", asks Mia to choose; look-alike |

Borderline, dropped as other reasons but worth knowing: 0493, 0497, 0510 (move a slot or time: no dispatcher intent, a reschedule), 0501 and 0518 (a supervisor says a cleaner is not coming: closest is report_absence, but role.yaml gives it to the cleaner, so `other`).

### 3. Coverage for dispatcher.assign, fi

What a usable fi assign set needs and this batch does not have:
- A named cover person plus an identifiable visit in most rows. Only the qwen informal set names anyone (Sanni, 23 times; Jarkko, 10 times). Vary the names (Finnish first names, both genders, a few foreign names common in cleaning: Maria, Ahmed, Olga) and name the visit by site, client or time: "laita Maria Kalevan koululle huomenna", "Jere ottaa Nordean aamukeikan", "anna Olgalle se Tampereen keskiviikon käynti".
- Replacement framing: "X Y:n tilalle" (X in place of Y), "X tuuraa Y:tä", "siirrä Y:n keikka X:lle", "vaihda X siihen Y:n paikalle". None survived.
- Supervisor style on web, not WhatsApp: shorter, no "Mia," prefix in every row (qwen put "Mia" in 40 of 47 rows), some all-lowercase, some with a trailing "kiitos".
- Styles missing after review: terse ("Sanni huomiseen", "Jere tuuraa", "laita Olga"), typo (both teachers' typo rows were gibberish, not typos: want "laiat Sanni huomsieen", "ota Jere siihe keikale"), formal with a real object ("Voisitko merkitä Jarkon huomisen klo 8 käynnin tekijäksi?"), indirect that still names the person ("Jere on vapaana huomenna aamulla, ja se Kampin keikka on vielä ilman tekijää"), mixed with English ("assignaa Sanni sille Friday slotille", "laita Jere coveriks").
- Situations: cover after a sick report ("Sini on kipeä, laita Sanni sen tilalle"), splitting a day between two people, assigning one person to several visits ("Jere ottaa kaikki Pasilan keikat tällä viikolla"), confirming a name Mia suggested ("joo, se Sanni, laita se") which should be checked against conversation.affirm as a follow-up, and a correction of an assignment ("ei Sanni vaan Sini") which belongs to conversation.correction and is a good negative.
- Counterpart: only supervisor (correct per role.yaml); a cleaner volunteering a colleague is `other` or find_cover, not needed here.
- Test split: 0 fi rows remain; the top-up must produce test rows too.

Systematic teacher problems:
- gemma4-mia wrote no names at all for this intent (37 of 37), so every row is find_cover or vague; it also used "tapaaminen", "kohtaaminen", "katsely" (meeting, encounter, a non-word) for a cleaning visit and produced garbled "typos" ("vaihdah", "tääne", "peitostaus", "Mekaannetaanpa"). Its indirect rows are translated-sounding ("Millaista suunnitelmaa pidetään"). Before a gemma top-up, the request should state that a message must contain the cover person's first name.
- qwen3.5-mia locked onto one name per cell (Sanni, Jarkko) and one time (15.5 klo 10) and produced many broken sentences (wrong verb forms, "läsnäolo" = attendance, "hoitaja" = nurse, a run of gibberish in the typo cell 0519 to 0521). Its context-style rows have no context field and are not follow-ups. Usable rows are the short informal ones ("Sanni hoitaa tänään", "anna Sannille kello 9–10").

---

## dispatcher.cannot_access_site, en

232 records (198 train, 34 test). No record carries slots (the intent declares none) and none
needs context (not a follow-up), so every decision is kept or dropped; nothing was fixed.

### 1. Counts

| source | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 98 | 0 | 1 | 99 |
| teacher:local/gemma4-mia | test | 30 | 0 | 4 | 34 |
| teacher:local/qwen3.5-mia | train | 88 | 0 | 11 | 99 |
| all | | 216 | 0 | 16 | 232 |

Main drop reasons:
- Test records that duplicate or near-duplicate a train record (4, all Gemma test): 0363 vs 0922,
  0366 vs 0947, 0373 vs 0953, 0376 vs 0958. Keeping them would inflate the test score.
- Incoherent or machine-sounding text (5, all Qwen): 1058, 1061, 1084, 1137, 1144.
- Too vague to carry the intent (2, Qwen terse): 1096 "blocked", 1100 "security on".
- Fits another label or two labels (4, Qwen): see section 2.
- Near-duplicate inside train (1, Gemma): 0976 vs 0950.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.cannot_access_site/en/local-qwen3.5-mia/1063 | other | "my apartment door" is the cleaner's own home, not a work site; outside every dispatcher intent |
| dispatcher.cannot_access_site/en/local-qwen3.5-mia/1070 | dispatcher.site_problem | "site is all blacked out" (no power) and "no one has a key": two labels, the action differs (record a power problem vs. get the cleaner in) |
| dispatcher.cannot_access_site/en/local-qwen3.5-mia/1077 | dispatcher.visit_details | not at the site; "I don't have the site code anymore" asks for the new code. Same action as a details question (give the code), the look-alike role.yaml names |
| dispatcher.cannot_access_site/en/local-qwen3.5-mia/1094 | dispatcher.site_problem | terse "site closed" reads as the site being shut (event, renovation) as much as a locked door; two labels |

Borderline but kept (listed for the developer, not dropped): records that report the code
fails AND ask for a new one (0928, 0948, 0982, 1017, 1019, 1109). The failing code is the
situation role.yaml describes ("wrong door code"), and a supervisor hears either way, so the
narrower intent wins. 1066 and 1148 ("don't have anyone's number", "how to contact security")
brush conversation.kb_who_to_contact but the message is a locked-out report first. No record
copies a conversation.yaml example; the nearest catalogue entries (kb_keys_security,
kb_who_to_contact, hazard_report, emergency) are questions or dangers, not a cleaner at a door.

### 3. Coverage and teacher notes

Missing for this intent in English:
- Finnish setting. Almost every record is generic or North American ("warehouse", "facility",
  "truck", "Smith Street", "Oak Street", "turnstile", "site 420"). Nothing mentions a
  taloyhtiö, a key box (avainboksi), an Abloy key, a cleaning cupboard key, a caretaker
  (huoltomies), an iLOQ fob, or Finnish place names. A top-up should ask for Finnish sites in
  English wording (English-speaking cleaners in Finland).
- Situations under-represented: key left at the office or with the previous cleaner; key box
  code wrong or key box empty; the client/caretaker was supposed to open and is not there;
  door opens but the alarm panel code is wrong (inside, alarm counting down); wrong building
  or wrong stairwell of a housing company; intercom/doorbell with no answer; access card
  expired; lift or stairwell door locked after hours; arriving at a client's home and nobody
  answers.
- Consequence phrasings: "do I wait or go to the next one", "I'll give it ten more minutes",
  "should I skip this visit", "I'm leaving if no one comes" (the report plus what the cleaner
  will do), and a cleaner saying it a second time ("still locked, anyone?").
- Time cues: "it's 6am and the door is locked", "nobody opens at this hour".
- Styles: the `typo` cells have almost no real typos, only dropped apostrophes and lower case;
  ask for misspellings and missing letters. The `mixed` cells are plain English (no Finnish
  words at all); for en the mixed style should carry a Finnish word or two (avain, ovikoodi,
  "the rappu door"). The `context` cells are ordinary messages with no context field; fine for a
  non-follow-up intent but they add no new coverage. More `terse` variety with a place
  ("locked out, Kamppi office") would help against check_in's location_name phrasing.
- Counterpart: only cleaners write this intent, as role.yaml says; nothing to add.
- Hard negatives for the look-alikes are thin in this file: a top-up for visit_details ("what's
  the door code for X"), key_location ("where's the key for X") and check_in ("at X, going in")
  is needed so the boundary is learnt from both sides.

Teacher notes:
- Gemma: clean, on-intent, varied situations (key, code, fob, keypad, alarm, gate, jammed
  door). Its only flaws are template reuse between the train and test files (the same "Hey, I'm
  at/outside the main entrance but the door is locked and I don't have the/a key" opener in 0922,
  0981, 1016, 0363, 0395 and the "Hello, I have arrived at the X Street location ..." formal
  opener in 0996 and 0387), which produced the four test leaks. Generate test rows with a
  different seed or filter against train before splitting.
- Qwen: more inventive but drifts into stories and incoherence (broken glass, security
  breaches, "reached the coordinates", a cleaner's own apartment) and its terse cells go too
  short to carry meaning ("blocked", "security on"). It also adds a second problem to many
  messages (blackout plus no key, broken window plus locked door), which makes labels ambiguous.
  Ask it for one problem per message and for a cleaner at a client site.

---

## dispatcher.cannot_access_site, fi

234 records: 200 train (100 per teacher), 34 test (Gemma).

### 1. Counts

| Teacher | Split | Kept | Fixed | Dropped | Total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 69 | 7 | 24 | 100 |
| teacher:local/gemma4-mia | test | 17 | 9 | 8 | 34 |
| teacher:local/qwen3.5-mia | train | 20 | 9 | 71 | 100 |
| **All** | | **106** | **25** | **103** | **234** |

Main drop reasons:
- Duplicates and templates (56): Gemma's informal cell repeats "Ovi on lukossa, en pääse sisään." / "En pääse sisään, ovi on lukittu." eleven times (1038 to 1050); Qwen's informal cell is five sentences cycled 30 times (1161 to 1185); Qwen's terse cell repeats Gemma's terse lines. Six test records duplicate or nearly duplicate train records (0398, 0406, 0407, 0408, 0425, 0429): a train/test leak, dropped from test.
- Not Finnish or garbled (40, almost all Qwen): invented words ("Alarmaattori", "hälyttymä", "kieltynyt", "Ovikoehdotus", "lukitusti"), wrong verb forms ("Oliin", "päästynyt", "auenna"), third person about self ("Oli jo paikalla"), and five typo-style texts that end "ei päästy ulos" (could not get OUT), contradicting the report.
- Translated or stilted formal text (5, Qwen): "Sijaintialueella", "avaus mahdotonta", "koodi päivitys vaaditaan".
- Overlap or wrong meaning (6): see section 2, plus 1194 "Oven lukko toimii" (says the lock works).

Fixes were small language repairs: a non-form ("ei avaa", "auenee", "ovit", "avautu") or a case error ("avaimen en löytänyt", "ovea ei aukea", "koodi ei tunnisteta") replaced with the natural form; typos in a non-typo style ("yrjytin", "peresalla", "ovakoodi"); one garbled phrase per text rewritten ("mun luulla", "avaintakumpua", "Sattuiko tässä ovi lukittua"). No slots exist for this intent and none were present. Context is not required (not a follow-up intent); the only context given (1254) was not a Mia question and the text was garbled, so it was dropped.

### 2. Overlap suspects

"Same action?" applied: a message that asks for the code or key is a read (visit_details, key_location), a message that reports the entry failed is this write. Both at once is two labels.

| id | other intent | rule or reason |
|---|---|---|
| local-gemma4-mia/1062 "Saisi avainta?" | dispatcher.key_location (or visit_details) | rule 2: asks for a key, reports nothing |
| local-gemma4-mia/1068 "mikä on ovi koodi???? ei toimi" | dispatcher.visit_details | two labels: leads with asking for the code, then says it fails |
| local-gemma4-mia/1069 "täällä on narko ja ei pääse sisään" | conversation.hazard_report / conversation.emergency | a person at the door, not a lock; safety precedence |
| local-gemma4-mia/1089 "En pääse perille." | dispatcher.report_absence (late, cannot reach the site) | different action: cannot travel there, not cannot enter |
| local-gemma4-mia/1056 "Pääsy estetty." | admin.reset_login | system wording, "access denied" reads as a login failure as much as a door |

Kept but close (not listed as drops): 1034, 0426, 0428 lead with the failed entry and then ask whether the code changed or whether there is another way in; the action is the report, the question is a natural follow-on. Keep an eye on them in the confusion list against visit_details.

### 3. Coverage: what a Finnish top-up needs

Situations covered: locked door, code rejected, no key, alarm goes off. Missing or thin:
- Key box / key safe (avainboksi, avainkaappi) with a wrong code or empty box; the key was not where it should be; key left at the office.
- Intercom / summeri nobody answers; reception closed; the client has not opened the gate.
- Wrong floor or wrong entrance found but still no way in; parking gate / barrier closed (only "portti kiinni" exists).
- Alarm: code accepted but alarm armed and cannot be disarmed; the alarm company calling. Only "hälytys meni päälle" variants exist.
- Night and weekend wording (ovet lukittu klo 18 jälkeen, viikonloppuna ei pääse); waited 15 minutes, what do I do; asking Mia to call the supervisor or client ("voitko soittaa asiakkaalle").
- Place names: not one record names the site (no slot, but natural messages say "Aalto-koulu" or "Kampin toimisto"). Add fictional Finnish site names in a share of the records so the classifier does not learn that this intent never carries a name.
- Styles: `mixed` records contain no English words at all (both teachers); a top-up should have a few ("door code ei toimi", "access denied ovella", "key box on tyhjä"). `typo` from Gemma is fine; from Qwen it was garbled, not typo-ed. `indirect` from Gemma is good ("Se ovi huutaa vaan", "Avainhuone on kiinni"); more of that kind (implied, no "en pääse sisään").
- Length: almost everything is one or two short sentences; add a few longer WhatsApp messages that tell the story (arrived, tried the code twice, alarm beeped, waiting outside) and a few past-tense reports written after leaving ("kävin mut en päässyt sisään, lähdin seuraavaan").
- Counterparts: all cleaner, which matches role.yaml (cannot_access_site lists only cleaner).
- Test split: after the leak drops the test set has 26 records; it needs a top-up of about 10 from a third model family, and the top-up must be deduplicated against train before it is accepted.

Systematic teacher problems:
- Qwen 3.5 (local): Finnish is not usable at this size for this cell. 71 of 100 dropped; the informal cell is five sentences cycled, the terse cell copies Gemma's lines, and the typo, indirect and formal cells produce non-words and sentences that say the opposite. Do not use it as a Finnish teacher without a stronger filter (or at all for fi).
- Gemma 4 12B (local): natural Finnish, but it loops on one sentence pair when asked for 30 in one call (11 duplicates in the informal cell) and writes `mixed` without any English. Ask for fewer per call or dedupe at generation time. Its test records partly repeat its train records, so test should come from a different family as the guidelines say.

---

## dispatcher.check_in, en (232 records)

### 1. Counts

| Teacher | Records | Kept | Fixed | Dropped |
|---|---|---|---|---|
| teacher:local/gemma4-mia (train, 100) | 100 | 70 | 19 | 11 |
| teacher:local/gemma4-mia (test, 32) | 32 | 24 | 2 | 6 |
| teacher:local/qwen3.5-mia (train, 100) | 100 | 35 | 53 | 12 |
| Total | 232 | 129 | 74 | 29 |

Main drop reasons:
- Near-duplicates and exact duplicates (16): mostly Gemma, whose short cells repeat "I'm here.",
  "On site.", "Checking in now.", "Just pulled up at the house" across styles. Six of these are
  test records that copy a train record (0246, 0248, 0250, 0270, 0275, 0277), which is a
  train/test leak; the test record was dropped and the train record kept.
- Slot placeholder leaked into the text (3, Qwen mixed cell): "Arrived at location_name."
- Machine-sounding or stilted formal text (5): "I have successfully arrived at the premises",
  "Arrival confirmed", "The visit has commenced", "I confirm my arrival and the beginning of my
  duties".
- Meaningless or ambiguous terse text (4, Qwen): "site", "there", "in progress", "done with
  check".
- Unnatural content (1): 0674 "They didn't put out enough trash".

Fixes are all slots (no text or context was changed):
- Gemma typo cell: all 15 records carried `location_name: ""`; the empty value was removed or
  replaced by the noun in the text (house, apt).
- Qwen informal cell: all 30 records name a place (Westside Apartments, Blue Sky Cafe, ...) with
  no slot; the slot was added.
- Slot policy applied to both teachers: `location_name` keeps a proper name or a site-type noun
  (house, office, clinic, gym); a placeholder that only means "the place I was sent to" (site,
  location, place, spot, premises, property, residence, building, unit, lobby, facility, center,
  client's place) was removed, and a leading "the " was stripped so spans match between the
  teachers (Gemma wrote "office", Qwen "the office").

### 2. Overlap suspects

No record fits another dispatcher intent or a catalogue intent better; the arrival message has
no near example in conversation.yaml. Two terse records would get two labels and were dropped:

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.check_in/en/local-qwen3.5-mia/0694 ("done with check") | dispatcher.check_out or dispatcher.checklist | "done with" reads as finishing (check_out look-alike) or a ticked item; not an arrival. Ambiguous, dropped |
| dispatcher.check_in/en/local-qwen3.5-mia/0707 ("in progress") | none clear | a status word, not an arrival; could as well follow a checklist question. Ambiguous, dropped |

Records kept despite a look-alike word, after the "same action?" test: 0690 ("I'll start
checking off the equipment", arrival first, the tick is future), 0709 ("let me know when you
want me 2 start", arrived and waiting, still an arrival), 0594 ("At the door.", arrival, no
access problem stated).

### 3. Coverage: what is missing for check_in / en

Situations not covered (every record is a plain on-time arrival at a single site):
- Late arrival stated at check-in ("here now, sorry, bus was late"), the overlap with
  report_absence (lateness) needs negatives on both sides.
- Arrival with a time ("got here 8:05"), arrival at the second or third visit of the day
  ("at the next one now", "second stop done, at Koivula now"), returning after a break.
- Arrival with a question or detail attached ("here, which floor do I start on", "arrived,
  client is home"), to keep check_in winning over visit_details or site_problem when the
  arrival is the main action.
- Arrival without entering yet ("outside, waiting for the client to open") versus
  cannot_access_site: a few records that are still check_in, not an access problem.
- Check-in via a photo or location pin with a few words ("here 📍", "[photo] arrived").
- Correcting a check-in ("checked in to the wrong visit", "forgot to check in, been here since 9").
- Finnish place names and site types: all names are US-flavoured (City Hall, Casino, Airport
  terminal B, 5th Ave, Smith residence). English-writing cleaners in Finland would name sites
  like "Aalto school", "Koivukatu 12", "the K-market", "the Kela office", "Nokia site".
- Terse arrivals that name a site ("Koivula", "aalto ✅", "here @ kela") rather than bare nouns.

Counterparts: only cleaner, which role.yaml declares; fine. A supervisor checking in on behalf
of a cleaner ("Maria is at the school now") is not covered; add a handful if that is wanted.

Styles: the informal, formal and indirect cells are full. `typo` from Gemma is light on real
typos (most records are only lowercase, no apostrophe); Qwen's typos repeat one pattern ("th e").
Emoji, voice-note transcript style and messages with a greeting first ("moi, here now") are
missing.

Systematic teacher issues:
- Gemma: short cells are repetitive (16 duplicates dropped, six leaking into the test split;
  the test split should be deduplicated against train before the next run). Typo cell wrote
  `location_name: ""` for every record. Placeholder nouns (site, residence) used as slot values.
- Qwen: never filled the slot in the informal cell although every record names a place; the
  mixed cell leaked the literal `location_name`; three terse records are not messages at all
  (site, there, in progress). The informal cell uses a fixed two-sentence template ("I'm at X
  now. I'll start with Y, <remark>") with US public buildings; they were kept with slots added,
  but a top-up should ask for Finnish sites and shorter messages. The indirect cell uses "we"
  throughout (team arrivals), which is useful variety but should not be the only voice.

---

## dispatcher.check_in, fi (218 records)

### 1. Counts

| Teacher (source) | Split | Kept | Fixed | Dropped | Total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 21 | 54 | 25 | 100 |
| teacher:local/qwen3.5-mia | train | 8 | 14 | 77 | 99 |
| teacher:local/gemma4-mia | test | 4 | 8 | 7 | 19 |
| **All** | | **33** | **76** | **109** | **218** |

Usable after review (kept + fixed): gemma train 75, qwen train 22, test 12.

Most "fixed" gemma records are a slot cleanup only: the teacher filled `location_name` with the
placeholder `"none"` (informal) or `""` (indirect, mixed, context, test); the slot is removed, the
text is untouched (note "ok; empty slot removed"). 19 fixes change the text (broken grammar,
misspellings outside `typo` style, anglicisms such as "visitin", "siivousprosessin").

Main drop reasons:
- Qwen informal (29 of 29): one template, `<interjection>, [Helsinki street address] <verb>`,
  with literal square brackets and real addresses (Mannerheimintie 50, Pohjoisesplanadi 11,
  Iso Roobertinkatu 22); five of them also mean the opposite (valmis, lähdin = check_out).
- Qwen typo (15 of 15): machine garbage ("pönttää", "alkuun", "Tuln"), slot values are random
  words from the text ("voin", "tullu", "oon").
- Qwen terse (15 of 15): a bare place name, mostly in the illative (Keskustaan, Matinkylään =
  heading there), no arrival and no context; one real shopping centre (Iso Omena).
- Not Finnish or not a word (gemma and qwen): "peresään" x3, "Mulla on nyt perilla", "Olla
  ollaan", "sinne saanu", "huoneen huomaan".
- Near-duplicates: 9 in train ("Aloitan nyt." appears 4 times across styles, "Täällä ollaan."
  3 times), plus 5 test records that duplicate a train record word for word (leakage) and 1
  duplicate inside test.
- Wrong meaning: "Oon jo kiinni" (busy), "Voin olla täällä", "tulen tänne nyt" (on my way),
  "Oltu paikalla" (past), "Siirryin sinne".
- Real organisation as the site: Turun yliopisto (0845), Iso Omena (0796).

### 2. Overlap suspects

"Same action?" applied: arriving and leaving are different actions, so check_in and check_out are
not an overlap of intents; the rows below are records whose text names the other action. Ids are
the last path segment under `dispatcher.check_in/fi/`.

| id | other intent | rule or reason |
|---|---|---|
| local-qwen3.5-mia/0764 | dispatcher.check_out | role.yaml look-alike: "oon valmis" = I'm done |
| local-qwen3.5-mia/0787 | dispatcher.check_out | look-alike: "valmis" = done |
| local-qwen3.5-mia/0789 | dispatcher.check_out | look-alike: "on valmis nyt" = done now |
| local-qwen3.5-mia/0768 | dispatcher.check_out | look-alike: "lähdin" = I left |
| local-qwen3.5-mia/0782 | dispatcher.check_out | look-alike: "lähdin nyt" = leaving now |
| local-qwen3.5-mia/0859 | dispatcher.checklist | look-alike: progress on one task ("alkanut tyhjentää keittiötä"), not an arrival |
| local-qwen3.5-mia/0826 | dispatcher.cover_reply | ambiguous: "pystyn aloittamaan nyt" is availability, not arrival |
| local-gemma4-mia/0639 | conversation.are_you_there | ambiguous: "Oon tässä" is a presence reply as much as an arrival |
| local-qwen3.5-mia/0778 | conversation.how_are_you | opens with "Mitä kuuluu?"; the rest is the address template |
| local-qwen3.5-mia/0770, 0784, 0788 | dispatcher.my_visits | "Tänään X oon/on" states today's site, not an arrival |
| local-qwen3.5-mia/0792 to 0806 (15) | ambiguous, no single intent | a bare place name answers absence_scope, visit_details or "where are you" equally; illative forms mean heading there |

No record copies a conversation.yaml example and none is a kb_* question.

### 3. Coverage: what a top-up for check_in / fi needs

Usable train data is 97 (75 gemma, 22 qwen) against the 100 target for a high-volume write
intent, and test is 12 against 30. Beyond the raw count, these cells are thin or empty:

- **Slot `location_name` with a natural, fictional site name.** Only the formal style carries a
  site name (gemma 0697 to 0706, qwen 0837 to 0846). Informal, terse and typo messages with a
  name are nearly absent: wanted "oon nyt Pihajärven koululla", "perillä Rantapuistossa, alotan",
  "Kivikko ✅". Teachers should use fictional names or generic site types (koulu, päiväkoti,
  toimisto, kerrostalo, kauppa), never Helsinki street addresses or real chains.
- **Terse style.** Survivors are 10 one-liners from gemma ("Perillä.", "Paikalla.", "Täällä.",
  "Aloitan."); qwen's whole terse cell was dropped. Wanted: "perillä 👍", "alotan", "sisällä",
  "paikalla, alotetaan", an emoji-plus-word, a time stamp ("perillä 7.02").
- **Typo style.** 7 gemma survivors, qwen none. Wanted realistic phone typos (missing umlauts,
  swapped letters, no punctuation): "oon perlla", "alotan nyt siivoksen", "paikala".
- **Mixed style.** No record has an English word; the style was treated as plain puhekieli.
  Wanted: "oon on site nyt", "check in, alotan", "arrived, alotan hommat".
- **Indirect style.** Most "indirect" records are direct ("Aloitan nyt."). Wanted real indirect
  arrivals: "ovi aukes vihdoin, pääsen töihin", "olipa ruuhka, mut nyt ollaan", "parkkipaikka
  löyty, menen sisään", "asiakas päästi sisään".
- **Context style.** Gemma left `context` empty; qwen's contexts named "Pasi", "Keittiö",
  "Huone" as the asker. Wanted a short Mia question ("Oletko jo kohteessa?", "Pääsitkö
  perille?", "Alkaako käynti?") followed by a natural reply ("joo, just tulin", "nyt ollaan").
- **Situations.** Late arrival ("myöhästyin 10 min mut nyt perillä"), arriving at the second
  visit of the day ("toinen kohde, alotan"), arriving with a colleague ("ollaan Marian kanssa
  paikalla"), arriving before the key holder ("paikalla, odotan talonmiestä", which must stay
  check_in and not drift into cannot_access_site).
- **Hard look-alikes for this cell** (so the classifier learns the border): "oon lähössä
  kohteeseen" (on the way, not arrived, is `other` or my_visits), "valmis" (check_out),
  "ovi ei aukea" (cannot_access_site), "pystyn tulla" (cover_reply).
- **Test split.** After dropping leakage and duplicates, 12 test records remain, all from gemma;
  the brief wants test from a third model family. A top-up of 20 test records from the third
  family should cover terse, typo, informal and formal with and without a site name.

Systematic teacher issues:
- Qwen 3.5 (fi): the informal cell is one template with bracketed real Helsinki addresses; the
  typo and terse cells are not Finnish; `location_name` is filled with any word from the text
  ("voin", "tällä", "paikalle"); contexts are not Mia questions. Qwen's Finnish is unusable for
  this cell without a stronger prompt (fictional names, no brackets, one example of a slot).
- Gemma 4 (fi): good puhekieli but fills `location_name` with "none" or "" instead of omitting
  it (99 of 119 records); recurring "Mulla on" for "Mä oon" (4 records); repeats the same
  short message across styles ("Aloitan nyt." x4, "Täällä ollaan." x3); formal cell is one
  template ("Olen saapunut perille X ja aloitan ..."); "mixed" cell has no English; test
  records duplicate train records (5 of 19).

---

## dispatcher.check_out, en (231 records)

### 1. Counts

| Teacher (source) | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 84 | 3 | 13 | 100 |
| teacher:local/gemma4-mia | test | 22 | 1 | 11 | 34 |
| teacher:local/qwen3.5-mia | train | 67 | 9 | 21 | 97 |
| all | | 173 | 13 | 45 | 231 |

Main drop reasons:
- Near-duplicates and template repeats (24): the same bare terse messages written by both teachers
  ("Done", "Finished", "Leaving now", "Out", "Done, thanks") and Gemma's frame "All done here at X.
  Heading out now." / "Done at X." reused with only the place swapped. 11 of the 34 test records
  are exact or template copies of a train record (test leak) and were dropped.
- Not a check-out (11): bare "Go", "Go now", "Exit", "End", "Wrap up", "Exit soon" (Qwen terse),
  "not finished yet" messages ("a few more minutes before we leave", "quick final sweep and we can
  wrap up"), "Moving on.", "Bye".
- Ambiguous label (6): check_in wording ("finished the check-in", "check in ... wrapped up"),
  checklist wording ("Done with the task", "the check is all done"), "signing off on this".
- Unnatural or garbled (4): "moving out of the office", "sunshine at Sunnydale is a go", "check is
  out of the airport", "Mia should wrap up the visit now,".

Fixes: slot values re-spelled to the typo in the text (3), one slot removed ("site"), one slash
alternative removed from the text ("next one/home"), and location_name added to the 8 Qwen mixed
records that name the site in the text without a slot.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.check_out/en/local-qwen3.5-mia/0890 | conversation.goodbye | word-for-word catalogue example "bye"; farewell, no finished visit (role.yaml look-alike) |
| dispatcher.check_out/en/local-gemma4-mia/0751 | dispatcher.checklist | "Done with the task." may be one item ticked; no leaving cue; two labels |
| dispatcher.check_out/en/local-qwen3.5-mia/0921 | dispatcher.checklist | "The check is all done on my end" reads as a checklist tick; two labels |
| dispatcher.check_out/en/local-qwen3.5-mia/0871 | dispatcher.check_in | "check in at Green Valley wrapped up" names the other action |
| dispatcher.check_out/en/local-qwen3.5-mia/0949 | dispatcher.check_in | "Just finished the check-in at the mall" names the other action |
| dispatcher.check_out/en/local-qwen3.5-mia/0928 | other | "signing off on this now if that's okay" reads as approving something, not leaving |
| dispatcher.check_out/en/local-gemma4-mia/0764 | other | "Moving on." has no finished-visit cue |
| dispatcher.check_out/en/local-qwen3.5-mia/0893 | other | "Go" |
| dispatcher.check_out/en/local-qwen3.5-mia/0897 | other | "Exit" |
| dispatcher.check_out/en/local-qwen3.5-mia/0899 | other | "End" |
| dispatcher.check_out/en/local-qwen3.5-mia/0900 | other | "Go now" |
| dispatcher.check_out/en/local-qwen3.5-mia/0901 | other | "Wrap up" reads as an instruction to Mia |
| dispatcher.check_out/en/local-qwen3.5-mia/0903 | other | "Exit soon": not finished, slot value absent |
| dispatcher.check_out/en/local-qwen3.5-mia/0926 | other (conversation.share_news) | "a few more minutes before we leave": the visit is not finished |
| dispatcher.check_out/en/local-qwen3.5-mia/0930 | other (conversation.share_news) | "quick final sweep and we can wrap up": not finished yet |

"Same action?" test applied: records that end the visit and also say goodbye or thanks
("done at cedar gardens. bye", "Done, thanks!", "Finished. See ya!") are one action (check-out)
and were kept; the goodbye is incidental. Records that name a cleaned area and then leave
("Finished the hall way and common area. Leaving.", "Finished with the floors. See you later.")
were kept as check_out: the leaving cue makes it the whole visit, not one checklist item.

### 3. Coverage: what is missing for check_out / en

Situations not present (or nearly):
- Leaving with something left undone or a caveat: "done, couldn't do the windows, no ladder",
  "finished but the client wants the hallway redone", "leaving, ran out of time for the kitchen".
- Leaving early or late with the time: "out at 14.10", "finished 20 min late", "leaving now, 16:05".
- Lock-up and key handling at departure: "locked up, key back in the box", "alarm set, door locked"
  (only "Shutters are down" and "let's lock up" exist).
- Check-out plus proof: "done, photos coming" (keep it check_out when the leaving is the main point;
  the send_photos boundary needs a few examples on each side).
- Check-out of a named Finnish site: every location is US-style (Central Park, Main St, Oak Ave,
  Smith residence). Countries: [FI]; sites should be Finnish (Kauppakeskus Sello, Tapiolan koulu,
  Hämeentie 12, Prisma Kerava, päiväkoti Vuokko) and include street addresses and client names
  (K-Market, Kela toimisto), not only "the clinic" / "the gym".
- Forgot to check out earlier (retroactive): "forgot to say, left Sello at 3", "oh I'm already home,
  finished the office an hour ago".
- Reply-to-Mia form: Mia asks "Are you still at Sello?" and the cleaner answers "no, done and gone".
  Style `context` (12 records) has no context field in either teacher; the style was treated as
  plain informal.
- Multi-visit day: "done with the first one, driving to the next" (only two such records).
- Single-person voice from Qwen: all Qwen records say "we", Gemma's all say "I"; the mix is fine
  but a top-up should ask Qwen for first person singular.

Phrasings and styles:
- Terse with a slot survives thin (Done at Central Park, Done at Pine Rd, All set at Main St);
  the terse Qwen cell was almost entirely bare one-word commands and was dropped. Ask for terse
  messages that carry the place or a time: "sello done", "out, kerava", "finished 1540".
- Typo style from Qwen has almost no typos (2 of 15); it is lowercase run-on text. Ask for real
  typos and missing letters, phone autocorrect errors, and emoji.
- `mixed` style in en is plain English for both teachers; if mixed means English with Finnish words
  ("done at the koulu, lähden nyt"), none exist.
- Indirect from Gemma is just shorter informal ("All done here.", "Leaving now."); real indirect
  check-outs are missing: "that's me for the day", "see you at the next one", "heading to the car".
- No messages with timestamps, emoji-only endings (✅, 👍 after "done"), or voice-note-like
  transcriptions ("ok so I'm finished now at the uh school").

Systematic issues per teacher:
- Gemma: reuses a handful of frames ("All done here at X. Heading out now.", "Done at X.",
  "Finished. Heading out.") across styles and across train/test, which caused the 11 test-leak
  drops; test should be regenerated from different frames. Two "moving out" records misread the
  intent as relocating.
- Qwen: the terse cell is unusable (one-word commands "Go", "Exit", "End"); the indirect cell drifts
  into not-yet-finished or third-person text; the mixed cell names the site in text but never fills
  the slot (fixed here); one slot value ("Store 5") was invented. Every informal record follows
  "<room or thing> at <Place> is <adjective>, we're leaving", which is varied enough to keep but a
  top-up should vary the frame.

---

## dispatcher.check_out, fi (230 records)

### 1. Counts

| Teacher | Split | Kept | Fixed | Dropped | Total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 47 | 24 | 29 | 100 |
| teacher:local/gemma4-mia | test | 6 | 10 | 16 | 32 |
| teacher:local/qwen3.5-mia | train | 9 | 16 | 73 | 98 |
| **All** | | **62** | **50** | **118** | **230** |

Usable after review: 112 (96 train, 16 test). Train target for a high-volume write intent is 100,
test 30, so train is just under and test needs a top-up of about 14.

Main drop reasons:
- Machine template (Qwen informal batch): 26 records are permutations of "Siivooja on valmis. /
  Siivooja on lähdetty. / Siivooja on siellä. / Siivooja on tehty työnsä." in the third person,
  not a cleaner checking out (1961 to 1986 inclusive, plus 0960).
- Broken or meaningless Finnish: 33 (Gemma: ootan, ootettu, setteli, "Tää on ovi", "Otan nyt
  takaisin"; Qwen terse and typo batches: "Lopu. Lähetetään.", "Siistiin", "tyhyn", "Aiemme",
  "Mekaanista pois").
- Duplicates and near-duplicates: 27, of which 11 are test records that copy a train record
  word for word or minus one filler (Valmis. / Done. / Lähden nyt. / Valmis tästä. / Lähden nyt
  kotiin. and five more). The Gemma typo batch is one template ("oon valmis täältä, lähden nyt")
  permuted nine ways.
- Translated-sounding or stilted formal text (Qwen formal and context batches): 9.
- Fits another intent or two labels: 14 (table below).
- Wrong or empty slot values were fixed, not dropped: 24 records had `location_name: ""` and 7 had
  `location_name: "paikasta"` (the word "place" in the elative, not a name). No record in the file
  carries a real location name; `location_name` is effectively unfilled in Finnish.

Fixes: 50. Mostly slot removal (empty or "paikasta"), "puhdistus" to "siivous" (a cleaner does
not say puhdistus), one-word Finnish errors in non-typo styles (hoitoit, hommattuna, menomassa,
Siivoppaja, Vieraillu, Ois, "oon siivottu" passive), and stilted formal endings
("Aloitamme poistumisen", "Siivousoperaatio").

### 2. Overlap suspects

Dropped because another label fits better, or two labels fit. "Same action?" test applied:
each row names a different action from finishing a visit, or no action at all.

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.check_out/fi/local-gemma4-mia/0862 | conversation.affirm | "Kunnossa." is a bare ok, no action (rule 2) |
| dispatcher.check_out/fi/local-gemma4-mia/0865 | conversation.affirm / conversation.goodbye | "Mennään." has no finishing signal; two labels |
| dispatcher.check_out/fi/local-gemma4-mia/0888 | conversation.goodbye | "Oli hienoa, mä lähen nyt." is a farewell, nothing about the visit (role.yaml look-alike) |
| dispatcher.check_out/fi/local-gemma4-mia/0855 | dispatcher.checklist | "Puhdas." alone reads as a tick or an answer; two labels |
| dispatcher.check_out/fi/local-gemma4-mia/0894 | dispatcher.checklist | "Se oli se viimeinen." can be the last item or the last visit; two labels |
| dispatcher.check_out/fi/local-gemma4-mia/0868 | dispatcher.check_in | "Heti lähden" can be leaving for a site; two labels |
| dispatcher.check_out/fi/local-qwen3.5-mia/0997 | dispatcher.check_in | "Valmiina. Lähdetään." means ready to start |
| dispatcher.check_out/fi/local-qwen3.5-mia/1003 | dispatcher.check_in | "ok siirrytään ulko-ovi 22B" is moving to a door, arriving not leaving (also 1011, 1016 duplicates) |
| dispatcher.check_out/fi/local-qwen3.5-mia/1004 | dispatcher.check_in | "käyn siivoamassa nyt" is going to clean, the start (also 1010 duplicate) |
| dispatcher.check_out/fi/local-qwen3.5-mia/0992 | conversation.affirm | "Hyvä. Poistutaan." no finishing signal |
| dispatcher.check_out/fi/local-qwen3.5-mia/1002 | conversation.affirm / conversation.goodbye | "ok mennään nyt" bare let's go; two labels |
| dispatcher.check_out/fi/local-qwen3.5-mia/1008 | conversation.goodbye | "ok siirrytään pois" leaving with no finishing signal (also 1013 duplicate) |
| dispatcher.check_out/fi/local-qwen3.5-mia/1045 | dispatcher.my_visits | "Näytä siivoukset." asks for the list (rule 2, a different action) |
| dispatcher.check_out/fi/local-qwen3.5-mia/0960 | none (not a cleaner intent) | third-person report that Matti left, not the writer checking out |

No record copies a conversation.yaml example and none is a kb_* question. Kept records that sit
close to conversation.goodbye but still name leaving the site or going home after work
("Lähden nyt kotiin.", "Mä lähden.", "Mun vuoro ohi.") were kept: a cleaner writing them to the
dispatcher is ending the visit, and the role.yaml terse style wants exactly these. If the
confusion report later shows goodbye leakage, these are the ones to look at first.

### 3. Coverage: what is missing for check_out in Finnish

Situations (almost every kept record is "valmis, lähden"):
- A named site: not one usable `location_name` in 230 records. Need texts like "Keskuskoulu
  valmis, lähen", "Lähden nyt Pihlajatieltä", "Prisma Kaleva tehty", with the name as the slot.
- Time of leaving: "lähdin 14.30", "oon pois klo 16", "lopetin just".
- Leaving with a remark that is not a problem: "valmis, jätin avaimen postilaatikkoon",
  "valmis, roskat vein", "ovi lukossa perässä", "hälyt päällä".
- Finishing early or late: "sain valmiiks etuajassa", "meni vähän yli mutta nyt valmis".
- Last visit of the day versus moving to the next site: "tää oli viimeinen tänään",
  "lähen seuraavaan kohteeseen".
- Check-out that mentions proof without attaching: "valmis, kuvat tulee kohta" is a hard
  look-alike for send_photos and should be generated for both intents with a written line.
- Negative look-alikes to generate on the other side: check_in ("oon perillä", "aloitan nyt"),
  checklist ("ikkunat tehty"), goodbye ("moikka, huomiseen").

Phrasings and styles:
- The kept set is heavy on "valmis" + "lähden"; wanted: "kuitattu", "lopetin", "homma paketissa",
  "ulkona nyt", "pois paikalta", "ovet kiinni ja lähdin", "siivous ohi tältä päivältä".
- `mixed` style has no English words in either teacher's output (only "Done"). Wanted: "finished,
  lähen", "kaikki ok, leaving now", "job done tältä päivältä".
- `typo` style from Gemma has few real typos; Qwen's are unreadable. Wanted: realistic phone
  typos on real check-out sentences ("vlamis, lähen nyt", "siivuos ohi").
- `terse` is well covered by Gemma; after dedup only one copy of each one-worder survives, so
  the test split lost all its terse records. Generate test terse records with different words
  ("Ohi.", "Loppu.", "Kuitattu.").
- `indirect` from Gemma is good (keys returned, lights off); more of that kind with site
  details.
- `formal` is thin after fixes: six kept. A few more complete-sentence Finnish records
  ("Hei, kohde on valmis ja poistun nyt") would do.
- `context` style: the intent is not a follow-up, so no context is required; the two
  teachers filled it with longer monologues. Short second sentences are enough.

Counterpart: cleaner only, as role.yaml says. Nothing from supervisors is needed.

Test split: 16 usable records remain of 32 (11 were word-for-word copies of train records). A
top-up of about 15 test records, generated with a third model family and deduplicated against
train before review, is needed.

Systematic teacher issues:
- Qwen 3.5 (fi): the informal cell collapsed into a 26-record third-person template
  ("Siivooja on ..."); the terse cell is broken Finnish ("Lähetään", "Siistiin", "Lopu"); the
  typo cell repeats three strings three times each; formal and context cells are translated
  English ("toiminta on nyt suoritettu", "tehneet kaikkemme tässä tilassa"). Only its
  indirect cell is usable (13 of 15 kept or fixed). Qwen's Finnish for this intent should not be
  used without a native filter, or the cell should be regenerated with a higher temperature and
  a duplicate check.
- Gemma 4 (fi): good puhekieli but a narrow template ("valmis, lähden" in 60 of 132), fills
  `location_name` with "" or a common noun in the mixed and formal cells, and uses "puhdistus"
  for cleaning. Its test cell reuses its own train strings, so test must be deduplicated
  against train at generation time.

---

## dispatcher.checklist, en

205 records (173 train, 32 test). The intent declares one slot (`item`) and is not a follow-up,
so no record needed a context; fixes are slot corrections and one text cleanup (a template
suffix the Qwen teacher leaked into ten messages).

### 1. Counts

| source | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 88 | 4 | 8 | 100 |
| teacher:local/gemma4-mia | test | 24 | 1 | 7 | 32 |
| teacher:local/qwen3.5-mia | train | 19 | 17 | 37 | 73 |
| all | | 131 | 22 | 52 | 205 |

Main drop reasons:
- Qwen `terse` cell (15 records, 1508 to 1522): one-word messages repeated ("checklist" x5,
  "done" x5) plus "broom", "cleaner", "dust", "check", "cleaned". Only the first "checklist"
  (1508) is kept; "done" and "cleaned" are two-label (see section 2), the rest carry no intent.
- Qwen `formal` cell (9 records, 1554 to 1562): one template, "I have ... the item 'X' ...",
  stilted and in three cases the item is not done ("will now check", "in progress").
- Progress notes where the item is NOT done (1393, 1452, 1533) or no item is named (1397, 1448,
  0554 "moving on to the next room"): nothing for Mia to tick or send.
- Wrong direction: the cleaner asks Mia whether Mia finished the work or needs the list (1526,
  1537, 0549) or how the restrooms smell (1536).
- Test records that duplicate train (3, Gemma test): 0537 vs 1392, 0547 vs 1389/1436, 0548 vs
  1437. Duplicates inside train or test (5): 1430, 1480, 1510/1514/1519/1522, 0561.
- Machine-sounding or off-domain items (1506, 1507 "floor plan", 1542 pen and paper, 1544
  gloves, 1548, 1565, 1574, 1576 temperature sensors).
- Fits another label or two labels (5): see section 2.

Fixes: slot value not in the text (1425 "Mopped", 1433 "floorin", 1446 "floorz", 1546 "under
the sink", 1567 "light fixtures"), an empty slot (1553), a slot added where the text names one
item (1444, 1529, 1530, 1532, 1573, 1575, 1577, 0552), and the " Item: X" suffix stripped from
the nine kept Qwen `mixed` records (1563 to 1572 minus 1565).

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.checklist/en/local-gemma4-mia/1407 | dispatcher.check_out | "Everything on the list is done": the whole visit, not one item; the look-alike role.yaml names. Same action? No: a tick on every item vs completing the visit; two labels |
| dispatcher.checklist/en/local-qwen3.5-mia/1509 | dispatcher.check_out | bare "done" (and its copies 1511, 1516, 1518, 1521): the visit or an item; two labels |
| dispatcher.checklist/en/local-qwen3.5-mia/1520 | dispatcher.check_out | bare "cleaned": same as "done"; two labels |
| dispatcher.checklist/en/local-qwen3.5-mia/1505 | conversation.affirm | "Got it, added the checklist items to my notes": an acknowledgement of the list Mia sent, no tick and no request (rule 2, no action) |
| dispatcher.checklist/en/local-qwen3.5-mia/1574 | dispatcher.check_out | "Room 204 ready" plus three ticks; the room-ready part is the visit finished; two labels |

Borderline but kept (listed for the developer, not dropped): the "what is left" questions
(1389, 1415, 1436, 1438, 1440, 0536, 0539) are requests for the remaining checklist, the read
half of this intent, not kb_* questions (they ask about this visit, not about rules). Whole-area
ticks ("Kitchen is clear and done" 1396, "Bedroom is good to go" 1459, "master bedroom is all
done and dusted" 0534) stay checklist: a room is one item on a visit checklist, and none says
the cleaner is leaving. No record copies a conversation.yaml example; the nearest catalogue
text is share_news "long day but finally done", which the bare "done" records brush, another
reason they are dropped.

### 3. Coverage and teacher notes

Missing for this intent in English:
- The site_problem boundary: no record says an item cannot be done because of the site
  ("can't do the windows, scaffolding outside", "skipped the kitchen, client was cooking"). A
  top-up for site_problem is needed so the classifier learns that side; and a few checklist
  records that skip an item for a non-site reason ("ran out of time for the oven, rest done")
  so "skip" is not always site_problem.
- Explicit "mark it" verbs are rare (1411, 1472, 0560, 0563 only); most ticks are implicit
  ("floors done"). More "tick/mark/check off X for me" and "X done, next" phrasings.
- Item types are narrow: rooms and surfaces. Add consumables and end-of-visit items that
  Finnish cleaning checklists carry: bins out, paper and soap refilled, keys back in the box,
  alarm set, lights off, windows closed, cleaning cart put away, dishwasher emptied, sauna.
- Asking for the checklist of a named site ("checklist for Kamppi office", "what's on the list
  at the taloyhtiö on Mannerheimintie") is almost absent (1442, 1479, 1524 only, all "lobby" or
  "office"). Finnish place and site names in English messages are missing entirely.
- Asking for the list before arriving ("send me tomorrow's checklist for X") and asking what a
  listed item means ("what does 'high dusting' mean on the list") are not covered.
- Two-item ticks ("kitchen and bathroom done") are rare (1467, 1534 only).
- Styles: Gemma's `typo` cells have few real typos (mostly "u", "r", lower case); Qwen's have
  more but drift ("da", "neda"). The `mixed` cells are plain English on both sides; for en the
  style should carry a Finnish word or two ("siivouslista", "roskat out", "the eteinen is
  done"). `context` cells are ordinary messages without a context field (fine, not a follow-up)
  but they add nothing new. The `terse` cell needs two-word ticks with an item, not one word.
- Counterpart: only cleaners write this intent, as role.yaml says; nothing to add.
- Test split after drops: 25 records, no `context` style and only 2 `terse`; the top-up should
  rebalance it and seed test generation differently so it stops copying train.

Teacher notes:
- Gemma: on-intent and natural; 92 of 100 train kept or fixed. Its weaknesses are a few
  progress notes without a tick (1393, 1397, 1448, 1452) and reuse between its train and test
  files (three test leaks, plus "done with the windows" twice in test). Its items are generic
  (floors, windows, kitchen, bathroom, dusting, vacuuming repeat many times); ask for a wider
  item list.
- Qwen: systematically weak in three cells. `terse` collapsed to single repeated words;
  `formal` used one quoted-item template for all ten; `mixed` appended "Item: <slot>" to the
  text (slot leakage, fixed by stripping). Its `indirect` and `context` cells are usable but
  wander off cleaning (thermostat, temperature sensors, first aid kit, outlet plugs, floor plan)
  and several messages are addressed the wrong way (asking Mia whether the work is done). Ask it
  for cleaning items only, a message a cleaner sends to Mia, and no slot echo in the text.

---

## dispatcher.checklist, fi (232 records)

### 1. Counts

| Teacher (source) | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 53 | 20 | 27 | 100 |
| teacher:local/gemma4-mia | test | 13 | 4 | 17 | 34 |
| teacher:local/qwen3.5-mia | train | 7 | 15 | 76 | 98 |
| **all** | | **73** | **39** | **120** | **232** |

Main drop reasons (approximate, a record can hit several):
- Unnatural or nonsense Finnish (invented words such as "tikkautettu", "pyydytettynä", "astiatuuliset", "Kiepit", "lattiapäällä"; broken case and sentence structure): about 85, of which about 65 are Qwen.
- Not a checklist action: statements about what a list contains, proposals to draft a list, messages in Mia's voice ("mitä sinun on tehtävä"), reports of dirt or of furniture moved: about 15 (nearly all Qwen).
- Fits dispatcher.check_out better (whole visit done: "Kaikki hommat valmiit", "Valmis", "siivous ois done", "Siivoitus valmis", "valmiina"): 7.
- Two labels (check_in + checklist, check_out + checklist, send_photos + checklist): 3.
- Near-duplicates: 8, of which 4 are Gemma test records that repeat a Gemma train record word for word ("Pöydät on pyyhitty", "Mitä seuraavaksi?", "Keittiö on kunnossa", "Keittiö ok"), a train/test leak.
- Vague without context ("Tätä on tehty", "se osa on nyt kunnossa", "Miten mulla menee?", "Onko vielä jotain muuta?"): 6.
- Context-style records with no context or with a context that is not a checklist question: 6 (all but one Qwen).

Fixes were mostly slot values not present in the text (nominalised forms such as "pöytien pyyhkiminen" for "Pöydät on pyyhitty"), single wrong words ("imety", "hoitoit", "hommattu", "suunnellusti", "kohtija") and odd openers ("Kiva,", "Oikee,", "Saa olla,").

### 2. Overlap suspects

"Same action?" test applied: a record is listed only when the agent would do something else (complete the visit, start the visit, attach a photo) rather than tick an item or show the list. Records that name the list explicitly ("kaikki listan kohdat on tehty", "Checklisti on tehty") were kept as checklist (ticking everything), since the action is still a tick.

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.checklist/fi/local-gemma4-mia/1487 | dispatcher.check_out | "tehtiin siivous valmiina": whole cleaning done, look-alike in role.yaml (rule 2, narrower action is check_out) |
| dispatcher.checklist/fi/local-gemma4-mia/1498 | dispatcher.check_out | "Kaikki hommat valmiit." whole visit done, no item or list named |
| dispatcher.checklist/fi/local-gemma4-mia/1531 | dispatcher.check_out | bare "Valmis": whole visit done; also reads as a context reply (two labels) |
| dispatcher.checklist/fi/local-gemma4-mia/1534 | dispatcher.check_out | "siivous ois done": the cleaning, not an item |
| dispatcher.checklist/fi/local-gemma4-mia/1573 | dispatcher.check_out | "Puhdistus valmis, tikattiin kaikki kohdat." two labels: visit done and all ticked |
| dispatcher.checklist/fi/local-gemma4-mia/0592 | dispatcher.check_in | "oon nyt siellä" (arrived) plus a checklist question, two labels |
| dispatcher.checklist/fi/local-gemma4-mia/0567 | dispatcher.send_photos | "Lähetän kuvan checklististä": a photo is coming, two labels |
| dispatcher.checklist/fi/local-gemma4-mia/0574 | dispatcher.check_out | "Siivoitus valmis": whole cleaning done |
| dispatcher.checklist/fi/local-qwen3.5-mia/1606 | dispatcher.check_out | bare "valmiina", slot item not in text |
| dispatcher.checklist/fi/local-gemma4-mia/1546 | conversation.confusion | "mulla on lista, mut ei oo varmoa onko tää se": unsure which list, no tick or request |

No record copies a conversation.yaml example and none is a kb_* question. Note for the developer: short "X tehty / X ok" ticks (kept) are close to conversation.share_news example "long day but finally done" only when nothing is named; every kept tick names an item.

### 3. Coverage for dispatcher.checklist, fi

Surviving set (112 kept+fixed) is dominated by one shape: "<item> on tehty / ok / valmis" (about 65) and "mitä vielä jäi / lähetä lista" (about 25). Missing or thin, in order of value for a top-up:

Situations
- Ticking several items in one message ("vessat ja keittiö tehty, lattiat vielä kesken") and partial progress ("tiskit tehty mut lattia jäi", only one survives).
- Asking for the checklist of a named site or visit ("mikä on Kallion toimiston lista", "onko huomisen käynnillä jotain erikoista listalla"); every surviving ask is "se lista" with no site.
- Asking whether a specific item is on the list or required today ("kuuluuko ikkunat tänään", "pitääkö jääkaappi tehdä").
- Correcting a tick ("ruksasin vahingossa uunin, se ei oo tehty") so the classifier sees the checklist vocabulary with an undo flavour (and the developer can decide whether that is conversation.correction).
- Finishing the last item without closing the visit ("viimenen kohta tehty, lähden kohta"), the hard boundary with check_out.
- An item that could not be done because of the site (the site_problem look-alike) is absent from the negative side; the top-up for site_problem should include "ikkunat jäi, kun vesi oli poikki" type texts so the boundary is learnt.
- Checklist items beyond kitchen, floors, windows and dust: toilets, bins, refilling consumables (saippua, paperit), mopping stairs, cleaning glass doors, emptying dishwasher, changing bins in offices. Only a handful survive.

Counterparts and channel
- All records are cleaner. role.yaml lists cleaner only, so no supervisor cell is needed, but a cleaner addressing Mia by name ("Mia, lista?") appears only once.

Phrasings and styles
- `typo` cell is weak: Gemma's typos are mostly invented words rather than phone typos (missing letters, swapped letters, no ä/ö: "lattiat tehty, keittio kesken", "ikkunat valmiit, mita seuraavaks"). Qwen's typo cell contained no typos at all (formal full sentences in Mia's voice).
- `indirect` cell: surviving indirect texts are mostly plain ticks. Need genuinely implied requests ("en nää mitä listalla on", "en muista oliko parveke mukana", "tää on tehty, vai mitä sulla lukee").
- `context` cell: only 5 usable follow-ups, all Gemma. Need replies to "Onko X tehty?", "Mitä on vielä kesken?", "Haluatko että merkkaan kaikki tehdyksi?" in puhekieli ("joo se on tehty", "ei vielä, teen sen viimeiseks", "kaikki paitsi vessat").
- `terse` cell: good coverage of "X ok" but no bare ask variants beyond "Checklisti?" ("lista?", "mitä jäi?", "seuraava?").
- `mixed` style: only two with English words ("checklisti", "tikkaan"); add "done", "check", "list" mixes ("keittiö done", "voitko sendaa listan").
- Emoji ticks (✅, 👍 after an item) appear once.

Systematic teacher problems
- Qwen 3.5 (fi): 76 of 98 dropped. It invents Finnish words, writes in Mia's voice ("Tässä on listan viimeinen kohta, mitä sinun on tehtävä"), addresses a third person "Matti" instead of Mia, uses a nominalised slot value that never appears in the text ("pintojen pölyttäminen" for "pölytys ok"), and repeats records verbatim (1631/1634, 1632/1635, 1602/1592). Its terse cell is almost entirely nonsense. Its context cell wrote contexts that are not checklist questions ("onko matto likana"). A Qwen fi top-up for this intent is not worth running without a stronger constraint; the informal and formal cells are the only ones with partial yield.
- Gemma 4 (fi): usable, but the test split repeats train texts word for word (4 of 34), slot values are nominalised instead of quoted from the text (about 10 fixes), and its typo cell produces invented words rather than typos. Several "whole visit done" texts landed in checklist instead of check_out.

---

## dispatcher.cover_reply, en (153 records: 119 train, 34 test; all counterpart cleaner)

### 1. Counts

| Teacher | Records | Kept | Fixed | Dropped |
|---|---|---|---|---|
| teacher:local/gemma4-mia (train) | 56 | 48 | 7 | 1 |
| teacher:local/gemma4-mia (test) | 34 | 33 | 0 | 1 |
| teacher:local/qwen3.5-mia (train) | 63 | 0 | 28 | 35 |
| Total | 153 | 81 | 35 | 37 |

Fix reasons:
- Follow-up with no `context` (32: Gemma formal 0448 to 0454, Qwen informal, typo and mixed).
  A short Mia cover question was added (Finnish fictional sites and first names); text untouched
  except where noted.
- Context was a colleague's message ("Can you cover for me on my shift today?"), not a Mia
  question (3: Qwen 0596, 0597, 0599). Replaced.
- Text corrected in 4 Qwen records (0552 "counting on me" to "count on me", 0564 "truck" to
  "traffic", 0568 "in a shot" to "in a bit", 0572 truncated "im almost" completed).

Drop reasons:
- Wrong speaker, 25 (all Qwen): system or dispatcher voice reporting a reassignment. Terse
  0555 to 0563 ("Decline. Reassigned.", nine near-identical template lines), formal 0582 to 0588
  ("Acknowledged. The task is now being reassigned"), indirect 0573 to 0581 (the office handing
  the visit to someone else, "Switching it over to Anna for you").
- Confused addressee or nonsense, 8 (Qwen 0537, 0539, 0541, 0544, 0547, 0549, 0551, 0594,
  0598): Mia treated as a person at the site or as the one being sent.
- Ambiguous, 3: Gemma 0425 and 0189 ("Done" to a cover request), Qwen 0595 (a status line, no
  accept or decline).

### 2. Overlap suspects

Same-action test applied. Dropped records that fit another intent or would get two labels:

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.cover_reply/en/local-qwen3.5-mia/0574 | dispatcher.assign | "Switching it over to Anna for you": names the person who takes the visit, that is the assign action (rule 3, same action whoever writes it) |
| dispatcher.cover_reply/en/local-qwen3.5-mia/0577 | dispatcher.assign | "I've assigned it to another person": a statement of the assign action, no accept or decline |
| dispatcher.cover_reply/en/local-gemma4-mia/0425 | dispatcher.check_out / dispatcher.checklist | "Done" answers "finished?" as readily as "can you cover?"; two labels |
| dispatcher.cover_reply/en/local-gemma4-mia/0189 | dispatcher.check_out / dispatcher.checklist | "Done." same as above (test split) |
| dispatcher.cover_reply/en/local-qwen3.5-mia/0595 | none clear | "switched over to my route now": status, no cover answer; would not be labelled cover_reply by a reader |

Kept but listed for the developer (word-for-word catalogue examples, kept because role.yaml
says a yes or no to a cover request is this intent and the trainer embeds `context` with the
text, so the pending question separates them from the bare conversation examples):

| id | catalogue intent | text |
|---|---|---|
| dispatcher.cover_reply/en/local-gemma4-mia/0423 | conversation.affirm | "Sure" (example "sure") |
| dispatcher.cover_reply/en/local-gemma4-mia/0424 | conversation.deny | "No thanks" (example "no thanks") |
| dispatcher.cover_reply/en/local-gemma4-mia/0429 | conversation.affirm | "Yeah" (near "yep") |

If the trained model confuses these with affirm/deny, drop the three rather than relabel.

No kb_* questions, no greetings, no report_absence look-alikes (every decline gives a reason
for this visit, none reports a day off).

Train/test closeness worth knowing (not duplicates by the modulo-punctuation rule): test 0201
"Sure thing, I'll head over there." vs train 0433 "sure thing ill head over there now"; test
0181 "Sure thing, I'll head over now." vs the same 0433. Gemma reuses "Sure thing", "I can take
that one", "Send me the details" across cells, so the test split measures these phrasings
generously.

### 3. Coverage: what a top-up should add (en, cover_reply)

What survives is 81 kept + 35 fixed = 116 records, about 60% accepts and 40% declines, almost
all from Gemma with the same context "Can you cover the Smith job ...". Missing:

Situations
- Conditional or partial answers: "yes if it's after 4", "I can do the morning one but not both",
  "only if someone drives me", "yes but I'll be 20 min late". None present.
- Questions back before answering ("where is it?", "how long does it take?", "is it paid as
  overtime?") that still read as a cover reply; today the few that ask for details already accept.
- Accept with a counter-proposal of time ("can I do it at 5 instead of 3?").
- Declines without a reason ("no", "not this time") beyond the two terse ones; declines citing
  childcare, a doctor's appointment, being on sick leave, no car, too far.
- Accepting a visit for several days ("I can do all three days") or declining one of several.
- Replies to a cover request for a named Finnish site or client (Virtanen, Keskuskatu): every
  Gemma context names "Smith" or "Miller" and one says "Soho"; contexts should sound like Mia in
  Finland (office, school, daycare, apartment, address) and vary.
- Replies that mention the colleague ("tell Jonna I've got it", "is Sami ok?").
- Late or changed answers ("actually I can't anymore", "I said no but I'm free now"): useful
  but check them against conversation.undo / correction before adding.

Counterparts and channel
- Only cleaner, as role.yaml declares. Nothing to add there.

Styles
- `mixed` for en should carry a Finnish word or two ("joo I can take it", "ei onnistu sorry,
  busy"); the 11 mixed records are plain English.
- `indirect` is nearly direct ("I'm good for that one"); real indirect declines ("my kid is home
  sick today", "I'm in Tampere till Sunday") and indirect accepts ("what's the door code?",
  "which floor?") are missing.
- `typo` from Qwen is all accepts and all "on my way" phrasing; typo declines are missing.
- `terse` survivors are 11; add "ok", "yes", "nope", "fine", "k", "cant", "no sorry" with a
  cover context, since role.yaml wants bare yes/no with context to be this intent.
- Emoji-only or emoji-led replies (a thumbs up, "👍 on it") are absent.

Systematic problems by teacher
- Qwen (63 records): 35 dropped, 28 fixed, 0 kept as written. It never filled `context` for a
  follow-up intent, and in the terse, formal and indirect cells it wrote as the dispatcher or
  the system ("Visit reassigned", "sending it to another cleaner"), not as the cleaner
  answering. Its informal cell confuses who is talking to whom (Mia as a person at the site).
  For a top-up give Qwen the context in the request or do not use it for follow-up intents.
- Gemma (90 records): usable, but one context per cell copied across every record in that cell
  (18 records share "Can you cover the Smith job on Thursday?"), and English-speaking-world
  names (Smith, Miller, Soho) instead of Finnish ones. Vary the context per record.

---

## dispatcher.cover_reply, fi (159 records)

### 1. Counts

| Teacher | Split | Kept | Fixed | Dropped | Total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 15 | 35 | 13 | 63 |
| teacher:local/qwen3.5-mia | train | 0 | 5 | 58 | 63 |
| teacher:local/gemma4-mia | test | 3 | 25 | 5 | 33 |
| **All** | | **18** | **65** | **76** | **159** |

Surviving (kept + fixed): gemma train 50, qwen train 5, gemma test 28. Total 83.

Main drop reasons:
- Garbled or meaningless Finnish (not something anyone types): 56, of which 51 are qwen. Qwen's output is
  almost entirely unusable for this cell: route-change templates ("reitti muuttu, käydäänkö?", 0606-0617),
  meta text about "Mian pyyntö" being accepted (0636-0644), "varaus" templates (0653-0658), and one-word
  replies to invented contexts (0618-0626).
- Bare affirm / thanks that would get two labels (overlap, listed below): 6.
- Near-duplicates: 5 (0485, 0492, 0501, 0620, 0244).
- Ambiguous accept-and-decline in one message: 1 (0520).
- Not a cover reply (question about a reassignment, "I'll send it"): 3 (0601, 0659, 0496).
- Test record whose only natural fix would duplicate a train record: 1 (0225).

Main fix reasons (65):
- Context missing (indirect cells 0495-0503, all surviving qwen records): 14.
- Context present but not a plausible cover question from Mia: 46. Gemma reused one bad context per
  style cell: "kaukopäältä tai siirtää sen jollekin toiselle" (typo cell), "kysymystä varten" (formal),
  "täällä olevan siivouspäivän" (mixed), "löytyis muulle työpäivä" (context), "katsoa mun työtä kello
  14:00" (test informal), "korvata minulle" (test typo, means compensate), "Mia kysyi voiko..." (test
  indirect, a narration not a question), "Mia: Voitko kattaa" (test mixed, prefix and anglicism).
- Text fixes: 17, mostly single-word grammar ("ei menee", "multa", "kiireinenä", "oon jo lomaa",
  "lounaasta jäljellä", "varoittamisella") and Mia-does-that clauses removed from formal accepts
  ("sisäänkirjaudun järjestelmään", "päivitin tilan järjestelmässä", "Muutin varauksen sitten").
- No slots declared for this intent and none were filled; nothing to fix there.

### 2. Overlap suspects

All six are bare one-word replies. role.yaml says "a yes to a cover request is this intent, not a bare
affirm", but the classifier sees text only, and conversation.affirm's description already routes a yes
with a pending question through the resolver. Both labels fit the text, so they are dropped and listed
rather than relabelled; if the developer decides bare yes/ok with cover context belongs here, 0477 and
0480 can be restored (0623 and 0625 only with their contexts rewritten). "Sopii", "Ei pysty", "Ei käy",
"Mä voin" and the like were kept: they state capacity for the visit, which a bare "ok" does not (same
action test: accepting a visit vs acknowledging).

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.cover_reply/fi/local-gemma4-mia/0477 | conversation.affirm | "Ok" is word-for-word the catalogue example "ok"; two labels |
| dispatcher.cover_reply/fi/local-gemma4-mia/0480 | conversation.affirm | "Selvä" = catalogue example "alright"; two labels |
| dispatcher.cover_reply/fi/local-qwen3.5-mia/0623 | conversation.affirm | "OK." copies the catalogue example "ok"; two labels; context also nonsense |
| dispatcher.cover_reply/fi/local-qwen3.5-mia/0624 | conversation.affirm | "Hyvä." bare affirm; context nonsense |
| dispatcher.cover_reply/fi/local-qwen3.5-mia/0625 | conversation.affirm | "Joo." = catalogue example "yes"; context is the cleaner asking Mia |
| dispatcher.cover_reply/fi/local-qwen3.5-mia/0626 | conversation.thanks | "Kiitos." is a bare thanks, says nothing about the visit |

No record fits dispatcher.report_absence better: every decline refuses the offered visit without
reporting an absence of its own. No kb_* questions in this file.

### 3. Coverage gaps (fi, dispatcher.cover_reply)

After review: 83 records (55 train, 28 test). Train needs 60 minimum for a follow-up intent, so a top-up
of 20 to 40 train records is needed, and the target should favour the cells below. Test (28) is close to
the 30 target; 2 to 5 more test records would do.

Situations missing or thin:
- Conditional accepts: "voin jos joku vie avaimen", "joo mut vasta klo 17 jälkeen", "otan jos saan
  huomisen vapaaks". Only 0521 touches this.
- Accepts that ask a practical follow-up in the same breath: "joo, mikä ovikoodi?", "ok, onko siellä
  välineet?" (these should stay cover_reply, the accept is the action).
- Declines with a concrete reason other than "full": childcare, bus connection, already on the other
  side of town, own visit overrunning, not qualified for that site (window cleaning, floor machine).
- Declines that name someone else: "kysy Marialta, se asuu lähempänä" (decline, not assign).
- Late replies: "sori näin vasta nyt, pääsen vielä jos tarviit".
- Accept of part of the request: "voin ottaa aamun mut en iltaa".
- Replies to a request with a named colleague and site in the context (contexts are now varied, but the
  texts rarely echo the name or place: "Maijan kohde onnistuu", "Kamppiin pääsen").
- Emoji-only or emoji-heavy accepts (thumbs up plus a word), common on WhatsApp.

Styles:
- `terse` accepts: nearly all terse one-word yeses were overlap drops; need two-to-three-word terse
  accepts ("joo pääsen", "otan sen", "käy mulle", "mä hoidan") and terse declines beyond "ei pysty / ei
  ehdi / ei käy" ("en pääse", "en kerkee", "ei onnistu").
- `typo`: the surviving typo texts are mild; need realistic phone typos (missing ä/ö dots, swapped
  letters, no spaces) in longer replies.
- `mixed`: only "Sorry" appears; need "ok otan sen, no problem", "sure pääsen", "can't, oon Espoossa".
- `formal`: fine on count but all are one-sentence; one polite decline with an alternative day is missing.
- `indirect`: declines are fine ("Tää menee toiselle", "Joku muu hoitaa tän"); indirect accepts are thin
  ("Käyn siinä", "Hoidetaan" only).

Counterparts: cleaner only, as declared; nothing to add.

Systematic teacher issues:
- qwen3.5-mia: 58 of 63 dropped. It did not understand the cell. Its texts are about route changes,
  bookings and "Mia's request" in the abstract, its contexts are the cleaner addressing Mia, and no
  record was native Finnish. Do not use it for Finnish follow-up cells without a worked example in the
  prompt; or drop it as a Finnish teacher for this role.
- gemma4-mia: texts are mostly good puhekieli, but it writes one context per style cell and that
  context is often wrong (compensate instead of cover, a narration instead of a question, a "Mia:"
  prefix). The generator prompt should ask for a different context per message and give one example of a
  Mia cover question. Its formal accepts add clauses about logging in or updating the system; the prompt
  could say the cleaner only answers, Mia records.

---

## dispatcher.find_cover, en (87 records)

### 1. Counts

| source | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 32 | 2 | 0 | 34 |
| teacher:local/gemma4-mia | test | 24 | 0 | 0 | 24 |
| teacher:local/qwen3.5-mia | train | 26 | 0 | 3 | 29 |
| total | | 82 | 2 | 3 | 87 |

Drop reasons (all Qwen): unnatural or stilted text (0339 "so sorry about the client call" has no
referent; 0345 "supervisors who could cover today visit?" is unreadable; 0356 "compromised by the
cleaner's unavailability" is machine-sounding). No label drops, no language drops, no slot
problems (the intent declares no slots and no record carried one), no safety drops (Brooklyn,
Oak Street, Mornington Peninsula are places, not a person's data).

Fixes (both Gemma, style `context`): 0322 and 0323 carried a `context` that was the supervisor's
own message ("We just lost the cleaner ... Can someone else step in?"), not a Mia turn. Replaced
with a plausible Mia notice ("Anna has reported sick. Her 2 PM visit at the Smith residence is
now uncovered.") so the text reads as a reply to it. find_cover is not a follow-up intent, so an
empty context would also have been acceptable.

### 2. Overlap suspects

None dropped for fitting another intent, copying a catalogue example, or taking two labels.

Considered and kept after the "same action?" test:

| id | other intent | why kept |
|---|---|---|
| 0303 "Who's free?" | dispatcher.who_is_working | asks for availability, not who is on shift; same action as the search for cover from a supervisor. Terse is a wanted style. |
| 0361 "who can cover for Sarah at the downtown park" | dispatcher.assign | the name is the absent cleaner, not the person to assign; still the search. |
| 0320 "Someone's out sick and I need to find a replacement" | dispatcher.report_absence | written by the supervisor about a third person; the asked action is the search, the absence is background. |
| 0334 "did anyone say they could pick up the visit" | dispatcher.cover_reply | asks Mia for the state of the search, not an answer to a cover request. |

### 3. Coverage

Missing for find_cover / en:

- Finnish names and places. Every site is Anglo-American (Smith, Jones, Miller, Davis, Wilson,
  Brooklyn, Oak Street, Maple, "downtown") or Australian (Mornington Peninsula x4). A top-up
  should name Finnish sites and people (Kamppi office, Hervanta school, Anna, Jukka, Sanna) to
  match the fi data and the assign intent's examples.
- The visit named by time and site together ("Thursday 8am at the Leppävaara gym"), by the absent
  cleaner ("Anna's Tuesday visits"), or by a visit id (only 0344 "visit 452").
- Constraints on the candidate: someone with a car, someone who holds the key, someone who has
  done the site before, someone nearby, someone under the overtime limit.
- Several visits at once: "the whole route", "all of Anna's visits tomorrow", "both afternoon
  slots".
- Asking Mia to ask around rather than to list: "send a cover request to whoever is free",
  "ping the pool", "shortlist", "options", "candidates", "suggest someone", "who's nearest".
- Context style built on a Mia-initiated notice ("Anna is sick, two visits are uncovered") with a
  short reply ("ok who can take them", "options?"). Only 2 records had a context and both needed
  a fix; 3 others tagged `context` had none.
- Supervisor on the web channel (counterpart share 0.2, channel web): the data reads as
  WhatsApp. A few desk-style one-liners typed into a web chat ("cover for Kamppi 14:00?") would
  help.
- Non-urgent planning: cover for next week's leave, a known gap in the rota, not only "just
  bailed".

Teacher patterns:

- Gemma: one template dominates, "<site> ... cleaner just bailed" (0290, 0304, 0309, 0318, 0119,
  0130, 0140), with the same three surnames across train and test (Smith x8, Jones x4,
  Miller x4). Not near-duplicates by the rule, but a classifier can learn the surname. `typo`
  style is mostly lowercase with few real typos (0304, 0305, 0306 have none); 0132, 0133 do.
- Qwen: "the visit we just lost" repeated six times (0334, 0338, 0342, 0351, 0353, 0355); all
  four `mixed` records are set on the Mornington Peninsula (Australia); formal records lean
  stilted (two of four dropped or borderline, 0354 kept with "in light of the cancellation of
  the previous assignment"). Qwen's `context` records (0361, 0362) carry no context field.

---

## dispatcher.find_cover, fi (92 records)

### 1. Counts

| Teacher | Records | Kept | Fixed | Dropped |
|---|---|---|---|---|
| teacher:local/gemma4-mia (train 34, test 24) | 58 | 23 | 27 | 8 |
| teacher:local/qwen3.5-mia (train 34) | 34 | 2 | 11 | 21 |
| Total | 92 | 25 | 38 | 29 |

Main drop reasons:
- Gibberish or machine-translated Finnish that no small edit rescues (18): Qwen's calques
  "vieras" (guest) for visit, "puhdistaja" (purifier) for cleaner, "peittoon" for cover, and the
  four-record "äitiä ... Paja on nyt tyhjä" series (0391 to 0394); Gemma's "meesittiin",
  "Sunnustan", "tjaisuun", "tölkkui".
- Ambiguous or outside the intent (8): bare "Kuka hoitaa?", "Kuka tekee (visitin)?", "Vapaa?",
  "Teetkö (sitä)?", a sender who cannot come (0378), a message with no visit or cover at all
  (0345), see section 2.
- Near-duplicate (1): 0152 repeats 0334 "Kuka vapaana?".
- Context problems (2): 0166 and 0395 have a context that is not a Mia question (a supervisor
  line, or the text itself) and garbled text.

Fixes were language only: ungrammatical cases ("tähän kohteen", "huomisella kohteella"),
non-words ("vedottavaksi", "löytyisikökö", "ketäköllä", "onulla"), wrong words ("korvaus"
compensation, "hoivattua" nursed, "vanhempi" parent) and the English calque "hypätä sisään".
Three Qwen records (0384, 0385, 0396) also had their `context` cleared: find_cover is not a
follow-up and the contexts were either the text copied or an implausible Mia line. No slots:
role.yaml declares none for this intent and no record carried any.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.find_cover/fi/local-qwen3.5-mia/0378 | dispatcher.report_absence | rule 3: "Mä en pääse tänne, keksi kukaan korvaamaan" is the sender reporting they cannot come; the search is Mia's follow-up, not the message. Same action? No: report vs search. |
| dispatcher.find_cover/fi/local-gemma4-mia/0335 | dispatcher.who_is_working / dispatcher.my_visits | ambiguous: "Kuka hoitaa?" alone is "who is doing it"; the catalogue maps "who's covering?" to my_visits. Two labels. |
| dispatcher.find_cover/fi/local-qwen3.5-mia/0372 | dispatcher.who_is_working | ambiguous: "Kuka tekee visitin?" asks who is assigned, not who could cover. |
| dispatcher.find_cover/fi/local-qwen3.5-mia/0373 | dispatcher.who_is_working | ambiguous: "Kuka tekee?" same as above, no cover meaning. |
| dispatcher.find_cover/fi/local-qwen3.5-mia/0374 | other | "Vapaa?" is a bare word, fits nothing; the catalogue treats "cover me" the same way. |
| dispatcher.find_cover/fi/local-qwen3.5-mia/0375 | other | "Teetkö sitä?" asks one person whether they will do it (a human-to-human line), not Mia for candidates. |
| dispatcher.find_cover/fi/local-qwen3.5-mia/0376 | other | "Teetkö?" as above. |
| dispatcher.find_cover/fi/local-gemma4-mia/0345 | other | "Mulla on tässä tilanne, jonka pitäis saada hoidettua nopeasti" names no visit, cleaner or cover; nothing to classify. |

No record copied a conversation.yaml example and none was a kb_* question or a bare
affirm/deny/greeting. No record named a person for assignment (dispatcher.assign), so the
nearest look-alike is unrepresented on the negative side (see coverage).

### 3. Coverage for find_cover / fi

Situations missing or thin:
- A concrete visit with a date or time and a place: "huomenna klo 8 Kaisaniemen toimisto",
  "perjantain iltasiivous Tapiolassa". Nearly every record says "tää kohde" or "se siivous"
  with no referent; the model never sees find_cover with a specific slotless visit mention.
- A named absent cleaner without naming a replacement: "Sanna on kipeenä huomenna, kuka vois
  ottaa sen kohteet?" (Only 0395, dropped, had a name, Kari.)
- Constraints on the candidate: has a car, lives near, has the site induction, has a key, speaks
  Finnish, is not already over hours.
- Multiple visits at once: "Jonna jää pois koko viikon, keitä on vapaana sen reitille?"
- Partial cover: only the morning, only one of two sites.
- Asking for the second candidate after the first declined: "Ville ei voi, kuka seuraavaks?"
- Routine, non-urgent tone: next week's gap, a planned leave.
- Fewer "Mia," openers (Qwen put it on 30 of 34) and fewer "Kuka vois korvata/hoitaa ..." shapes;
  more verbs real supervisors use: tuurata, paikata, ottaa keikka, mennä tilalle, saada joku.

Counterparts: all 92 are supervisor, matching role.yaml. The look-alike boundary with
dispatcher.assign (a supervisor who names the person) and dispatcher.who_is_working (who is on
today) needs negative examples generated in those cells, not here; none of the kept records
drifts toward assign.

Styles after review: terse is thin and weak (kept 6, several near-identical "Kuka vapaana /
hoitaa / korvata?"), typo is thin (kept 2, fixed 7), context style has no valid records left
(0356 and 0357 fixed but carry no context; 0166, 0395, 0396 lost theirs). Formal is fine (kept
3, fixed 6). Mixed has no actual English words; a top-up should include a few ("backup",
"shift", "cover", "available").

Teacher notes:
- Qwen 3.5 fi output is systematically machine-translated: visit becomes "vieras" (guest),
  cleaner "puhdistaja" or "puhdas työntekijä", cover "peittoon", and it repeats one bad template
  four times (0391 to 0394). It also filled `context` for indirect and context styles with
  either the text itself or a made-up supervisor line, though find_cover is not a follow-up.
  Its train cells for this intent should be regenerated by another teacher.
- Gemma 4 produces the right intent and register but about half the records carry one non-word
  or wrong case; the fixes above were small. Watch the calque "hypätä sisään" (jump in) and
  "siivousmies/siivoushenkilö" for "siivooja".

---

## dispatcher.my_visits, en

Input: 99 records (gemma4-mia train 36, gemma4-mia test 27, qwen3.5-mia train 36).
Output: 54 kept, 20 fixed, 25 dropped.

### 1. Counts

| source | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 27 | 6 | 3 | 36 |
| teacher:local/gemma4-mia | test | 17 | 6 | 4 | 27 |
| teacher:local/qwen3.5-mia | train | 10 | 8 | 18 | 36 |
| all | | 54 | 20 | 25 | 99 |

Main drop reasons (25):
- 9: the message asks for Mia's own schedule ("your / ur / Mia's / her visits", "your visits log",
  "completed visits") so that no your->my swap gives a natural, non-duplicate my_visits message,
  or the request is really a report on done work (0274, 0275, 0283, 0284, 0285, 0290, 0292;
  0246 and 0090 would duplicate a kept record after the swap).
- 7: overlap suspects, fits another intent better or ambiguous (0232, 0278, 0279, 0280, 0281,
  0287, 0296). See section 2.
- 5: near-duplicates, two of them test records that copy train word for word (0243, 0266,
  0073 = train 0226, 0074 = train 0227, 0086).
- 4: unnatural or meaningless (0270 "my_visits", 0273 "today", 0293 clinic and pharmacy run,
  0297 rambling).

All 20 fixes are the same correction: the teacher wrote the message as if Mia were the cleaner
with the visits ("show me your schedule for today") and the fix swaps the possessive to the
sender's own ("my schedule"). Each fixed text was checked against the kept set so it is not a
near-duplicate. One further fix (0289) clears a `context` that was the user's own previous
message, not a Mia question; my_visits is not a follow-up intent.

No slot problems (the intent declares no slots, none were filled). No safety findings: no real
people, numbers or addresses; 0287 mentions "5th Ave" (not Finland) and was dropped anyway.

### 2. Overlap suspects

"Same action?" test applied: a record is listed only when Mia would do something other than
show the sender their own visit list.

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.my_visits/en/local-gemma4-mia/0232 | conversation.how_to_use_mia | "where can i see which houses im doing tomorrow??" is near the catalogue example "how do I see my shifts in here" (product help, rule 1/2); the time window suggests the list is wanted, so ambiguous, dropped not relabelled |
| dispatcher.my_visits/en/local-qwen3.5-mia/0278 | dispatcher.who_is_working | asks for Mia's schedule to see "when we're all headed out": team availability, the role.yaml look-alike |
| dispatcher.my_visits/en/local-qwen3.5-mia/0279 | dispatcher.who_is_working | "do you know her schedule for tomorrow ... if we're all free": another person's and the team's schedule |
| dispatcher.my_visits/en/local-qwen3.5-mia/0280 | dispatcher.who_is_working | "Are we all set for this week? Could you get Mia's visits up?": team schedule |
| dispatcher.my_visits/en/local-qwen3.5-mia/0281 | dispatcher.who_is_working | "show her visits so we can see who's free today": who is free |
| dispatcher.my_visits/en/local-qwen3.5-mia/0287 | dispatcher.visit_details | "are you visiting the client on 5th Ave tomorrow or is that slot booked?": one visit's booking state, not the list |
| dispatcher.my_visits/en/local-qwen3.5-mia/0296 | dispatcher.who_is_working | "pull up your visit list ... Need to check who's covered": coverage of the team |

Note for the developer: dispatcher.who_is_working is named as a look-alike in role.yaml but is
not one of the 13 trained intents, so these five would fall to `other` in this model. The
catalogue hard negative "is maria working tomorrow -> dispatcher.my_visits (RBAC decides)"
pulls the other way; decide whether supervisor team-schedule questions belong to my_visits
before the top-up, and if they do, generate them natively rather than restoring these.

### 3. Coverage

What is missing for this intent in English:

- Supervisor counterpart written natively. Both teachers wrote the supervisor cells as a
  supervisor asking Mia for Mia's own schedule; the surviving supervisor records are mostly
  your->my fixes plus two terse ones (0248, 0089). Top up with a supervisor asking for their own
  visits (supervisors in a cleaning company also have sites) and, if the developer decides so,
  team-schedule questions ("who's on the Kamppi site tomorrow", "what's the plan for the team on
  friday").
- Time windows beyond today / tomorrow / this week: a weekday ("what have I got on thursday"),
  a date ("my visits on the 14th"), next week, the weekend, "after lunch", "this afternoon",
  "first job tomorrow morning", "what's my last one today".
- Next-visit phrasing: only 0237, 0289, the fixed 0276 and 0291, and test 0081 ask "what's
  next / where next"; a few more ("where am I after this", "what time is my next one").
- Counts and existence questions that still want the list: "do I have anything on saturday",
  "am I working tomorrow", "how many visits have I got tomorrow", "is my friday still on".
- Change checks: "has my schedule changed", "did anything move for tomorrow", "is the Hakaniemi
  one still at 9".
- Site-name anchored lists: "when am I at the school this week", "what time is the dental
  clinic tomorrow" (these sit on the my_visits / visit_details border and the model needs them
  on the right side).
- Delivery wording: "send it to whatsapp", "send me the week as a list", "resend my schedule"
  (the message was sent earlier and lost).
- Styles: `typo` records mostly carry no typos (0230, 0233, 0274, 0277); ask for real misspellings
  ("shedule", "tommorow", "visists"). `indirect` for cleaners is good (0234 to 0237, 0079,
  0081); `terse` has saturated on "my visits / my schedule today / visits for tomorrow" and
  needs variety ("tomorrow?", "week plan", "jobs tmrw", "friday?"). `context` cells produced
  plain requests, which is fine, but a few genuine in-conversation ones ("and tomorrow?",
  "what about the rest of the week" after a shown list) would be useful.
- Phrasings not yet present: "shifts" (the catalogue uses it, the teachers never did), "rota",
  "roster", "gigs", "where am I tomorrow", "which sites tomorrow", "what's on", "run me
  through tomorrow".
- Test split: two test records copied train word for word and several more are one-token
  paraphrases of train (0068 vs 0244, 0085 vs 0248, 0082 vs 0238); the test cell for
  `informal`/`terse` should be regenerated with the train set shown as "do not copy".

Systematic problems per teacher:

- qwen3.5-mia: addressed Mia as the person who has the visits in 22 of 36 records, and in
  the `indirect`, `formal` and `mixed` cleaner cells it drifted into asking about a colleague's
  or the team's schedule, completed-visit reports and logbooks. Its `terse` cell emitted the
  intent id ("my_visits") and a bare "today". Its `context` cell put the user's own message in
  `context`. Its `typo` cell has no typos. Only 10 of 36 kept.
- gemma4-mia: cleaner cells are good and varied; the supervisor cells have the same "your
  schedule" misreading in all but the terse one (both splits). `formal` leans on one template
  ("could you please provide me with a list/summary of my scheduled visits for the remainder
  of ..." in 0238, 0239, 0251, 0082, 0092). The test split duplicates train in two terse records.

---

## dispatcher.my_visits, fi (96 records: 72 train, 24 test)

### 1. Counts

| Teacher | kept | fixed | dropped | total |
|---|---|---|---|---|
| teacher:local/gemma4-mia (train, 0254-0289) | 19 | 13 | 4 | 36 |
| teacher:local/gemma4-mia (test, 0095-0118) | 8 | 12 | 4 | 24 |
| teacher:local/gemma4-mia (all) | 27 | 25 | 8 | 60 |
| teacher:local/qwen3.5-mia (train, 0298-0333) | 5 | 10 | 21 | 36 |
| all | 32 | 35 | 29 | 96 |

Surviving after review: 67 (49 train, 20 test). Train is below the 60 target for a read intent
but above the 30 minimum; test holds exactly 20.

Main drop reasons:
- Garbled or invented Finnish, mostly Qwen (0299, 0300, 0301, 0304, 0305, 0306, 0307, 0310, 0311,
  0312, 0313, 0316, 0320, 0322, 0323, 0326, 0330, 0331, 0333; Gemma 0277, 0115): 21.
- Degenerate token loops in Gemma's typo cells ("nahoaa nahoaa", 0102, 0103): 2.
- Not a request for the sender's visits (0286 asks whether Mia checked Mia's sites, 0289 is a
  statement that the schedule is entered, 0317 asks to move a visit): 3.
- Ambiguous, two labels (0264, 0308): 2, listed below.
- Duplicate across splits (0099 copies train 0262 "Mitä tänään?"): 1.

Main fix reasons (35):
- Second-person possessive addressed to Mia ("sun aikataulun", "omat käyntisi", "suunnitelmasi",
  "sinun tulee tehdä"): the text asked for Mia's own schedule. Changed to mun/minun on 0282, 0285,
  0288, 0303, 0315, 0318, 0321, 0327, 0332, 0112, 0113, 0116, 0118 (13 records, both teachers;
  every Gemma supervisor cell but two had it).
- Generator artifact ",context:" glued to the end of every Gemma typo-style train text (0266,
  0267, 0268, 0269): 4.
- Non-words in non-typo styles ("sunnain", "sekaaessa", "sekaaa", "Poisitko", "katsota",
  "Heitää", "viiveet" meaning delays, "Tärppäisi", "kysyttyjen tapausten osalta"): 12.
- Missing verb or ungrammatical frame (0097, 0109, 0314, 0319): 4, rewritten keeping the ask.
- Noise that is not a plausible typo in a typo cell (0101 "katsotaa nahoaa"): 1, realistic typos
  substituted.

No slots are declared for this intent and none were present; nothing to check. No record is a
follow-up, so no context was expected; 0289 was the only one with a context and it was dropped.
No safety or personal-data issues.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.my_visits/fi/local-gemma4-mia/0264 | dispatcher.absence_scope | "Tänään ja huomenna?" with no context is a natural scope answer to "which visits does the absence cover?" as much as a visits question; two labels. Same action? No: one reads visits, the other narrows an absence, so the pair is real and the bare text cannot decide it. |
| dispatcher.my_visits/fi/local-qwen3.5-mia/0308 | dispatcher.checklist | "Huominen siivouslista?": "siivouslista" is the cleaning checklist as readily as a list of cleanings; two labels. Same action? No: show visits vs show checklist items, so listed. |
| dispatcher.my_visits/fi/local-qwen3.5-mia/0317 | other | "Onko huomenna mahdollista tehä se käynti?" asks to do or move one visit tomorrow; no dispatcher intent reads visits here, and a reschedule request is outside the 13 intents, so it belongs to `other`, not my_visits. |

Not listed, judged in favour of my_visits: 0283 "laita nää huomisen käynnit näytölle" and 0114
"Näytä käynnit tänään." from a supervisor have no "mun"; role.yaml names dispatcher.who_is_working
as the look-alike but that intent is not among the 13, so there is no second label today. If
who_is_working is added, both need a second look. No record copies a conversation.yaml example;
none is a bare affirm, deny or greeting; none is a kb_* question (0273 "Mun kalenteri näyttää
tyhjältä" is an indirect ask, not conversation.how_to_use_mia's "how do I see my shifts in
here").

### 3. Coverage: what a top-up should add

Situations missing or thin:
- Next visit only ("mikä on mun seuraava paikka?", "mihin mun pitää mennä seuraavaksi?"): only
  0271 touches it.
- Specific weekday or date ("mitä mulla on perjantaina?", "onko mulla 14.10. mitään?"): only the
  two Sunday records (0256, 0260) after the fix.
- Specific time of day ("onko mulla iltavuoroja tällä viikolla?", "mitä mulla on aamulla?").
- Next week and the weekend ("ensi viikko?", "onko mulla viikonloppuna töitä?"): only 0268 and
  0101.
- Counting or confirming ("montako käyntiä mulla on tänään?", "onko mulla tänään vaan kaks?",
  "oliko mulla huomenna vapaata?").
- Where to go first, order of the day ("missä järjestyksessä ne on?", "mistä mä aloitan?").
- Questions tied to a change ("muuttuko mun aikataulu?", "tuliko mulle uusia käyntejä?"), which
  sit between my_visits and conversation.correction; a few clear ones help the boundary.
- Asking the same thing after a greeting or with a thanks ("moi, kiitos eilisestä, mitä mulla on
  tänään?").

Counterparts: the supervisor share (0.2) is present (13 of 96 in, 10 surviving) but Gemma's
supervisor cells are mostly cleaner phrasings with "sun" swapped in; a top-up should make the
supervisor ask for their own day as a supervisor would on the web client ("mitä mulla on tänään
listalla?", "näytä mun päivä"), and keep the "näytä kaikki käynnit" phrasing out of this intent
until who_is_working exists.

Phrasings: the surviving set leans on "aikataulu", "käynnit", "reitit"; add "vuorot",
"keikat", "paikat", "kohteet", "työt" and the anglicism "visitit" more (only 0265, 0328, 0327).
Terse cells are good ("Aikataulu?", "Visitit", "Tänään mitä?") but there are no one-word
weekday or site-less terse asks ("huomenna?", "ens viikko?"). Mixed style has almost no English
("pls" in 0279 is the only one); add "schedule", "shift", "check" sprinkled into Finnish.

Styles: typo cells need regenerating, Gemma's carried a ",context:" artifact in every train
record and token loops in test, Qwen's were garbled rather than typo-ridden; only 6 typo records
survive out of 16. Indirect survived well from Gemma and badly from Qwen.

Test split: 0111 "Voinko nähdä mun aikataulun tälle viikolle?" sits close to train 0254 and
0280 (the same ask with hei hei / voisiko / voitko näyttää); it passes the near-duplicate rule
but a third teacher family would make the test split more independent, as the guidelines ask.

Systematic teacher problems:
- Qwen 3.5 (fi): 21 of 36 dropped; invented words (viikkoveto, viivittelytieto, aikaus,
  Omatkiin), wrong person (asks Mia for Mia's visits in 8 records), and off-topic booking
  phrasings (0299, 0316, 0317). Its Finnish for this intent is not usable without a stronger
  Finnish generator or a second pass; keep its five kept records but do not count on it for
  the top-up.
- Gemma 4 (fi): good cleaner informal and terse cells; the typo style breaks (artifact suffix,
  token loops), the supervisor cells confuse "sun" and "mun", and the formal cells drift into
  filler ("kysyttyjen tapausten osalta") or wrong possessives ("aikataulunsa").

---

## dispatcher.report_absence, en (232 records: 198 train, 34 test; all counterpart cleaner)

Input note for the developer: the 34 gemma test records reuse the ids 0000 to 0033 of the gemma
train records, so the input has 34 duplicate ids (198 distinct ids for 232 lines). The output
has one line per input line in input order; the duplicate ids were not changed (the brief forbids
it). Tell the ids apart by `split` until the generator numbers test records after train.

### 1. Counts

| Teacher | Split | Records | Kept | Fixed | Dropped |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 100 | 76 | 23 | 1 |
| teacher:local/gemma4-mia | test | 34 | 20 | 9 | 5 |
| teacher:local/qwen3.5-mia | train | 98 | 24 | 56 | 18 |
| Total | | 232 | 120 | 88 | 24 |

Surviving after review: 208 (train 179, test 29).

Main fix reasons (88):
- Slot value not in the text or not verbatim (about 50, two thirds Qwen): Qwen wrote
  `partial_day` as `true` / `false` / `yes` / `today` (26 records) and `reason` as a paraphrase
  or a label (`mourning`, `implied`, `partial_day`, `late`, `overworking`); Gemma wrote
  `partial_day: leaving early` for texts that say "head out early", "depart early", "out for the
  rest of the day". Values were set to the span in the text.
- Slot in the wrong name (10): `reason: late` / `running late` / `early leave` / `gone home
  early` moved to `partial_day`.
- Slot the text clearly fills but the teacher left out (about 20): `reason: Traffic`,
  `partial_day: late` and the like added.
- Text trimmed (10, all Qwen `formal`): every Qwen formal record ended with a system-voice
  sentence, "I have recorded this as a sick absence", "I will log this as a partial day", "This
  will be marked as a full sick day". The tail was removed, the report kept; slots fixed where
  the value was not verbatim.
- Apostrophe form (2, Qwen): slot written with a straight apostrophe, text uses a curly one.

Main drop reasons (24):
- Unnatural or machine-sounding, 10 (9 Qwen, 1 Gemma): "Overloaded childcare", "supplies for
  the car", "Run over a bit", "log off early", "who I'm sending to for my shift", "coming in
  full time", "cant work half shift", "missed visit. cant come.", the roommate's mess, and a
  rambling record that asks Mia "Will I reach on time?".
- Label leak, 4 (Qwen): the slot name spoken as text, "partial day. headache.", "cant work
  partial day. left early.", "mark me down as partial", "flag this as partial".
- Near-duplicate across splits, 5 (Gemma test): a test record equal to or one word away from a
  train record (see section 3); the train copy is kept, the test copy dropped.
- Fits another intent or ambiguous, 4 (Qwen): section 2.
- Self-contradictory, 1 (Qwen 0045: "cant work today. ill be late.").

### 2. Overlap suspects

Same-action test applied: each one below is not "record that I cannot work a day or visit".

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.report_absence/en/local-qwen3.5-mia/0052 | dispatcher.cover_reply | "thnks for asking but cant make tomorrow either. sick." answers a request; role.yaml look-alike (a decline is not an absence), rule 2 (different action); two labels, dropped |
| dispatcher.report_absence/en/local-qwen3.5-mia/0086 | conversation.share_news | "Had a family emergency yesterday. I'm okay now but just wanted to update you" reports a past absence that is over, no action; rule 2 |
| dispatcher.report_absence/en/local-qwen3.5-mia/0011 | conversation.injury_minor / share_news | "waking up with severe pain in my back." states no absence; catalogue example "my back hurts after lifting" is injury_minor; ambiguous |
| dispatcher.report_absence/en/local-qwen3.5-mia/0018 | conversation.injury_minor | "my leg injury is flaring up, can't stand for long." states no absence; ambiguous |

Checked and kept, for the record: lateness reports ("running late, be there in 30") are this
intent by role.yaml ("sick, late, leaving early") and by the catalogue hard negative "sorry I'm
late"; "can u cancel my shift for tomorrow?? i got a bad migraine" (gemma 0049) and "Is there
any way to move it or cancel?" (qwen 0096) are absence reports phrased as requests, same action;
"doctor said rest for 3 days" after an accident (qwen 0003) is a multi-day absence, not an
injury report; "my mom passed away last night" (qwen 0020) is bereavement absence, not distress.
No record copies a conversation.yaml example; no kb_sick_leave_rules question (nothing asks
about notice, certificates or pay); no bare affirm/deny/greeting; no venting without an absence.

### 3. Coverage: what a top-up should add (en, report_absence)

Situations, by rough count of the 208 survivors: whole day or visit 109, leaving early 46, late
35, part of the day named 18. Missing or thin:
- Multi-day and future absences: only qwen 0003 (3 days), gemma 0079/0084/test 0006/0024
  (tomorrow) and qwen 0091 (Tuesday). Add "out the rest of the week", "sick note until Friday",
  "can't do Thursday and Friday", "doctor's appointment next Tuesday morning".
- Absence for a named visit or site: almost every record says "today", "my shift", "the visit".
  Add visits by name or time ("can't do the Aalto school one", "the 7am at the gym is off for
  me", "skip Mäkelä's tomorrow"). role.yaml records an absence per visit; the data never names one.
- Late with an arrival time or next visit named ("there by 9.30", "skip the first, make the
  second"); late that is really a missed first visit.
- Non-illness reasons beyond car and traffic: childcare fallthrough, exam, court or immigration
  appointment (common for the cleaner population), snowstorm, bus strike, no sitter.
- Sick-child or dependant cases with a time ("back after the doctor at 2").
- Absence with a question about cover ("who takes my visits?") still one action; and the
  catalogue hard negative "hi, I can't come today, fever" style (greeting then report).
- Replies to a Mia prompt ("Are you working today?" then "no, sick") would need context; none
  here, and `context` style records carry no context at all (fine for a non-follow-up, but the
  12 "context" records are indistinguishable from informal).
- Emoji and WhatsApp habits: one emoji in 232 records (test 0028). Add "🤒", "😷", "🚗💨".
- Counterpart is cleaner only, as role.yaml declares; fine.
- `mixed` style is plain English in every record (both teachers); for en the brief does not
  require code-mixing, but if mixed means English with Finnish words, none exists.
- Hard negatives to generate under their own intents, not here: "how many days can I be off
  without a note" and "do I get paid when sick" (kb_sick_leave_rules), "can't take that visit,
  sorry" as an answer to a cover request (cover_reply), "I'm sick of this" and "so tired of
  these shifts" (venting), "cut my hand, going to the health centre" (injury_minor), "sorry for
  the late reply" (apology).

Repetition to avoid in the top-up (Gemma): "Hey Mia, I'm so sorry but I woke up with a
<illness> and won't be able to make it to my shift today" appears four times across train and
test (0085, 0095, test 0028, test 0032); "feeling (really/very) under the weather" six times;
"car won't start" five times; "kid is sick so i gotta stay home" three times;
"sorry for the short notice" six times. The test split is written by the same teacher as
train and reuses its templates, so five test records were one word from a train record; a test
set from a third model family (guidelines.md) would avoid the leak.

Systematic teacher issues:
- Qwen 3.5: `partial_day` written as a boolean or `today` (26 records) and `reason` as a
  category word not in the text; the slot name spoken in the text ("partial day", "mark me down
  as partial"); every `formal` record ends with the cleaner saying the system will record the
  absence; two "mixed" records had `reason: partial_day`. Its terse and indirect records are the
  most varied in the file once the slots are fixed, and its short informal ones are good.
- Gemma 4: slots mostly right, text natural, but a few templates reused heavily (above) and
  `partial_day` values normalised to "leaving early" / "late" instead of the span. One
  unnatural record (0041). Test split numbering restarts at 0000 (input issue, not the text).

---

## dispatcher.report_absence, fi

Input: 204 records (Gemma train 100, Gemma test 34, Qwen train 70). Every id decided, in input order.

### 1. Counts

| Teacher | Split | Kept | Fixed | Dropped | Total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 54 | 32 | 14 | 100 |
| teacher:local/gemma4-mia | test | 8 | 16 | 10 | 34 |
| teacher:local/qwen3.5-mia | train | 0 | 31 | 39 | 70 |
| **All** | | **62** | **79** | **63** | **204** |

Usable after review (kept + fixed): Gemma train 86, Gemma test 24, Qwen train 31; 141 in all.

Main drop reasons:
- Not Finnish or meaningless text (invented words such as "sairausloitsu", "autoilijassa",
  "kuumekuumisessa", "vatsanpysähdys", "flunssaannehdintää"; broken sentences such as "En oo tää
  vuoro", "Pimeä on, en voi tää"): 45 (Qwen 34, Gemma 11).
- Near-duplicates (Gemma "Oon flunssassa, en pääse tänään." three times; test records echoing
  train records G0146 and G0197; Qwen Q0145/Q0152 word order only): 7.
- Fits another intent, ambiguous, or no absence stated: 6 (see section 2).
- Translated-sounding or template repeat: 3 (G0177, G0119, Q0160).
- Unclear meaning: 2 (G0123, G0044).

Main fix reasons: slot value not verbatim (the teachers dropped "noin" from durations, or wrote
"sairaus" for "sairauden vuoksi"); Qwen slot values that are flags or words not in the text
("true", "false", "", "viivy", "määrä", "puuttunut"); single non-words inside an otherwise natural
sentence; Gemma's "--> syy: ..." annotation leaked into four `mixed` texts; three Qwen `context`
records whose context was not a Mia message.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.report_absence/fi/local-gemma4-mia/0165 | dispatcher.find_cover / ambiguous | "Tuleeko joku toinen hoitamaan tänään?" asks whether someone else covers; no absence is reported. Different action (asking about cover vs reporting an absence), so not the same action; it is ambiguous, not a relabel (rule 2). |
| dispatcher.report_absence/fi/local-gemma4-mia/0173 | dispatcher.find_cover / ambiguous | Same shape as 0165 ("Tuleeko joku ... ottamaan tänään sen vierailun?"), plus the non-word "varteen". |
| dispatcher.report_absence/fi/local-qwen3.5-mia/0099 | conversation.venting | "En kestä." (I can't take it) is venting, like the catalogue hard negative "I'm sick of this"; no absence (rule 2). |
| dispatcher.report_absence/fi/local-qwen3.5-mia/0123 | client_service.cancel_booking / ambiguous | "Olen joutunut perumaan, en voi tää." reads the same from a client cancelling a booking; the classifier sees text only, and nothing marks a shift or visit. Two labels, dropped. |
| dispatcher.report_absence/fi/local-qwen3.5-mia/0146 | conversation.goodbye | "Mukavaa huomista." is a farewell. |
| dispatcher.report_absence/fi/local-qwen3.5-mia/0143 | other | "Hyvä päivällinen." (good dinner) is outside every dispatcher intent. |

Borderline but kept (same action, listed for the developer):
- G0190, G0193 ("en pääse tänään ... oisko mahdollista siirtää/hoitaa huomenna?"): the absence is
  stated and the reschedule is a follow-on wish; "en pääse siivoamaan" marks the cleaner.
- G0102, G0109 ("Oon myöhässä noin X, onko se ok?"): lateness report with a question tail; the
  catalogue hard negative "sorry I'm late" sets lateness as report_absence.
- G0132 ("Laitoin sairausloman."): tells Mia sick leave was filed; an absence report, not a
  kb_sick_leave_rules question.
- G0176, G0184 ("joudun perumaan tämän päivän vuoron / työvuoro"): "vuoro" marks the employee, so
  these are not cancel_booking, unlike Q0123.

No record copied a conversation.yaml example word for word; no record was a bare affirm/deny or
greeting; no kb_* question appeared (the "who do I tell if I get sick" shape is absent, which is
good for this file but means the look-alike cell must be generated separately).

### 3. Coverage: what is missing for report_absence, fi

Situations (nearly every record is "today, sick"):
- Future absences: huomenna, ylihuomenna, perjantaina, ensi viikolla, a date ("15.10."), a range
  ("ma-ke"). Only G0164 (torstai) and G0061 (huominen) are not about today.
- Absence from one named visit rather than the whole day: "en pääse Kirkkokadulle klo 10",
  "aamun käynti jää väliin, iltapäivän teen". Only G0039, G0106, G0121 name a visit.
- Lateness with an arrival time for a named visit ("tuun Rantatielle vasta 9.30"), a bus or train
  delay, snow, a car that will not start (two records only), waiting for a child's daycare.
- Doctor, dentist, neuvola, therapy appointments as partial-day reasons; a sick child with the
  daycare refusing them; a death or emergency in the family (one record).
- Sick leave with a certificate mentioned ("lääkärintodistus tulee", "oon sairaslomalla loppuviikon").
- Lateness or absence reported after the fact ("en päässyt eilen", "tulin tunnin myöhässä") so
  the model learns past tense too; Qwen tried this but the texts were broken.
- Partial day stated as a clock time ("lähden klo 14", "pystyn tekemään vaan aamun").

Counterparts: all 204 are cleaner (role.yaml declares only cleaner for this intent); fine.

Phrasings and styles:
- `mixed` style has zero English words in either teacher; both teachers wrote plain Finnish or
  leaked "--> syy:" annotations. Generate real Finnish-English mixing: "oon sick tänään", "sorry
  en pääse today", "joudun skippaa tän päivän", "car broke down, en pääse", "en oo fit for work".
- `terse` from Qwen was all unusable; usable terse is 14 Gemma lines. Top up with 15 to 20:
  "sairaana", "kuumetta", "myöhässä 20 min", "en tuu tänään", "lapsi kipee", "flunssa, kotona".
- Lowercase, no punctuation, emoji, and voice-note style ("moi mia sairaana tänään en tuu") are
  nearly absent; the test set has a few lowercase typo records and train has none.
- `indirect` from Gemma leaned on "tuleeko joku muu" cover questions (dropped). Wanted indirect:
  "tänään jää väliin", "pitäkää Kirkkokatu ilman mua tänään", "sänky voitti tänään".
- `context` records for this intent: a previous Mia message is not required, but the three fixed
  Qwen records show the useful shape (Mia lists today's visits, cleaner replies sick).
- Greetings before the report ("Hei Mia, ...", "Moi, Milla tässä, ...") and a thanks or apology
  tail are rare; add some so the model does not key on bare "en pääse tänään".
- Reason vocabulary is narrow: flunssa dominates (about 25 records). Add migreeni, selkä
  (back pain), vatsatauti, korona, allergia, hammassärky, loukkaantuminen, "huono olo",
  crisis reasons without health detail.

Test split: after review only 24 Gemma test records remain against a target of 30; the test
top-up should come from a third model family, not Gemma, and must avoid train sentences
(G0063 and G0067 echoed G0146 and G0197).

Systematic problems per teacher:
- Qwen 3.5: Finnish is largely broken. All 15 terse records were non-sentences ("En oo tää",
  "Jospa.", "Lepo."); indirect and formal invented words or wrote nonsense clauses; slots carried
  flags ("true", "false", "") or words absent from the text; `context` was never a Mia message;
  four `mixed` records ended with the same filler "En pysty tekemään työtä." Zero kept as-is, 31
  rescued by rewriting. Its Finnish output should not be used for this role without review, or
  Qwen should be dropped as a Finnish teacher.
- Gemma 4: natural puhekieli with the right register, but (1) it invents words when it tries a
  rarer reason (sairausloitsu, kuumekuumisessa, vatsatori, flunttaa, Sairastupaketti), mostly in
  typo and indirect cells; (2) slot values drop "noin" or an auxiliary word from the text; (3) in
  `mixed` it appended "--> syy: ..." instead of mixing languages; (4) it repeats "Oon flunssassa,
  en pääse tänään" and "Pääsen tekemään vain puolet päivästä" across cells and splits; (5) "oon
  pakko" (for "mun on pakko") recurs. Test quality was lower than train (10 of 34 dropped).

---

## dispatcher.send_photos, en

223 records (189 train, 34 test). The intent declares no slots and is not a follow-up, so every
decision is kept or dropped; nothing was fixed. Decisions were produced by
review/work/send_photos_en.py (one table of drop reasons, everything else kept).

### 1. Counts

| source | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 88 | 0 | 12 | 100 |
| teacher:local/gemma4-mia | test | 26 | 0 | 8 | 34 |
| teacher:local/qwen3.5-mia | train | 65 | 0 | 24 | 89 |
| all | | 179 | 0 | 44 | 223 |

Main drop reasons:
- Unnatural or template-like text (17, all Qwen): the informal block is one template,
  {Here, Check, See, Look} + {clean, tidy} + {pics, shots} + {attached}, and several lines are
  not English a person types ("Snap the clean, coming your way", "Check the attach for the
  work done", "See the tidy shots, work's in", "Tidy pics for this place, attached",
  "A few snapshots are with the message", "for your look").
- Too vague to carry the intent (10, 9 Gemma, 1 Qwen): no photo, pic, shot, proof or upload
  word at all ("Just sent 'em", "Here you go", "Look at these", "Here they are", "sent em",
  "Check your WhatsApp in a sec", "I'll put them in the chat", "Be right there with the
  updates"); such a caption could sit under a damage photo as easily as proof of work, so it
  teaches the classifier nothing it can use.
- Exact or near-duplicates (10): Gemma repeats itself across its own styles (Pics attached x3,
  Done. Sending pics., pics coming thru x2), Qwen's terse cell repeats Gemma's (Photos coming,
  Pics attached, Photos sent, Check photos), and three Gemma test lines duplicate train lines
  (0600, 0608, 0611), which would inflate the test score.
- Fits another label or two labels (6, Gemma test and Qwen): see section 2.
- Garbled (1, Qwen 1730).

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.send_photos/en/local-gemma4-mia/0617 | dispatcher.checklist or dispatcher.check_out | "Done with the kitchen and living room." names rooms done and no photo; the action is a tick or a check-out, not a photo reference (rule 2, role.yaml look-alike "finishing, without a photo") |
| dispatcher.send_photos/en/local-gemma4-mia/0618 | dispatcher.check_out | "Just finished the last room. See the updates below." is a finish report; "updates" never says photo; two labels |
| dispatcher.send_photos/en/local-gemma4-mia/0619 | dispatcher.check_out | "Everything is sparkling now ✨" is a finish report with no attachment cue |
| dispatcher.send_photos/en/local-gemma4-mia/0620 | dispatcher.check_out | "Leaving now, took some shots of the floor and bathroom." Same action? No: leaving completes the visit, the shots are referenced on it; two actions, two labels |
| dispatcher.send_photos/en/local-gemma4-mia/0621 | dispatcher.check_out or conversation.affirm | "All set." is a bare completion or a bare OK; nothing about photos |
| dispatcher.send_photos/en/local-qwen3.5-mia/1714 | dispatcher.checklist | "Photos done." reads as the item "photos" ticked as readily as photos sent; two labels |

Borderline but kept (listed for the developer, not dropped): the many "done + photos" lines
(g1588, g1592, g1598, g1602, g1634, g1646, g1660, g1672, g1675, g1678, g1685, q1680, q1694,
q1738, q1740, g0598, g0604, g0626, g0627, g0629, g0630, g0631). They finish AND send a photo;
role.yaml makes check_out the case "without a photo", so the narrower intent (photo
referenced on the visit) wins and they stay here. If the trained model confuses check_out and
send_photos, these are the records to look at first; the right fix is a sharper check_out
description, not relabelling. g0627 ("about to head out. Attached some photos") is the
closest to a check-out. g1669 ("The cleaners have finished. I am sending over the proof of
work photos") speaks for a team, a supervisor voice, but rule 3 says the label does not
change with the sender. Indirect lines kept on a weaker cue: g1650 ("need to snap a few
things first"), g1653 ("Uploading now."), g1658 ("get the right angles, then I'll send"),
g1659 ("Waiting for them to upload..."), g1661 ("I'll send over what I did"), g0602 ("Check
em out, looks good now"); upload and angles are photo words, so they stay, but they are the
hardest kept cases.

No record copies a conversation.yaml example. Nearest catalogue entries: media_without_text
(a bare "[photo]", none here carry only an attachment marker) and how_to_use_mia ("how do I
send you a photo", a question; none here ask how).

### 3. Coverage and teacher notes

Missing for this intent in English:
- The bare attachment plus a short caption, as WhatsApp really delivers it: "[photo] kitchen
  done", "[3 photos]", "[video 0:12] floors", "IMG_4412.jpg", a photo caption with only the
  room name ("bathroom", "hallway after"). This is the dominant real form and no record has it.
- Finnish setting in English wording: the sites are generic (kitchen, living room, office,
  room 204). Nothing names a taloyhtiö stairwell, a porras, a saunaosasto, a keittiö of a
  daycare (päiväkoti), a school, a sauna, a laundry room, a snow-covered entrance; the mixed
  cells (both teachers) are plain English with no Finnish word at all (kuvat, valmis, tehty,
  siivous, keittiö), so the mixed style is effectively uncovered.
- Before/after pairs ("before and after of the oven", "here's the before, after coming") and
  a photo per checklist item ("pic of the windows as asked").
- Photos sent because Mia or the supervisor asked for them ("you asked for a pic of the
  storeroom, here"), photos of a specific client complaint ("the stain they complained about,
  gone, see pic"), and photos of the key returned to the key box.
- Trouble sending: "photos won't upload, bad signal here, will send from the car", "sent them
  twice, did they arrive?", "too big to send, sending smaller ones", "sending one at a time".
- Volume and timing: "sending 6 pics", "last photos for today", "photos from this morning's
  visit, forgot to send", a next-day late send ("yesterday's pics, sorry").
- Styles: `typo` cells have few real typos (dropped apostrophes, "sendin", "thru"); ask for
  misspellings and missing letters ("fotos", "attched", "sendng the pcitures"). `indirect`
  from Qwen is direct ("Pics of the work are attached."); real indirect is "camera roll is
  full of your kitchen", "the oven deserves a photo, sending". `terse` is covered by both
  teachers but the two sets overlap heavily; a top-up terse cell is not needed.
- Counterparts: cleaner only, as role.yaml says; fine.
- Non-proof photos that still belong here versus not: a photo of damage or a broken machine
  belongs to site_problem or purchaser.broken_equipment, not here. The dropped vague captions
  show the classifier needs the hard negative cells "photo of a problem" (site_problem with a
  photo cue) so that "look at these" does not get learned as proof of work.

Teacher notes:
- Gemma: natural and varied, but repeats its own short lines across styles (the terse cell
  re-uses informal lines) and its `indirect` cell drifts into captions with no photo cue
  (5 of 15 dropped). Its test cell borrowed three train lines verbatim and five of its 34 test
  lines have no photo at all (0617 to 0621, all in the indirect cell); the indirect test cell
  should be regenerated.
- Qwen: systematically stilted in the informal cell (13 of 29 dropped); it writes "the
  clean" and "tidy" as nouns in nearly every line and chains fragments with commas ("Here,
  proof pics of the clean room."). Its terse cell is almost identical to Gemma's. Its typo
  cell has few typos. Its indirect cell is direct. Prefer Gemma, or a third teacher, for an
  informal top-up of this intent.

---

## dispatcher.send_photos, fi

Input: 233 records (gemma4-mia train 100, gemma4-mia test 34, qwen3.5-mia train 99).
role.yaml declares no slots for this intent; no record carried a slot.

### 1. Counts

| source | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 52 | 10 | 38 | 100 |
| teacher:local/gemma4-mia | test | 15 | 10 | 9 | 34 |
| teacher:local/qwen3.5-mia | train | 10 | 6 | 83 | 99 |
| all | | 77 | 26 | 130 | 233 |

Main drop reasons:
- Garbled Finnish (not a sentence a Finn would type): qwen 45, gemma 11.
- No photo reference and no context ("Laitan ne nyt", "Tässä.", "Lähetän nyt.", "Tsekkaa ne vähän
  myöhemmin"): gemma 20, qwen 2 (plus 4 qwen one-word verbs). Only a caption that names kuvat,
  näyttöä, todisteet or liite can be learned from text alone; a bare "here" is any intent.
- Template-like qwen filler with a trailing ", näin" / ", ei" / ", tässä" / ", eikun": 10.
- Near-duplicates (same words modulo case, punctuation, emoji): gemma 11, of which 2 are test
  records that copy a train record ("Kuvat on tulossa.", "Tässä kuvat."), a split leak.
- Stilted or nominalised ("valokuvien lähettäminen on tulossa", "dokumentaatiota kuvien
  muodossa"): 6.
- Fits another intent or a question with no action (see section 2): 6.

Fixes are small Finnish repairs only: wrong case ("siitä keittiötä", "muutamaa kuvaa", "sovittuun
aikataulun"), non-words ("kuvit", "Laitanet", "siivoitsemassa", "hetkiin"), tense clash, and one
record (qwen 1861) that also got a context because its style is `context` and the field was
missing.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.send_photos/fi/local-qwen3.5-mia/1801 ("Ok.") | conversation.affirm | rule 2: no action named, a bare ok; same action? no, nothing is sent |
| dispatcher.send_photos/fi/local-qwen3.5-mia/1802 ("Selvä.") | conversation.affirm | rule 2: bare acknowledgement |
| dispatcher.send_photos/fi/local-qwen3.5-mia/1804 ("Joo.") | conversation.affirm | rule 2: bare yes, no pending photo request in context |
| dispatcher.send_photos/fi/local-qwen3.5-mia/1800 ("Kiitän.") | conversation.thanks | thanks, no photo action |
| dispatcher.send_photos/fi/local-gemma4-mia/1750 ("Katsoitteko ne jo?") | none (other) | a question whether Mia looked, not an announcement; would get no dispatcher label |
| dispatcher.send_photos/fi/local-qwen3.5-mia/1775 ("Onko tämä kuva?") | none (other) | a question, not an announcement |

No record copies a conversation.yaml example (how_to_use_mia "how do I send you a photo" and
media_without_text "[photo]" have no counterpart here). No record is a kb_* question. The
check_out look-alike was tested on every "kaikki valmista" / "kaikki on tehty" record: each one
names kuvat or todisteet, so the narrower photo intent wins and they are kept.

### 3. Coverage: what is missing for send_photos / fi

Situations and phrasings
- Photos of a problem or a before state ("tässä kuva ennen", "laitoin kuvan siitä tahrasta")
  do not appear; all kept records are after-work proof. Note the boundary: a photo that reports
  damage or a site condition may be site_problem, so a top-up should stay with proof of work.
- Photos sent late or on request after the visit ("unohdin laittaa kuvat eilen, tässä ne",
  "laitoin kuvat vasta nyt").
- A single photo versus several ("yks kuva vielä", "laitan vielä yhden").
- Naming the room or site ("kuvat vessasta ja keittiöstä", "kuvat Koivulan koulusta"): only 3
  records name a room; none names a site. role.yaml declares no slot, so these are text only.
- Video or voice mentions ("laitoin videon") are absent; decide whether they belong here.
- Finnish photo vocabulary beyond kuva: "fotot", "kuvii", "pari kuvaa", "valokuvat" barely
  appear; "näyttö" / "todiste" appear a handful of times.
- Realistic captions that still name the thing: "kuvat 📷", "ennen/jälkeen", "valmis, kuvat
  alla". The teachers wrote many bare captions ("Tässä.", "Laitan ne nyt") that had to be dropped;
  a top-up should put such replies only in the `context` style with Mia's photo request as
  context ("Laitatko kuvat kun olet valmis?", "Saisinko kuvat käynnistä?").

Styles
- `mixed`: no English words in either teacher's output (gemma wrote plain Finnish, qwen wrote
  nonsense). Need "pics tulossa", "sent the photos, check", "kuvat done".
- `indirect`: gemma kept 3 of 15, qwen 3 of 15; this cell is nearly empty. Wanted: "näet itse
  miltä nyt näyttää", "lattia kiiltää, kato itse".
- `terse`: qwen's 15 are all unusable (one random verb each); gemma's survive at 9. Wanted:
  "kuvat ✔", "kuvat lähetetty", "pari kuvaa".
- `context`: 7 usable records, all with the same Mia question "Laitatko kuvat kun olet valmis?";
  vary the question (asking for a specific room, asking again after a missing photo).
- `typo` and `informal` are the healthy cells.

Counterparts
- role.yaml lists cleaner only; every record is a cleaner. Fine as planned.

Test split
- After review the test split holds 25 records (15 kept, 10 fixed), all gemma. Two test
  records duplicated train records and were dropped; a top-up for test should be checked against
  train for exact duplicates before writing.

Teacher-specific
- qwen3.5-mia: 83 of 99 dropped. Its Finnish is not usable for this cell: invented words
  ("kuvit", "siemenhän", "Kuulan", "Teehan"), trailing fillers (", näin", ", ei", ", eikun"),
  nominalised stilted sentences in `indirect` and `formal`, contexts written from the user's
  side ("Mä lähetän kuvia.") or copied from the text. Do not use qwen for a Finnish top-up of
  this intent without a stronger prompt or a different model.
- gemma4-mia: usable but repetitive; 20 train records have no photo reference and 11 are
  duplicates of each other. Its `formal` cell leans on translation-like words ("verifioimiseksi",
  "saavutettavissa", "dokumentaatiota"). Its `mixed` cell has no code-switching.

---

## dispatcher.site_problem, en

Input: 230 records (100 gemma4 train, 100 qwen3.5 train, 30 gemma4 test). No slots are declared
for this intent and no record carried one; it is not a follow-up, so no context was needed. No
record was fixed: every problem was a label or naturalness problem, not a slot or context one.

### 1. Counts

| Teacher | Split | Kept | Fixed | Dropped |
|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 85 | 0 | 15 |
| teacher:local/qwen3.5-mia | train | 71 | 0 | 29 |
| teacher:local/gemma4-mia | test | 28 | 0 | 2 |
| Total | | 184 | 0 | 46 |

Main drop reasons:
- Fits or is ambiguous with dispatcher.cannot_access_site (locked door, no code, nobody to let
  me in, gate closed, access denied): 12.
- Fits or is ambiguous with conversation.hazard_report or emergency (water everywhere, flooded,
  chemical spill, smoke, broken window, fire alarm, "safety hazard", lockdown, unnamed incident): 12.
- Stilted or template-like text, mostly qwen3.5 informal records that open with "Reporting a
  stoppage/halt/problem", "Calling out a site condition", "Issue reported.", "Alert.", or echo
  the description's words "site conditions": 10.
- Meaningless or unnatural terse records ("Client stuck.", "Blocked.", "Renov.", "Still
  client.", "Site stopped.", "Event blocked."): 6.
- Weak fit, nothing stops or changes the work (mess after a party, leftover catering, wet floor
  to dry, HVAC noise, manager cleaning up): 5.
- Other: one near-duplicate ("No power." twice), one request_human, one broken_equipment
  ambiguity, one unclear text.

### 2. Overlap suspects

"Same action?" test applied: all records below either name a different cause class that
role.yaml assigns to another intent (entry failure, danger to people, own machine, wanting a
person) or name no cause at all, so the message would get two labels.

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.site_problem/en/local-gemma4-mia/1125 | dispatcher.cannot_access_site | role.yaml look-alike: locked gate, nobody answering |
| dispatcher.site_problem/en/local-gemma4-mia/1131 | conversation.hazard_report | two labels: huge leak, water everywhere |
| dispatcher.site_problem/en/local-gemma4-mia/1138 | dispatcher.cannot_access_site | role.yaml look-alike: nobody to let me in |
| dispatcher.site_problem/en/local-gemma4-mia/1144 | dispatcher.cannot_access_site | two labels: door jammed, cannot enter |
| dispatcher.site_problem/en/local-gemma4-mia/1146 | conversation.hazard_report | two labels: "very unsafe to work" |
| dispatcher.site_problem/en/local-gemma4-mia/1155 | dispatcher.cannot_access_site | role.yaml look-alike: door locked, no entry |
| dispatcher.site_problem/en/local-gemma4-mia/1171 | dispatcher.cannot_access_site | role.yaml look-alike: locked, no door code |
| dispatcher.site_problem/en/local-gemma4-mia/1179 | dispatcher.cannot_access_site | two labels: gate closed |
| dispatcher.site_problem/en/local-gemma4-mia/1181 | dispatcher.cannot_access_site | role.yaml look-alike: main door locked |
| dispatcher.site_problem/en/local-gemma4-mia/1193 | conversation.hazard_report | two labels: water everywhere in the corridor |
| dispatcher.site_problem/en/local-gemma4-mia/1195 | dispatcher.key_location / cannot_access_site | locked supply closet, wants the key |
| dispatcher.site_problem/en/local-gemma4-mia/1203 | conversation.hazard_report | chemical spill in the lobby (danger to people) |
| dispatcher.site_problem/en/local-gemma4-mia/1211 | conversation.hazard_report | two labels: says "safety hazard" |
| dispatcher.site_problem/en/local-qwen3.5-mia/1305 | conversation.hazard_report / emergency | site flooded |
| dispatcher.site_problem/en/local-qwen3.5-mia/1308 | conversation.emergency | lockdown, no site condition named |
| dispatcher.site_problem/en/local-qwen3.5-mia/1311 | conversation.emergency / dispatcher.cannot_access_site | fire alarm went off |
| dispatcher.site_problem/en/local-qwen3.5-mia/1312 | conversation.request_human | "supervisor call me back please" |
| dispatcher.site_problem/en/local-qwen3.5-mia/1313 | dispatcher.cannot_access_site | "access denied by the client", no condition named |
| dispatcher.site_problem/en/local-qwen3.5-mia/1314 | purchaser.broken_equipment | role.yaml look-alike: machine not working |
| dispatcher.site_problem/en/local-qwen3.5-mia/1323 | conversation.emergency | unnamed "incident", need to wait |
| dispatcher.site_problem/en/local-qwen3.5-mia/1325 | conversation.hazard_report / emergency | smell of smoke from the vents |
| dispatcher.site_problem/en/local-qwen3.5-mia/1329 | conversation.hazard_report | broken window, unsafe to clean near it |
| dispatcher.site_problem/en/local-gemma4-mia/0450 (test) | dispatcher.cannot_access_site | role.yaml look-alike: main door locked, no way in |

Kept but borderline, for the developer's eye (cause is a site condition, not a lock or key, so
site_problem wins under the role.yaml wording "cannot enter at all" versus "locked door, no
key, wrong door code, alarm"): 1121, 1126, 1140 (delivery truck blocks the site), 1159, 1206,
1280 (renovation crew blocks entry), 1353, 0434 and 0449 (event staff or security will not let
the cleaner past), 0459. If the developer reads cannot_access_site as "any failure to enter",
these should move there; the two descriptions should then say so.

Also kept but borderline with hazard_report: 1310 and 1321 (building heating broken, no danger
named), 1346 (bathroom leak, waiting for repairs), 1355 (burst pipe, power cut, work prevented).
The role.yaml line "a danger to people, not a work stoppage" is the right test; a leak with no
danger named is a work stoppage.

No catalogue examples were copied. No real personal data, no harmful payloads.

### 3. Coverage

Kept records cover: no water, no power or lights, renovation or construction, event or party or
crowd, client or owner still in the room, floors being polished or waxed by others, heating out,
elevator down, dust and noise, blocked-off areas; styles informal, terse, typo, indirect,
formal, mixed (all plain English), context (plain messages, no context needed). Counterpart is
cleaner in every record, which matches role.yaml.

Missing for a top-up (en):
- Finnish-flavoured English and real `mixed` records: an English message with a Finnish word or
  place in it (taloyhtiö, siivouskomero, "the koulu is closed"), as a Finnish cleaner writing in
  English would. Every `mixed` record here is pure English.
- Finnish sites and situations: school closed for a holiday or an exam, daycare children still
  in, a hospital ward closed for infection, a gym class running late, a staircase being painted,
  a snow-blocked entrance, sauna evening in a taloyhtiö, hallway full of moving boxes.
- A follow-up or second message: "still no power, do I wait or go to the next site?", "water is
  back, starting now", "they said come back at 7", a reply when Mia asks which area is affected.
- Partial problems: one room or floor skipped, the rest done ("did all but the kitchen, client
  was still in there").
- The cleaner proposing an action (skip the visit, come back later, move to the next site) so
  the model learns the report plus a question is still site_problem.
- Hard negatives for the look-alikes, generated under their own intents: locked door or no code
  (cannot_access_site), water everywhere or smoke (hazard_report), own vacuum broken
  (purchaser.broken_equipment), "how do I report a site problem" (kb question).
- Fewer messages that open "Site problem" or "Reporting a"; more that just describe what they
  see, as the gemma4 informal records do.

Teacher-specific:
- qwen3.5: about a quarter of its informal records are templates ("Reporting a X. Y.", "Site
  issue. Y.", "Alert.") and several echo the description's words "site conditions" and
  "stoppage"; its terse cell produced fragments with no meaning ("Renov.", "Still client.",
  "Client stuck."); its indirect cell drifted into hazard and maintenance remarks (smoke, broken
  window, HVAC noise). Its mixed and formal cells are fine.
- gemma4: natural throughout; its main fault is drifting into cannot_access_site (locked doors,
  no one to let me in) in the informal and indirect cells, 7 of 15 train drops, and one in test.

---

## dispatcher.site_problem, fi (218 records)

### 1. Counts

| Teacher | Split | Total | Kept | Fixed | Dropped |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 100 | 53 | 25 | 22 |
| teacher:local/gemma4-mia | test | 34 | 21 | 9 | 4 |
| teacher:local/qwen3.5-mia | train | 84 | 1 | 13 | 70 |
| **All** | | **218** | **75** | **47** | **96** |

Surviving (kept + fixed): gemma 108 of 134, qwen 14 of 84. Train survivors 92, test survivors 30.

Main drop reasons:
- Garbled or nonsense Finnish (qwen: "Tonttija ei ole voitu työnsiä", "Supervoim", "Herra/Seni",
  "Klientin on olemis"; gemma: "tyvennettya", "jaha tai jotakin", "puhtaistoon"): about 45.
- Verbatim or near-verbatim repeats (qwen 1363 to 1384 are the same two garbled sentences 20
  times; gemma 1246, 1263, 1265, 1250; qwen 1398, 1413): about 27.
- Fits another intent or two labels (cannot_access_site, hazard_report): 15, listed below.
- States the opposite of a problem (qwen "indirect" cell: "huone on tyhjä kiitos", "sähkö
  toimii", "tapahtuma ei ole"): 7.
- Questions or vague text with no site condition (gemma indirect cell: "Mitä tässä on
  tapahtunut?", "Onko tässä vielä vieraita?"; qwen "Päivä on hukassa"): about 10.
- Stilted, translated-sounding formal text (qwen 1415, 1421, 1422): 3.
- Test split: 0468 dropped as a near-duplicate of train 1228 (split leak).

Fixes were mostly single-word repairs: "Asukkaas" -> "Asukas" (5 informal records), non-words
("pyykimään", "saista", "Remontteri", "Renovoidaan", "katki", "veskatkosku", "tapahtus"),
and qwen's recurring "jättää siivoamisesta / työt pois" rewritten to natural puhekieli.

Label policy applied: "ei pääse sisään" because of a renovation, an event or the client being
present is kept as site_problem (the message names the site condition). A message whose only
reason is a locked or closed door is cannot_access_site and is dropped and listed.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.site_problem/fi/local-gemma4-mia/1255 | dispatcher.cannot_access_site | "Ei pääsy sisään." names no condition, only no entry (rule 2, narrower intent wins) |
| dispatcher.site_problem/fi/local-gemma4-mia/1267 | dispatcher.cannot_access_site | "kohde on ihan lukossa" plus remontti: two labels |
| dispatcher.site_problem/fi/local-gemma4-mia/1273 | conversation.hazard_report | loose electrical cables, "turvallisesti ei pääse": a danger to people |
| dispatcher.site_problem/fi/local-gemma4-mia/1283 | dispatcher.visit_details | a question whether people are still on site, not a report (rule 2) |
| dispatcher.site_problem/fi/local-gemma4-mia/1286 | dispatcher.cannot_access_site | "Pääsenkö sisälle?" is a question about entry, no condition (rule 2) |
| dispatcher.site_problem/fi/local-gemma4-mia/1289 | dispatcher.cannot_access_site | "ihan lukko ja ovet kiinni": locked door only |
| dispatcher.site_problem/fi/local-gemma4-mia/1292 | dispatcher.cannot_access_site | "ovet on lukittu": locked door only |
| dispatcher.site_problem/fi/local-gemma4-mia/1301 | dispatcher.cannot_access_site | "kohde on tällä hetkellä lukossa": locked only |
| dispatcher.site_problem/fi/local-gemma4-mia/1306 | dispatcher.cannot_access_site | "kohde on ihan lukossa, ei pääse sisään": locked only |
| dispatcher.site_problem/fi/local-gemma4-mia/1314 | dispatcher.cannot_access_site | "ihan suljettu, ei pääse sisään": closed only |
| dispatcher.site_problem/fi/local-qwen3.5-mia/1365 | dispatcher.cannot_access_site | "Kiinteistö on kiinni.": closed only |
| dispatcher.site_problem/fi/local-qwen3.5-mia/1386 | conversation.hazard_report | "Vesi putki on rikki": a broken pipe may be a leak (danger) or just no water, two labels |
| dispatcher.site_problem/fi/local-qwen3.5-mia/1405 | conversation.hazard_report / emergency | "huoneessa on vesi": water in the room reads as a flood, not a dry tap |
| dispatcher.site_problem/fi/local-gemma4-mia/0475 | dispatcher.cannot_access_site | "siivouspaikka on suljettuin": closed only (also garbled) |
| dispatcher.site_problem/fi/local-gemma4-mia/0476 | dispatcher.cannot_access_site | no power (site_problem) and "ovet on lukittu" (cannot_access_site): two labels |
| dispatcher.site_problem/fi/local-gemma4-mia/0480 | dispatcher.cannot_access_site | "vaikea päästä sisään, ovet on lukossa": locked only |

"Same action?" test: cannot_access_site and site_problem both record a site problem for the
supervisors, so the pair shares the action; the split is by cause (door versus conditions). The
locked-door records above are therefore real overlaps, not different actions. No record copied a
conversation.yaml example and none was a kb_* question or a bare affirm/deny/greeting.

Not listed, but worth a developer's eye: 1223, 1241, 1230, 1242, 1278, 1309, 0465 say "ei pääse
sisään" with a renovation or event as the reason. They are kept as site_problem under the policy
above; if the owner wants "cannot enter" to win regardless of cause, these move.

### 3. Coverage: what is missing for site_problem / fi

Situations (the kept data is almost all four motifs: no water, no power, remontti, asukas/
tapahtuma paikalla). Missing:
- Heating or ventilation off (kylmä, ilmastointi pois), frozen pipes in winter.
- Elevator out of order with a heavy trolley (hissi rikki).
- Site in use by others: meeting in the room, school exam, shop still open, staff still working
  late, a patient in the room (healthcare site), guests still in the hotel room.
- Alarm or security guard stopping the work inside (not the door).
- Client-side supplies missing: no cleaning cupboard access, no bags, no bin emptied, client's
  own machine broken (contrast with purchaser.broken_equipment, which must NOT be generated here).
- Weather or outdoor: yard flooded, snow blocking the back door, pollen or sand after a storm.
- Partial stoppage: one floor or one room off limits, work can continue elsewhere (the model
  should learn "changes the work", not only "stops the work").
- Work changed rather than stopped: client asks for a different room, extra mess after a party,
  floors wet from a leak that is already handled (no danger).
- Reports after the fact ("jouduin lähtemään kesken, sähköt meni") and reports with a time ("tulen
  takaisin kolmelta jos vesi palaa").

Counterparts: all 218 records are cleaner, which matches role.yaml. A few supervisor forwarding a
cleaner's report ("Jonna sanoo ettei Keskuskadulla oo vettä") would help robustness even though
role.yaml lists cleaner only.

Phrasings and styles:
- Named sites (only 0489 "Mannerheimintieltä" and 1437 "Huone 204" name a place). Add
  fictional site names and room numbers ("Pähkinärinteen koulu", "3. kerros").
- Greetings plus report with a question at the end ("mitä teen", "odotanko", "tuleeko joku")
  are the natural WhatsApp shape; indirect style from both teachers failed (questions with no
  condition, or statements of the opposite). Regenerate the indirect cell with a brief: the
  stoppage is implied by what the cleaner cannot do ("en saa edes valoja päälle", "pesen sit
  ens kerralla kun vesi on palannu").
- Mixed style has no English words in any record; add "tääl on blackout", "client on vielä
  on site", "no water, mitä teen".
- Typo style survivors are good; keep that cell as is.
- Formal survivors are mostly "Hei, kohteessa on ..." openers; add a couple without the greeting.
- Terse cell is thin after drops (about 14): add "Vesikatko.", "Hissi rikki.", "Kokous kesken."

Teacher findings:
- qwen3.5-mia (fi): systematically broken for this cell. The informal cell is two garbled
  sentences repeated about 25 times ("Kiinteistön pihan vedet ovat katkettu", "Tonttija ei ole
  voitu työnsiä"), the indirect cell states the opposite of a problem, the formal cell is
  translated-sounding ("Tämä on merkittävä ongelma", "tilanne on pysähtynyt"), and "Supervoim"
  appears as an address form. Only 14 of 84 survive, all after rewriting. Do not top up fi from
  this teacher without a repetition check and a Finnish grammar sanity pass.
- gemma4-mia (fi): natural puhekieli; recurring one-word slips ("Asukkaas", "katki", "meneillä")
  that are easy fixes. Its indirect cell drifted into bare questions and locked-door messages
  (the cannot_access_site overlaps above come almost entirely from it). Its "mixed" cell has no
  English. Test records had the same quality as train.

---

## dispatcher.visit_details, en (87 records)

### 1. Counts

| Teacher | Records | Kept | Fixed | Dropped |
|---|---|---|---|---|
| teacher:local/gemma4-mia (train) | 32 | 17 | 12 | 3 |
| teacher:local/gemma4-mia (test) | 21 | 9 | 2 | 10 |
| teacher:local/qwen3.5-mia (train) | 34 | 15 | 9 | 10 |
| Total | 87 | 41 | 23 | 23 |

Main drop reasons:
- Fits dispatcher.key_location (6): pure "where are the keys" questions (1332, 1453, 0498, 0504,
  0507, and 1470 together with a supplies question). role.yaml names key_location as the
  look-alike for this intent, but it is not one of the 13 intents today, so the developer must
  decide: either add the intent (docs/capabilities.md lists it) or widen visit_details to "where
  things are, keys included" and restore these six. Records that ask for keys among other details
  (1328, 1346, 1350) or where to leave the keys afterwards (1337) were kept as visit_details.
- Test copies train (4): 0502 "Address?", 0503 "Door code?", 0505 "What's the location name?",
  0510 (Can/Could variant of 1340). The test record was dropped and the train record kept.
- Not a message or meaningless alone (4, Qwen terse): "where", "gate", "apts", "keys".
- Unnatural or machine-sounding (5): "drop off the furniture" (1445), "the visitor's address"
  (1466), "login info for the gate" (0501), "I am requesting the practical details" (1347, copies
  the intent description), "instructions for the cleaner" in the third person (0515).
- Addressed to the client, not Mia (2, Qwen typo cell): "if u r not home" (1457), and 1455 where
  the writer sends a location and asks to be texted.
- Slot placeholder leaked into the text (1): 0499 "double check the location_name".
- Ambiguous with another intent (2): 1336 (asks the code and reports "i cant get in"), 1456
  (where to start cleaning, kitchen or living room: the task order, checklist).

Fixes (no fix changed a label):
- Gemma typo, formal and mixed cells wrote `location_name: ""` on every record (12 records);
  the empty slot was removed. Gemma also used "not specified" and "not provided" as values
  (1334, 0514), removed.
- Qwen filled the slot with a word that is not a place: "address", "entrance", "location name"
  (1440, 1443, 1465), or with a place that is not in the text: "the house", "the place", "house",
  "front door", "the apartment" (1454 fixed; the others were dropped for other reasons).
- Slot policy as in the check_in review: a proper name or a site-type noun in the text becomes
  the slot (house 1441, 1447; apartment 0513; Sunset Heights and Old Town Warehouse were already
  right); a placeholder (place, property, site, location, unit, complex) gets no slot.
- Qwen context cell (1472, 1473) carried the literal `_dispatcher.visit_details` as context; a
  short previous Mia message was written (a visit reminder and an address line).
- One text fix: 1458 "before u r gone" (to the client) became "before i head over".

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| local-gemma4-mia/1332 "Where are the keys?" | dispatcher.key_location | role.yaml look-alike (where the physical key is); not among the 13 intents |
| local-qwen3.5-mia/1453 "keys" | dispatcher.key_location | same; also not a message |
| local-gemma4-mia/0498 "Is there any specific info on where the keys are?" | dispatcher.key_location | same |
| local-gemma4-mia/0504 "Keys location?" | dispatcher.key_location | same |
| local-gemma4-mia/0507 "im outside ... where r u hiding them?" | dispatcher.key_location | same; the "outside" part reports no failure, so not cannot_access_site |
| local-qwen3.5-mia/1470 "Where exactly are the keys hidden? Do I bring my own cleaning supplies?" | dispatcher.key_location, conversation.kb_uniform_equipment | two labels, neither is visit_details |
| local-gemma4-mia/1336 "do u have a door code for the apartmnt? i cant get in" | dispatcher.cannot_access_site | asks the code (read) and reports entry failed (write); two labels, as the cannot_access_site review treated the mirror cases |
| local-qwen3.5-mia/1456 "where shud i start cleaning? in kitchen or living room first?" | dispatcher.checklist | rule 2 narrower intent: asks the task order, which is the checklist, not where or how to get in |
| local-qwen3.5-mia/1449 "where" | conversation.confusion | bare question word, no request |
| local-gemma4-mia/0501 "Can u send the login info for the gate too?" | admin.reset_login (wording only) | "login info" is credentials wording; dropped as unnatural rather than relabelled |

No record copies a conversation.yaml example. "Same action?" applied and kept:
- 1326 "where should i park when i get there?" and 1350 (parking plus gate code): the
  catalogue has "where can I park near kamppi" under conversation.oos_directions_transport, but
  these ask for the site's own parking instruction, which the dispatcher answers from the visit
  notes; kept. A top-up should avoid making parking the only ask so the boundary stays clear.
- 1448 "Are there pets or kids there? Just wanted to check safety instructions." and 1458:
  conversation.kb_pets is the client's policy question; a cleaner asking about this site's pets
  is a visit detail; kept.
- 0497 "Do they have a door code or something? I'm outside": asks the code, reports no failure;
  kept (cannot_access_site needs the failure stated).
- 1337 "where do u want me to leave the keys when im done": where to leave keys afterwards is a
  site instruction, not where the key is; kept.

### 3. Coverage: what is missing for visit_details / en

Situations not covered (almost every record is "address and door code before I set off"):
- A visit named by site or time: only four records name a site (Sunset Heights, Old Town
  Warehouse, loneside apt, and "the one downtown" which was dropped). Nearly all records have an
  empty slot, so the slot head gets little signal. A top-up should name Finnish sites: "the
  Aalto school", "Koivukatu 12", "the K-market in Leppävaara", "the Kela office", "Nokia site
  tomorrow", and times ("the 3 pm one", "tomorrow's first visit").
- Details other than entry: which floor or unit, alarm on or off and how to disarm (a question
  for the code, not a report that it fails), where the cleaning cupboard or the water tap is,
  what the client wants left alone, whether the client is home, how long the visit is booked
  for, the contact person on site, where to put rubbish, bins on which day.
- Asking details of a visit later in the day or week ("what's the address for the Tuesday
  one"), asking again ("send the code again, deleted the message" with the conversation.repeat
  boundary in mind), and asking for details on behalf of a colleague ("Sanna needs the code for
  Kamppi"; a supervisor counterpart, which role.yaml does not list for this intent).
- Negatives on the key_location side (if that intent is added) and on the cannot_access_site
  side: the kept data has few "asks the code while standing outside" records; add a handful that
  ask without reporting a failure, and leave the failure reports to cannot_access_site.
- Mixed-language records: both teachers' `mixed` cells are plain English. English-writing
  cleaners in Finland would mix in Finnish words ("what's the ovikoodi for the Kamppi kohde",
  "where's the siivouskomero").
- Terse records that name the thing and the site ("code for koivukatu?", "aalto address",
  "which floor @ kela") instead of bare nouns; Qwen's bare one-word terse cell was dropped
  almost entirely.
- Context style with a real previous Mia message: Qwen's two context records had a placeholder,
  so the teacher never saw Mia's turn. Give the generator sample Mia messages (a visit reminder,
  an assignment confirmation) and ask for replies that request the details.

Counterparts: only cleaner, as role.yaml declares; fine.

Styles: informal, formal and indirect cells are full enough once duplicates are removed. The
typo cells are light on real typos (Gemma: "apartmnt", "lmk", lowercase only; Qwen: "shud",
"plz"). Emoji and voice-note transcript style are missing.

Systematic teacher issues:
- Gemma: every record in the typo, formal and mixed cells carried `location_name: ""`; the
  terse cell repeats across train and test ("Address?", "Door code?", "What's the location
  name?"), so the test split should be deduplicated against train before the next run (four
  leaks here). The slot name leaked into the text as "location name" / "location_name" in four
  records (1334, 1348, 0499, 0505). The mixed cell has no Finnish.
- Qwen: fills the slot with the wrong thing (the word "address", "entrance", "location name")
  or with a place that is not in the text; the typo cell writes to the client ("if u r not
  home", "before u r gone", "text me when ur near") instead of to Mia; the terse cell is single
  nouns ("gate", "apts", "keys") that are not messages; the context cell carries the literal
  intent id as context; place names are US-flavoured (Sunset Heights, Old Town Warehouse).

---

## dispatcher.visit_details, fi

81 records: 65 train (34 Gemma, 31 Qwen), 16 test (Gemma).

### 1. Counts

| Teacher | Split | Kept | Fixed | Dropped | Total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 2 | 20 | 12 | 34 |
| teacher:local/gemma4-mia | test | 5 | 8 | 3 | 16 |
| teacher:local/qwen3.5-mia | train | 1 | 8 | 22 | 31 |
| **All** | | **8** | **36** | **37** | **81** |

Main drop reasons:
- Not Finnish or nonsense (17, all Qwen): non-words and broken syntax ("ajit", "onnistuisin varustelemaan", "Olipa kieltä kysyä", "ikkunauunessa", "Tiedänpa", "Hyvä päivänjat"), a message in Mia's voice (1501), one addressed to a colleague (1503).
- Not a request for details (12): Gemma's whole `indirect` cell (1372 to 1376) is the cleaner saying they have or will send the info; Qwen's `informal` cell (1475 to 1481) is bare affirms and statements ("Kyllä, se on se talo"). Test 0531 gives the address instead of asking for it.
- Overlap or two labels (8): see section 2.
- Terse words with no request meaning (4): "Laitteet?", "Ovi.", "Huone.", "Asema.".

Fixes:
- Slots (28 of the 36): `location_name` was filled with the thing asked for ("tarkka osoite", "koodi", "avaimet", "Sijainti.") or a placeholder ("None", "none", ""). Not one record names a site, so every slot was removed. The only slot values that looked like site names (1503 "Teollisuusranta 10", 1504 "Myntintie 25") were on records dropped for other reasons, and 1504's value did not even match its text ("Myyntintie").
- Language (12): one garbled word or phrase replaced ("voiskoon", "saako saatas", "ooja", "nekoitukset", "soittaa eteen", "sun osoitteen ... oviin", "säätöohjeita", "tai niin"; Qwen's "Mistäkö tiiä", "Tiiän kysyä", "Eihkö saa kysyä", "Onko sinulla oveen koodi"). Records needing a full rewrite were dropped instead.
- Context: not a follow-up intent, none required. The two contexts given (1475, 0531) were not Mia questions; both records were dropped for their text.

### 2. Overlap suspects

"Same action?" applied: every record here is a read (asking), so the test does not separate them; the narrower intent or the catalogue example wins.

| id | other intent | rule or reason |
|---|---|---|
| local-gemma4-mia/1355 "Missä ne avaimet on jos ..." | dispatcher.key_location | narrower intent named as a look-alike in role.yaml; asks only where the keys are |
| local-gemma4-mia/1365 "Missä avaimet?" | dispatcher.key_location | same |
| local-gemma4-mia/1369 "missä ne avaimet on? ja onko siellä jotkut erityiset ohjeet?" | dispatcher.key_location | two labels: leads with the keys, then instructions |
| local-gemma4-mia/0524 "lähetätkö vielä ne ohjeet miten pääsen sisään? ja missä ne avaimet on?" | dispatcher.key_location | two labels (test split) |
| local-gemma4-mia/1368 "mulla on vaikeuksia päästä sisään, onko siin joku ovakoodi?" | dispatcher.cannot_access_site | two labels: reports trouble getting in, then asks for the code (the cannot_access_site review dropped the mirror case 1068 the same way) |
| local-gemma4-mia/1370 "voitko laittaa tarkan osoitteen ja koodin vielä kerran?" | conversation.repeat | catalogue examples "send that again", "repeat the address" |
| local-gemma4-mia/0528 "Ootko sä lähettänyt jo tota osoitetta ja koodia? En mä löydä sitä viestiä." | conversation.repeat | asks for the last message again (test split) |
| local-gemma4-mia/1359 "Onko siellä parkkipaikka johon voin pysäköidä?" | conversation.oos_directions_transport | catalogue example "where can I park near kamppi"; site parking is arguably a site detail, developer's call |
| local-gemma4-mia/1366 "Laitteet?" | conversation.kb_uniform_equipment | one word, two readings |
| local-qwen3.5-mia/1490 "Sanoonpa missä on pesuaineet ja mitä pitää tehdä?" | dispatcher.checklist | two labels: where the products are, and what to do |

Open point for the developer: `dispatcher.key_location` is listed as a look-alike of visit_details and cannot_access_site but is not one of the 13 intents in role.yaml. If it will not be built, the four key records above (1355, 1365, 1369, 0524) fit visit_details ("where things are") and can be restored; if it will, the look-alike should become an intent before training. Kept records that mention keys as one item inside a wider request for instructions (1380, 1382) and 0527 (has the keys, asks where the doors are) stayed as visit_details.

Kept but close, watch in the confusion list: 0521 "Missä ne roskat pitäis heittää?" (site waste instruction, could be read as conversation.kb_cleaning_howto); 0529 "Mä oon jo täällä lähellä, mut en tiedä miten pääsen sisälle" (asks before trying, so not cannot_access_site); 1354, 1361, 0519 use "vielä" meaning "also", not "again", so they are not conversation.repeat.

### 3. Coverage: what a Finnish top-up needs

After review 44 records survive (36 train, 13 test), which is thin for a `read` intent that a cleaner uses daily. Nearly all survivors ask the same two things, the address and the door code.

Situations covered: address, door code, how to get in, where supplies and tools are, special instructions, parking (dropped), waste (one). Missing or thin:
- Named sites: zero kept records name a site, so the `location_name` slot has no training signal at all. A top-up must put fictional Finnish site names in at least half the records ("Mikä on Kampin toimiston ovikoodi?", "Osoite Aalto-koululle?", "Missä Tikkurilan päiväkodin siivouskomero on?", "Kerro Lauttasaaren kohteen ohjeet") so the slot head learns the pattern.
- Which visit: today's / tomorrow's / the afternoon one / the second visit ("huomisen kohteen osoite", "iltapäivän keikan ovikoodi"), so the request ties to a visit rather than a bare "kohde".
- Detail types beyond address and code: floor and stairwell (kerros, rappu, A-porras), alarm code and how to disarm (hälytin), key box code (avainboksi), which entrance to use (takaovi, lastauslaituri), where the cleaning cupboard / water point / waste room is (siivouskomero, vesipiste, jätehuone), client contact on site, opening hours or a time window when the site must be done, whether the client is home, pets at the site, light switches and alarm re-arming on leaving, where the trolley or machine is kept, what to do with the key afterwards.
- Phrasings: "mitä siel pitää huomioida", "onks siit kohteesta mitään ohjeita", "kerro vähän siitä paikasta", "lähetä ohjeet", "mikä rappu", "monesko kerros". Also a request with a slash or a list ("osoite + koodi + kerros?").
- Styles: `mixed` has no English words at all from either teacher; add some ("door code Kamppiin?", "instructions sinne kohteeseen?", "mikä on access code"). `indirect` from Gemma missed the intent entirely (the cleaner having the info, not asking); the wanted indirect form is implied asking ("oon lähdössä kohti kohdetta, mitään erityistä tiedossa?", "en oo käyny siellä ennen"). `terse` survivors are "Osoite?", "Onko ovikoodi?", "Missä kohde on?", "Sijainti.", "Koodi."; add "ovikoodi?", "kerros?", "rappu?", "ohjeet?".
- Counterparts: all cleaner, which matches role.yaml. A couple of supervisor-written ones would still be natural ("mikä on Kampin kohteen ovikoodi, Sanna kysyy") but role.yaml lists only cleaner, so optional.
- Length: all one or two sentences; add a few longer WhatsApp messages (first visit to a site, lists three things they want to know).
- Test split: 13 survive; the test set needs about 10 more from a third model family, deduplicated against train (0526 is wording-close to train 1370).

Systematic teacher problems:
- Qwen 3.5 (local): not usable for Finnish at this size. 22 of 31 dropped; the informal cell is affirms and statements, the terse cell is single nouns, the typo and indirect cells are non-words rather than typos, the formal cell is nonsense. The 8 fixed records each needed a phrase rewritten.
- Gemma 4 12B (local): natural Finnish, but it fills `location_name` with whatever noun the message asks for (or "None"), and its whole `indirect` cell inverted the intent (the cleaner having the details instead of asking). Its `mixed` cell contains no English. Ask it for a site name in the message when the slot is wanted, and reject records whose slot value is not a proper noun at generation time.

---

## other / en (dispatcher)

### 1. Counts

| teacher | kept | fixed | dropped | total |
|---|---|---|---|---|
| teacher:local/gemma4-mia | 69 | 0 | 40 | 109 |
| teacher:local/qwen3.5-mia | 53 | 0 | 32 | 85 |
| all | 122 | 0 | 72 | 194 |

Main drop reasons:
- fits another intent or ambiguous: 65
- unnatural or machine-sounding: 5
- near-duplicate: 2

### 2. Overlap suspects

| id | other intent | rule or reason | text |
|---|---|---|---|
| other/en/local-gemma4-mia/1796 | dispatcher.visit_details | fits dispatcher.visit_details better (where things go at the site, rule 2) | Where do we put the old furniture? |
| other/en/local-gemma4-mia/1799 | conversation.kb_cleaning_howto | fits conversation.kb_cleaning_howto better (can I use X on Y, rule 1) | Is it okay to use the industrial vacuum on the rugs? |
| other/en/local-gemma4-mia/1801 | dispatcher.visit_details | ambiguous: dispatcher.visit_details (scope of the visit) vs checklist | Are we cleaning the gym today or just the lobby? |
| other/en/local-gemma4-mia/1803 | dispatcher.visit_details | fits dispatcher.visit_details better (where things are, rule 2) | Could someone tell me where the extra bleach is? |
| other/en/local-gemma4-mia/1805 | conversation.kb_company_policy | fits conversation.kb_company_policy / how_to_use_mia better (process question, rule 1) | Do I need to sign out before I leave for the day? |
| other/en/local-gemma4-mia/1806 | conversation.kb_cleaning_howto | fits conversation.kb_cleaning_howto better (which product for mirrors, rule 1) | Is there a specific spray for the mirrors? |
| other/en/local-gemma4-mia/1808 | dispatcher.assign | ambiguous: a shift swap with a named person reads as dispatcher.assign / find_cover | Can I swap shifts with Maria next Tuesday? |
| other/en/local-gemma4-mia/1811 | dispatcher.visit_details | fits dispatcher.visit_details better (where things are, rule 2) | Where's the mop? |
| other/en/local-gemma4-mia/1812 | dispatcher.check_out | fits dispatcher.check_out better (terse 'done' is the check-out form) | Done. |
| other/en/local-gemma4-mia/1813 | dispatcher.cannot_access_site | ambiguous: dispatcher.cannot_access_site (no key) vs a key request | Need keys. |
| other/en/local-gemma4-mia/1815 | dispatcher.cannot_access_site | fits dispatcher.cannot_access_site better (locked out) | Locked out. |
| other/en/local-gemma4-mia/1817 | dispatcher.site_problem | fits dispatcher.site_problem better (no water) | Water's off. |
| other/en/local-gemma4-mia/1821 | dispatcher.visit_details | fits dispatcher.visit_details better (where things are, rule 2) | Can't find bin. |
| other/en/local-gemma4-mia/1823 | dispatcher.checklist | fits dispatcher.checklist better (one item done) | Done with floor. |
| other/en/local-gemma4-mia/1824 | conversation.are_you_there | fits conversation.are_you_there better | hey, r u there? |
| other/en/local-gemma4-mia/1826 | dispatcher.cannot_access_site | ambiguous: dispatcher.cannot_access_site (trouble with a door) vs unclear | can u help me with this door? |
| other/en/local-gemma4-mia/1827 | dispatcher.visit_details | fits dispatcher.visit_details better (site instructions, rule 2) | where do i put the trash bags? |
| other/en/local-gemma4-mia/1830 | dispatcher.report_absence | fits dispatcher.report_absence better (running late; hard negative 'sorry I'm late') | sorry i'm running late, traffic is bad |
| other/en/local-gemma4-mia/1832 | dispatcher.cannot_access_site | ambiguous: dispatcher.cannot_access_site (no key to a room) vs lost item | i cant find the keys to the back room |
| other/en/local-gemma4-mia/1837 | dispatcher.cannot_access_site | ambiguous: dispatcher.cannot_access_site (needs a key for the door) vs key question | Hey, do you know if there's a spare key for the back door? |
| other/en/local-gemma4-mia/1839 | dispatcher.visit_details | fits dispatcher.visit_details better (where things are, rule 2) | I can't find the mop bucket anywhere... |
| other/en/local-gemma4-mia/1840 | dispatcher.visit_details | fits dispatcher.visit_details better (where things are, rule 2) | Anyone seen the extra paper towels? |
| other/en/local-gemma4-mia/1844 | dispatcher.visit_details | fits dispatcher.visit_details better (where things go, rule 2) | Is there a specific spot for the old rugs? |
| other/en/local-gemma4-mia/1849 | dispatcher.visit_details | fits dispatcher.visit_details better (where things go, rule 2) | Where do the dirty linens usually go? |
| other/en/local-gemma4-mia/1850 | dispatcher.check_out | fits dispatcher.check_out better (visit completed); also stilted | Good morning, I am writing to inform you that I have completed the cleaning of the main lobby as requested. |
| other/en/local-gemma4-mia/1851 | conversation.kb_safety_rules | fits conversation.kb_safety_rules better (protocol question, rule 1) | Could you please clarify the protocol for disposing of hazardous waste materials in the chemical storage area? |
| other/en/local-gemma4-mia/1853 | dispatcher.visit_details | fits dispatcher.visit_details better (instructions for the visit, rule 2) | Please let me know if there are any specific instructions regarding the high-traffic zones for the evening shift. |
| other/en/local-gemma4-mia/1857 | conversation.thanks | fits conversation.thanks better | Thank you for providing the keys to the secondary storage unit earlier today. |
| other/en/local-gemma4-mia/1860 | dispatcher.report_absence | fits dispatcher.report_absence better (running late) | I'm gonna be running late today, there was a lot of traffic on the highway. |
| other/en/local-gemma4-mia/1861 | dispatcher.cannot_access_site | ambiguous: dispatcher.cannot_access_site (lost key to the entrance) vs key request | Do you have a spare key for the back entrance? I seem to have misplaced mine. |
| other/en/local-gemma4-mia/1862 | dispatcher.visit_details | ambiguous: dispatcher.visit_details (site instructions) vs conversation.kb_cleaning_howto | Is there a specific soap you want me to use in the restrooms? |
| other/en/local-qwen3.5-mia/1865 | conversation.injury_minor | fits conversation.injury_minor / venting better | lol my foot really hurts from all the stairs 😩 |
| other/en/local-qwen3.5-mia/1870 | conversation.medical_advice | fits conversation.medical_advice better (asks tips for back pain) | wow my back is killing me rn, any tips? |
| other/en/local-qwen3.5-mia/1872 | dispatcher.visit_details | fits dispatcher.visit_details better (where things are, rule 2) | does anyone know where the extra mop heads are? |
| other/en/local-qwen3.5-mia/1876 | conversation.hazard_report | ambiguous: conversation.hazard_report (glass in the hallway) vs unclear complaint | seriously who put the glass in the hallway today?! |
| other/en/local-qwen3.5-mia/1891 | dispatcher.checklist | fits dispatcher.checklist better (one area done) | Done hall. |
| other/en/local-qwen3.5-mia/1896 | dispatcher.checklist | fits dispatcher.checklist better (one item done) | Sweep done. |
| other/en/local-qwen3.5-mia/1901 | conversation.how_are_you | fits conversation.how_are_you / greeting better | hello how r doin today? |
| other/en/local-qwen3.5-mia/1902 | conversation.are_you_there | fits conversation.are_you_there better | u up? |
| other/en/local-qwen3.5-mia/1904 | dispatcher.checklist | fits dispatcher.checklist better (one item done) | just finished vac of the lobby |
| other/en/local-qwen3.5-mia/1908 | conversation.thanks | fits conversation.thanks better | thx for helping me carry the boxes |
| other/en/local-qwen3.5-mia/1911 | dispatcher.report_absence | fits dispatcher.report_absence better (late, sick) | guess ima be late today im sick |
| other/en/local-qwen3.5-mia/1913 | conversation.venting | fits conversation.venting better | lol the boss wont even answer his phone |
| other/en/local-qwen3.5-mia/1916 | conversation.apology | no content; fits conversation.apology / help | Sorry to bother you, but I need a quick answer. |
| other/en/local-qwen3.5-mia/1918 | conversation.help | no content; fits conversation.help (bare request) | Just wondering if you could spare a moment. |
| other/en/local-qwen3.5-mia/1921 | dispatcher.visit_details | fits dispatcher.visit_details better (where things are, rule 2) | Where did you put the new cleaning supplies? |
| other/en/local-qwen3.5-mia/1924 | conversation.kb_company_policy | fits conversation.kb_company_policy better (guests at work, rule 1) | Is it okay to bring guests to the office today? |
| other/en/local-qwen3.5-mia/1935 | dispatcher.checklist | fits dispatcher.checklist better (one item done) | hey, just finished sweeping the lobby, it looks clean now. |
| other/en/local-qwen3.5-mia/1937 | conversation.thanks | fits conversation.thanks better | okkkk cool thanks |
| other/en/local-qwen3.5-mia/1938 | dispatcher.visit_details | fits dispatcher.visit_details better (where things are, rule 2) | can u tell me where the broom is? i think i left it. |
| other/en/local-qwen3.5-mia/1939 | conversation.laughter | fits conversation.laughter better | lol nice one |
| other/en/local-qwen3.5-mia/1940 | conversation.confusion | ambiguous: conversation.confusion vs dispatcher.my_visits (what next) | i mean, what am i supposed to do now? |
| other/en/local-qwen3.5-mia/1941 | dispatcher.my_visits | ambiguous: dispatcher.my_visits (when does the shift end) vs unclear | just let me know when i get out of here |
| other/en/local-qwen3.5-mia/1943 | conversation.injury_minor | fits conversation.injury_minor better (catalogue example 'my back hurts after lifting') | my back hurts so much lol |
| other/en/local-qwen3.5-mia/1945 | dispatcher.my_visits | fits dispatcher.my_visits better (where next) | Hey Mike, where are we heading next? |
| other/en/local-qwen3.5-mia/1946 | conversation.oos_directions_transport | fits conversation.oos_directions_transport better | I'm getting lost, do you know exactly which street we're on? |
| other/en/local-qwen3.5-mia/1947 | conversation.kb_safety_rules | fits conversation.kb_safety_rules better (protocol question, rule 1) | What's the protocol for handling broken glass? My last shift was a nightmare. |
| other/en/local-qwen3.5-mia/1948 | dispatcher.my_visits | fits dispatcher.my_visits better (update me on the schedule) | Can someone update me on the schedule? I feel like we've moved three times today. |
| other/en/local-gemma4-mia/0673 | dispatcher.checklist | two labels: break request plus dispatcher.checklist (finished the lobby) | can i take a 15 min break soon? finished the lobby area |
| other/en/local-gemma4-mia/0677 | dispatcher.check_out | fits dispatcher.check_out better; also duplicate of 1812 | Done. |
| other/en/local-gemma4-mia/0678 | dispatcher.visit_details | ambiguous: dispatcher.visit_details (where things are) vs supply request | Where soap? |
| other/en/local-gemma4-mia/0682 | dispatcher.report_absence | fits dispatcher.report_absence better (10 min late) | im gonna be like 10 mins late bc of traffic |
| other/en/local-gemma4-mia/0690 | dispatcher.site_problem | ambiguous: dispatcher.site_problem (locked closet stops work) vs conversation.kb_who_to_contact | Hello, I am writing to inform you that the supply closet on the third floor is currently locked. Could you please advise on who has the key? |
| other/en/local-gemma4-mia/0692 | dispatcher.report_absence | ambiguous: dispatcher.report_absence (cannot work next Friday) vs conversation.kb_leave_rules (procedure) | I would like to request a formal leave of absence for next Friday, the 20th. Please let me know the procedure for submitting this request. |
| other/en/local-gemma4-mia/0695 | dispatcher.visit_details | fits dispatcher.visit_details better (site instructions, rule 2) | Is there a specific place for the trash today or should I just put it in the bin outside? |

### 3. Coverage

What this group is for: `other` is the label for text that fits none of the 13 dispatcher intents and none of the 87 conversation intents. Both teachers produced plausible out-of-scope work chatter, but a third of the records sit on a dispatcher intent, mostly visit_details and checklist, which is the opposite of what `other` should teach.

Systematic issues:
- Both teachers: "where is / where do I put X at the site" questions (mop, bleach, bins, rugs, linens, trash bags) were labelled `other`; role.yaml puts "where things are" and "instructions" under dispatcher.visit_details. 17 records dropped for this. The generator request for `other` should say what the dispatcher intents cover so the teacher writes around them.
- Both teachers: "done / finished X" terse messages (Done., Done hall., Sweep done., just finished vac of the lobby) are dispatcher.checklist or check_out, not `other`. Likewise "running late" (4 records) is dispatcher.report_absence per the catalogue hard negatives.
- Qwen: `mixed` style produced plain English (no second language); the style tag is wrong for the whole cell. Qwen `formal` reads as office broadcast notices ("Your attention is requested", "sector 4"), not a cleaner on WhatsApp; three dropped as machine-sounding, the rest kept as out-of-scope text but they are not realistic cleaner messages.
- Qwen `context` and Gemma `context` cells have no context field (fine for `other`, which is not a follow-up), but several are chat addressed to a coworker by name ("Hey Mike"), which a model-facing chat would not see.
- Gemma: heavy repetition of a few themes (soap, keys, supply closet, flickering light, sticky floor) across styles and across train/test; 2 near-duplicates dropped, several more are the same situation in different words (1809/0688 smell, 1845/0686 sticky floor, 1831/0681/0687/0693 soap). A top-up should ban soap, keys and supply closet.
- Both teachers wrote only for counterpart cleaner. No supervisor records at all (role.yaml gives supervisors a 0.2 share).

Missing for a top-up (en, `other`):
- Supervisor counterpart via web: office or admin chatter that is not dispatcher work (invoice questions, client contract changes, hiring, payroll runs, equipment orders), so the model learns supervisor text that is not find_cover/assign/my_visits.
- Other roles' business intents written as actions, which are `other` for this model: ordering supplies (purchaser), reporting damage at a client's (site_manager), client booking or cancellation (client_service), updating a client's address (admin), quotes (sales). Current data covers purchaser-style supply requests well and the rest barely.
- Messages addressed to Mia that are out of scope but work-adjacent: asking Mia to call a client, to order a taxi, to print something, to book a meeting room, to remind them tomorrow (close to feedback_about_mia; keep clearly outside), to translate a client note.
- Clear non-dispatcher look-alikes near the hard intents, phrased so they are not the intent: "is the key box at Kamppi the grey one" (key_location is not a label today), "who is working at Kamppi tomorrow" (who_is_working is not a label today). These need an explicit decision whether they are `other` or future intents before generating.
- Styles: `mixed` with real Finnish words in English text (e.g. "can't find the varasto key"), `indirect` with hints rather than questions, and `formal` as a polite cleaner, not a memo.
- Short reactions to a Mia answer that are neither affirm/deny/thanks nor a dispatcher reply (e.g. "noted, I'll ask Pekka", "will do after lunch"), to sharpen the boundary with cover_reply and absence_scope.
- Keep the share of `other` at 5 to 10% of the dataset; after this review 122 records remain, which is already large relative to the planned per-intent counts, so a top-up should replace the dropped themes rather than grow the cell.

---

## other, fi (181 records)

`other` here means outside every dispatcher intent AND outside the 87 shared conversation intents
(the role model's labels are the dispatcher intents, the conversation intents and `other`, so a
bare "Kiitos" labelled `other` would fight conversation.thanks from the parallel fi suite). A record
that clearly belongs to a conversation intent is dropped and listed, never relabelled.

### 1. Counts

| source | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | train | 21 | 5 | 61 | 87 |
| teacher:local/gemma4-mia | test | 8 | 4 | 20 | 32 |
| teacher:local/qwen3.5-mia | train | 6 | 0 | 56 | 62 |
| total | | 35 | 9 | 137 | 181 |

Drop reasons (Gemma / Qwen):

| reason | Gemma | Qwen |
|---|---|---|
| not Finnish: gibberish, invented words, broken grammar, stilted machine text | 33 | 20 |
| bare social turn that is a conversation intent (greeting, thanks, affirm, deny, apology, goodbye, how_are_you, are_you_there, sent_by_mistake) | 25 | 22 |
| fits a dispatcher intent (rule 2) | 12 | 2 |
| fits another conversation intent (venting, distress, confusion, about_mia, kb_*) | 5 | 7 |
| ambiguous, two labels | 5 | 3 |
| near-duplicate of an earlier record | 1 | 2 |

Six unnatural drops also carried an intent (noted in the jsonl, not in the table below): G1875
(broken glass, damage/hazard), G1881 (are_you_there), G1882 (spilled chemical, hazard_report),
G1914 (repeat), G1941 (frustration/request_human), Q1992 ("tila on valmis", check_out).

Fixes (all Gemma): one or two words that are not Finnish replaced, meaning kept: G1906
("ihmeen" to "ihan"), G1931 ("käytöstä olevasta" to "ostamastani"), G1936 (stilted tail removed),
G1947 ("Käytätkö sä sinne" to "Käytkö sä siellä"), G1950 ("Sulla onko sattumaan ... ylimäärällä"),
G0702 ("moppituloksia" to "mopit"), G0722 (ungrammatical participle), G0725 ("pihatalta" to
"pihalta"), G0726 ("pesumukit ... huomenen mukaan" to "pesusienet ... huomiseksi"). No slot or
context problems: the intent declares no slots, none were given, and `other` is not a follow-up
(the three Qwen contexts were dropped for other reasons; Q1950's context "Ettekö saaneet kiinni?"
is not a Mia question).

No safety drops: no real names, numbers or addresses; no harmful payload.

### 2. Overlap suspects

Every record dropped because it fits another intent, copies a catalogue example, or would get two
labels. "G"/"Q" is the teacher, "/test" marks the test split. The "same action?" test was applied:
a record is listed only when the text asks for or does the same thing the other intent does.

Fits a dispatcher intent (rule 2, an action or request the dispatcher handles):

| id | text | other intent | reason |
|---|---|---|---|
| G1868 | Oon tänään vähän myöhässä, onko se okei? | dispatcher.report_absence | lateness report (hard negative "sorry I'm late") |
| Q1968 | Mä oon taas myöhäny. | dispatcher.report_absence | lateness report |
| G1870 | Moi, onko ketään täällä? Kaikki ovet kiinni. | dispatcher.cannot_access_site | at the site, cannot get in |
| G1905 | mulla onnaa ongelmaa nääa lukkojen kanssa | dispatcher.cannot_access_site | problem with the locks (also garbled) |
| G1943 | Eiku toi ovi on lukossa tai jotaa. | dispatcher.cannot_access_site | door locked |
| G0718/test | Tää on se siivoushuoneen avainkoppi taas lukossa. | dispatcher.cannot_access_site | key box locked, no key |
| G1877 | Onko situlla koodi siihen varastoon? Munne ei oo vielä saanu. | dispatcher.visit_details | asks the door code (also broken) |
| G1946 | Moi, onko se vessan avain vielä siellä huolletussa huoneessa? | dispatcher.visit_details | where is the key |
| G1948 | Onko se koodi vielä voimassa vai pitääkö mä pyytää uusi? | dispatcher.visit_details | is the door code valid |
| G0729/test | Heippa, pitäisikö mun ottaa ne ikkunatkin huomioon tänään vaia pelkkä lattia riittää? | dispatcher.visit_details | what the job includes (instructions) |
| G1878 | Moi, oon jo melkein valmis, lähen pian. | dispatcher.check_out | finishing and leaving |
| G1902 | Moi, onko sihi joku vapaa nyt? | dispatcher.find_cover | asks who is free now, the same action as "who's free?" (kept as find_cover in the en review) |
| G1929 | Pahoittelut häiriötä, mutta minulla on kysymys työvuorojen aikatauluista ensi viikolla. | dispatcher.my_visits | wants own schedule for next week |

Ambiguous, two labels:

| id | text | labels | reason |
|---|---|---|---|
| G1884 | Onko kukaan täällä jo? Tulin aikaisemmin kuin olin ajatellut. | dispatcher.check_in / other | announces arrival, asks if anyone is there |
| G1920 | Täällä on vähän pimeää nyt. | dispatcher.site_problem / other | "dark" may mean no power; indirect style with no request |
| G1921 | Onko se ovi lukossa? | dispatcher.visit_details / dispatcher.cannot_access_site | asks about access, could be a report |
| G0728/test | Moikka, onko se olohuoneen pyyhkäisy jo tehty? Tuntuu siltä et siellä on vielä pölyä. | dispatcher.checklist / client complaint | asks whether an item is done; reads as a client, not a cleaner |
| Q1958 | Ei. (context: Haluatko auttaa?) | conversation.deny / dispatcher.cover_reply | a no to "do you want to help" is a cover decline |
| Q2010 | Sillä ei ole mitään tekemistä kanssani, en tee sitä. | dispatcher.cover_reply / conversation.deny | refusal of something unnamed |
| Q1961 | No. | conversation.deny / other | Finnish filler "No." or English "No" |
| G0709/test | Kuka? | conversation.confusion / conversation.about_mia | one word, no referent |

Bare social turns, a conversation intent (catalogue examples in brackets):

| id | text | other intent |
|---|---|---|
| G1889, Q1987, G0707/test | Moi | conversation.greeting ("hi") |
| G1895, G0708/test | Terve | conversation.greeting |
| G1900 | Heippa | conversation.greeting (or goodbye) |
| G0710/test | Moi moi | conversation.greeting |
| G0711/test | Tervehdys | conversation.greeting |
| G1904 | onko tää se siivousohjelman ryhmä?? | conversation.greeting ("hello is this the cleaning company") |
| G1910 | tää onko se oikee numero? | conversation.greeting / about_mia (identity check) |
| G1867 | Kuka tää on? Saatan soittaa väärään numeroon. | conversation.about_mia (who is this) |
| G0712/test | onko se kenen numm? en tunnex kuka on | conversation.about_mia |
| G0716/test | hei kuka tää on?? | conversation.about_mia |
| G1891, Q1959, Q1960, Q1976 | Kiitos | conversation.thanks ("thanks") |
| Q1980 | Kiitos paljon | conversation.thanks ("thank you so much") |
| Q1984 | Kiitos etukäteen | conversation.thanks |
| G1890, G1898 | Hieno | conversation.thanks / affirm ("nice") |
| G1901 | Kiva | conversation.thanks |
| Q1995 | Kiitos tiedonannosta, ymmärrän asian. | conversation.thanks / affirm (also stilted) |
| G1892 | Joo | conversation.affirm ("yes") |
| G1894, Q1949, Q1978 | Ok / Okei | conversation.affirm ("ok") |
| Q1952, Q1977 | Kyllä | conversation.affirm |
| Q1979 | Toki | conversation.affirm ("sure") |
| Q1954 | No joo. | conversation.affirm |
| Q1956 | Niin. | conversation.affirm |
| Q1950 | Totta. (context: Ettekö saaneet kiinni?) | conversation.affirm |
| Q1981 | Ei ongelmaa | conversation.affirm |
| Q1982 | Sain viestin | conversation.affirm (acknowledgement) |
| Q1985 | Selvä | conversation.affirm |
| Q1986 | Kyllä näin | conversation.affirm |
| G1893 | Ei | conversation.deny ("no") |
| G1897 | Sori | conversation.apology |
| Q2009 | Anteeksi häiriöstä, se oli vain pieni ongelma. | conversation.apology ("sorry to bother you again") |
| G1924 | Nähdäänkö myöhemmin? | conversation.goodbye ("ok see you tomorrow") |
| Q1955 | Puhutaan myöhemmin. | conversation.goodbye |
| G1918, G0721/test | Mitä kuuluu? | conversation.how_are_you ("how are you?") |
| G1922 | Mitä meininkiä? | conversation.how_are_you ("what's up") |
| G1926 | Mitä on menossa? | conversation.how_are_you / are_you_there |
| Q1965 | Kuinkas nyt menee? | conversation.how_are_you |
| Q1997 | Moi, mitä teet tänään? | conversation.how_are_you (small talk) |
| G0706/test | Heippa! Onko sun päivä sujunu hyvin? | conversation.how_are_you |
| G1915 | Onko täällä ketään? | conversation.are_you_there ("anyone?") |
| G0717/test | Moi, onko siellä ketään? | conversation.are_you_there |
| G1945 | Sorry, meni ihan väärä numero. | conversation.sent_by_mistake ("sorry wrong chat") |
| Q1951 | Odottaa. (context: Menee nyt, vai odotatko?) | conversation.wait (also not a reply a person types) |

Other conversation intents:

| id | text | other intent | rule or reason |
|---|---|---|---|
| G1932 | Onko mahdollista saada ohjeita siitä, miten tässä uudessa koneessa käytetään kemikaaleja? | conversation.kb_cleaning_howto | rule 1, a knowledge question |
| G1935 | Voisitteko kertoa, kuka on yhteyshenkilö siivousvälineiden tilauksiin? | conversation.kb_who_to_contact | rule 1 ("who handles keys" pattern) |
| Q1973 | Mä oon uuvutunut. | conversation.distress | catalogue "I'm burned out"; a safety intent must never train as `other` |
| Q1963 | Mä oon jo siivoannu koko päivän. | conversation.venting | complaint, no request |
| Q1964 | Ei tää homma oo enää okei. | conversation.venting | complaint, no request |
| Q1971 | Tämä on helvetti. | conversation.venting | complaint, no request |
| Q1972 | Kyllä tää on hirvittävää. | conversation.venting | complaint, no request |
| Q1962 | Mitä helvetti tapahtuu? | conversation.confusion / frustration_with_mia | reaction to Mia, no content |
| Q1970 | Mitä sinä sanot? | conversation.confusion / repeat | "what are you saying" |

Considered and kept after the "same action?" test:

| id | text | looks like | why kept |
|---|---|---|---|
| G1872 | Täällä on ihan valtava sotku kuistilla, pitää hoitaa se ensin. | dispatcher.site_problem | extra work found, nothing stops the work; an FYI, not a stoppage report |
| G1885 | Täällä on ihan hirveet määrät pölyä noissa hyllyissä. Pitää varaa aikaa. | dispatcher.site_problem | same: more work, not a site condition that stops it |
| G1928 | Hei, onko mahdollista saada huoltohuoneen avaimet hieman aikaisemmin huomenna? | dispatcher.visit_details / key_location | asks to change a key handover time, not where the key is |
| G1933 | Haluaisin kysyä, onko tällä viikolla mahdollista saada vaihtopäivä siivouksen osalta? | dispatcher.report_absence | asks to swap a day, a different action from recording an absence; no dispatcher intent for shift swaps |
| Q1989 | Onko mahdollista muuttaa siivousaikataulua? | dispatcher.my_visits | asks to change the schedule, not to see it |
| G0719/test | Onko tänään joku vuorossa? | dispatcher.find_cover / who_is_working | asks whether anyone is on shift, not who could cover; who_is_working is not one of the 13 intents |
| G0724/test | Hei, minulle jäi viesti henkilökunnalta, että huoltoyhtiö tulee huomenna. Onko se vielä voimassa? | dispatcher.site_problem | a question whether a maintenance visit still stands, not a report that it stops the work |
| G1866, G1880, G1906, G1930, G1936, G0702/test, G0726/test | supplies requests (lemon cleaner, gloves, mop, detergents, sponges) | conversation.kb_uniform_equipment | a request to get supplies is an action for the purchaser role (rule 2), not the kb question "where do I get them" |

### 3. Coverage

What survives (44 records: 35 kept, 9 fixed; 12 of them in test) is thin and lopsided: 7 supplies
requests, 5 misdirected messages to a person on site (water, toilet, "did you leave the rubbish"),
4 schedule or key administration requests, about 10 vague fragments with no referent ("Onko se jo
valmis?", "En tiedä.", "Mutta", "Huok."), and a few asides. Qwen contributes only 6. The train
cell is 32, below the 60 target; test is 12 of 20 (30 for a high-volume label).

Missing for `other` / fi, to generate as a top-up (all must stay outside the 13 dispatcher intents
AND the 87 conversation intents):

- Other roles' business intents, which are the natural bulk of `other` for the dispatcher model:
  client messages (book a cleaning, move my booking, complaint about the last visit, quote for a
  3-room flat, invoice question), applicant messages (sending a CV, asking about an interview
  slot), accountant or office messages (receipt attached, mileage claim, invoice number), a
  supervisor's admin actions (change a client's address, add a new site, update a cleaner's phone
  number). The generator wrote none of these; counterpart was `cleaner` for every record.
- Cleaner messages that belong to other roles: leave request (not an absence: "voinko pitää
  lomaa heinäkuussa"), payslip missing, tax card, contract or hours question stated as an action
  ("laita mulle lisää tunteja"), damage report ("rikoin vahingossa maljakon"), broken own
  equipment ("imuri hajosi", purchaser.broken_equipment), uniform order, training sign-up.
- Realistic out-of-scope but not a catalogue intent: a long forwarded message, a shopping list
  typed into the wrong chat, a message to a colleague by name ("Jukka, otatko mun avaimet"),
  a reply to a group poll, a voice-note transcript fragment, a copied link with one word.
- Supervisor counterpart on the web channel (share 0.2): none at all.
- Styles: `terse` and `indirect` were almost entirely bare social turns (greeting, thanks, yes)
  and all dropped; real terse `other` is a two-word non-dispatcher request ("uudet hanskat",
  "lasku puuttuu", "Jukalle terveisiä"). `mixed` had no English in it from either teacher; a
  top-up should mix a few English words ("sorry, wrong chat", "ok noted, btw kuitti tulee").
  `context` style gave no usable context; `other` is not a follow-up, so drop the style or make
  it a reply that does not answer Mia's question ("asked about today's visit, user sends a
  shopping list").
- Typos: Gemma's `typo` cell was mostly gibberish (16 of 18 dropped); needs real phone typos on real
  words ("saisnko", "tarvisin", "huomen").

Systematic teacher problems:

- Gemma (fi): about a third of the train cell is not Finnish (invented words "äkkijättä",
  "kukkasuihkeita", "vessasyltti", "moppituloksia"; broken morphology "Haluutasinko",
  "olisti", "sattuunu"; wrong word order "Sulla onko sattumaan"). The `typo` style collapses into
  keyboard mash. Of its 18 `terse` records, 16 are catalogue social turns. On the
  plus side, Gemma's informal and formal registers, when grammatical, are real puhekieli and
  real asiatyyli, and its workplace situations (supplies, keys, lost items, maintenance) are the
  right kind of `other`.
- Qwen (fi): 56 of 62 dropped. Its `terse` and `indirect` cells are the same bare affirm/thanks
  list twice ("Kiitos" x3, "Kyllä" x2, "Okei" x2); its `mixed` cell is nine variants of one
  broken sentence ending "Tai mitä muuta."; its `formal` cell is machine prose ("Yhteydenotto on
  nyt hoitunut asianmukaisesti"); its `context` cell carries no context and no meaning. Four of
  its `typo` records are venting or distress, which are catalogue safety intents. Qwen's fi output
  for this label is not usable as is; regenerate with Gemma or a third teacher, or give Qwen a
  negative list (no greetings, no thanks, no yes/no, no complaints).
- Both teachers read `other` as "anything that is not a dispatcher action", so the cell filled
  with conversation intents (about 65 of 181, counting the ambiguous and the garbled ones). The generator request for `other` should state that the
  87 conversation intents are also excluded and list the bare social turns as forbidden.

---

## The top-up wave (absence_scope and assign for train from both teachers; absence_scope, assign, check_in fi and visit_details fi for test; the sharpened descriptions)

---

## Top-up: dispatcher.absence_scope, en (top-up, train and test)

160 records, every id decided. Context is the only field the intent declares nothing for; role.yaml
lists no slots for absence_scope and no record carried one.

### 1. Counts

| source | kept | fixed | dropped | total |
|---|---|---|---|---|
| teacher:local/gemma4-mia (train 63, test 34) | 60 | 18 | 19 | 97 |
| teacher:local/qwen3.5-mia (train 63) | 36 | 15 | 12 | 63 |
| total | 96 | 33 | 31 | 160 |

Test split (gemma only, 34 records): 31 kept, 3 dropped (near-duplicates inside the test set).

Main drop reasons:
- Near-duplicates, 13 (3 inside test; 7 train records that repeat a test text word for word, which
  would leak test into train: "Whole day.", "Just the morning.", "All day.", "Until Thursday.",
  "only the morning shift", "Just for the morning shift."; 3 train-train).
- Fits dispatcher.report_absence better, 9 (gemma formal cell, all 7 records, are standalone
  "please mark my absence for the morning only" requests with no Mia question; 2 indirect
  records give a reason and say they cannot come in, with no scope).
- Unnatural or meaningless, 8 (qwen: passive "was missed", "got cut", "the whole day is
  covered", the intent name echoed back as "absence scope is limited to").
- Wrong meaning, 2 ("i need to be there the whole day" retracts the absence; "I will be here
  till Thursday" says present).

Main fix reason: missing or wrong context, 33 (gemma informal train cell asked "Are you going to
be absent today?", which invites a report, not a scope; qwen terse, formal and one context
record had no context at all; qwen context cell carried a second question "What time did she
arrive?"). One text edit: 2071 "she's back from 12ish" to first person.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.absence_scope/en/local-gemma4-mia/1992 | dispatcher.report_absence | "My car is acting up so I can't come in today": a reason and a new report, no scope answer. Same action? No: report_absence records, absence_scope narrows a recorded absence. |
| dispatcher.absence_scope/en/local-gemma4-mia/1995 | dispatcher.report_absence | "Everything is a mess so I'm staying home today": fresh report with reason. |
| dispatcher.absence_scope/en/local-gemma4-mia/1996 | dispatcher.report_absence | "Could you please mark me as absent for the entire day today?": a standalone request, no Mia question (look-alike in role.yaml: the first report, not the follow-up answer). |
| dispatcher.absence_scope/en/local-gemma4-mia/1997 | dispatcher.report_absence | "I will be unavailable for the morning session only": standalone, partial_day slot of report_absence. |
| dispatcher.absence_scope/en/local-gemma4-mia/1998 | dispatcher.report_absence | "unable to make it in this afternoon due to an emergency. Please record my absence": reason plus record request. |
| dispatcher.absence_scope/en/local-gemma4-mia/1999 | dispatcher.report_absence | "I need to be absent for the whole day today": standalone report. |
| dispatcher.absence_scope/en/local-gemma4-mia/2000 | dispatcher.report_absence | "I am requesting to mark my absence as morning only": standalone request. |
| dispatcher.absence_scope/en/local-gemma4-mia/2001 | dispatcher.report_absence | "Please register my absence for the afternoon only": standalone request. |
| dispatcher.absence_scope/en/local-gemma4-mia/2002 | dispatcher.report_absence / conversation.correction | "I need to change my reported absence. Please set it to cover the whole day": not an answer to Mia; two labels possible, ambiguous. |
| dispatcher.absence_scope/en/local-gemma4-mia/1981 | conversation.correction | "wait i need to be there the whole day, sorry": withdraws the absence rather than scoping it. |

No record copied a conversation.yaml example. Several kept records start with "Yeah"/"Yes" but
carry a scope ("Yes, I won't be available at all today"), so they are not bare affirm (role.yaml
look-alike: a bare yes is not a scope). No kb_* questions in the file.

### 3. Coverage for absence_scope, en

Situations well covered: whole day, morning only, afternoon only, until Thursday. Thin or missing:
- A named visit or site as the scope: only the gemma test cell has it ("Only the Smith house",
  "the Miller job", "Mrs. Higgins"), and with English surnames. Train has almost none. Needed:
  Finnish site names and clients in English text ("only the Kamppi office", "just the Lehtonen
  place", "the school visit, the rest I can do"), and two named visits in one answer.
- Scope by time of day with clock times beyond 9-12 ("the 7 o'clock one", "anything before 10").
- Multi-day scopes other than Thursday: "the rest of the week", "today and tomorrow", "till I get
  the doctor's note", "back on Monday".
- "All visits except X" and "the first one only" phrasings.
- Corrections of scope after Mia summarised it ("no, the afternoon, not the morning").
- A scope answer that also tells who could cover ("just the morning, Sanna said she can do it")
  so the classifier learns the scope label still wins when a name appears.
- Counterparts: role.yaml allows only cleaner; fine, but supervisor-on-behalf answers ("for
  Jonna it's the whole day") would appear in the web channel and are absent.
- Styles: `mixed` has no non-English words in either teacher's output (all plain English);
  `formal` train is empty after review (gemma's 7 were standalone reports, qwen's good ones are
  three), so a formal top-up is needed with the Mia question in the request.
- Test set has no named-visit variety beyond Smith/Miller/Higgins and no multi-day scope beyond
  Thursday; if train gets the new situations, test needs a few too.

Systematic teacher issues:
- gemma4-mia: the formal cell ignored the follow-up instruction and wrote first-person
  absence requests with no context (7 of 7 dropped). The informal train cell used a context
  ("Are you going to be absent today?") that is not a scope question (18 of 18 fixed). Terse
  cell contexts were machine-speak ("Can you confirm your absence scope?", "Specify the time for
  your absence."). Six train texts repeat gemma's own test texts word for word.
- qwen3.5-mia: terse and formal cells left context empty (16 fixed). Informal and indirect
  cells drift into past-tense reporting after the fact ("was missed", "got cut", "the whole day
  was covered"), which reads like an attendance log, not a reply; 8 dropped for that. One
  context cell appended an unrelated second question ("What time did she arrive?").
- Both teachers: "until Thursday" is the only multi-day scope, lifted from the role.yaml
  description; the description's examples anchor the output too strongly.

---

## Top-up: dispatcher.absence_scope, fi (top-up, train and test)

160 records: gemma4-mia 97 (63 train, 34 test), qwen3.5-mia 63 (train). No slots declared for
this intent, so no slot checks applied.

### 1. Counts

| teacher | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| teacher:local/gemma4-mia | test | 20 | 5 | 9 | 34 |
| teacher:local/gemma4-mia | train | 17 | 31 | 15 | 63 |
| teacher:local/qwen3.5-mia | train | 0 | 34 | 29 | 63 |
| all | | 37 | 70 | 53 | 160 |

Main drop reasons:
- Meaningless or non-Finnish text (word salad such as "oot oonsi", "Puoliaamuna.", "Kattoi eilen
  aamupuolen.", "Kokopäiväpuute on tehty torstaina."): gemma 7, qwen 17.
- Near-duplicates (same words modulo case and punctuation: "Koko päivä." x6, "Vain aamu." x4,
  "Torstaihin asti.", "Iltapäivä.", "Vain se aamun vierailu.", "Se on koko päivä."): gemma 13,
  qwen 2. One qwen train record ("Se on torstaihin asti.") duplicates a test record after its
  typo fix, so the train copy was dropped to avoid leakage.
- Stilted formal text built on "poikkeama" (deviation) for an absence: gemma 2.
- Text addressed to Mia as if Mia were the absent one ("Sinulla on vain aamukauden poisolo"):
  qwen 3.
- Not a scope answer ("Koko ajan.", "Ainoastaan.", past tense about yesterday, "I will only go
  once"): qwen 5.
- Overlap: gemma 1 (see section 2).

Main fix reasons (70 fixed):
- Context (57 records): qwen's whole batch and about half of gemma's train batch had either no
  context (26 records) or an implausible one. Gemma train used "Mitä tarkoitat poissaololla?"
  (asks what absence means, not its scope) and the non-word "aikajatasi". Qwen's contexts were
  broken Finnish ("Käytkö poissaolo kokopäivä tai vain tietyt vieraat?", vieraat = guests),
  third-person narration ("Mia kysyi, käsittääkö puuttuminen...") or a user line addressed to Mia.
  All replaced with one of three plausible Mia questions:
  "Koskeeko poissaolo koko päivää vai vain tiettyjä käyntejä?", "Onko poissaolo koko päivän vai
  vain joku tietty käynti?", "Kattaako poissaolo koko päivän vai vain osan käynneistä?".
- Text (28 records, 15 of them also context): non-words ("poissaan", "ainesti", "puuttelen",
  "torjeihin", "ehjän", "jatuu"), wrong word "puuttuminen"/"poikkeama" for an absence, wrong
  case endings ("tässä iltapäivässä", "iltana"), third person ("sairastuu", "se oli ... poissa").

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.absence_scope/fi/local-gemma4-mia/2071 | dispatcher.report_absence | "En pääse tänään koko päivää, vähän flunssaa." has no context and carries a reason; it is the first report, not the follow-up answer (role.yaml look-alike). Same action? No: report creates the absence, scope narrows it. |

No record copied a catalogue example. Bare "Joo, koko työpäivän." style answers were kept: they
carry a scope ("koko työpäivän"), so they are not conversation.affirm.

### 3. Coverage for absence_scope, fi

What survives is dominated by three answers: whole day, morning only, until Thursday. Missing:

Situations
- One visit named by site, in natural Finnish place or client names ("vaan se Keskustan kauppa",
  "se Lidlin käynti", "Nokian toimisto", "päiväkodin käynti"). Only 4 survive (Joeniva, Turku,
  Kangas, Tori).
- A visit named by time ("se klo 15 käynti", "iltavuoro", "se yökäynti"). Only 2 survive.
- Several visits but not all ("kaks ensimmäistä", "aamun molemmat, iltapäivä hoituu").
- Scope by number of days other than Thursday ("huomiseen asti", "loppuviikon", "maanantaina
  takas", "koko viikon", "pari päivää ainakin").
- Open-ended scope ("en vielä tiedä, ainakin tänään", "katsotaan huomenna", "lääkäri sanoo").
- Partial-day with a time boundary ("klo 12 jälkeen pääsen", "aamupäivän oon poissa, iltapäivällä
  tuun").
- Correcting a scope Mia proposed ("ei koko päivää, pelkästään se eka").

Phrasings and styles
- Qwen produced zero kept records; every surviving qwen record needed a context rewrite. The
  informal style is thin after review (many gemma informal records were word salad). A top-up
  should target informal and typo styles with puhekieli ("vaan", "oon", "pääse", "tuu").
- Mixed style barely contains English; a few records with "whole day", "only the morning one",
  "ok" sprinkled in would match the style definition.
- Indirect style: answers that imply the scope ("lapsi on kuumeessa, en pääse ennen iltaa",
  "aamulla oon lääkärissä, sen jälkeen ok").
- Context style: answers that reference Mia's wording ("se mitä sanoit, koko päivä").

Contexts
- All plausible contexts are now three near-identical Mia questions. A top-up should vary the
  question (Mia naming the visits: "Sulla on tänään Kamppi klo 8 ja Pasila klo 13, koskeeko
  molempia?", or asking about days: "Vain tänään vai pidempään?").

Systematic teacher issues
- qwen3.5-mia: 27 of 63 texts are not Finnish anyone would type; several address Mia as the
  absent person; contexts are machine-translated or narrated, never a plausible Mia question.
  The 18 informal records had no context at all. Its formal records were the usable part.
- gemma4-mia: train contexts repeat one question per style cell and two cells had a bad one
  ("Mitä tarkoitat poissaololla?", "Mitä aikajatasi on tänään?"); terse cells are mostly the same
  two answers repeated ("Koko päivä.", "Vain aamu."), so 13 of 97 fell as duplicates. Test
  records were cleaner than train (20 of 34 kept untouched).

---

## Top-up: dispatcher.assign, en (top-up, train and test)

Input: 233 records (gemma4-mia 134 = 34 test + 100 train; qwen3.5-mia 99 train). No record carried
slots; `dispatcher.assign` declares none, so there was nothing to check there.

### 1. Counts

| teacher | kept | fixed | dropped | total |
|---|---|---|---|---|
| teacher:local/gemma4-mia (test, 2345-2378) | 27 | 0 | 7 | 34 |
| teacher:local/gemma4-mia (train, 2077-2176) | 78 | 0 | 22 | 100 |
| teacher:local/qwen3.5-mia (train, 2137-2235) | 54 | 4 | 41 | 99 |
| all | 159 | 4 | 70 | 233 |

Main drop reasons:
- No first name, so really `find_cover` (26: all gemma `indirect` test and train cells, six qwen
  `typo`/`indirect` records, one qwen `mixed`). The indirect style was read by both teachers as
  "leave the person out", which turns the intent into its look-alike.
- Sanna/Kamppi/tomorrow saturation: near-duplicates of each other or of a test record (16). Three
  train records copy the role.yaml example "Put Sanna on the Kamppi visit tomorrow" word for word,
  which also sits in the test split (gemma 2354, kept as the first occurrence). Four more qwen
  train records are near-copies of gemma test records 2345, 2371, 2372 (leak, dropped on the train
  side).
- Incoherent qwen `indirect` records that treat Mia as the cleaner who should take the visit, or
  say Sanna already accepted and then ask who takes over (12).
- Ambiguous or label-less (correction, undo, help, roster talk, status check) (9).
- Wrong domain or unnatural (tech, case, record, drivers, repairs; "Action required:") (6).
- Safety: one real company (Vapo). One cleaner named "Mia".

Fixes (all qwen): `800` -> `8am` (2180), `helming` -> `helsinki` (2191), and the `context`
removed on two non-follow-up records whose context was not a Mia question (2227, 2229).

### 2. Overlap suspects

"Same action?" applied: a message that asks Mia to find or check for a person is a search, a
message that names the person is the assignment. All below fail the name test or ask something
else.

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.assign/en/local-gemma4-mia/2364 | dispatcher.find_cover | rule 2, no name ("we need someone there") |
| dispatcher.assign/en/local-gemma4-mia/2365 | dispatcher.find_cover | rule 2, "a staff member", no name |
| dispatcher.assign/en/local-gemma4-mia/2366 | dispatcher.find_cover | rule 2, "could you handle that", no name |
| dispatcher.assign/en/local-gemma4-mia/2367 | dispatcher.find_cover | rule 2, "need a person", no name |
| dispatcher.assign/en/local-gemma4-mia/2368 | dispatcher.find_cover | rule 2, "is someone booked ... get that filled" |
| dispatcher.assign/en/local-gemma4-mia/2137 | dispatcher.find_cover | rule 2, "get someone" |
| dispatcher.assign/en/local-gemma4-mia/2138 | dispatcher.find_cover | rule 2, "anyone available" |
| dispatcher.assign/en/local-gemma4-mia/2139 | dispatcher.find_cover | rule 2, "slot isn't left empty" |
| dispatcher.assign/en/local-gemma4-mia/2140 | dispatcher.find_cover | rule 2, "still showing as open" |
| dispatcher.assign/en/local-gemma4-mia/2141 | dispatcher.find_cover | rule 2, "any of the drivers can grab" (also wrong domain) |
| dispatcher.assign/en/local-gemma4-mia/2142 | conversation.help / find_cover | two labels, no action named |
| dispatcher.assign/en/local-gemma4-mia/2143 | find_cover / other | two labels, no name, no visit |
| dispatcher.assign/en/local-gemma4-mia/2144 | find_cover / other | two labels, "fill in the gaps" |
| dispatcher.assign/en/local-gemma4-mia/2145 | dispatcher.find_cover | rule 2, "still unassigned" |
| dispatcher.assign/en/local-gemma4-mia/2146 | dispatcher.my_visits | question who is on a visit (hard negative "is maria working tomorrow") |
| dispatcher.assign/en/local-gemma4-mia/2147 | other | roster update, no name, no visit |
| dispatcher.assign/en/local-gemma4-mia/2148 | dispatcher.find_cover | rule 2, "need a name on that ticket" |
| dispatcher.assign/en/local-gemma4-mia/2149 | dispatcher.find_cover | rule 2, "next available tech" (also wrong domain) |
| dispatcher.assign/en/local-gemma4-mia/2150 | dispatcher.visit_details / my_visits | status question, not an action |
| dispatcher.assign/en/local-gemma4-mia/2151 | other | "sort out the scheduling", no name, no visit |
| dispatcher.assign/en/local-qwen3.5-mia/2186 | dispatcher.find_cover | rule 2, literally "find cover" |
| dispatcher.assign/en/local-qwen3.5-mia/2188 | dispatcher.find_cover | rule 2, "find someone" |
| dispatcher.assign/en/local-qwen3.5-mia/2189 | dispatcher.find_cover | rule 2, literally "find cover" |
| dispatcher.assign/en/local-qwen3.5-mia/2192 | dispatcher.find_cover | rule 2, "who is free for" |
| dispatcher.assign/en/local-qwen3.5-mia/2196 | dispatcher.find_cover | rule 2, "see who fits in" |
| dispatcher.assign/en/local-qwen3.5-mia/2199 | dispatcher.find_cover | rule 2, "who's up for replacing Sanna" |
| dispatcher.assign/en/local-qwen3.5-mia/2222 | conversation.correction | "Not on the Kamppi one" leads; two labels |
| dispatcher.assign/en/local-qwen3.5-mia/2223 | dispatcher.find_cover | rule 2, "find someone else for Hietaniemi" |
| dispatcher.assign/en/local-qwen3.5-mia/2226 | conversation.correction / undo | "don't send Kalle ... keep him"; two labels |
| dispatcher.assign/en/local-qwen3.5-mia/2230 | ambiguous | "she", no first name; assign only if the pronoun resolves |

No record copied a conversation.yaml example.

### 3. Coverage for dispatcher.assign, en

What the kept 163 records cover: imperative assign with a first name and a site or a time
(informal, terse, typo, formal), supervisor only (correct per role.yaml), a few indirect assigns
that still name the person ("Looks like Sanna is free for the Kamppi visit tomorrow. Shall we lock
that in?", "Can Mike take the Evans visit?", "Sanna is covering Kamppi tomorrow.").

Missing or thin, in order of value for a top-up:
- Indirect style that keeps the name. Nearly every indirect record dropped the name and became
  find_cover. The top-up request should say: indirect means the request is implied, the person is
  still named ("Sanna said she can do Kamppi tomorrow", "Kamppi tomorrow, I was thinking Leo",
  "Leo's free tomorrow morning, Kamppi?").
- Entity variety. Train is dominated by Sanna and Kamppi (qwen's whole informal and formal cells)
  or by Anglo client surnames (gemma's "the Smith visit", "the Miller residence"). Ask for Finnish
  first names and Finnish site types: a school, a daycare, an office, a stairwell (rappu), a
  shop, a gym, a client's flat, named by place (Tapiola, Hervanta, Oulunkylä) rather than by
  the client's surname.
- Visit named by time or weekday only ("the 7 o'clock on Thursday", "Friday's late shift",
  "both Kamppi visits this week"), by recurrence ("every Tuesday from next week"), and by a
  cleaner being replaced ("Leo instead of Sanna at Kamppi", "swap Sanna for Leo tomorrow"). Only
  a handful exist.
- Reassignment and partial assign: moving a person from one visit to another, assigning two
  people, assigning for a date range (sick-leave cover until Thursday).
- Mixed style for en: both teachers read `mixed` as "mixed content" (assign plus a follow-up
  request). For en the wanted meaning is a Finnish word or two inside English ("put Leo on the
  Kamppi keikka tomorrow", "Sanna to the siivous at Hervanta"). None exist.
- Context style: records exist but none carry a context. A couple of assigns that answer a Mia
  line ("Who should I put on Kamppi tomorrow?" -> "Leo") would help the resolver, if assign is
  ever allowed a context.
- Web-channel phrasing (the supervisor counterpart is on web): slightly longer, with a reason
  ("Sanna is sick, put Leo on Kamppi tomorrow") so the classifier learns the assign survives a
  leading absence mention. One hard negative cell would also help: assign-like sentences with no
  name labelled find_cover, since the boundary is exactly the name.

Systematic per teacher:
- gemma4-mia: field-service vocabulary (appointment, gig, tech, drivers, call, case, ticket,
  record, residence, account) rather than cleaning; client surnames as site names; `indirect`
  cell is 100 percent find_cover (15 of 15 train, 5 of 5 test); `mixed` cell is one frame with a
  "let me know when he confirms" tail lifted from the description.
- qwen3.5-mia: Sanna/Kamppi/tomorrow in 56 of 99 records including verbatim copies of the
  role.yaml example; `indirect` cell is incoherent (Mia addressed as the cleaner, 12 of 15
  dropped); `terse` cell is one frame "Put <name> on the <time> visit" with 24-hour times
  written without a colon (1500, 1430, 800). Also one real company (Vapo) and a cleaner named Mia.

---

## Top-up: dispatcher.assign, fi (top-up, train and test)

Input: 231 records (gemma4-mia 134: 100 train + 34 test; qwen3.5-mia 97 train). No record carried
slots or context; role.yaml declares no slots for this intent and it is not a follow-up, so
nothing to check there.

### 1. Counts

| teacher | split | kept | fixed | dropped | total |
|---|---|---|---|---|---|
| gemma4-mia | test | 17 | 10 | 7 | 34 |
| gemma4-mia | train | 46 | 24 | 30 | 100 |
| qwen3.5-mia | train | 21 | 19 | 57 | 97 |
| all | | 84 | 53 | 94 | 231 |

Main drop reasons:
- qwen typo cell (15/15): every record is "Sanna teki hyväksynnän Kamppiin huomiseen, lista
  päivitetään", a status line Mia would write, not a supervisor instruction; no typos at all.
- qwen informal cell: garbage verbs "laissa" / "laittu" (11 dropped) in a rigid "Mia, Sanna ..."
  template; the usable ones were fixed.
- gemma terse cell (14/15 dropped): "hoitoon" read as "to handle" but it means "into care"
  ("Matti hoitoon", "Laita Juho hoitoon"); plus "Anna X-lle" template repeats and bare names.
- Garbled or invented words (seelle, kieriin, keksyykö, henkikko, vitsiin, viittiin, Okta, Näin,
  Kamppis, Totta huomi), mostly qwen indirect/formal/mixed/context and gemma context cells.
- Messages addressed to the cleaner, not to Mia ("Sanna, varaa Kampin käynti", "Eliis, teetkö
  Kamppin huomiseen?", "Teet Kampin.", "Voisitko vastata tästä käynnistä Pekka?"): 6.
- Terse "First Surname-genitive" lines that read as a person's full name, not a site (Aino
  Siltalan, Sini Korhosen, Kati Eerolan, Samu Haapalan, Mikael Viikkosen): 5.
- No visit referenced at all ("Pekka hoitaa sen.", "Pekka hoitaa tän.", "Mennään Pekalla.",
  "Pekka.", "Siirrä Pekka tänne."): 6.
- Exact or near duplicates: 9 (keeping the first).

Fixes were light: name case forms (Markuksen, Juhon, Sarin, Mikon, Minnan, Tuomaksen, Matille),
one garbage word swapped for the obvious one, translated openers ("Ole hyvä, aseta") made
Finnish, wrong-domain nouns (kotilääkäri, kyyti, tapaaminen, katselmus) replaced by käynti or a
site. No label, lang or split changed.

### 2. Overlap suspects

| id | other intent | rule or reason |
|---|---|---|
| dispatcher.assign/fi/local-gemma4-mia/2399 | dispatcher.find_cover | no name: "Katotaanpa kuka on vapaana huomispäivän Kampiin" asks who is free (role.yaml: without a name it is find_cover) |
| dispatcher.assign/fi/local-gemma4-mia/2400 | dispatcher.find_cover | no name: "pitäis olla joku hoitamassa" |
| dispatcher.assign/fi/local-gemma4-mia/2402 | dispatcher.find_cover | no name: "Huominen Kampi-käynti pitäis saada täytettyä" |
| dispatcher.assign/fi/local-qwen3.5-mia/2300 | dispatcher.find_cover | "Sanna vai joku muu?" asks for candidates; two labels, dropped |
| dispatcher.assign/fi/local-qwen3.5-mia/2302 | conversation.correction | "Aika korjausta, Sanna Kamppiin" corrects a previous assignment and assigns in one line; two labels, dropped |
| dispatcher.assign/fi/local-gemma4-mia/2243 | (none; status question) | "Sanoitko jo Mattille tuosta asiakaskäynnistä?" asks whether Matti was notified, not an assignment; ambiguous, dropped |
| dispatcher.assign/fi/local-qwen3.5-mia/2301 | (none; status question) | "Kamppi-siivous on nyt Sannan hoita?" asks whether it is already Sanna's; ambiguous, dropped |

"Same action?" check: find_cover (search for a candidate) and assign (name the person) are
different actions, so the first four are genuine mislabels, not a close-pair artefact. The
qwen "Kyllä, Sanna tekee Kampin huomenna" records (2323 fixed, 2327 dropped as a repeat) were
kept as assign and not listed: they name the person and the visit, so the "Kyllä" is not a bare
conversation.affirm. No record copied a conversation.yaml example and none is a kb_* question.

### 3. Coverage: what is missing for assign / fi

Situations
- Almost everything is "Sanna to Kamppi tomorrow" (the role.yaml example, 90+ records across
  both teachers) or "Pekka to that visit". Missing: assigning for today or later this week by
  weekday and time ("Jari Lauttasaareen torstaina klo 8"), a specific client or building name
  (not just a district), a recurring visit ("Pekan vakiovuoro Tapiolassa perjantaisin"),
  swapping two cleaners ("vaihda Mikko ja Sari keskenään"), reassigning from a named absent
  cleaner ("Annan tilalle Tero"), assigning two people to one big site, assigning after Mia
  listed candidates ("ota se ekana ehdotettu, Tero").
- Only one surviving message mentions the acceptance step (2318). A few "laita X ja kysy
  ehtiikö" / "pyydä Sannalta vahvistus" would help.
- Missing negatives inside the cell style set: messages that name a person but are NOT assign
  (asking if someone is working, telling Mia someone accepted) exist only as drops here; the
  who_is_working / cover_reply cells should carry them.

Counterparts: all supervisor (correct for this intent). Web-channel register (longer, typed on a
keyboard, "voisitko siirtää") is covered; short phone-style supervisor messages on the go
("tero malmi klo 9") are thin because the terse cells collapsed.

Phrasings and names
- Name diversity is poor: gemma uses Pekka (30 of 30 informal), Matti (15 of 15 indirect),
  Sanna in test; qwen uses Sanna in 80 of 97. Add Finnish and non-Finnish first names common in
  Finnish cleaning teams (Aleksi, Noora, Jenna, Ville, Mohamed, Amina, Oksana, Nguyen).
- Site diversity is poor: Kamppi dominates; the fixed records add Hatanpää, Kallio, Vantaa,
  Viikki, Sörnäinen, Lauttasaari, Rautatienkatu. More Tampere/Turku/Espoo sites and client names
  ("Prisma Sello", "Aalto-yliopisto", "päiväkoti Tuulenpesä") would help.
- Verbs: laita, siirrä, anna, määritä, varaa, assignata are present. Missing: "merkkaa Sanna
  Kamppiin", "vaihda Sanna tilalle", "Sanna ottaa Kampin", "buukkaa", "laita Sanna sinne
  Mikon tilalle".

Styles
- terse: nearly empty after review (gemma "hoitoon" cell lost 14/15; qwen kept 9 "Name Site" or
  "Name time" lines). Needs a fresh terse cell: "tero malmi huomenna", "sanna kamppi 9.00",
  "mikko tilalle".
- typo: qwen's typo cell contained no typos (all dropped); only gemma's 14 survive. Regenerate.
- indirect: qwen's were mostly garbage; gemma's are decent but availability-check flavoured
  ("onko Matti vapaa", "sopisiko Matille"). Add implied assignments like "Sanna on huomenna
  vapaana ja asuu Kampin vieressä..." or "Pekka tuntee sen kohteen parhaiten".
- mixed: no actual English words in most records (only "visitti", "assignata"). Ask for
  Finnish with English work jargon ("laita Sanna siihen Kamppi shiftiin", "assign Pekka
  huomiselle").
- context: assign is not a follow-up, so these cells had no context field; fine, but the
  generated texts in them were the worst (gemma "syyttelemään", qwen "Kamppi-ajoon"). If the
  context style is meant as "reply after Mia listed candidates", give the generator the Mia
  question so the text can be short ("ota Tero", "se ensimmäinen").

Systematic teacher issues
- qwen3.5-mia: writes from Mia's point of view (status lines, "lista päivitetään",
  "sijoitetaan", "on valittu") and addresses the cleaner by name; invents words (laissa,
  laittu, vitsiin, Kamppis, Okta); prefixes every informal message with "Mia,". 57 of 97
  dropped. Its typo cell has no typos. Unusable without a stronger "you are the supervisor
  writing to Mia" framing.
- gemma4-mia: understands the intent but repeats one name per cell, misreads "hoitoon" in the
  terse cell, and drifts to a care domain (kotihoito, kotilääkäri, hoivakoti). Its grammar
  slips in formal style (name left in nominative: "varaamaan Juho") were fixed.
- Both teachers copy the role.yaml example ("put Sanna on the Kamppi visit tomorrow") as the
  base of most messages; the test split is 30 of 34 Sanna/Kamppi/huomenna, so Gate 2 numbers
  for this intent will be optimistic until the test cell is regenerated with other names and
  sites.

---

## Top-up: dispatcher.check_in, fi (test top-up, 34 records)

### 1. Counts

| source | kept | fixed | dropped | total |
|---|---|---|---|---|
| teacher:local/gemma4-mia | 2 | 10 | 22 | 34 |

All 34 records are from one teacher (gemma4-mia), all split test.

Main drop reasons:
- Test leak, 17: word-for-word copy of a train record (2415, 2419, 2422, 2423, 2424, 2425, 2434) or a near copy differing by one word, a verb form or a removed place name (2417, 2421, 2429, 2432, 2433, 2436, 2437, 2444, 2446) plus 2440 (near copy of train 0705 and of 2438 in this file). The teacher recycled its own train phrasings; short terse/indirect messages leaked almost without exception.
- Gibberish or broken grammar, 4: 2427, 2430, 2431, 2445 (the `typo` style produced nonsense words and "Mulla on nyt saapun" grammar errors rather than typos).
- Translated-sounding, 1: 2439 ("aloitan vierailun").

Fixes: 4 slot values were nominative forms that do not occur in the inflected text (Tapanilahti/Tapanilahdella, Pihdeniemi/Pihdeniemellä, Karihunranta/Karihunrannalla, Pohjoisreitti/Pohjoisreitillä), set to the surface form; 4 empty `location_name: ""` slots removed (2426, 2435, 2438; the other empty ones were dropped for leaks); 2 text fixes for non-Finnish wording (2414 invented non-word "Keskusasiatissa", 2442 "rullaan homman käyntiin"); 1 text fix for a grammar error in a typo-style record (2428).

### 2. Overlap suspects

None. Every record is an arrival report; none fits check_out, cannot_access_site, a kb_* question, greeting or affirm better, and none copies a conversation.yaml example. "Menen sisään" / "menen töihin" (2414, 2418, 2435) pass the same-action test: entering the building is the start of the visit, not a site-access problem.

### 3. Coverage: what the fi test set for check_in still lacks

Surviving records: 12 (2 kept, 10 fixed), 7 of them carry a location_name. Styles left: informal 6, terse 1, typo 1, formal 1, mixed 3, indirect 1 (2435), context 0.

Missing situations and phrasings (none in train either, so safe to generate for test):
- Arrival with a time or lateness note ("oon perillä, vähän myöhässä", "pääsin paikalle vasta nyt kun bussi oli myöhässä").
- Arrival at a named site type instead of a street: koulu, päiväkoti, toimisto, kerrostalon rappu, kauppa, hoivakoti, with the location_name slot filled from the text.
- Arrival stated through the key or door ("sain oven auki, aloitan", "avain löytyi, oon sisällä") without any access problem, to sharpen the cannot_access_site boundary.
- Arrival with a question or a second clause that stays check_in ("oon paikalla, alotanko keittiöstä?", "perillä, saako aloittaa vaikka asiakas on vielä paikalla?" would be site_problem, so only the first kind).
- Second visit of the day ("nyt toisessa kohteessa, aloitan", "siirryin Hakaniemen kohteeseen").
- Terse with a place ("Kamppi, perillä", "Kirkkokatu 5 ok", "paikalla 7.58"), emoji-only-plus-word ("perillä 👍").
- Indirect style that is actually indirect ("voit merkata mut alkaneeksi", "kello käy, hommiin"), not a typo'd "Olen perillä".
- Typo style with realistic phone typos (missing letters, autocorrect, no umlauts: "oon perilla ja aloitn nyt") instead of invented words.
- Mixed style with an English word or two ("checkasin sisään", "oon on site, starttaan").
- Context style: a message answering Mia's reminder ("Oletko jo kohteessa?" -> "joo, oon, aloitan nyt"), with a context field, so the set has a check_in follow-up.
- Group chat tone to a supervisor named in passing ("Hei, oon nyt Kaisan kohteessa, aloitan") is still cleaner-written check_in.

Systematic issues with gemma4-mia's output:
- Reuses its own train sentences for the test split; a top-up for test must be deduplicated against train (surface-form similarity above about 0.8 dropped) before review.
- Writes `location_name: ""` for every record without a place; slot should be absent instead.
- Puts the nominative in the slot while the text has an inflected form; the slot should be the surface span.
- Opens formal records with "Tervehdys", which no Finnish cleaner types; prefer "Hei" or nothing.
- `typo` style degrades into non-words (saippua, tsiin, alkon on) and into "Mulla on" + participle grammar errors.
- `indirect` style is not indirect; it is the same terse arrival sentence.

---

## Top-up: dispatcher.visit_details, fi (test top-up, 23 records)

### 1. Counts

| source | kept | fixed | dropped | total |
|---|---|---|---|---|
| teacher:local/gemma4-mia | 10 | 9 | 4 | 23 |

Only one teacher wrote this cell.

Drop reasons:
- 2 test leaks: `Osoite?` (2455) and `Onko ovikoodi?` (2456) are word-for-word copies of fi
  train records for this intent.
- 1 template repeat: 2461 reuses the opener and the typo of 2459 (`onko siha joku ... tai ... ohjeita`).
- 1 near-duplicate: 2463 is 2452 with the clauses swapped (and not indirect as labelled).

Fix reasons (9):
- 5 slot fixes: `location_name: ""` on terse and mixed records (2454, 2457, 2468, 2469) and
  `location_name: "asunnon numero"` (2464), which is not a place name. None of the 23 texts names
  a site, so no record keeps a location_name slot.
- 5 text fixes for non-Finnish or ungrammatical phrases outside the typo style: `onko siellä
  kiinni pitää jotain erityistä` (2449), `epävara` (2462), `oon jo lähimpänä` (2465),
  `Olisikin hyvä` (2467), `voisinko sun osoitteen nähdä` (2468, asked for Mia's own address),
  `onko joku erityinen huomioitavaa` (2469).

### 2. Overlap suspects

None dropped for fitting another intent or copying a catalogue example. Checked:

| id | other intent considered | outcome |
|---|---|---|
| 2465 | dispatcher.cannot_access_site | kept (fixed): cannot find the entrance is a question about where to go in, not a locked door, code or alarm; same-action test says different action (ask for directions vs report a failure). Watch it in the confusion list. |
| 2457, 2460, 2464, 2448 | dispatcher.key_location (named as look-alike in role.yaml) | kept: role.yaml declares no `dispatcher.key_location` intent, so "where are the keys" is visit_details ("where things are"). Either add the intent or delete the two look-alike lines. |
| 2451 | conversation.kb_cleaning_howto | kept: where the detergents and bins are, not how to clean. |
| 2450 | conversation.repeat (`repeat the address` example) | kept: the address was never sent, so it is a details request, not a repeat. |

### 3. Coverage (fi, visit_details)

Missing after this top-up, together with the existing fi train data:
- Named sites: no record names a location (slot `location_name` is empty in all 23 and in all
  21 fi train records). Need messages like "mikä on Kampin kohteen ovikoodi", "osoite huomisen
  Tapiolan keikkaan", "missä Lauttasaaren toimiston siivouskomero on" so the slot head sees
  Finnish place names.
- Time-anchored questions: "huomisen aamun kohde", "iltavuoron paikka", "ens viikon tiistain
  keikka": every record asks about an unspecified visit.
- Detail types beyond address and door code: parking, which floor or staircase (rappu),
  alarm code to disarm, where the cleaning cupboard and the vacuum are, client contact person,
  whether the client is home, what to do with the key afterwards (one record), waste sorting room.
- Styles: `context` style (follow-up after Mia listed visits, e.g. "ja toi eka, mikä sen koodi
  oli?") has one train record and none here; `mixed` records contain no English words at all
  (the teacher treats mixed as neutral Finnish); `indirect` records are mostly direct questions.
- Counterpart: all cleaner, which matches role.yaml.
- Supervisor-free, so no coverage gap there.

Systematic teacher issues (gemma4-mia): fills `location_name` with an empty string on terse and
mixed cells instead of omitting the slot; repeats one typo token (`siha`) across a typo cell;
produces ungrammatical clause endings in about a quarter of the longer records (`kiinni pitää
jotain erityistä`, `joku erityinen huomioitavaa`, `Olisikin`); two terse records are verbatim
copies of the train split, so terse cells need a dedup against train before splitting.
