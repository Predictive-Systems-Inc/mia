# /mia-build-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/mia-build-agent <agent_id>` carries a catalogue row to a reviewed, gated agent: a deterministic scaffold command makes the files every agent shares, and the skill drives spec, plan, build, gates and docs with the lessons of parts 1 and 2 in every review.

**Architecture:** `node/mia/agents/scaffold.py` renders templates from `node/mia/agents/_template/` into a new agent package and edits the five shared files (registry, stubs, i18n label, policy, layout) through small, idempotent text operations; `mia agent scaffold` exposes it. `.claude/skills/mia-build-agent/` holds SKILL.md, the checklist and the three prompt templates. No agent logic lives in the scaffold: a scaffolded agent greets and says it cannot do anything else yet.

**Tech Stack:** Python 3.12 stdlib (`string.Template`, `pathlib`), argparse CLI, pytest.

**Spec:** docs/superpowers/specs/2026-10-19-mia-build-agent-design.md

## Global Constraints

- Rule 15: the scaffold never writes the bare quoted agent id into Python; rendered modules use `MANIFEST.id`; the only id literals are in `manifest.yaml`, `agents/stubs.py` (an entry removed) and `core/orgconfig.py`. `tests/test_architecture.py` must pass after a scaffold.
- Rule 9: `models.py` is scaffolded empty (a docstring) and imported by `mia/schema.py`; the scaffold adds that import line.
- Idempotent and safe: a file that exists is never overwritten (`FileExistsError` naming it) unless `--force`; shared-file edits are inserted only when the marker text is absent; running twice refuses on the first existing file and changes nothing.
- No em-dashes; docstrings state guarantees; mypy strict on mia/agents; `uv run ruff format node`, never `ruff format .`.
- User-facing strings through i18n; the label in ten languages (en and fi from the flags; the eight modules get the English label with the Q28 to Q35 review note). Filipino, never Tagalog.
- Checks before every commit: `uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest`.
- Tests run offline; the scaffold's tests run against a temporary tree, never against the repo.
- Commit messages in the branch's style (`git log -5`).

## Review Focus

1. A scaffold run against the real repo followed by the full checks must be green, and `git status` after `git checkout .` and removing the new package must be clean (Task 1, test `test_scaffold_then_checks_in_a_temp_copy`).
2. Running the scaffold twice must change nothing on the second run (Task 1, `test_second_run_refuses_and_changes_nothing`).
3. The rendered `turn.py` must not import the sales supervisor's modules (Task 1, `test_rendered_modules_import_only_shared_code`).
4. The removed stub must not break `tests/test_access.py`'s roster assertions (Task 1 edits the test's expectation by rule, not by hand).
5. The skill must stop at the data standard gate when a table has a second reader (Task 2, the SKILL.md gate text and the checklist).

---

### Task 1: `mia agent scaffold`

**Files:**
- Create: `node/mia/agents/scaffold.py`, `node/mia/agents/_template/` (`__init__.py.tmpl`, `manifest.yaml.tmpl`, `job.md.tmpl`, `prompts/base.md.tmpl`, `models.py.tmpl`, `actions.py.tmpl`, `decider.py.tmpl`, `tools.py.tmpl`, `turn.py.tmpl`, `replies.py.tmpl`, `tests/scenarios.yaml.tmpl`, `test_chat.py.tmpl`, `eval_cases.py.tmpl`, `test_evals.py.tmpl`)
- Modify: `node/mia/cli.py` (`agent scaffold` subcommand), `node/tests/test_access.py` (ROSTER derived from the manifests on disk plus the stubs, not a literal list), `docs/layout.md`
- Test: `node/tests/test_scaffold.py`

