# Shift Supervisor Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `dispatcher` agent to `shift_supervisor` and move its absences, cover requests, timesheets and site problems into shared core tables (data standard 1.4), with no behaviour change.

**Architecture:** Task 1 moves the five tables (models plus Alembic migration 0008, a rename in place). Task 2 renames the agent package, ids, roles and intent ids in code, config and data with two one-off scripts, verified by the unchanged test suite. Task 3 writes the ADR and updates the docs.

**Tech Stack:** Python 3.12, SQLModel, Alembic (SQLite), pytest, ruff, mypy.

**Spec:** docs/superpowers/specs/2026-10-18-shift-supervisor-rename-design.md

## Global Constraints

- No behaviour change: test logic does not change, only names, imports and expected ids.
- Table mapping: `dispatcher_absences` to `absences`, `dispatcher_cover_requests` to `cover_requests`, `dispatcher_timesheets` to `timesheets`, `dispatcher_site_problems` to `incidents` (all in `mia/core/models.py`), `dispatcher_checklist_ticks` to `cleaning_checklist_ticks` (`mia/templates/cleaning/models.py`).
- Classes: `Absence`, `CoverRequest`, `Timesheet`, `Incident` (was `SiteProblem`), `CleaningChecklistTick` (was `ChecklistTick`).
- RBAC resources: `data:core.absence`, `data:core.cover_request`, `data:core.timesheet`, `data:core.incident`, `data:cleaning_checklist_ticks`.
- `STANDARD_VERSION` becomes `"1.4"`.
- Migrations 0001 to 0007, dated docs (docs/research, earlier specs and plans), `skill/reports/` and `skill/review.md` are history: never rewritten.
- Utterance texts, contexts and review notes in the data files are user words: never rewritten.
- Shown name: "Shift Supervisor" (en, fil), "Vuoropäällikkö" (fi).
- No em-dashes in docs or comments. Commands from the repo root unless a step says `node/`.

## Review Focus

1. An existing demo database at revision 0007 with rows in all five tables upgrades and keeps every row (Task 1 test).
2. Downgrade from 0008 to 0007 restores the old table and index names (Task 1 test).
3. A permission check on a renamed resource still denies a cleaner writing another person's absence (existing negative tests in tests/test_tools.py; Task 2 runs them unchanged).
4. A trained role model package on disk (`data/models/dispatcher/`) would no longer load under the new role id; the script moves it and rewrites `card.json` labels (Task 2 script, checked by a script assertion).
5. User texts that mention "dispatcher" ("tell the dispatcher to ...") keep their words (Task 2 data script only rewrites id fields; checked by an assertion in the script).

---

### Task 1: Shared tables and migration 0008

**Files:**
- Modify: `node/mia/core/models.py` (add `Absence`, `CoverRequest`, `Timesheet`, `Incident`; `STANDARD_VERSION = "1.4"`)
- Modify: `node/mia/templates/cleaning/models.py` (add `CleaningChecklistTick`)
- Delete: `node/mia/agents/dispatcher/models.py`
- Modify: `node/mia/schema.py` (drop the dispatcher models import)
- Modify: every importer of `mia.agents.dispatcher.models` (find with grep in Step 3)
- Modify: `node/config/policies/policy.csv`, `node/mia/agents/dispatcher/manifest.yaml`, `node/mia/agents/dispatcher/tools.py`, `node/mia/agents/dispatcher/timesheets.py` (resource names)
- Create: `node/migrations/versions/0008_data_standard_1_4_shared_tables.py`
- Test: `node/tests/test_migrations.py`

**Interfaces:**
- Produces: `mia.core.models.Absence`, `CoverRequest`, `Timesheet`, `Incident`; `mia.templates.cleaning.models.CleaningChecklistTick`. Same columns as before.

- [ ] **Step 1: Write the failing migration test**

Append to `node/tests/test_migrations.py`:

