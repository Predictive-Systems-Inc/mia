from mia.learning.gate import check_gate
from mia.learning.metrics import EvalReport, IntentScore
from mia.learning.schema import IntentSpec, RoleSpec

ROLE = RoleSpec(
    id="r",
    job_summary="j",
    responsibilities=["x"],
    counterparts=[],
    languages=["en", "fi"],
    countries=["FI"],
    styles={"informal": 1.0},
    intents=[
        IntentSpec(id="r.write", description="d", counterparts=["c"], risk="write", label_en="W")
    ],
)


def report(**over: object) -> EvalReport:
    base: dict[str, object] = {
        "accuracy": 0.95,
        "macro_f1": 0.93,
        "coverage": 0.8,
        "ece": 0.03,
        "per_intent": {
            "r.write": IntentScore(
                support=30, precision_at_threshold=0.995, recall=0.9, f1=0.9, auto_share=0.8
            )
        },
        "per_lang": {"en": 0.95, "fi": 0.94},
        "safety_recall": 1.0,
        "actions_from_other": 0,
        "confusions": [],
    }
    base.update(over)
    return EvalReport.model_validate(base)


def test_good_report_passes() -> None:
    assert check_gate(report(), ROLE, previous=None).passed


def test_each_rule_fails_with_a_reason() -> None:
    cases = {
        "precision": report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.97, recall=0.9, f1=0.9, auto_share=0.8
                )
            }
        ),
        "coverage": report(coverage=0.5),
        "language": report(per_lang={"en": 0.95, "fi": 0.85}),
        "safety": report(safety_recall=0.9),
        "other": report(actions_from_other=1),
        "calibration": report(ece=0.2),
    }
    for word, rep in cases.items():
        result = check_gate(rep, ROLE, previous=None)
        assert not result.passed and any(word in f for f in result.failures), word


def test_regression_against_the_active_version_fails() -> None:
    result = check_gate(report(per_lang={"en": 0.95, "fi": 0.93}), ROLE, previous=report())
    assert not result.passed and any("worse than active" in f for f in result.failures)
