# Sales supervisor v1: counts, short codes, reminders, targets, reports

19 Oct 2026. Part 2 of the retail work (part 1: docs/superpowers/specs/2026-10-18-multi-agent-routing-design.md). The first agent built for a shop, and the template the `/mia-build-agent` skill (part 4) is extracted from. Proof shop: Ferino's Bibingka, a Philippine chain of kiosks with a commissary.

**Status: in execution (19 Oct 2026).** Section 4 first proposed new core tables (data standard 1.5) and waited for the owner. The owner asked for all use cases to be built; under rule 9 a table is shared only once a second agent reads it, and none does yet, so v1 uses agent-owned `sales_supervisor_*` tables, with promotion to core when the branch_manager (part 3) arrives (Q39). That promotion edits `0000_initial` in place before the first candidate release (rule 14) and gets an ADR; the owner can still say "1.5 now" and the plan's data task moves the tables to core.

## 1. Goal

A clerk sends what they sold, in their own words and language, from a phone; the owner and head staff see the day without asking; targets are set once and compared every day; the reason behind a good day is written down the day it happens. All of it offline-testable: Jev picks, code counts, templates word.

Out of scope here (decided 19 Oct): coaching, cheers, motivational quotes, tips, experiments and owner recommendations (part 3, branch_manager); stock, cash, pay, menu changes (their own agents); every feature that needs a generative, vision or speech model (next phase: voice notes, receipt photos, translation of free text, drafts).

## 2. Who talks to it

| Role | Does | Sees |
| --- | --- | --- |
| clerk | reports counts, corrects them, asks "how are we doing" | own branch, today |
| supervisor (head staff) | the same, plus the branch's day and week, sets the branch's target when allowed | own branch |
| owner, admin | all of the above for every branch, sets targets, gets the end-of-day report | every branch |

Roles already exist (`clerk` is in `HUMAN_ROLES` since part 1; `supervisor`, `owner`, `admin` from the cleaning work). `policy.csv` gains `agent:sales_supervisor, use` for these four and the tool lines below.

## 3. Scenarios (the acceptance list)

