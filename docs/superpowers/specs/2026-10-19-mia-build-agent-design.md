# /mia-build-agent: a skill that builds one Mia agent from the catalogue

19 Oct 2026. Part 4 of the retail work. Draft for the owner's review. Extracted from how the
shift supervisor's rename (part 0), multi-agent routing (part 1), the router follow-up and the
sales supervisor v1 (part 2) were built, with the findings their reviews kept making.

## 1. Goal

`/mia-build-agent <agent_id>` takes a job title from docs/agents-catalogue.md and carries it
from catalogue row to a reviewed, gated agent on the branch: spec, plan, scaffolding, the
subagent-driven build with the review loop, the eval gates and the docs. It does not design
the agent's domain for the developer; it makes the parts that are the same for every agent
mechanical, and it puts the lessons of parts 1 and 2 in front of every implementer and
reviewer.

Out of scope: agents that need a generative, vision or speech model (next phase); changing the
data standard without the owner (rule 9 and CLAUDE.md "ask before"); a web UI.

## 2. Shape

A Claude Code skill in `.claude/skills/mia-build-agent/`, in the shape of `mia-train-role`:

```
.claude/skills/mia-build-agent/
  SKILL.md            the steps below, each with its gate
  checklist.md        the review focus list (section 5), the rules an agent must satisfy
  prompts/spec.md     the spec template (section 3), filled from the catalogue row
  prompts/plan.md     the plan skeleton (section 4), the standard eight tasks
  prompts/reviewer.md the extra review questions per task kind
```

plus one deterministic command in the node, `uv run mia agent scaffold <agent_id>` (section
4), because files that are the same for every agent should come from code, not from a prompt.

## 3. Steps of the skill

Each step writes files; the skill resumes at the first step whose output is missing.

1. **Understand.** Read the catalogue row, docs/decisions.md, CLAUDE.md, the two built agents
   (`shift_supervisor`, `sales_supervisor`) as the shapes, and `checklist.md`. Ask the
   developer only what the catalogue lacks: the proof shop, the roles that talk to the agent,
   the first five scenarios in priority order.
2. **Data standard check (gate 1, the owner).** List the tables the agent reads and writes and
   which other agents read them. A table read by a second agent is core (rule 9). If the list
   changes core, stop and ask the owner for the data standard bump ("1.5 yes" style); record the
   question in docs/questions.md; without a yes, build on agent-owned tables and record the
   promotion as blocking before the next reader.
3. **Spec (gate 2, the developer).** Fill `prompts/spec.md` into
   `docs/superpowers/specs/<date>-<agent_id>-design.md`: goal and non-goals, who talks to it,
   the scenarios as an acceptance list, data (agent-owned, template, core), the agent shape
   (actions and slots, tools with risk and roles, due work, events), parsing rules (code
   splits, Jev picks), i18n, seed and config, testing and gates, open questions, order of
   work. The developer approves it in chat.
4. **Plan.** Fill `prompts/plan.md` into `docs/superpowers/plans/<date>-<agent_id>.md`: the
   standard tasks (data; actions and decider; tools and policy; turn and replies; the rest of
   the scenarios; due work; ten languages; evals and docs), each with the test names from the
   spec's scenarios and the review focus lines from `checklist.md` pinned to the task that owns
   them. The developer picks the execution method (subagent-driven recommended).
5. **Scaffold.** `uv run mia agent scaffold <agent_id> --label-en "..." --label-fi "..."`
   (section 4) and commit.
6. **Build.** superpowers:subagent-driven-development on the plan, with `prompts/reviewer.md`
   appended to every task review and the whole-branch review. Rulings go to the ledger as
   usual; the standard rulings of parts 1 and 2 (section 6) are pre-made, so they are not
   re-litigated.
7. **Gates.** Add the agent's seeds to the router case set (ten per gated language plus the
   contrast line in its router description) and run the router gate; run the agent's decider
   gate (the harness from the scaffold) at the Q40 bar; both on fresh gate halves; write the
   reports under docs/research/. A failing gate is reported, never tuned on the gate half.
8. **Finish.** README and docs/layout.md lines, ADR when the data standard changed, questions,
   the follow-ups carried into the spec, the finishing menu for the branch.

## 4. `mia agent scaffold`

Deterministic, idempotent (refuses to overwrite a file that exists unless `--force`), code in
`node/mia/agents/scaffold.py` with templates under `node/mia/agents/_template/`:

- `node/mia/agents/<id>/`: `__init__.py` (AGENT_DIR, MANIFEST), `manifest.yaml` (minimal,
  valid), `job.md`, `prompts/base.md`, `models.py` (empty table module imported by
  `mia/schema.py`), `actions.py` (ACTIONS with `reply_only` and `clarify`, Query, build_query,
  build_request skeleton with the shared decider), `decider.py` (the two-line wrapper and an
  `_args` with the two default actions), `tools.py` (BINDINGS empty), `turn.py` (the Jev turn
  copied from the sales supervisor with the agent's MANIFEST, SPEC with `run_due=None`,
  `stream_agent=None`), `replies.py` (conversation replies), `tests/scenarios.yaml` (empty
  list).
