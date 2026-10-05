"""Shared test builders for the learning package tests."""

from mia.learning.gate import GateResult
from mia.learning.metrics import EvalReport
from mia.learning.package import ModelCard


def card(passed: bool = True, version: str = "v1") -> ModelCard:
    rep = EvalReport(
        accuracy=1,
        macro_f1=1,
        coverage=1,
        ece=0,
        per_intent={},
        per_lang={},
        safety_recall=1,
        false_emergency=0,
        actions_from_other=0,
        confusions=[],
    )
    return ModelCard(
        role="r",
        version=version,
        base_model="m",
        data_hash="h",
        temperature=1.0,
        medium_floor=0.35,
        safety_floor=0.2,
        labels=["r.a", "other"],
        langs=["en"],
        slots={},
        thresholds={"r.a": 0.9},
        report=rep,
        gate=GateResult(passed=passed, failures=[] if passed else ["coverage"]),
    )