1. **Counts in free text.** "3 special 5 classic 2 salted egg", "sp 3 cl 5", "nakabenta ng 12 ube", mixed languages, typos. Code splits numbers from words; Jev maps each word group to one item from the branch's menu (a choice per group over item names and short codes, "none" allowed); a group Jev is unsure about becomes a "Did you mean" with the three nearest items (nothing in the message is recorded until every group has an item, Q50). Amount is quantity times the item's current price; a stated total that disagrees asks before recording (Q44, 24 Oct 2026).
2. **Correction.** "sorry, 4 special not 3" replaces the last count of that item today by that clerk; the old row is kept and marked superseded. "Cancel the last one" supersedes the last count.
3. **How are we doing.** Today's total and per item for the branch, against the target when one exists, in one short message; for owners, per branch.
4. **Closing reminder.** At the branch's closing time minus 30 minutes, every clerk on shift today (from `core.visit` or, with no roster, every active clerk of the branch) who has sent no count today gets one reminder; 30 minutes after closing head staff gets the list of who has not reported. Quiet hours (`OrgSettings.quiet_hours`) are respected.
5. **End-of-day report to the owner.** At closing plus one hour: per branch and item, total against target, against the same weekday last week and the last four weeks' average. One notification per owner and admin, in their language.
6. **Morning message to staff.** At opening: yesterday's result in one line and today's target. No tips, no quotes (part 3).
7. **Targets.** "Target for December is 60,000 for the mall branch", "target tomorrow 3,500": a target per branch per day, or per month spread evenly over open days (a month target is stored as one row with `period = month`; code derives the day's share). Only supervisor, owner and admin; a clerk is told who can.
8. **Why did it go well.** When a branch beats its target (or its four-week average by 20% with no target), the agent asks everyone who reported that day, once, in the evening: "Why do you think sales went well?" Free-text answers are stored as notes, pseudonymised in nothing (they stay on the node), themed by Jev against a fixed list (`weather`, `foot_traffic`, `event`, `promo`, `staffing`, `supply`, `technique`, `other`), and never answered with advice (part 3 reads them).
9. **Questions across days.** "Best day this month", "how did Saturday go", "which branch sells most salted egg": code answers from counts; Jev fills the period, branch and item slots.
10. **First contact on a channel.** A new clerk added by the owner with a phone number sends "hi" on WhatsApp: the language question (part 1, `language_known=False`, its first production caller) comes first, then the sales supervisor's greeting with the three things it does.

Every scenario has an eval case per gated language (en, fil, ceb, hil, war, bcl) in the decider's eval set, and a chat test with the fake Jev.

## 4. Data

Rule 9: a table more than one agent reads or writes is shared (core); industry fields live in a template; data no other agent needs is agent-owned and prefixed with the agent id. Today only the sales supervisor reads these tables, so v1 keeps them agent-owned (Q39). The branch_manager (part 3) will read counts, targets and notes; the inventory_manager will read counts; the bookkeeper will read daily totals. When the first of them is built, the three tables move to core as data standard 1.5 with an ADR (an in-place edit of `0000_initial` before the first candidate, rule 14). Column names below are chosen so the move is a rename of the table only.

**Agent-owned, in `mia/agents/sales_supervisor/models.py`:**

| Table | Row | Notes |
| --- | --- | --- |
| `sales_supervisor_counts` | one item count by one person at one branch: `item_id`, `quantity`, `amount` (minor units, currency), `reported_at`, `reported_by`, `business_date`, `supersedes` (id or null), `superseded_by` (id or null), `source_message_id` | append-only in spirit: a correction inserts and links; `superseded_by` is the one updated field |
| `sales_supervisor_targets` | `branch_id`, `period` (`day` or `month`), `starts_on`, `amount` or `quantity` with `item_id` optional, `set_by` | the day's share of a month target is computed, never stored |
| `sales_supervisor_notes` | `branch_id`, `business_date`, `person_id`, `text`, `themes` (list), `asked_message_id` | the "why" answers; part 3 reads them after promotion |

**Template `mia/templates/retail` (industry, like `cleaning`):**

| Table | Row |
| --- | --- |
| `retail_items` | `branch_id` (null for all branches), `name`, `short_codes` (list), `price` (minor units, currency), `active`, `sort_order` |
| `retail_branch_hours` | `branch_id`, `weekday`, `opens`, `closes` (local time), `time_zone` on the branch |

Price history is the event log (`retail.item_priced`), not a table. Items and hours are owned by the branch_manager later; in v1 they come from the seed and the importer (`mia import` gains an `items:` section).

Alternative considered: core tables from the start (data standard 1.5 now). Deferred because changing the data standard needs the owner's explicit yes (CLAUDE.md) and the promotion costs no extra migration before the first candidate release.

Money is integer minor units plus currency (PHP, EUR), times ISO 8601 with offset, ids ULIDs (rule 10). `business_date` is the branch's local date at `reported_at`, except that a count sent before today's opening and within two hours after yesterday's closing (00:30 after a 23:00 close) belongs to yesterday. The agent never asks which day (final fix wave ruling); a day the user names is accepted only as today or yesterday. A turn resumed after a Jev outage uses the user message's time.

## 5. The agent

Package `mia/agents/sales_supervisor/` in the shape of `shift_supervisor`: `manifest.yaml`, `job.md`, `prompts/base.md` (short; the agent words nothing itself in v1), `actions.py` (the Jev decider's actions and slots), `decider.py` (reuse `shift_supervisor/decider.py` by moving the generic parts to `mia/agents/decider.py`: `_Reader`, `parse` with an actions table passed in, `_pseudonymised`, `decide`; the shift supervisor keeps only its `_args`), `tools.py`, `turn.py` (`SPEC` with `handle_turn`, `run_due`, `label_key`, `router_description` from part 1's contrast line), `tests/scenarios.yaml`.

**Actions** (Jev choice, threshold 0.6 as everywhere): `report_sales`, `correct_sales`, `sales_today`, `sales_period`, `set_target`, `why_answer` (only when the why question is the thread's last Mia message), `reply_only` (greeting, thanks, capabilities, other), `clarify`.

**Slots:** `items` (one choice per pre-parsed group over the branch's item names and codes plus `none`), `period` (`today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, a weekday name, `not_stated`), `branch` (every branch of the organisation by name, `all`, `not_stated`; the tools refuse a branch the person may not reach, and an owner or admin who names none sees every branch), `amount` (a pre-parsed number chosen from candidates, `not_stated`), `target_period` (`day`, `month`), `target_start` (`today`, `tomorrow`, `this_month`, `next_month`, `m01` to `m12` for the next such month, `not_stated`). The `item` slot of a period question is asked only when the message has no number group; with groups it is read from `item_0`.

**Tools** (each with `rbac.require`, a manifest row, unit tests with mocked dependencies):

| Tool | Risk | Writes | Who |
| --- | --- | --- | --- |
| `sales_supervisor.record_counts` | write_internal | sales_counts | clerk, supervisor, owner, admin |
| `sales_supervisor.correct_count` | write_internal | sales_counts | the reporter, supervisor, owner, admin |
| `sales_supervisor.today` | read | | all four |
| `sales_supervisor.period_report` | read | | supervisor (own branch), owner, admin |
| `sales_supervisor.set_target` | write_internal | sales_targets | supervisor (own branch), owner, admin |
| `sales_supervisor.record_note` | write_internal | sales_notes | all four, only as the answer to the why question |

No money, external or delete risk in v1, so no approvals. A target is a plan, not a payment.

**Due work (`run_due`, the tick):** closing reminders, the head-staff list, the end-of-day report, the morning message, the why question. Each is a pure "what is due now" function over the branch's hours and the day's counts, with unit tests at fixed clocks, and sends through `chat/channels.notify` (notifications, so they do not change the active agent: part 1 rule). Idempotent per branch and day through an event (`sales.reminder_sent`, `sales.report_sent`, `sales.why_asked`) checked before sending.

**Events:** `sales.counted`, `sales.corrected`, `sales.target_set`, `sales.note_recorded`, `sales.reminder_sent`, `sales.report_sent`, `sales.why_asked`, `retail.item_priced` (seed and importer).

## 6. Parsing counts (rule 7 in detail)

`actions.pre_parse(text, menu_tokens) -> (groups, total)` is pure code: split on numbers, keep the words before or after a number as the item phrase (both orders occur: "3 special" and "special 3"), keep a trailing "total 1450" or "1,450 total" as the amount candidate, strip filler words per language from a small list (`po`, `na`, `pcs`, `pieces`, `kpl`). A negation word (not, hindi, dili, diri, indi, bako, ali, aliwa, ei, instead, saan, haan) drops itself and the number after it, the old value of a correction. Both orientations are built and the one whose words hold more menu tokens (item name words and short codes) wins; on a tie, words-then-number only when the message ends with a number and every number follows words. Jev gets one choice per group over the branch's items (names and codes as criteria text, pseudonymised state is just the message) plus `none`. Confidence below threshold on any group: a "Did you mean" for that group with the three most probable items, the other groups recorded. Unit tests for `pre_parse` cover the ten seed phrasings per language.

## 7. i18n

New keys under `sales.*` (reports, reminders, the why question, the morning message, target confirmations, the capabilities greeting) in all ten languages; the eight Philippine-language modules are machine drafts noted under Q28 to Q35, with the Filipino drafts checked first since Ferino's clerks mostly read Filipino. Item names are data, not keys. Numbers and money are formatted by code (`1,450` and `₱1,450.00` for PHP; `1 450,00 €` for EUR).

## 8. Seed and configuration

- `config/org/ferinos/settings.yaml`: `agents: [sales_supervisor, shift_supervisor]`, `languages: [fil, ceb, en]`, quiet hours 21:00 to 06:00, channels as the demo org.
- `mia seed --org ferinos` (or a `MIA_ORG=ferinos` seed): two branches (a mall kiosk, a street stall) in Asia/Manila, eight items with short codes and PHP prices, six people (owner, one supervisor per branch, three clerks) with Filipino names and `language_known=True`, two weeks of plausible counts and one month target, so reports have something to show on day one.
- Rule 14: schema changes edit `0000_initial` in place; dev databases are rebuilt.

## 9. Testing

- Unit: `pre_parse`, the business-date rule, the target share, the due-work functions at fixed clocks, each tool with mocked dependencies, rbac negative tests (a clerk setting a target, a clerk reading another branch).
- Chat (fake Jev): every scenario in section 3 in English, plus the correction and the why flow in Filipino.
- Decider eval (opt in, real Jev): ten messages per scenario per gated language, gate 90% right action with the right items, 2% wrong; report in `docs/research/sales-supervisor-<date>.md`.
- Router: the retail case set of the follow-up plan already names the sales supervisor; no change.
- Architecture test: no `sales_supervisor` literal outside the manifest, `stubs.py` (where the stub is removed) and tests.

## 10. Open questions (docs/questions.md)

- Q39 (in docs/questions.md): the tables are agent-owned until a second agent reads them, then core as data standard 1.5.
- Q41: do counts need the selling price at the time, or is quantity enough and the amount derived at read time from the price history? Assumed: store both at write time; a price change never rewrites history.
- Q42: who may set a branch target: the supervisor of that branch, or only the owner? Assumed: both; the owner's target wins when both exist for a day.
- Q43: the why question goes to everyone who reported that day; should the owner get it too? Assumed: no, owners read the notes.

## 11. Order of work (for the plan)

1. Data: the agent-owned tables and the retail template, migration edit, models, store functions, seed.
2. `pre_parse` and the shared decider extraction.
3. Tools and rbac.
4. Turn, actions, chat tests.
5. Due work and notifications.
6. i18n in ten languages.
7. Decider eval set, report, ADR 017 (data standard 1.5), README and layout.

## Carried over from the whole-branch review's re-review (19 Oct 2026)

- `tools._asked_day` scans every `sales.why_asked` marker of the branch per why answer; bound it
  by date or count when a branch's history grows.
- `sales.not_allowed.branch` ("You can only report for {branch}") is also the wording for a
  denied `today` or `period_report` on another branch; a second key for reads would read better.
- No dedicated test for a why answer typed after the morning message (the decider then asks to
  rephrase, by reading); add one with the next change to the why flow.
