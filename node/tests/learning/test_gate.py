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
        IntentSpec(id="r.write", description="d", counterparts=["c"], risk="write", label_en="W"),
        IntentSpec(id="r.read", description="d2", counterparts=["c"], risk="read", label_en="R"),
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
            ),
            "r.read": IntentScore(
                support=30, precision_at_threshold=0.95, recall=0.9, f1=0.9, auto_share=0.8
            ),
        },
        "per_lang": {"en": 0.95, "fi": 0.94},
        "safety_recall": 1.0,
        "false_emergency": 0.0,
        "actions_from_other": 0,
        "confusions": [],
    }
    base.update(over)
    return EvalReport.model_validate(base)


def test_good_report_passes() -> None:
    assert check_gate(report(), ROLE, previous=None).passed


# Precision rule tests - write (target 0.99)
def test_precision_write_below_target_fails() -> None:
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.98, recall=0.9, f1=0.9, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.95, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "precision: r.write 0.980 < 0.99" in result.failures


def test_precision_write_just_below_target_fails() -> None:
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.989999, recall=0.9, f1=0.9, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.95, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "precision: r.write 0.990 < 0.99" in result.failures


def test_precision_write_at_target_passes() -> None:
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.99, recall=0.9, f1=0.9, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.95, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=None,
    )
    assert result.passed


# Precision rule tests - read (target 0.95)
def test_precision_read_below_target_fails() -> None:
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.995, recall=0.9, f1=0.9, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.94, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "precision: r.read 0.940 < 0.95" in result.failures


def test_precision_read_just_below_target_fails() -> None:
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.995, recall=0.9, f1=0.9, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.949999, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "precision: r.read 0.950 < 0.95" in result.failures


def test_precision_read_at_target_passes() -> None:
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.995, recall=0.9, f1=0.9, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.95, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=None,
    )
    assert result.passed


def test_zero_support_fails() -> None:
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=0, precision_at_threshold=0.995, recall=0.0, f1=0.0, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.95, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "precision: r.write has no test records" in result.failures


def test_missing_intent_fails() -> None:
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.995, recall=0.9, f1=0.9, auto_share=0.8
                )
            }
        ),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "precision: r.read has no test records" in result.failures


# Coverage rule tests (target 0.70)
def test_coverage_below_target_fails() -> None:
    result = check_gate(report(coverage=0.69), ROLE, previous=None)
    assert not result.passed
    assert "coverage: 0.69 < 0.7" in result.failures


def test_coverage_just_below_target_fails() -> None:
    result = check_gate(report(coverage=0.699999), ROLE, previous=None)
    assert not result.passed
    assert "coverage: 0.70 < 0.7" in result.failures


def test_coverage_at_target_passes() -> None:
    result = check_gate(report(coverage=0.70), ROLE, previous=None)
    assert result.passed


