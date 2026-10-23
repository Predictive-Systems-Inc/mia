"""node/tests/affected.py picks the tests a change affects from a reverse import graph."""

from pathlib import Path

from tests.affected import affected


def _tree(root: Path) -> Path:
    """Two agents, a and b, each with a test that imports it; a's turn imports calc relatively."""
    files = {
        "node/mia/__init__.py": "",
        "node/mia/agents/__init__.py": "",
        "node/mia/agents/a/__init__.py": "",
        "node/mia/agents/a/calc.py": "X = 1\n",
        "node/mia/agents/a/turn.py": "from .calc import X\n",
        "node/mia/agents/a/tests/scenarios.yaml": "[]\n",
        "node/mia/agents/b/__init__.py": "",
        "node/mia/agents/b/calc.py": "import mia.agents.b\n",
        "node/mia/agents/b/tests/scenarios.yaml": "[]\n",
        "node/tests/conftest.py": "from mia.agents.b import calc\n",
        "node/tests/test_architecture.py": "",
        "node/tests/test_a.py": "from mia.agents.a.turn import X\n",
        "node/tests/test_b.py": "from mia.agents.b import calc\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def test_an_agent_change_selects_its_tests_and_not_another_agents(tmp_path: Path) -> None:
    assert affected(["node/mia/agents/a/calc.py"], _tree(tmp_path)) == [
        "node/mia/agents/a/tests",
        "node/tests/test_a.py",
        "node/tests/test_architecture.py",
    ]


def test_a_data_file_counts_as_its_package(tmp_path: Path) -> None:
    assert "node/tests/test_b.py" in affected(
        ["node/mia/agents/b/tests/scenarios.yaml"], _tree(tmp_path)
    )


def test_a_changed_test_runs_itself(tmp_path: Path) -> None:
    assert affected(["node/tests/test_b.py"], _tree(tmp_path)) == ["node/tests/test_b.py"]


def test_a_conftest_change_runs_everything(tmp_path: Path) -> None:
    assert affected(["node/tests/conftest.py"], _tree(tmp_path)) == ["ALL"]


def test_docs_run_nothing_and_eval_csvs_run_the_case_tests(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert affected(["docs/plan.md", "README.md"], root) == []
    assert affected(["node/tests/evals/cases/router.csv"], root) == ["node/tests/evals"]


def test_an_unplaced_file_runs_everything(tmp_path: Path) -> None:
    assert affected([".github/workflows/ci.yml"], _tree(tmp_path)) == ["ALL"]
