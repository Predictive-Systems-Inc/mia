import json
import types
from pathlib import Path

import numpy as np
import pytest

from mia.cli import main
from mia.learning import commands


class FakeEmbedder:
    """Bag of words over a tiny vocabulary: texts sharing words are close."""

    prefix = ""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, texts: list[str]) -> np.ndarray:
        vocab = ["pay", "day", "price", "clean", "hello"]
        m = np.array([[t.lower().count(w) + 0.01 for w in vocab] for t in texts], dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.SimpleNamespace(Embedder=FakeEmbedder)
    real = commands.import_module
    monkeypatch.setattr(
        commands, "import_module", lambda n: module if n == "mia.learning.embed" else real(n)
    )


def write_dataset(path: Path) -> None:
    rows = [
        ("a/1", "hr.payday", "when is pay day"),
        ("a/2", "hr.payday", "pay day when"),
        ("b/1", "conversation.kb_payday", "what day is pay day"),
        ("b/2", "conversation.kb_payday", "pay day date"),
    ]
    path.write_text(
        "".join(json.dumps({"id": i, "intent": n, "text": t}) + "\n" for i, n, t in rows),
        encoding="utf-8",
    )


def test_overlap_on_a_dataset_writes_the_report_and_recall(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "d.jsonl"
    write_dataset(data)
    review = tmp_path / "review.md"
    review.write_text(
        "## Decisions\n\n| Pair | D |\n| --- | --- |\n| hr.payday / conversation.kb_payday | x |\n",
        encoding="utf-8",
    )
    out = tmp_path / "r.md"
    argv = ["skills", "overlap", "--dataset", str(data), "--expect", str(review), "--out", str(out)]
    assert main(argv) == 0
    text = out.read_text(encoding="utf-8")
    assert "| conversation.kb_payday | hr.payday |" in text
    assert "recall 1.00 (1/1)" in capsys.readouterr().out


def test_overlap_needs_a_role_or_a_dataset(fake: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skills", "overlap"]) == 1
    assert capsys.readouterr().out.strip() == "give a role or --dataset"


def test_overlap_with_no_records_is_an_error(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "e.jsonl"
    empty.write_text("", encoding="utf-8")
    assert main(["skills", "overlap", "--dataset", str(empty), "--no-conversation"]) == 1
    assert capsys.readouterr().out.strip() == "no records to compare"


def test_overlap_without_the_learning_group_prints_the_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def missing(name: str) -> object:
        raise ModuleNotFoundError("no torch", name="torch")

    monkeypatch.setattr(commands, "import_module", missing)
    data = tmp_path / "d.jsonl"
    write_dataset(data)
    assert main(["skills", "overlap", "--dataset", str(data)]) == 2
    assert capsys.readouterr().out.strip() == commands.LEARNING_HINT


def test_overlap_names_unfindable_pairs_and_scores_only_findable_ones(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "d.jsonl"
    write_dataset(data)
    review = tmp_path / "review.md"
    review.write_text(
        "## Decisions\n\n| Pair | D |\n| --- | --- |\n"
        "| hr.payday / conversation.kb_payday | x |\n| hr.payday / hr.ghost | y |\n",
        encoding="utf-8",
    )
    argv = ["skills", "overlap", "--dataset", str(data), "--expect", str(review)]
    assert main([*argv, "--out", str(tmp_path / "r.md")]) == 0
    out = capsys.readouterr().out
    assert "unfindable: 1 pairs (no records): hr.ghost / hr.payday\n" in out
    assert "recall 1.00 (1/1)\n" in out


def test_overlap_calibrate_writes_the_thresholds(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "d.jsonl"
    write_dataset(data)
    review = tmp_path / "review.md"
    review.write_text(
        "## Decisions\n\n| Pair | D |\n| --- | --- |\n| hr.payday / conversation.kb_payday | x |\n",
        encoding="utf-8",
    )
    out = tmp_path / "r.md"
    argv = ["skills", "overlap", "--dataset", str(data), "--expect", str(review), "--out", str(out)]
    assert main([*argv, "--calibrate"]) == 0
    assert "Calibrated thresholds: {" in out.read_text(encoding="utf-8")


def test_overlap_for_a_role_without_role_yaml_is_an_error(
    fake: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["skills", "overlap", "nosuchrole"]) == 1
    assert "role.yaml not found" in capsys.readouterr().out


def test_overlap_reports_a_missing_dataset(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "nope.jsonl"
    assert main(["skills", "overlap", "--dataset", str(path)]) == 1
    assert capsys.readouterr().out == f"error: {path}: file not found\n"


def test_overlap_reports_a_missing_expect_file(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "d.jsonl"
    write_dataset(data)
    review = tmp_path / "nope.md"
    assert main(["skills", "overlap", "--dataset", str(data), "--expect", str(review)]) == 1
    assert capsys.readouterr().out == f"error: {review}: file not found\n"


def test_overlap_reports_malformed_json_and_incomplete_rows(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "b.jsonl"
    bad.write_text('{"id": "a", "intent": "x", "text": "t"}\n{oops\n', encoding="utf-8")
    assert main(["skills", "overlap", "--dataset", str(bad)]) == 1
    assert capsys.readouterr().out == f"error: {bad}: line 2: invalid JSON\n"
    short = tmp_path / "s.jsonl"
    short.write_text('{"id": "a", "intent": "x"}\n', encoding="utf-8")
    assert main(["skills", "overlap", "--dataset", str(short)]) == 1
    assert capsys.readouterr().out == f"error: {short}: line 1: needs id, intent and text\n"


def test_overlap_recall_is_not_available_when_nothing_is_findable(
    fake: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "d.jsonl"
    write_dataset(data)
    review = tmp_path / "review.md"
    review.write_text(
        "## Decisions\n\n| Pair | D |\n| --- | --- |\n| hr.ghost / hr.phantom | x |\n",
        encoding="utf-8",
    )
    argv = ["skills", "overlap", "--dataset", str(data), "--expect", str(review)]
    assert main([*argv, "--out", str(tmp_path / "r.md")]) == 0
    assert "recall n/a (0/0)\n" in capsys.readouterr().out