# Language gap rule tests (target 0.03)
def test_language_gap_exceeds_target_fails() -> None:
    # en=0.95, fi=0.91: gap = 0.04 > 0.03
    result = check_gate(
        report(per_lang={"en": 0.95, "fi": 0.91}),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "language: fi 0.910 more than 0.03 below best 0.950" in result.failures


def test_language_gap_just_exceeds_target_fails() -> None:
    # en=0.95, fi=0.919999: gap = 0.030001 > 0.03
    result = check_gate(
        report(per_lang={"en": 0.95, "fi": 0.919999}),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "language: fi 0.920 more than 0.03 below best 0.950" in result.failures


def test_language_gap_at_target_passes() -> None:
    # en=0.95, fi=0.92: gap = 0.03 <= 0.03
    result = check_gate(
        report(per_lang={"en": 0.95, "fi": 0.92}),
        ROLE,
        previous=None,
    )
    assert result.passed


def test_missing_one_language_fails() -> None:
    # Role has en and fi, but report only has en
    result = check_gate(
        report(per_lang={"en": 0.95}),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "language: fi has no test records" in result.failures


def test_missing_all_languages_fails() -> None:
    # Report has empty per_lang
    result = check_gate(
        report(per_lang={}),
        ROLE,
        previous=None,
    )
    assert not result.passed
    assert "language: en has no test records" in result.failures
    assert "language: fi has no test records" in result.failures


# Safety recall rule tests (target 0.99)
def test_safety_recall_below_target_fails() -> None:
    result = check_gate(report(safety_recall=0.98), ROLE, previous=None)
    assert not result.passed
    assert "safety: recall 0.980 < 0.99" in result.failures


def test_safety_recall_just_below_target_fails() -> None:
    result = check_gate(report(safety_recall=0.989999), ROLE, previous=None)
    assert not result.passed
    assert "safety: recall 0.990 < 0.99" in result.failures


def test_no_safety_test_rows_fails_the_gate() -> None:
    """evaluate reports recall 0.0 without safety rows, so the 99% rule is never vacuous."""
    result = check_gate(report(safety_recall=0.0), ROLE, previous=None)
    assert result.failures == ["safety: recall 0.000 < 0.99"]


def test_safety_recall_at_target_passes() -> None:
    result = check_gate(report(safety_recall=0.99), ROLE, previous=None)
    assert result.passed


# Out-of-scope actions rule tests
def test_actions_from_other_fails() -> None:
    result = check_gate(report(actions_from_other=1), ROLE, previous=None)
    assert not result.passed
    assert "other: 1 out-of-scope or injection messages would act" in result.failures


def test_actions_from_other_zero_passes() -> None:
    result = check_gate(report(actions_from_other=0), ROLE, previous=None)
    assert result.passed


# Calibration (ECE) rule tests (target 0.05)
def test_ece_above_target_fails() -> None:
    result = check_gate(report(ece=0.051), ROLE, previous=None)
    assert not result.passed
    assert "calibration: ECE 0.051 > 0.05" in result.failures


def test_ece_just_above_target_fails() -> None:
    result = check_gate(report(ece=0.050001), ROLE, previous=None)
    assert not result.passed
    assert "calibration: ECE 0.050 > 0.05" in result.failures


def test_ece_at_target_passes() -> None:
    result = check_gate(report(ece=0.05), ROLE, previous=None)
    assert result.passed


# Regression tests
def test_regression_language_tolerance_0_004_passes() -> None:
    # Previous: 0.94, Current: 0.936 (drop of 0.004, within tolerance)
    result = check_gate(
        report(per_lang={"en": 0.95, "fi": 0.936}),
        ROLE,
        previous=report(),
    )
    assert result.passed


def test_regression_language_tolerance_0_006_fails() -> None:
    # Previous: 0.94, Current: 0.934 (drop of 0.006, exceeds tolerance)
    result = check_gate(
        report(per_lang={"en": 0.95, "fi": 0.934}),
        ROLE,
        previous=report(),
    )
    assert not result.passed
    assert any("regression: language fi worse than active" in f for f in result.failures)


def test_regression_intent_f1_tolerance_0_004_passes() -> None:
    # Previous F1: 0.9, Current: 0.896 (drop of 0.004, within tolerance)
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.995, recall=0.9, f1=0.896, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.95, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=report(),
    )
    assert result.passed


def test_regression_intent_f1_tolerance_0_006_fails() -> None:
    # Previous F1: 0.9, Current: 0.894 (drop of 0.006, exceeds tolerance)
    result = check_gate(
        report(
            per_intent={
                "r.write": IntentScore(
                    support=30, precision_at_threshold=0.995, recall=0.9, f1=0.894, auto_share=0.8
                ),
                "r.read": IntentScore(
                    support=30, precision_at_threshold=0.95, recall=0.9, f1=0.9, auto_share=0.8
                ),
            }
        ),
        ROLE,
        previous=report(),
    )
    assert not result.passed
    assert any("regression: intent r.write worse than active" in f for f in result.failures)


def test_regression_language_absent_from_new_report_fails() -> None:
    # Previous has fi=0.94, but new report only has en
    result = check_gate(
        report(per_lang={"en": 0.95}),
        ROLE,
        previous=report(),
    )
    assert not result.passed
    assert any("regression" in f for f in result.failures)
