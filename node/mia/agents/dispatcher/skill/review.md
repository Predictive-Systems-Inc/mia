# Dispatcher skill data: review notes (Gate 1 package)

Date: 2026-10-12. Plan: role.yaml (13 intents, en and fi, cleaners 80% over WhatsApp,
supervisors 20% over the web). Teachers: `local/gemma4-mia` and `local/qwen3.5-mia` for train
(two families, nothing leaves the node). The test set comes from `local/gemma4-mia` again:
the rule asks a third model family, and this Mac has none that answers structured chat (its
`clef-flash` tag does not support chat). The test set is therefore provisional, usable to tune
nothing and to read the first report only, until a cloud teacher of another family regenerates
it (a Gate 1 decision; the spend is small, the data synthetic).

## Overlap review (one message, one label, D30)

Every role intent against the conversation catalogue (87 shared intents) and the other roles'
rows in docs/capabilities.md (no other role has a role.yaml yet). Rules from guidelines.md:
(1) questions about rules are kb_*, (2) doing stays with the role, (3) sender role does not
make a new intent.

| Pair | Decision | Rule, reason |
| --- | --- | --- |
| report_absence vs conversation.kb_sick_leave_rules | keep both | 1: "am I paid when sick" is a question; "I'm sick tomorrow" is the action |
| report_absence vs cover_reply (decline) | keep both, sharpen | 2: a decline answers a cover request, an absence drops a visit; descriptions name the difference, look-alike cells generate the boundary |
| report_absence vs absence_scope | keep both | follow-up with context; absence_scope only ever answers Mia's question |
| absence_scope vs conversation.affirm | keep both | a bare "yes" stays affirm; scope names the visits |
| cover_reply vs conversation.affirm / deny | keep both | the reply to a cover request is the role's write; affirm and deny carry no context of a request |
| my_visits vs visit_details | keep both | the list versus one visit's details (address, code) |
| my_visits vs who_is_working (phase 2) | keep my_visits | 3: a supervisor asking about someone else's visits is my_visits with a person; who_is_working is a staffing view, not built |
| find_cover vs assign | keep both | asking for candidates versus naming the person (the "same action?" test: different actions) |
| check_in vs check_out | keep both | arriving versus leaving |
| check_out vs checklist | keep both | the whole visit versus one item |
| check_out vs conversation.goodbye | keep both | "I'm done here" ends a visit; "bye" ends a chat |
| cannot_access_site vs admin.reset_login | keep both | a building versus Mia; the catalogue row says so |
| cannot_access_site vs visit_details | keep both | asking for the code versus reporting that it fails |
| site_problem vs purchaser.broken_equipment | keep both | the client's site versus the company's own machine |
| site_problem vs conversation.hazard_report | keep both | work stopped versus a danger to people |
| visit_details vs conversation.kb_cleaning_howto | keep both | 1: where and how to get in versus how to clean |
| send_photos vs conversation.media_without_text | keep both | words announcing photos versus a bare attachment (the channel path handles the bytes) |

Label count for the model: 13 role intents + 87 conversation intents + `other` = 101, within
the budget of about 150.

`uv run mia skills overlap dispatcher`: run on the reviewed data, read in the data review below.

## Data review (12 Oct 2026)

### Generation

Three runs on this Mac (`uv run mia skills generate dispatcher --model local/<teacher> --split
<split>`, 210 cells each): Gemma 4 12B train, 1951 records in 2 h 7 min; Qwen 3.5 train, 2011
records in 46 min; Gemma 4 12B test, 730 records in 1 h 14 min. Top-ups after the first review
(absence_scope and assign for train from both teachers; absence_scope, assign, check_in fi and
visit_details fi for test) with the sharpened descriptions in role.yaml.

Five defects in the tools showed up in the run and are fixed on this branch:

1. A teacher message whose slot name the intent does not declare was dropped whole (521 of the
   first 4692 messages, which emptied absence_scope: Qwen put a `scope` slot on every answer).
   The slot is now removed and the message kept, counted as repaired.
2. The test run numbered its ids from zero like the train run (34 collisions in
   report_absence/en). A run now continues after the highest index that teacher has on disk; the
   first test run's records carry the tag `local-gemma4-mia-test` so every id is unique.
