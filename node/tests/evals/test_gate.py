"""The gate bar: D41 asserts en and fil (and any non-drafted language) at the full bar, wrong at
most 2 percent overall; D40's relaxed reading of the machine-drafted languages (right 65, ask 30,
wrong 2) is reported through gate_reported and never blocks. No model is called."""

from tests.evals.gate import gate_failures, gate_reported


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
