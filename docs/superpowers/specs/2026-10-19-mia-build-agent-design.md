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

## Carried over from the whole-branch review (19 Oct 2026)

Minor findings ruled as follow-up after the fix wave (77dfe36 fixed I1, I2, the greeting wording, the kept-label notice, PENDING parsing and the edit guards). Pick them up with the next scaffold change.


1. **`reply.not_built` is the wrong capabilities line.**
   - Where: `_template/replies.py.tmpl:7-8`, pinned by `test_chat.py.tmpl:51`.
   - What: a greeting is answered "Hi! What can I do for you today? / Mia cannot help with
     that yet." There is no "that" to refer to, and the greeting has just offered help.
     "What can you do?" and an injection both get "Mia cannot help with that yet", which reads
     as a refusal of the question.
   - The spec (section 4) asks for an agent that "greets and says it cannot do anything else
     yet".
   - Fix: add one shared key in ten languages, rendered with the label, for example
     `agent.scaffolded.capabilities`: "I am the {agent}. I cannot do anything else yet."
   - It is unreachable for Ferino's today (see Declined), so Minor.
2. **Label flags are silently ignored when the key already exists.**
   - Where: `scaffold.py:112` (`if marker in text: return text`).
   - What: in the dry run, `--label-fi "Varastovastaava"` was dropped and the repo keeps
     "Varastopäällikkö". `strings.py` is simply missing from the printed file list. The same
     happens for every promoted stub, because all stubs have their labels already.
   - Fix: when the key exists with another value, raise, or print the kept value. Or make the
     label flags optional for a stub.
3. **Some anchors fail silently, and some failures surface badly.** Ranked by which breaks
   first as the shared files evolve:
   - a. `router_cases.PENDING` (`scaffold.py:170`). The one-line set passes 100 columns at the
     fourth pending id (146 columns at six). `ruff format` then wraps it, the line becomes
     `{`, and the next scaffold raises SyntaxError with a raw traceback. The CLI catches only
     ValueError and FileExistsError (`cli.py:268`). This surfaces, but badly.
   - b. `edit_schema` (`scaffold.py:160`) silently drops any non-`import mia.` line between
     the first and last `import mia.` lines (a comment, a blank line, a conditional import).
     Probe: `"import mia.a.models\n# keep\n..."` loses `# keep`. This one hides.
   - c. `edit_stubs` (`scaffold.py:103`) is a no-op when an entry is not in the
     `"<id>": (\n ... ),\n` shape, for example a one-line entry. Since
     `AGENTS = {... for s in [*BUILT, *STUBS]}`, the stub then silently **shadows** the built
     agent. `test_access`'s stub-set assertion catches it, but the scaffold does not.
   - d. `edit_layout` (`scaffold.py:184`) and `edit_module` (a module with no label group)
     are no-ops when their anchor is gone. These hide; the i18n coverage test catches the
     second.
   - e. `edit_registry` raises `ValueError("substring not found")` when `BUILT` is reformatted
     to one line. This surfaces, but the message names nothing.
   - Fix (one guard for all of them): after computing the edits in `run()`, check the
     post-conditions on the new texts and raise a ValueError naming the file:
     - the import and `{CONST},` are in registry;
     - `stub_description(new_stubs, id) is None`;
     - the label key is in every i18n file;
     - the layout line is there;
     - the id is in `PENDING` or in a case;
     - the line count of schema.py grew by exactly one.
4. **`edit_policy` writes redundant lines for inherited roles.**
   - What: the dry run added `p, owner, *, agent:inventory_manager, use, allow`, which owner
     already has through `owner > admin > supervisor`. It is harmless, but noise in a security
     file.
   - Fix: skip a role that `rbac` already allows for the resource, or document why the lines
     are explicit.
5. **The rendered `_unavailable` dropped the sales supervisor's once-per-process warning.**
   - Where: `_template/turn.py.tmpl:104`.
   - What: with the default `MIA_DECIDER=agent` (`.env.example:30`), an org that enables the
     agent now gets "Sorry, I cannot answer right now. Please try again in a minute."
     permanently. As a stub, it answered the honest `reply.not_built`.
   - This is consistent with the D18 gate, but nothing is logged.
   - Fix: keep the `log.warning("%s answers only with MIA_DECIDER=jev", MANIFEST.id)` once,
     as in sales.
6. **`prompts/reviewer.md` misses two of the questions the parts kept producing.**
   - It names branch scoping (tools) and midnight windows (due). It has no "pseudonymised,
     lists item by item" question in the actions block. It also has no business-date question
     ("a late count is yesterday's only before opening and within two hours of a late close";
     "branch local clock, never `now.date()` in UTC").
   - Both are in checklist.md, which reviewer.md says to run whole, so Minor.
   - Fix: add one line to `## actions` and one to `## due`.
7. **No offline cases-shape test is rendered.**
   - What: sales has `test_sales_cases.py` (ten per language, scenario and half; no text in
     both halves; split by seed). The scaffold renders the harness but no shape test, although
     the checklist's Evals lines require one.
   - Fix: render `test_<id>_cases.py.tmpl`, which skips while `CASES` is empty.
8. **The em-dash guard is narrow.**
   - What: `test_skill_files.py` checks checklist.md only, and `test_scaffold.py` checks the
     rendered `.py` files only. SKILL.md, the prompts and the `.md`, `.yaml` templates are
     unchecked. They are clean today (I grepped).
   - Fix: extend the loop to every file under the skill and `_template/`.
9. **`$label_lower` lowercases acronyms.** "HR Officer" renders "the hr officer's tables" in
   docstrings and in the Jev instruction "Mia, the shop's hr officer". Fix: lowercase only the
   first letter of each word that is not all caps, or pass a `label_lower` that the caller can
   override.
10. **The CLI help names a registered id.** `cli.py:749`: `help="snake_case job title, e.g.
    inventory_manager"`. It is not a bare id, so the architecture scan passes, but rule 15
    (focus 6) prefers no registered id in node/mia outside stubs and orgconfig. Use a
    non-roster example (`quality_officer`).