**Interfaces:**
- `scaffold.run(root: Path, agent_id: str, *, label_en: str, label_fi: str, roles: list[str], description: str, force: bool = False) -> list[Path]` returns the files written. `root` is the repository root (the directory holding `node/` and `docs/`).
- Validation: `agent_id` matches `^[a-z][a-z0-9_]*$` and is not already a package under `node/mia/agents/`; `roles` from `HUMAN_ROLES`.
- Shared-file edits (each a pure function `edit_<name>(text: str, ...) -> str` with a unit test, applied only when its marker is absent):
  - `registry.py`: import `from mia.agents.<id>.turn import SPEC as <ID>` and add `<ID>` to the list before `*STUBS`.
  - `stubs.py`: delete the `"<id>": (...)` entry of `DESCRIPTIONS` when present (the description text is moved into the rendered `turn.py` SPEC).
  - `i18n/strings.py`: `"agent.<id>.label"` in en and fi next to the other labels (skip when present); the eight modules: the English label (skip when present).
  - `config/policies/policy.csv`: `p, <role>, *, agent:<id>, use, allow` per role (skip when present).
  - `mia/schema.py`: `import mia.agents.<id>.models  # noqa: F401`.
  - `docs/layout.md`: one line under `agents/`.
- `test_access.py`: `ROSTER` becomes the ids of `AGENTS` (built agents plus stubs) and the stub-set assertion becomes `{s.id for s in STUBS} == set(ROSTER) - {s.id for s in BUILT}` where `BUILT` is derived from the registry; no literal list to maintain.
- Rendered modules import only `mia.agents.base`, `mia.agents.decider`, `mia.core.*`, `mia.chat.*`, `mia.i18n`, the shift supervisor's `classifier.classify` (the shared injection flag) and the new package itself.

- [ ] **Step 1: Failing tests**

`node/tests/test_scaffold.py`:

```python
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mia.agents import scaffold

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A copy of the parts of the repo the scaffold touches."""
    for rel in (
        "node/mia",
        "node/config",
        "node/tests/test_access.py",
        "docs/layout.md",
        "pyproject.toml",
    ):
        src = REPO / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy(src, dst)
    return tmp_path


def _run(tree: Path, agent_id: str = "quality_officer", **kw: object) -> list[Path]:
    return scaffold.run(
        tree,
        agent_id,
        label_en="Quality Officer",
        label_fi="Laatuvastaava",
        roles=["supervisor", "owner"],
        description="Food safety: temperature logs, expiry, hygiene checklists.",
        **kw,
    )


def test_scaffold_writes_the_package_and_edits_the_shared_files(tree: Path) -> None:
    written = _run(tree)
    pkg = tree / "node/mia/agents/quality_officer"
    assert (pkg / "manifest.yaml").exists() and (pkg / "turn.py").exists()
    registry = (tree / "node/mia/agents/registry.py").read_text()
    assert "quality_officer.turn import SPEC" in registry
    assert '"quality_officer"' not in (tree / "node/mia/agents/stubs.py").read_text()
    assert "agent.quality_officer.label" in (tree / "node/mia/i18n/strings.py").read_text()
    assert "agent:quality_officer, use" in (tree / "node/config/policies/policy.csv").read_text()
    assert "mia.agents.quality_officer.models" in (tree / "node/mia/schema.py").read_text()
    assert all(p.exists() for p in written)


def test_second_run_refuses_and_changes_nothing(tree: Path) -> None:
    _run(tree)
    before = {p: p.read_text() for p in tree.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        _run(tree)
    after = {p: p.read_text() for p in tree.rglob("*") if p.is_file()}
    assert before == after


def test_rendered_modules_spell_no_id_and_import_only_shared_code(tree: Path) -> None:
    _run(tree)
    pkg = tree / "node/mia/agents/quality_officer"
    for py in pkg.rglob("*.py"):
        text = py.read_text()
        assert '"quality_officer"' not in text, py
        assert "sales_supervisor" not in text, py
        compile(text, str(py), "exec")


def test_unknown_role_and_bad_id_are_refused(tree: Path) -> None:
    with pytest.raises(ValueError):
        scaffold.run(
            tree, "Quality-Officer", label_en="x", label_fi="x", roles=["owner"], description="d"
        )
    with pytest.raises(ValueError):
        scaffold.run(
            tree, "quality_officer", label_en="x", label_fi="x", roles=["janitor"], description="d"
        )


@pytest.mark.slow
def test_scaffold_then_checks_in_a_temp_copy(tmp_path: Path) -> None:
    """The real repo copied, scaffolded, and the fast checks run: lint and the new agent's tests."""
    ...
```

