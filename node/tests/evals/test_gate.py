"""The gate bar: D41 asserts en and fil (and any non-drafted language) at the full bar, wrong at
most 2 percent overall; D40's relaxed reading of the machine-drafted languages (right 65, ask 30,
wrong 2) is reported through gate_reported and never blocks. The short half's one rule (D42) is
no wrong write, read from the manifest. A run's results CSV never overwrites. No model is
called."""

from pathlib import Path

import pytest

from tests.evals import gate
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


def test_a_writing_action_with_wrong_inputs_is_a_wrong_write() -> None:
    """The expected action with other items or another amount writes the wrong row (D42)."""
    row = {"half": "short", "error": None, "missing": None}
    sold = row | {"expected_action": "report_sales", "action": "report_sales"}
    assert wrong_writes([sold | {"score": "wrong_items"}], "sales_supervisor") == [
        sold | {"score": "wrong_items"}
    ]
    counted = row | {"expected_action": "cash_count", "action": "cash_count"}
    assert wrong_writes([counted | {"score": "wrong"}], "bookkeeper")  # another amount
    assert not wrong_writes([counted | {"score": "right"}], "bookkeeper")
    asked = row | {"expected_action": "balances", "action": "balances", "score": "wrong"}
    assert not wrong_writes([asked], "bookkeeper")  # wrong inputs, no write


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


def test_a_new_run_refuses_when_its_raw_file_or_results_csv_exists(tmp_path: Path) -> None:
    from tests.evals.cases import new_run

    raw = tmp_path / "bookkeeper-2026-10-21-0905.raw.json"
    assert new_run(raw) == raw
    raw.with_name("bookkeeper-2026-10-21-0905.results.csv").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        new_run(raw)  # before anything is written
    assert not raw.exists()


def _csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    from tests.evals import cases

    monkeypatch.setattr(cases, "FOLDER", tmp_path)
    (tmp_path / "x.csv").write_text(text, encoding="utf-8")


def test_a_cases_csv_with_a_bad_header_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.evals.cases import HEADER, read

    _csv(tmp_path, monkeypatch, ",".join(HEADER[:-1]) + "\n")
    with pytest.raises(ValueError, match="header"):
        read("x")


@pytest.mark.parametrize("cells", [17, 15])  # an extra field, a missing field
def test_a_cases_row_with_extra_or_missing_fields_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cells: int
) -> None:
    from tests.evals.cases import HEADER, read

    row = ["ask", "cash", "en", "short"] + [""] * (cells - 4)
    _csv(tmp_path, monkeypatch, ",".join(HEADER) + "\n" + ",".join(row) + "\n")
    with pytest.raises(ValueError, match="line 2: 16 fields"):
        read("x")


def test_the_sales_supervisors_short_half_has_seventeen_rows_per_language() -> None:
    """SHORT_ROWS: seventeen per language for the sales supervisor (its receipt rows and
    item_codes), twelve for every other agent; two asks each either way."""
    from tests.evals.gate import short_failures

    def rows(n: int) -> list[gate.ShortRow]:
        return [
            (lang, f"x {lang} {i}", "ask" if i < 2 else "reply_only", "", None, None)
            for lang in ("en", "fil")
            for i in range(n)
        ]

    def size(agent: str, n: int) -> list[str]:
        return [f for f in short_failures(agent, rows(n)) if f.startswith("counts")]

    assert size("sales_supervisor", 17) == [] and size("sales_supervisor", 12) != []
    assert size("bookkeeper", 12) == [] and size("bookkeeper", 17) != []
