"""The D40 gate bar: full for en and fil, relaxed right 65 / ask 30 for machine-drafted languages,
wrong at most 2 percent everywhere. No model is called."""

from tests.evals.gate import gate_failures


def _gated(lang: str, right: float, ask: float, wrong: float = 0.0) -> dict[str, object]:
    return {
        "all": {"wrong": wrong},
        "by_language": {lang: {"right": right, "ask": ask, "wrong": wrong}},
    }


def test_the_gate_is_the_d40_bar() -> None:
    assert gate_failures(_gated("en", 0.80, 0.15, 0.02)) == []
    assert gate_failures(_gated("fil", 0.79, 0.15)) == ["fil right 0.79"]
    assert gate_failures(_gated("en", 0.80, 0.16)) == ["en ask 0.16"]
    assert gate_failures(_gated("ceb", 0.66, 0.29)) == []
    assert gate_failures(_gated("war", 0.64, 0.31)) == ["war right 0.64", "war ask 0.31"]
    assert gate_failures(_gated("ceb", 0.90, 0.05, 0.03)) == ["wrong 0.03", "ceb wrong 0.03"]
    one_language = {
        "all": {"wrong": 0.01},
        "by_language": {"hil": {"right": 0.76, "ask": 0.20, "wrong": 0.036}},
    }
    assert gate_failures(one_language) == ["hil wrong 0.036"]