For the last test copy the whole repo except `.git`, `.venv`, `data`, run `scaffold.run`, then `subprocess.run([sys.executable, "-m", "pytest", "node/tests/test_quality_officer_chat.py", "node/tests/test_architecture.py", "node/tests/test_access.py", "--no-cov", "-q"], cwd=copy)` and assert returncode 0. Mark it `slow` and register the marker in `pyproject.toml` if it is not there; it runs in the normal suite (it takes about a minute). If copying the venv is needed for imports, run with `PYTHONPATH` pointing at the copy's `node` and the repo's `.venv` site-packages instead of copying it; say which in the report.

- [ ] **Step 2: Run, expect failure** `uv run pytest node/tests/test_scaffold.py --no-cov` (ImportError).

- [ ] **Step 3: Implement**

Templates use `string.Template` with `$agent_id`, `$AgentClass`, `$label_en`, `$description`, `$roles_yaml`. The rendered `turn.py` is the sales supervisor's Jev turn reduced to: the gate on `MIA_DECIDER`, the tap check, the injection check, `build_query`, `decide`, `reply_only` through `replies.conversation_reply`, `clarify` through `clarify.rephrase`; no tools (`_BINDINGS` empty, a tool action in a Decision answers `reply.unavailable`). `actions.py` renders `ACTIONS = {"reply_only": Action(...), "clarify": Action(...)}`, a `Query(message, previous_mia_message, role, today)`, `build_query`, `build_request` with the `action` and `conversation` questions only. `decider.py` renders the wrapper and `_args` for the two actions. `test_chat.py.tmpl` renders `node/tests/test_<id>_chat.py` with one test: the agent greets through `run_turn` with the fake Jev answering `reply_only`/`greeting`. `eval_cases.py.tmpl` and `test_evals.py.tmpl` render the empty case list and a harness built on `tests/evals/gate.py` (skips when the list is empty). `cli.py`: `agent scaffold <id> --label-en --label-fi --role (append) --description [--force]` calling `scaffold.run(Path.cwd(), ...)` with the repo root found by walking up to `pyproject.toml`.

- [ ] **Step 4: Run, expect pass** `uv run pytest node/tests/test_scaffold.py node/tests/test_access.py node/tests/test_architecture.py --no-cov`

- [ ] **Step 5: Full checks and commit**

```bash
uv run ruff check . && uv run ruff format node && uv run mypy node/mia && uv run pytest
git add node/mia/agents/scaffold.py node/mia/agents/_template node/mia/cli.py node/tests/test_scaffold.py node/tests/test_access.py docs/layout.md pyproject.toml
git commit -m "agents: mia agent scaffold renders a new agent package (a Jev turn that greets), wires the registry, label, policy, schema and layout, and refuses to overwrite"
```

---

### Task 2: The skill files

**Files:**
- Create: `.claude/skills/mia-build-agent/SKILL.md`, `checklist.md`, `prompts/spec.md`, `prompts/plan.md`, `prompts/reviewer.md`
- Modify: `CLAUDE.md` (one line under "Library skills": `mia-build-agent` is a project skill, when to use it), `README.md` (one paragraph: building a new agent), `docs/questions.md` (Q51, Q52 as the spec words them), `docs/layout.md` (`.claude/skills/mia-build-agent/`)
- Test: `node/tests/test_skill_files.py` (new, offline)