- Registry entry, the stub entry removed from `agents/stubs.py` (the router description
  moves to the SPEC), `agent.<id>.label` in ten languages (en and fi from the flags, the eight
  modules drafted as the label itself with the Q28 to Q35 note), policy lines
  `agent:<id>, use` for the roles given with `--roles`, `tests/test_access.py` roster
  updated, `docs/layout.md` line, a test file `node/tests/test_<id>_chat.py` with one passing
  test (a greeting), and `node/tests/evals/<id>_cases.py` plus `test_<id>_evals.py` built on
  `tests/evals/gate.py` with an empty case list and the Q40 bar.
- After the scaffold the full checks are green: the agent greets and says it cannot do
  anything else yet. Everything domain-specific is the plan's work.

The shared decider (`mia/agents/decider.py`), the gate helper (`tests/evals/gate.py`), the
conftest fixtures pattern (`<org>` fixture, `manila_at`-style clocks) and `tools.utcnow`
patching through `CLOCK_USERS` are what the scaffold relies on; the scaffold adds the new
modules to `CLOCK_USERS` when they import `utcnow`.

## 5. The checklist (what every review asks)

From the findings parts 1 and 2 kept producing:

- Rule 15: no bare agent id literal; ids from `MANIFEST.id`; label keys built from it.
- Rule 8 and 6: the message and any list of its parts in Jev state, pseudonymised (lists item
  by item); nothing from the message in instructions; requests only inside the egress context.
- Rule 7: every number computed by code; money typed in major units converted once to minor;
  dates from the branch's local clock, never `now.date()` in UTC.
- Rule 4: branch scoping through casbin (`read_all`, `write_all`), every read and write
  `_check`ed, a denial visible as an event or a `tool.called` refusal; `read_own` gates by
  role only, say so.
- Rule 11 and 12: commit before the Jev await; sync DB work in threads; one Session per
  thread; per-branch commits in due work.
- Taps: a button value is a stored decision; validated against the agent's own ACTIONS;
  stale after a notification; never replayed across a date.
- Due work: windows as datetimes that may cross midnight, business date from the closing's
  day; markers per branch and date written with the send; end-of-shift messages urgent,
  reminders and morning messages not; nothing sent when there is nothing to say.
- Business dates: a late count is yesterday's only before opening and within two hours of a
  late close; never ask.
- Parsing: both orientations scored by menu tokens; negation drops the next number and makes
  the message a correction by rule; leading stray words dropped; currency symbols stripped.
- Harvest and learning: sensitive skip depends on an active role model; records pending
  review (D27).
- i18n: every key in ten languages (the coverage test forces it), placeholders identical, no
  digits, Filipino never Tagalog, tests assert through `t(...)`.
- Evals: fresh gate half per run, split by seed, no text in both halves, the raw file by local
  time never overwritten, the report in the research shape with the gate stated as it is.
- Tests: through `run_turn` with the fake Jev; negative tests for permissions; the Review
  Focus list of the plan pinned to tasks.

## 6. Standard rulings (pre-made)

A learned route applies only with no agent active. One undo rule (first switch away within the
hour). A confident "no agent" is small talk for the lead agent. Agent-owned tables until a
second reader, then core with an ADR (pre-candidate: edit `0000_initial`). The owner's target
wins; a day target beats a month target. Quiet hours do not hold end-of-shift messages. The
item question only without a number group.

## 7. Testing the skill

- `mia agent scaffold demo_officer` in a temp checkout: the full checks pass; the agent greets;
  `tests/test_architecture.py` passes (a scaffolded agent spells no id); running it twice
  refuses.
- The skill run end to end once on `inventory_manager` (the next agent after branch_manager),
  measured by the time from catalogue row to green suite and by how many review findings
  were new versus on the checklist.

## 8. Open questions

- Q51: should the scaffold also write the eight-language label drafts, or leave them to the
  i18n task? Assumed: write the English label into the eight modules with the review note,
  so the coverage test is green from the first commit.
- Q52: does `/mia-build-agent` run the real-Jev gates itself, or hand the command to the
  developer? Assumed: it runs them when `MIA_TYPESAFE_KEY` is set and reports; the developer
  decides on tuning.

## 9. Order of work

1. `tests/evals/gate.py` and the conftest patterns the scaffold needs (already there after the
   rerun fix). 2. `mia agent scaffold` with its test. 3. The skill files. 4. A dry run on
   `inventory_manager` after branch_manager, with the measurements of section 7.
