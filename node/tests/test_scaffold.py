import ast
import os
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
        "node/tests/jev_fake.py",  # ruff sees `tests` as first-party
        "node/tests/test_access.py",
        "node/tests/evals/router_cases.py",
        "docs/layout.md",
        "pyproject.toml",
    ):
        src = REPO / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(src, dst)
    return tmp_path


def _run(root: Path, agent_id: str = "quality_officer", **kw: bool) -> list[Path]:
    return scaffold.run(
        root,
        agent_id,
        label_en="Quality Officer",
        label_fi="Laatuvastaava",
        roles=["supervisor", "owner"],
        description="Food safety: temperature logs, expiry, hygiene checklists; not stock.",
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
    assert "quality_officer/" in (tree / "docs/layout.md").read_text()
    router_cases = (tree / "node/tests/evals/router_cases.py").read_text()
    pending = router_cases[router_cases.index("PENDING") :].split("}")[0]  # joins the ids waiting
    assert '"quality_officer"' in pending
    assert (tree / "node/tests/test_quality_officer_chat.py") in written
    assert all(p.exists() for p in written)


def test_second_run_refuses_and_changes_nothing(tree: Path) -> None:
    _run(tree)
    before = {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        _run(tree)
    after = {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}
    assert before == after


def test_force_rewrites_the_package_and_edits_the_shared_files_once(tree: Path) -> None:
    _run(tree)
    _run(tree, force=True)
    assert (tree / "node/mia/agents/registry.py").read_text().count("QUALITY_OFFICER,") == 1
    policy = (tree / "node/config/policies/policy.csv").read_text()
    assert policy.count("p, owner, *, agent:quality_officer, use, allow") == 1


def test_rendered_modules_spell_no_id_and_import_only_shared_code(tree: Path) -> None:
    _run(tree)
    pkg = tree / "node/mia/agents/quality_officer"
    shared = (
        "mia.agents.base",
        "mia.agents.decider",
        "mia.agents.shift_supervisor.classifier",  # the shared injection flag
        "mia.agents.quality_officer",
        "mia.core",
        "mia.chat",
        "mia.i18n",
        "mia.settings",
    )
    for py in pkg.rglob("*.py"):
        text = py.read_text()
        assert '"quality_officer"' not in text, py
        assert "sales_supervisor" not in text, py
        assert "\u2014" not in text, py
        for node in ast.walk(ast.parse(text, str(py))):
            if isinstance(node, ast.ImportFrom) and node.module == "mia.agents":
                names = [f"mia.agents.{a.name}" for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                continue
            mia = [n for n in names if n.startswith("mia")]
            assert all(n.startswith(shared) for n in mia), (py, names)


def test_unknown_role_and_bad_id_are_refused(tree: Path) -> None:
    def run(agent_id: str, roles: list[str]) -> None:
        scaffold.run(tree, agent_id, label_en="x", label_fi="x", roles=roles, description="d")

    with pytest.raises(ValueError):
        run("Quality-Officer", ["owner"])
    with pytest.raises(ValueError):
        run("quality_officer", ["janitor"])
    with pytest.raises(ValueError):
        run("decider", ["owner"])  # a module of mia/agents, not a package


def test_a_description_without_a_contrast_line_is_refused(tree: Path) -> None:
    with pytest.raises(ValueError, match="; not "):
        scaffold.run(
            tree, "quality_officer", label_en="x", label_fi="x", roles=["owner"], description="d"
        )
    assert not (tree / "node/mia/agents/quality_officer").exists()


def test_a_stub_is_built_with_its_router_description(tree: Path) -> None:
    stubs = (tree / "node/mia/agents/stubs.py").read_text()
    text = scaffold.stub_description(stubs, "bookkeeper")
    assert text is not None and text.startswith("Money: the cash count")
    scaffold.run(
        tree, "bookkeeper", label_en="Bookkeeper", label_fi="x", roles=["owner"], description=""
    )
    turn = (tree / "node/mia/agents/bookkeeper/turn.py").read_text()
    assert '"Money: the cash count' in turn
    assert max(len(line) for line in turn.splitlines()) <= 100
    ast.parse(turn)
    assert "agent.bookkeeper.label" in (tree / "node/mia/i18n/strings.py").read_text()
    assert (tree / "node/mia/i18n/strings.py").read_text().count("agent.bookkeeper.label") == 2


def _ruff_imports(root: Path, files: list[Path]) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "ruff", "check", "--select", "I", *map(str, files)]
    return subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)


def test_rendered_imports_are_sorted_for_ids_before_and_after_the_shared_modules(
    tree: Path,
) -> None:
    """bookkeeper sorts before decider, warehouse_officer after shift_supervisor."""
    written = scaffold.run(
        tree, "bookkeeper", label_en="Bookkeeper", label_fi="x", roles=["owner"], description=""
    )
    written += _run(tree, "warehouse_officer")
    done = _ruff_imports(tree, [p for p in written if p.suffix == ".py"])
    assert done.returncode == 0, done.stdout


def test_a_built_agent_is_refused_even_with_force(tree: Path) -> None:
    from mia.agents.sales_supervisor import MANIFEST

    with pytest.raises(ValueError, match="already built"):
        _run(tree, MANIFEST.id, force=True)


def test_a_label_that_could_break_the_rendered_code_is_refused(tree: Path) -> None:
    for label in ('Quality "Officer"', "Quality\\Officer", "Quality\nOfficer"):
        with pytest.raises(ValueError, match="label"):
            scaffold.run(
                tree,
                "quality_officer",
                label_en=label,
                label_fi="x",
                roles=["owner"],
                description="d; not e",
            )
    assert not (tree / "node/mia/agents/quality_officer").exists()


def test_a_missing_anchor_raises_before_any_write(tree: Path) -> None:
    layout = tree / "docs/layout.md"
    layout.write_text(layout.read_text().replace("<role>/skill/", "<role>/other/"))
    before = {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}
    with pytest.raises(RuntimeError, match=r"docs/layout\.md.*<role>/skill/"):
        _run(tree)
    assert before == {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}


def test_a_label_flag_on_a_promoted_stub_prints_the_kept_label(
    tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mia import cli

    monkeypatch.setattr(cli, "NODE_DIR", tree / "node")
    argv = ["agent", "scaffold", "bookkeeper", "--role", "owner", "--label-en", "Bookkeeper"]
    args = cli.build_parser().parse_args([*argv, "--label-fi", "Kirjanpitäjä-x"])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "label for bookkeeper already set in fi: kept " in out
    assert "already set in en" not in out


def test_the_command_refuses_a_bad_id_before_writing() -> None:
    from mia.cli import build_parser

    argv = ["agent", "scaffold", "Bad-Id", "--label-en", "x", "--label-fi", "x", "--role", "owner"]
    args = build_parser().parse_args(argv)
    with pytest.raises(SystemExit, match="agent id must match"):
        args.func(args)


# The pure edits, one per shared file.
def test_edit_registry_imports_and_lists_the_spec() -> None:
    text = (
        "from mia.agents.base import AgentSpec\n"
        "from mia.agents.sales_supervisor.turn import SPEC as SALES_SUPERVISOR\n"
        "from mia.agents.stubs import STUBS\n"
        "\nBUILT = [\n    SALES_SUPERVISOR,\n]\n"
    )
    out = scaffold.edit_registry(text, "quality_officer")
    assert (
        out.splitlines()[1] == "from mia.agents.quality_officer.turn import SPEC as QUALITY_OFFICER"
    )
    assert out.endswith("    SALES_SUPERVISOR,\n    QUALITY_OFFICER,\n]\n")
    assert scaffold.edit_registry(out, "quality_officer") == out


def test_edit_stubs_deletes_only_the_entry() -> None:
    text = (
        'DESCRIPTIONS = {\n    "a_one": (\n        "First"\n        " more"\n    ),\n'
        '    "b_two": (\n        "Second"\n    ),\n}\n'
    )
    assert (
        scaffold.edit_stubs(text, "a_one")
        == 'DESCRIPTIONS = {\n    "b_two": (\n        "Second"\n    ),\n}\n'
    )
    assert scaffold.edit_stubs(text, "c_three") == text
    assert scaffold.stub_description(text, "a_one") == "First more"


def test_edit_strings_adds_the_label_after_each_label_group() -> None:
    text = (
        '    "en": {\n        "agent.x.label": "X",\n        "k": "v",\n    },\n'
        '    "fi": {\n        "agent.x.label": "Iks",\n    },\n'
    )
    out = scaffold.edit_strings(text, "q_o", "Quality", "Laatu")
    assert out.splitlines()[2] == '        "agent.q_o.label": "Quality",'
    assert out.splitlines()[7] == '        "agent.q_o.label": "Laatu",'
    assert scaffold.edit_strings(out, "q_o", "Quality", "Laatu") == out


def test_edit_module_adds_the_english_label() -> None:
    text = 'STRINGS = {\n    "agent.x.label": "X",\n    "k": "v",\n}\n'
    out = scaffold.edit_module(text, "q_o", 'Say "hi"')
    assert out.splitlines()[2] == '    "agent.q_o.label": "Say \\"hi\\"",'
    assert scaffold.edit_module(out, "q_o", "other") == out


def test_edit_policy_adds_one_line_per_role_after_the_agent_lines() -> None:
    text = "p, staff, *, agent:a, use, allow\n\n# later\n"
    out = scaffold.edit_policy(text, "q_o", ["owner", "staff"])
    lines = out.splitlines()
    assert lines[1:3] == [
        "p, owner, *, agent:q_o, use, allow",
        "p, staff, *, agent:q_o, use, allow",
    ]
    assert scaffold.edit_policy(out, "q_o", ["owner"]) == out


def test_edit_schema_keeps_the_imports_sorted() -> None:
    text = "import mia.agents.sales_supervisor.models\nimport mia.core.models  # noqa: F401\n"
    out = scaffold.edit_schema(text, "a_one")
    assert out.splitlines() == [
        "import mia.agents.a_one.models",
        "import mia.agents.sales_supervisor.models",
        "import mia.core.models  # noqa: F401",
    ]
    assert scaffold.edit_schema(out, "a_one") == out


def test_edit_router_pending_adds_the_id_sorted() -> None:
    text = "X = 1\nPENDING: set[str] = set()\nY = 2\n"
    out = scaffold.edit_router_pending(text, "b_two")
    assert out == 'X = 1\nPENDING: set[str] = {"b_two"}\nY = 2\n'
    out = scaffold.edit_router_pending(out, "a_one")
    assert 'PENDING: set[str] = {"a_one", "b_two"}\n' in out
    assert scaffold.edit_router_pending(out, "a_one") == out


def test_edit_router_pending_reads_a_wrapped_literal_and_writes_it_sorted() -> None:
    text = 'X = 1\nPENDING: set[str] = {\n    "c_three",\n    "a_one",\n    "b_two",\n}\nY = 2\n'
    out = scaffold.edit_router_pending(text, "d_four")
    assert out.splitlines()[1:8] == [
        "PENDING: set[str] = {",
        '    "a_one",',
        '    "b_two",',
        '    "c_three",',
        '    "d_four",',
        "}",
        "Y = 2",
    ]
    assert scaffold.edit_router_pending(out, "d_four") == out


def test_edit_router_pending_skips_an_id_that_has_cases() -> None:
    text = 'PENDING: set[str] = set()\nSEEDS = [\n    ("b_two", "hello"),\n]\n'
    assert scaffold.edit_router_pending(text, "b_two") == text


def test_edit_stubs_removing_the_last_entry_leaves_a_formatted_dict() -> None:
    text = 'DESCRIPTIONS = {\n    "b_two": (\n        "x"\n    ),\n}\n'
    assert scaffold.edit_stubs(text, "b_two") == "DESCRIPTIONS: dict[str, str] = {}\n"


def test_edit_layout_adds_a_line_before_the_role_skill_line() -> None:
    text = "        sales_supervisor/   manifest.yaml\n        <role>/skill/       role.yaml\n"
    out = scaffold.edit_layout(text, "q_o", "Quality")
    assert out.splitlines()[1].startswith("        q_o/                ")
    assert scaffold.edit_layout(out, "q_o", "Quality") == out


@pytest.mark.slow
def test_scaffold_then_checks_in_a_temp_copy(tmp_path: Path) -> None:
    """The real repo copied, scaffolded, and the checks run there: lint, format, types and the
    new agent's chat test with the architecture and access tests. The copy's node/ comes first
    on PYTHONPATH, so `mia` is the copy's; packages come from this interpreter's venv."""
    copy = tmp_path / "repo"
    skip = (".git", ".venv", "data", "node_modules", ".superpowers", "__pycache__", "*_cache")
    shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(*skip))
    _run(copy, "demo_officer")  # brand new: no router cases yet (PENDING)
    scaffold.run(  # a stub promoted: sorts before decider, keeps its router cases
        copy, "bookkeeper", label_en="Bookkeeper", label_fi="x", roles=["owner"], description=""
    )
    env = {**os.environ, "PYTHONPATH": str(copy / "node")}

    def check(*args: str) -> None:
        done = subprocess.run(
            [sys.executable, "-m", *args],
            cwd=copy,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]

    check("ruff", "check", ".")
    check("ruff", "format", "--check", "node")
    check("mypy", "node/mia")
    check(
        "pytest",
        "node/tests/test_demo_officer_chat.py",
        "node/tests/test_bookkeeper_chat.py",
        "node/tests/evals/test_router_cases.py",
        "node/tests/test_agent_router.py::test_router_descriptions_carry_a_contrast_line",
        "node/tests/test_architecture.py",
        "node/tests/test_access.py",
        "--no-cov",
        "-q",
        "-p",
        "no:cacheprovider",
    )