**Interfaces:**
- `SKILL.md` frontmatter like `mia-train-role` (`name`, `description`); the eight steps of the spec's section 3 with their gates; argument `<agent_id>`; "resume from the first step whose output is missing".
- `checklist.md`: the spec's section 5 verbatim, grouped by rule, each line with the file or test that proves it in the two built agents (for example "business date: `calc.business_date`, `test_sales_calc.py`").
- `prompts/spec.md`: the sales supervisor spec's section headings with one sentence each on what goes there, and the data standard gate as the first section after the goal.
- `prompts/plan.md`: the eight standard tasks with Files, Interfaces and the test names pattern; the Review Focus block pre-filled from `checklist.md` with "pin each to the task that owns it".
- `prompts/reviewer.md`: the extra questions per task kind (data, actions, tools, turn, due, i18n, evals), one block each, lifted from the review prompts used in parts 1 and 2.

- [ ] **Step 1: Failing test**

```python
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / ".claude/skills/mia-build-agent"


def test_skill_files_exist_and_name_the_gates() -> None:
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: mia-build-agent")
    for word in ("data standard", "scaffold", "subagent-driven", "gate half", "checklist.md"):
        assert word in text
    for name in ("checklist.md", "prompts/spec.md", "prompts/plan.md", "prompts/reviewer.md"):
        assert (SKILL / name).exists(), name


def test_checklist_covers_the_rules_parts_one_and_two_kept_finding() -> None:
    text = (SKILL / "checklist.md").read_text()
    for phrase in (
        "MANIFEST.id",
        "pseudonymised",
        "minor units",
        "read_all",
        "midnight",
        "negation",
        "fresh gate half",
        "Tagalog",
    ):
        assert phrase in text, phrase
    assert "—" not in text
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Write the files** (no em-dashes; Filipino never Tagalog; the CLAUDE.md line fits the existing section's style).
- [ ] **Step 4: Run, expect pass** `uv run pytest node/tests/test_skill_files.py --no-cov`
- [ ] **Step 5: Full checks and commit**

```bash
git commit -m "skills: /mia-build-agent carries a catalogue row to a gated agent (data standard gate, spec and plan templates, scaffold, the review checklist from parts 1 and 2)"
```

---

### Task 3: Dry run on the catalogue's next agent (scaffold only)

**Files:**
- Create: the scaffold's output for `inventory_manager` (the package, tests, eval files) through `uv run mia agent scaffold inventory_manager --label-en "Inventory Manager" --label-fi "Varastovastaava" --role clerk --role supervisor --role owner --description "<the stubs.py text>"`
- Modify: whatever the scaffold edits (registry, stubs, i18n, policy, schema, layout, test_access)
- Test: the rendered `node/tests/test_inventory_manager_chat.py` and the whole suite

- [ ] **Step 1: Run the scaffold in the repo** and `git diff --stat`.
- [ ] **Step 2: Full checks** must be green with no hand edits; if a hand edit is needed, that is a scaffold defect: fix Task 1's code or templates, revert the dry run (`git checkout . && git clean -fd node/mia/agents/inventory_manager node/tests/test_inventory_manager_chat.py node/tests/evals/inventory_manager_cases.py node/tests/evals/test_inventory_manager_evals.py`), rerun.
- [ ] **Step 3: Chat check** `MIA_DECIDER=agent uv run mia chat --as Ana "hello"` is not needed; the rendered chat test is the check.
- [ ] **Step 4: Commit** the dry run as the inventory manager's starting point:

```bash
git commit -m "agents: inventory_manager scaffolded by mia agent scaffold (greets; everything else is its plan's work)"
```

---

## Self-review notes

- Spec coverage: section 2 (Task 2 files), 3 (SKILL.md steps), 4 (Task 1), 5 (checklist.md), 6 (SKILL.md pre-made rulings), 7 (Task 1's temp-copy test and Task 3's dry run), 8 (Q51, Q52 in Task 2).
- Type consistency: `scaffold.run` signature in Task 1 and the CLI; the template names in Task 1 and the rendered file names in Task 3.
- Review Focus pinned: 1 to 4 in Task 1, 5 in Task 2.