```python
RENAMED = {
    "dispatcher_absences": "absences",
    "dispatcher_cover_requests": "cover_requests",
    "dispatcher_timesheets": "timesheets",
    "dispatcher_site_problems": "incidents",
    "dispatcher_checklist_ticks": "cleaning_checklist_ticks",
}


def test_upgrade_from_1_3_keeps_agent_rows_in_shared_tables() -> None:
    """The dispatcher's tables become shared (data standard 1.4) with their rows and indexes."""
    cfg = _alembic_config()
    command.upgrade(cfg, "0007")
    ts = "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'"
    with get_engine().begin() as conn:
        conn.execute(text(f"INSERT INTO organisation VALUES ('O', {ts}, 'Org', 'FI', 'fi')"))
        conn.execute(text(f"INSERT INTO branch VALUES ('B', {ts}, 'O', 'Hki', 'Europe/Helsinki')"))
        conn.execute(
            text(
                f"INSERT INTO person VALUES ('P', {ts}, 'B', 'Pia', 'active', '[\"staff\"]', '[]', "
                "'employee', 'fi', '', NULL, NULL, 1)"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO dispatcher_absences (id, created_at, updated_at, branch_id, person_id,"
                f" date, reason, partial_day, reported_by) VALUES ('A', {ts}, 'B', 'P',"
                " '2026-01-02', 'sick', NULL, 'P')"
            )
        )
    command.upgrade(cfg, "head")
    with get_engine().connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert set(RENAMED.values()) <= tables
        assert not set(RENAMED) & tables
        assert conn.execute(text("SELECT reason FROM absences")).scalar() == "sick"
        indexes = {i["name"] for i in inspect(conn).get_indexes("absences")}
        assert indexes == {"ix_absences_branch_id", "ix_absences_date", "ix_absences_person_id"}
    command.downgrade(cfg, "0007")
    with get_engine().connect() as conn:
        tables = set(inspect(conn).get_table_names())
        assert set(RENAMED) <= tables
        assert conn.execute(text("SELECT reason FROM dispatcher_absences")).scalar() == "sick"
```

If the `person` insert fails on column count at 0007, read the `person` columns with `PRAGMA table_info(person)` after `command.upgrade(cfg, "0007")` and match them; the 0003 test above shows the 1.2 shape.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd node && uv run pytest tests/test_migrations.py -k 1_3 --no-cov -q`
Expected: FAIL (`absences` not in tables: revision head is 0007).

- [ ] **Step 3: Move the models**

Cut the five classes out of `node/mia/agents/dispatcher/models.py` and delete the file. In `node/mia/core/models.py`, after `Visit` (they reference `visit` and `person`), add the four shared classes with these headers and the old bodies unchanged:

```python
class Absence(BranchScoped, table=True):
    """A person's reported absence for one day, or part of it (data standard 1.4)."""

    __tablename__: ClassVar[str] = "absences"
    # columns as before: person_id, date, reason, partial_day, reported_by


class CoverRequest(BranchScoped, table=True):
    """One ask to one candidate to cover a visit, with its escalation state (decision D10).

    status: awaiting_approval, asking, accepted, declined, timed_out, cancelled.
    stage (while asking): waiting_quiet (message held until quiet hours end), message, call.
    """

    __tablename__: ClassVar[str] = "cover_requests"
    # columns as before


class Timesheet(BranchScoped, table=True):
    """One person's time on one visit (data standard 1.4; Q20 placed it in core).

    source: check_out (from the visit's actual times), planned (a completed visit without
    them), correction. status: draft, approved. Whoever entered it never approves it.
    """

    __tablename__: ClassVar[str] = "timesheets"
    __table_args__ = (UniqueConstraint("visit_id", "person_id"),)
    # columns as before


class Incident(BranchScoped, table=True):
    """A problem reported from a site: cannot get in, or the site is unusable."""

    __tablename__: ClassVar[str] = "incidents"
    # columns as before (kind: cannot_access, site_problem)
```

Copy the column lines verbatim from the deleted file (the `# columns as before` comments are not kept). Add `UniqueConstraint` to the sqlalchemy import if missing. In `node/mia/templates/cleaning/models.py` add:

```python
class CleaningChecklistTick(BranchScoped, table=True):
    """One ticked checklist item of one visit (the checklist itself belongs to the job)."""

    __tablename__: ClassVar[str] = "cleaning_checklist_ticks"
    __table_args__ = (UniqueConstraint("visit_id", "item"),)

    visit_id: str = Field(foreign_key="visit.id", index=True)
    item: str  # the item text as on the job's checklist
    ticked_by: str
    ticked_at: dt.datetime = Field(sa_type=TZDateTime)
```

