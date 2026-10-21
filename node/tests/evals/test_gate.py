"""The gate bar: D41 asserts en and fil (and any non-drafted language) at the full bar, wrong at
most 2 percent overall; D40's relaxed reading of the machine-drafted languages (right 65, ask 30,
wrong 2) is reported through gate_reported and never blocks. The short half's one rule (D42) is
no wrong write, read from the manifest. A run's results CSV never overwrites. No model is
called."""

from pathlib import Path

import pytest

from tests.evals.cases import RESULTS
from tests.evals.cases import write_results as results_csv
from tests.evals.gate import gate_failures, gate_reported, writes, wrong_writes


def _gated(lang: str, right: float, ask: float, wrong: float = 0.0) -> dict[str, object]:
    return {
        "all": {"wrong": wrong},
        "by_language": {lang: {"right": right, "ask": ask, "wrong": wrong}},
    }


def test_the_gate_asserts_en_and_fil_at_the_full_bar() -> None:
    assert gate_failures(_gated("en", 0.80, 0.15, 0.02)) == []
    assert gate_failures(_gated("fil", 0.79, 0.15)) == ["fil right 0.79"]
    assert gate_failures(_gated("en", 0.80, 0.16)) == ["en ask 0.16"]
    assert gate_failures(_gated("fil", 0.90, 0.05, 0.03)) == ["wrong 0.03", "fil wrong 0.03"]
    one_language = {
        "all": {"wrong": 0.01},
        "by_language": {"fil": {"right": 0.76, "ask": 0.20, "wrong": 0.022}},
    }
    assert gate_failures(one_language) == ["fil wrong 0.022", "fil right 0.76", "fil ask 0.2"]


def test_the_drafted_languages_are_reported_never_asserted() -> None:
    assert gate_failures(_gated("war", 0.64, 0.31)) == []
    assert gate_reported(_gated("war", 0.64, 0.31)) == ["war right 0.64", "war ask 0.31"]
    assert gate_reported(_gated("ceb", 0.66, 0.29)) == []
    one_language = {
        "all": {"wrong": 0.01},
        "by_language": {"hil": {"right": 0.76, "ask": 0.20, "wrong": 0.036}},
    }
    assert gate_failures(one_language) == []
    assert gate_reported(one_language) == ["hil wrong 0.036"]
    overall = _gated("ceb", 0.90, 0.05, 0.03)
    assert gate_failures(overall) == ["wrong 0.03"]
    assert gate_reported(overall) == ["ceb wrong 0.03"]


def test_a_wrong_write_is_a_short_rows_writing_action_other_than_the_expected() -> None:
    assert writes("bookkeeper", "cash_count") and not writes("bookkeeper", "balances")
    assert not writes("bookkeeper", "clarify") and not writes("bookkeeper", "ask")
    assert writes("shift_supervisor", "check_in")  # the retail actions at Ferino's
    row = {"half": "short", "error": None, "expected_action": "ask", "missing": None}
    assert wrong_writes([row | {"action": "cash_count"}], "bookkeeper") == [
        row | {"action": "cash_count"}
    ]
    assert not wrong_writes([row | {"action": "balances"}], "bookkeeper")  # wrong, no write
    assert not wrong_writes([row | {"action": "clarify"}], "bookkeeper")
    assert not wrong_writes([row | {"action": "cash_count", "error": "boom"}], "bookkeeper")
    asked = row | {"expected_action": "deposit", "action": "cash_count", "missing": "amount"}
    assert not wrong_writes([asked], "bookkeeper")  # a missing input asks
    right = row | {"expected_action": "cash_count", "action": "cash_count"}
    assert not wrong_writes([right], "bookkeeper")
    gated = row | {"half": "gate", "action": "cash_count"}
    assert not wrong_writes([gated], "bookkeeper")  # a gate row never counts


def test_a_runs_results_csv_sits_beside_its_raw_file_and_never_overwrites(tmp_path: Path) -> None:
    raw = tmp_path / "bookkeeper-2026-10-21-0905.raw.json"
    row = {"text": "cash 12450", "lang": "en", "half": "short", "expected_action": "ask"}
    row |= {"action": "cash_count", "confidence": 0.9, "score": "wrong", "missing": None}
    out = results_csv(raw, [row])
    assert out == tmp_path / "bookkeeper-2026-10-21-0905.results.csv"
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines == [",".join(RESULTS), "cash 12450,en,short,ask,cash_count,0.9,wrong,"]
    with pytest.raises(FileExistsError):
        results_csv(raw, [row])