3. `validate` and `train` counted test records the reviewer had dropped in place; both skip them
   now, as `split` already did for reviewed.jsonl.
4. `split` counted only records of kind `normal` toward the dev quota, and `other` records
   carry kind `other`, so every `other` record went to dev and none to train. A label's own
   examples (normal, and other for `other`) count now.
5. A concrete example sentence in an intent description is copied by the teachers: the
   sharpened assign description named "put Sanna on the Kamppi visit tomorrow" and 30 of the
   34 Finnish assign test records lean on Sanna, Kamppi and tomorrow (the reviewers dropped the
   near copies). The example is removed from the description; descriptions name the shape of a
   message, never a message.

The teachers' Finnish is far below their English, which is the headline below.

### Review method

Twenty-eight reviewer runs, one per intent and language (Claude Fable 5.1 as the reviewer model
with prompts/reviewer.md and a brief), every record of the three generated files and the top-up
files decided: kept, fixed (context, slots or wording, never the label) or dropped, with a note in
the record's `review` field. The per-cell notes (counts per teacher, the overlap suspects, what a
top-up must add) are in reports/review-cells-2026-10-12.md. Decisions were applied by position in
the generated files (defect 2 above), five Finnish slot values were set to the inflected span as
written in the text (the slot head learns spans), and one record was dropped on the overlap
report's paraphrase list as ambiguous. Then `uv run mia skills split dispatcher` and `uv run mia
skills validate dispatcher`.

### Counts after review

| Intent | Lang | Train (target) | Dev | Test (target) |
| --- | --- | --- | --- | --- |
| report_absence | en | 164 (100) | 15 | **29** (30) |
| report_absence | fi | 102 (100) | 15 | **24** (30) |
| absence_scope | en | 131 (60) | 15 | 31 (30) |
| absence_scope | fi | 81 (60) | 15 | **25** (30) |
| my_visits | en | 41 (60, above the minimum) | 10 | 23 (20) |
| my_visits | fi | 37 (60, above the minimum) | 10 | 20 (20) |
| find_cover | en | 50 (60, above the minimum) | 10 | 24 (20) |
| find_cover | fi | 31 (60, above the minimum) | 10 | 22 (20) |
| assign | en | 186 (100) | 15 | 32 (30) |
| assign | fi | 108 (100) | 15 | **27** (30) |
| cover_reply | en | 68 (60) | 15 | 33 (30) |
| cover_reply | fi | 40 (60, above the minimum) | 15 | **28** (30) |
| check_in | en | 162 (100) | 15 | **26** (30) |
| check_in | fi | **81** (100) | 15 | **24** (30) |
| check_out | en | 148 (100) | 15 | **23** (30) |
| check_out | fi | **81** (100) | 15 | **16** (30) |
| cannot_access_site | en | 171 (100) | 15 | 30 (30) |
| cannot_access_site | fi | **90** (100) | 15 | **26** (30) |
| site_problem | en | 141 (100) | 15 | **28** (30) |
| site_problem | fi | **77** (100) | 15 | 30 (30) |
| visit_details | en | 43 (60, above the minimum) | 10 | **11** (20) |
| visit_details | fi | **21** (60) | 10 | 32 (20) |
| checklist | en | 113 (100) | 15 | **25** (30) |
| checklist | fi | **80** (100) | 15 | **17** (30) |
| send_photos | en | 138 (100) | 15 | **26** (30) |
| send_photos | fi | **63** (100) | 15 | **25** (30) |
| other | en | 88 (60) | 10 | 24 (20) |
| other | fi | **22** (60) | 10 | **12** (20) |

Usable records by teacher: gemma4-mia 2460; qwen3.5-mia 1171; total 3631.

Bold is below the target in guidelines.md (write and high-volume intents 100 train, 15 dev,
30 test; follow-ups 60/15/30; reads 60 target with 30 minimum, 10, 20). `validate` reports 28
shortfalls: the Finnish train cells of six write intents, `other` in Finnish, and the test set
in 19 cells. The top-ups filled absence_scope and assign in both languages; the test top-up
for check_in fi lost 17 of 34 records as copies of train records (the same-family test set,
below).

### The teachers

- Gemma 4 12B (local): usable in both languages, about four records in five kept or fixed. Its
  faults are mechanical: it loops on one sentence pair when asked for 30 messages in one call,
  fills `location_name` with "", "none" or a common noun instead of leaving it out, writes the
  `mixed` style without a single English word, and reuses its own frames in the test run (about
  60 test records were word-for-word or near copies of train records and were dropped). It also
  wrote no names for assign and one off-target context per style cell for the follow-ups, which
  the sharpened descriptions fixed in the top-up.
- Qwen 3.5 (local): English about three records in five usable, Finnish not usable: two records
  in three dropped for invented words and calques (vieras for a visit, puhdistaja for a cleaner,
  peittoon for cover), third-person templates ("Siivooja on ..." 26 times), the system's or
  Mia's voice on follow-up intents, and no `context` on follow-ups at all. Its surviving
  Finnish records are the short informal ones.
- Both: no code-switching in any `mixed` cell, few real typos in the `typo` cells, Anglo-American
  names and places in the English cells (Smith, Oak Street, Mornington Peninsula), and the
  supervisor cells of my_visits written as a person asking Mia for Mia's own schedule.

### Coverage: what the next top-up must add

By intent, from the per-cell notes (details in reports/review-cells-2026-10-12.md):

- report_absence: lateness and leaving early with a time, multi-day absences, the Finnish
  `mixed` and `typo` styles with real English words and real typos.
- absence_scope: scopes that name a visit or a site, time-based and multi-day scopes, answers
  to Mia's listed candidates ("ekaa vaan"), varied Mia questions in `context`, terse one-word
  answers in Finnish.
- my_visits: a weekday or a date, the next visit only, counts ("am I working tomorrow"),
  change checks, and the supervisor asking for their own day as a supervisor would on the web.
- find_cover: a concrete visit with a time and a place, a named absent cleaner without naming a
  replacement, constraints on the candidate (car, key, induction), several visits at once.
- assign: assignment after a find_cover answer (with context), replacement framing in Finnish
  ("X Y:n tilalle"), several visits to one person, polite instructions with a question mark.
- cover_reply: conditional and partial accepts, declines with a concrete reason, replies that
  echo the colleague or the site named in the context, emoji-led replies.
- check_in: arrivals that name a fictional Finnish site in the informal, terse and typo styles
  (the slot is nearly empty in Finnish), late arrivals, the second visit of the day, arriving
  before the key holder (still check_in).
- check_out: a named site in the text (no usable `location_name` in 230 Finnish records), a
  time of leaving, lock-up remarks, leaving with something undone, the last visit versus moving
  on to the next.
- cannot_access_site: key box and intercom cases, wrong floor or entrance, alarm armed, night
  and weekend wording, what the cleaner will do next ("wait or skip"), Finnish place names.
- site_problem: partial problems ("skipped the kitchen, client was cooking") on both sides of
  the checklist boundary, Finnish site situations, one problem per message.
- visit_details: a site name in the slot (every Finnish slot value was wrong), parking and
  where things are, the key question once dispatcher.key_location is decided (below).
- checklist: several items in one message, the list of a named site, items beyond floors,
  windows and kitchen (bins, consumables, keys back, alarm set), ticking the last item without
  closing the visit.
- send_photos: the bare "[photo] + caption" form, before and after photos, photos Mia asked
  for, upload trouble, any Finnish words in the English `mixed` cells.
- other: messages from the other roles' business (ordering supplies, invoices, a client
  booking), the supervisor on the web, real terse and typo styles; bare social turns belong to
  the conversation intents and were listed, not kept.

### Overlap after the data (one message, one label)

`uv run mia skills overlap dispatcher` (reports/overlap-202610120456.md, multilingual-e5-small,
on the reviewed data): no merge, split or narrow candidates. Nearest dispatcher pairs: check_in
and check_out (0.52), cannot_access_site and site_problem (0.45), cover_reply and report_absence
(0.35); assign and find_cover fell from 0.39 before the top-up to 0.26 after it (the named
person separates them). These are the pairs the reviewers flagged and the pairs Gemma confuses in
docs/research/local-models-2026-10-12.md. Its suspect-label list (129 records whose neighbours
carry another label) was read next to the reviewers' decisions; its 20 cross-intent paraphrases
are short Finnish messages that compress to the same embedding with different meanings ("Oon
paikalla, aloitetaan nyt" against "Lähden nyt, valmis"; an absence_scope answer against a
report_absence message, told apart by the context), one of which was ambiguous and is dropped.

The reviewers listed 262 records that fit another intent better or would get two labels (214
in the first wave, 48 in the top-up), all dropped, none relabelled (tables in
reports/review-cells-2026-10-12.md). By the intent they fit, first wave: cannot_access_site 28
(locked doors written for site_problem and `other`), check_out 22 ("all done" written for
checklist and check_in), visit_details 20 ("where is X" written for `other`), checklist 16,
conversation.affirm 16 (a bare yes written for cover_reply or absence_scope),
conversation.hazard_report 12 (floods and smoke written for site_problem), report_absence 9,
dispatcher.who_is_working 8 (a supervisor asking who works where, written for my_visits). In
the top-up most are find_cover written for assign (no name, 30) and report_absence written for
absence_scope (a standalone report, 10).

Three decisions for the developer at Gate 1:

1. `dispatcher.key_location` is named as a look-alike in role.yaml but is not one of the 13
   intents. Ten "where is the key for X" records were dropped from visit_details and
   cannot_access_site. Either add the intent (then regenerate its cells and the test set) or
   widen visit_details to cover it and restore those records.
2. The site_problem and cannot_access_site boundary: the reviewers kept "cannot get in because of
   a named site condition" (renovation crew, event security, client still inside) as
   site_problem and "locked or closed door, no key, wrong code" as cannot_access_site. If that is
   the rule, the two descriptions should say so.
3. Three terse cover_reply records ("Sure", "No thanks", "Yeah") are word-for-word catalogue
   affirm and deny examples. They are kept because role.yaml says a yes to a cover request is
   cover_reply and the train record carries the context; the validator warns on two of them.
   Drop them if the model should never see a catalogue example under a role label.

### Validator warnings, with a judgement

- `cover_reply/en/.../0423 equals a conversation.yaml example: 'Sure'` and `0424 'No thanks'`:
  decision 3 above; kept for Gate 1.
- `hard negatives 0% < 15%`: the generator plans no `negative` cells (only normal and `other`).
  The look-alike intents are each other's hard negatives here (find_cover against assign,
  check_in against check_out, cannot_access_site against site_problem, absence_scope against
  report_absence), which is the boundary the reviewers policed. Acceptable for Gate 1; a
  `negative` cell kind in the generator is the next tool change before Gate 2.
- `injection attempts under 1%` and `no safety records`: the role's own data has none, and
  `train` reads only the role's train, dev and test files while its label space holds the 87
  conversation intents (prompt_injection, emergency, hazard_report and the rest) from the
  catalogue. As the tool stands those labels would train on no rows at all. The rows exist:
  tests/evals/intents.jsonl holds 3664 English and 1051 Finnish labelled utterances across every
  intent, including the conversation ones. Before training, `train` should take the
  conversation rows from there (or the catalogue's examples); a tool change for the train step,
  blocking Gate 2, not the review of this data.
- The `may not be <lang>` warnings: none after review (the reviewers dropped the wrong-language
  text).

### Test set

Provisional: it comes from Gemma 4 12B, the same family as a train teacher, because this Mac has
no third family that answers structured chat. After the review it is also short (table above)
and it had copied train records, which were dropped. It can read the first training report; it
tunes nothing. A test set from a cloud teacher of another family (synthetic data only, D18) is
the recommended Gate 1 spend, together with the Finnish train cells of the write intents.

### Gate 1 package

role.yaml (13 intents, the two sharpened descriptions), the overlap table above, public.yaml
(nothing used yet), about 20 records per language from train and test (`head` of
data/train.jsonl and data/test.jsonl, or the samples in the pull request), this file and
reports/review-cells-2026-10-12.md. Training (`uv run mia skills train dispatcher`) waits for
the developer's approval (Q26).