Set `STANDARD_VERSION = "1.4"`. Remove `import mia.agents.dispatcher.models` from `node/mia/schema.py`. Then fix every importer:

Run: `grep -rn "dispatcher.models\|SiteProblem\|ChecklistTick" node/mia node/tests | grep -v __pycache__`
Replace `from mia.agents.dispatcher.models import X` with `from mia.core.models import X` (or `mia.templates.cleaning.models` for the tick), `SiteProblem` with `Incident`, `ChecklistTick` with `CleaningChecklistTick`.

- [ ] **Step 4: Rename the RBAC resources, then the table names**

Two forms exist. RBAC resources follow `core.<entity>` (`Resource(kind="data", name="core.visit")`, `data:core.visit` in policy.csv). Event `entity_type` and `action` (`dispatcher_absences.created`) and manifest `reads`/`writes` lists use the table name. So rename the RBAC contexts first, then every remaining occurrence to the table name:

```bash
cd node && for pair in "dispatcher_absences:core.absence" "dispatcher_cover_requests:core.cover_request" \
  "dispatcher_timesheets:core.timesheet" "dispatcher_site_problems:core.incident" \
  "dispatcher_checklist_ticks:cleaning_checklist_ticks"; do
  old=${pair%%:*}; new=${pair#*:}
  sed -i '' "s/data:$old/data:$new/g" config/policies/policy.csv mia/agents/dispatcher/manifest.yaml
  sed -i '' "s/name=\"$old\"/name=\"$new\"/g; s/RESOURCE = \"$old\"/RESOURCE = \"$new\"/" \
    mia/agents/dispatcher/tools.py mia/agents/dispatcher/timesheets.py
done
for pair in "dispatcher_absences:absences" "dispatcher_cover_requests:cover_requests" \
  "dispatcher_timesheets:timesheets" "dispatcher_site_problems:incidents" \
  "dispatcher_checklist_ticks:cleaning_checklist_ticks"; do
  old=${pair%%:*}; new=${pair#*:}
  grep -rl "$old" mia config tests | grep -v __pycache__ | xargs sed -i '' "s/$old/$new/g"
done; grep -rn "dispatcher_\|core\.absence\|core\.incident" mia config tests | grep -v __pycache__
```

Expected: `core.*` only in policy.csv, the manifest grants and the `Resource(...)`/`RESOURCE` lines (tools.py near lines 174, 611, 715; timesheets.py); events and tests now say `absences.created`; manifest `reads`/`writes` say `absences`, `incidents`. Remaining `dispatcher_` hits are the `data:dispatcher_*` wildcards (manifest grant, supervisor in policy.csv) and prose. Replace each wildcard with explicit lines for the five resources at the same action (manifest: `data:core.absence:write`, `data:core.cover_request:write`, `data:core.timesheet:write`, `data:core.incident:write`, `data:cleaning_checklist_ticks:write`; supervisor in policy.csv: the same five, each with `read` and with `write`). Fix the prose (timesheets.py docstring line 5) to describe the new tables.

- [ ] **Step 5: Write migration 0008**

Create `node/migrations/versions/0008_data_standard_1_4_shared_tables.py`:

```python
"""data standard 1.4: the dispatcher's tables become shared tables

absences, cover_requests, timesheets and incidents move to core; checklist ticks move to the
cleaning template. A rename in place: rows, columns and constraints are kept, indexes are
renamed to match the new table names.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = {
    "dispatcher_absences": "absences",
    "dispatcher_cover_requests": "cover_requests",
    "dispatcher_timesheets": "timesheets",
    "dispatcher_site_problems": "incidents",
    "dispatcher_checklist_ticks": "cleaning_checklist_ticks",
}


def _rename(old: str, new: str) -> None:
    """Drop the old ix_<old>_* indexes, rename the table, create ix_<new>_* on the same columns."""
    indexes = sa.inspect(op.get_bind()).get_indexes(old)
    with op.batch_alter_table(old) as b:
        for ix in indexes:
            b.drop_index(ix["name"])
    op.rename_table(old, new)
    with op.batch_alter_table(new) as b:
        for ix in indexes:
            name = str(ix["name"]).replace(f"ix_{old}_", f"ix_{new}_", 1)
            b.create_index(name, list(ix["column_names"]), unique=bool(ix["unique"]))


def upgrade() -> None:
    for old, new in TABLES.items():
        _rename(old, new)


def downgrade() -> None:
    for old, new in TABLES.items():
        _rename(new, old)
```

Note: unique constraints declared with `UniqueConstraint` show up in SQLite as `sqlite_autoindex_*`, which `get_indexes` does not return, so they travel with the table untouched.

- [ ] **Step 6: Run the migration tests**

Run: `cd node && uv run pytest tests/test_migrations.py --no-cov -q`
Expected: PASS, including `test_upgrade_matches_models_and_adds_triggers` (the models and the migrated schema agree, so `compare_metadata` is empty).

If `compare_metadata` reports an index difference, the model's `index=True` columns and the migrated `ix_<new>_<col>` names disagree; fix the migration's name mapping, never the model.

- [ ] **Step 7: Run the full suite and checks**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && cd node && uv run pytest -q > /tmp/p0t1.txt 2>&1; tail -5 /tmp/p0t1.txt`
Expected: all pass (954 passed plus the new migration test). Do not pipe mypy.

- [ ] **Step 8: Commit**

```bash
git add -A node
git commit -m "core: data standard 1.4: absences, cover_requests, timesheets and incidents become shared tables, checklist ticks move to the cleaning template (migration 0008 renames in place)"
```

---

### Task 2: Rename the agent to shift_supervisor

**Files:**
- Move: `node/mia/agents/dispatcher/` to `node/mia/agents/shift_supervisor/`
- Move: `node/tests/evals/test_dispatcher_evals.py` to `node/tests/evals/test_shift_supervisor_evals.py`
- Modify: every tracked file under `node/mia`, `node/tests`, `node/config` that names the agent (by script), except migrations 0001 to 0008 and `tests/test_migrations.py` (they name the old tables on purpose), `skill/reports/`, `skill/review.md` and `*.jsonl`
- Modify: `*.jsonl` id fields (by the data script), `docs/capabilities.md`, `node/tests/evals/intents_catalogue.yaml` (regenerated)
- Modify: `node/mia/agents/shift_supervisor/manifest.yaml` (`name: Shift Supervisor`), `node/mia/i18n/strings.py` (agent name labels if any)

**Interfaces:**
- Consumes: Task 1's shared tables.
- Produces: package `mia.agents.shift_supervisor`; manifest id `shift_supervisor`; agent role `agent.shift_supervisor`; tool ids `shift_supervisor.<tool>`; intent ids `shift_supervisor.<intent>`; i18n keys `intent.shift_supervisor.<intent>`; eval test `test_shift_supervisor_pass_rate`. Part 1 builds on these names.

- [ ] **Step 1: Move the package and the eval file**

```bash
git mv node/mia/agents/dispatcher node/mia/agents/shift_supervisor
git mv node/tests/evals/test_dispatcher_evals.py node/tests/evals/test_shift_supervisor_evals.py
```

- [ ] **Step 2: Rewrite code, config and docs-in-code with the rename script**

Save as `$SCRATCH/rename_code.py` (the scratchpad, not the repo):

```python
"""One-off: rename the dispatcher agent to shift_supervisor in code and config (not data)."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
SKIP = re.compile(
    r"node/migrations/versions/000[1-8]_|/skill/reports/|/skill/review\.md$|\.jsonl$|"
    r"node/tests/evals/intents_catalogue\.yaml$|node/tests/test_migrations\.py$"
)
# Prose first (a word on its own), then identifiers (module paths, ids, snake_case names).
PROSE = [
    (re.compile(r"(?<![\w./\"'`-])Dispatcher(?![\w./\"`-])"), "Shift supervisor"),
    (re.compile(r"(?<![\w./\"'`-])dispatcher(?='s\b)"), "shift supervisor"),
    (re.compile(r"(?<![\w./\"'`-])dispatcher(?![\w./\"'`-])"), "shift supervisor"),
]
IDENT = (re.compile(r"dispatcher"), "shift_supervisor")

files = subprocess.run(
    ["git", "ls-files", "node/mia", "node/tests", "node/config", "node/pyproject.toml"],
    cwd=ROOT, capture_output=True, text=True, check=True,
).stdout.split()
changed = 0
for name in files:
    if SKIP.search(name):
        continue
    path = ROOT / name
    try:
        old = path.read_text("utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        continue
    new = old
    for pattern, repl in PROSE:
        new = pattern.sub(repl, new)
    new = IDENT[0].sub(IDENT[1], new)
    if new != old:
        path.write_text(new, "utf-8")
        changed += 1
print("files changed:", changed)
```

Run: `python3 -I "$SCRATCH/rename_code.py" "$(pwd)"`
Expected: `files changed:` about 60.

- [ ] **Step 3: Fix the display name and read the prose diff**

Set `name: Shift Supervisor` in `node/mia/agents/shift_supervisor/manifest.yaml`. Then read the prose changes:

Run: `git diff -U0 node | grep "^+" | grep -i "shift supervisor" | head -80`
Expected: sentences that read naturally ("You are Mia's shift supervisor."). Fix any that do not by hand. A Finnish or Filipino user-facing string that named the role gets "Vuoropäällikkö" (fi) or "Shift Supervisor" (fil, en).

- [ ] **Step 4: Rewrite the intent ids in the data files**

Save as `$SCRATCH/rename_data.py`:

```python
"""One-off: rename dispatcher intent and role ids in the jsonl data; user words stay as they are."""

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
FIELDS = {"role", "id", "intent", "source_id", "negative_of"}
FILES = [
    *ROOT.glob("node/tests/evals/*.jsonl"),
    *ROOT.glob("node/mia/agents/shift_supervisor/skill/data/*.jsonl"),
]


def fix(value: str) -> str:
    return value.replace("dispatcher", "shift_supervisor")


for path in FILES:
    out = []
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            out.append(line)
            continue
        r = json.loads(line)
        before = (r.get("text"), r.get("context"), json.dumps(r.get("review")))
        for key in FIELDS & r.keys():
            if isinstance(r[key], str):
                r[key] = fix(r[key])
        if isinstance(r.get("slots"), dict) and isinstance(r["slots"].get("agent"), str):
            r["slots"]["agent"] = fix(r["slots"]["agent"])
        assert before == (r.get("text"), r.get("context"), json.dumps(r.get("review"))), path
        out.append(json.dumps(r, ensure_ascii=False))
    path.write_text("\n".join(out) + "\n", "utf-8")
    print(path.name, "ok")

models = ROOT / "node/data/models/dispatcher"
if models.exists():  # a locally trained role model: move it and relabel its cards
    target = models.with_name("shift_supervisor")
    models.rename(target)
    for card in target.glob("*/card.json"):
        card.write_text(fix(card.read_text("utf-8")), "utf-8")
    print("models moved; card sha256 artifacts are unchanged (labels live in card.json)")
```

Run: `python3 -I "$SCRATCH/rename_data.py" "$(pwd)"`
Expected: one `ok` line per jsonl file.

Check the line format matched the original: `git diff --stat node/tests/evals/intents.jsonl` shows only changed lines, not the whole file rewritten. If every line changed, the original used different JSON separators; read one original line with `git show HEAD:node/tests/evals/intents.jsonl | head -1` and pass the same `separators=` to `json.dumps`.

- [ ] **Step 5: Rename in the capabilities catalogue and regenerate**

Run: `sed -i '' 's/\bdispatcher\./shift_supervisor./g; s/^## Dispatcher (Operations)/## Shift supervisor (Operations)/; s/^| dispatcher |/| shift_supervisor |/' docs/capabilities.md && cd node && uv run python -m tests.evals.intents`
Expected: `intents_catalogue.yaml` regenerated with `shift_supervisor.*` ids. Read `git diff docs/capabilities.md | head -60`; prose mentions of "the dispatcher" in that file become "the shift supervisor".

- [ ] **Step 6: Verify nothing is left**

Run: `grep -rnw dispatcher node/mia node/tests node/config | grep -v __pycache__ | grep -v "migrations/versions/000[1-8]\|tests/test_migrations.py" | grep -v "/skill/reports/\|/skill/review.md" | grep -v '"text":\|"context":\|"note":'`
Expected: no output. Then `grep -rn "dispatcher_" node/mia node/tests node/config | grep -v __pycache__ | grep -v "migrations/versions/000[1-8]\|tests/test_migrations.py"`
Expected: no output.

- [ ] **Step 7: Run everything**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && cd node && uv run pytest -q > /tmp/p0t2.txt 2>&1; tail -5 /tmp/p0t2.txt`
Expected: same count as after Task 1, all pass. Then the scenario evals with the rules model: `cd node && uv run pytest tests/evals/test_shift_supervisor_evals.py -m evals --no-cov -q`
Expected: PASS (100% with the rules model, as before).

A failure here is a missed or wrong rename, never a reason to change test logic. Typical: an f-string that builds `f"{agent}_x"`, a regex in rules.py matching the old prompt words, a test asserting the model name `dispatcher-rules`.

- [ ] **Step 8: Commit**

```bash
git add -A node docs/capabilities.md
git commit -m "agents: the dispatcher is renamed shift_supervisor (package, manifest, agent role, tool and intent ids, events, i18n keys, data ids); no behaviour change"
```

---

### Task 3: ADR and docs

**Files:**
- Create: `docs/adr/014-shift-supervisor-and-shared-tables.md`
- Modify: `docs/adr/README.md` (index line), `docs/layout.md`, `README.md`, `docs/questions.md` (Q20 answered by 1.4), `docs/plan.md` and `docs/spec.md` only where they describe the current agent id or tables

- [ ] **Step 1: Write ADR 014**

```markdown
# ADR 014: The dispatcher becomes the shift supervisor; its tables become shared

## Context

Agents are named after real jobs (D16). Retail (the sales supervisor agent, part 2) needs the
same work the dispatcher does (rosters, absences, cover, check-in) under a shop's job title.
Its tables carried the agent prefix (rule 9) although HR and payroll read absences and
timesheets, and a shop's broken oven is the same record as a cleaner's site problem.

## Decision

- Agent id `dispatcher` becomes `shift_supervisor` in code, config, ids and data.
- Data standard 1.4: `absences`, `cover_requests`, `timesheets` and `incidents` (was
  `dispatcher_site_problems`) are core tables; `cleaning_checklist_ticks` belongs to the
  cleaning template. Migration 0008 renames in place.
- Dated documents (research reports, specs and plans before 18 Oct 2026, skill reports) are
  not rewritten: "dispatcher" in them means `shift_supervisor`.

## Consequences

- Event rows written before 0008 keep `dispatcher.*` names (append-only, rule 2). All data is
  seed and demo, so no compatibility map; reseed when history matters.
- Q20 (where timesheets live) is answered: core.
- New agents start with job ids: sales_supervisor, inventory_manager, bookkeeper, hr_officer,
  branch_manager.
```

- [ ] **Step 2: Update the docs**

- `docs/adr/README.md`: add `- [014](014-shift-supervisor-and-shared-tables.md) The dispatcher becomes the shift supervisor; shared tables` in the same format as the other lines.
- `docs/layout.md`: `dispatcher/` becomes `shift_supervisor/` in the tree; `scenarios.yaml` path follows.
- `README.md`: commands and paths that name the dispatcher (eval command `test_shift_supervisor_evals.py`).
- `docs/questions.md`: under Q20 add `Answered 18 Oct 2026 (ADR 014): timesheets are a core table (data standard 1.4).`
- `docs/spec.md`, `docs/plan.md`: only lines that state the current agent id or table names. Leave history and dated sections.

Run: `grep -n "dispatcher" docs/layout.md README.md docs/adr/README.md`
Expected: no output except deliberate history notes.

- [ ] **Step 3: Check and commit**

Run: `grep -c "—" docs/adr/014-shift-supervisor-and-shared-tables.md`
Expected: `0`.

```bash
git add docs README.md
git commit -m "docs: ADR 014 (dispatcher becomes shift_supervisor, data standard 1.4 shared tables); layout, README and Q20 follow"
```
