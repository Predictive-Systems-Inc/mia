import math

from mia.learning.metrics import (
    Prediction,
    choose_thresholds,
    evaluate,
    expected_calibration_error,
    fit_temperature,
    softmax,
)
from mia.learning.schema import IntentSpec, RoleSpec

LABELS = ["r.write", "r.read", "conversation.emergency", "other"]
ROLE = RoleSpec(
    id="r",
    job_summary="j",
    responsibilities=["x"],
    counterparts=[],
    languages=["en", "fi"],
    countries=["FI"],
    styles={"informal": 1.0},
    intents=[
        IntentSpec(
            id="r.write",
            description="d",
            counterparts=["c"],
            risk="write",
            label_en="W",
            handler="template",
        ),
        IntentSpec(id="r.read", description="d", counterparts=["c"], risk="read", label_en="R"),
    ],
)


def p(
    i: int, intent: str, logits: list[float], lang: str = "en", kind: str = "normal"
) -> Prediction:
    return Prediction(
        record_id=str(i),
        intent=intent,
        lang=lang,
        kind=kind,
        style="informal",
        labels=LABELS,
        logits=logits,
    )


def test_softmax_sums_to_one_and_temperature_flattens() -> None:
    s = softmax([2.0, 0.0])
    assert math.isclose(sum(s), 1.0)
    assert softmax([2.0, 0.0], temperature=2.0)[0] < s[0]


def test_thresholds_meet_precision_or_disable() -> None:
    preds = [p(i, "r.write", [5, 0, 0, 0]) for i in range(20)] + [p(30, "r.read", [3, 0, 0, 0])]
    thr = choose_thresholds(preds, ROLE, temperature=1.0)
    above = [x for x in preds if softmax(x.logits)[0] >= thr["r.write"]]
    assert all(x.intent == "r.write" for x in above)
    only_wrong = [p(i, "r.read", [5, 0, 0, 0]) for i in range(5)]
    assert choose_thresholds(only_wrong, ROLE, 1.0)["r.write"] > 1.0


def test_evaluate_counts_actions_from_other_and_safety_recall() -> None:
    preds = [
        p(1, "r.write", [6, 0, 0, 0]),
        p(2, "other", [6, 0, 0, 0], kind="injection"),  # routed to a template action: bad
        p(3, "conversation.emergency", [0, 0, 6, 0], kind="safety"),
        p(4, "r.read", [0, 6, 0, 0], lang="fi"),
    ]
    report = evaluate(
        preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety={"conversation.emergency"}
    )
    assert report.actions_from_other == 1
    assert report.safety_recall == 1.0
    assert set(report.per_lang) == {"en", "fi"}


def test_calibration_helpers_run() -> None:
    preds = [p(i, "r.write", [2, 0, 0, 0]) for i in range(10)]
    t = fit_temperature(preds)
    assert 0.5 <= t <= 5.0
    assert 0.0 <= expected_calibration_error(preds, t) <= 1.0


def test_thresholds_rejects_ties_with_mixed_correctness() -> None:
    """Tied confidences with mixed correctness must not all be accepted."""
    # Two predictions at same confidence, different correctness
    preds = [
        p(1, "r.write", [1.0, 0.0, 0.0, 0.0]),  # correct for r.write
        p(
            2, "r.read", [1.0, 0.0, 0.0, 0.0]
        ),  # wrong for r.write (pred says r.write but true is r.read)
    ]
    thr = choose_thresholds(preds, ROLE, 1.0)
    # With 99% precision target for write, we can't accept both at the tie
    assert thr["r.write"] > 1.0  # unreachable when all predictions have same confidence

    # Stricter case: require accepting only when precision can be met
    preds2 = [
        p(1, "r.write", [2.0, 0.0, 0.0, 0.0]),  # correct
        p(2, "r.write", [2.0, 0.0, 0.0, 0.0]),  # correct
        p(3, "r.read", [1.0, 0.0, 0.0, 0.0]),  # wrong
    ]
    thr2 = choose_thresholds(preds2, ROLE, 1.0)
    # With tie handling, threshold must be chosen carefully
    above = [x for x in preds2 if softmax(x.logits)[0] >= thr2["r.write"]]
    if above:
        # If any are accepted, all must be correct (99% precision)
        precision = sum(1 for x in above if x.intent == "r.write") / len(above)
        assert precision >= 0.99  # precision_write target


def test_macro_f1_excludes_zero_support_intents() -> None:
    """Intents with zero support in test set should not count in macro F1."""
    # Only r.write in predictions, r.read has zero support
    preds = [p(i, "r.write", [5, 0, 0, 0]) for i in range(5)]
    report = evaluate(preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety=set())
    # F1 for r.write should be 1.0, r.read should not affect macro average
    assert report.per_intent["r.write"].support == 5
    assert report.per_intent["r.read"].support == 0
    # macro_f1 should be just r.write's F1 (1.0), not average of all intents
    assert report.macro_f1 == 1.0


def test_pinned_values_for_ece_per_lang_precision_coverage() -> None:
    """Verify specific metrics on a deterministic test case."""
    # Tiny case: 2 predictions, both correct on r.write at same logit
    preds = [
        p(1, "r.write", [2.0, 0.0, 0.0, 0.0], lang="en"),
        p(2, "r.write", [2.0, 0.0, 0.0, 0.0], lang="fi"),
    ]
    t = 1.0  # temperature
    # Softmax of [2.0, 0, 0, 0]: 1/(1+3*e^-2)
    expected_conf = 1.0 / (1.0 + 3.0 * math.exp(-2.0))
    # ECE: both in bin 7 with accuracy 100%, confidence ~71.1%
    # ECE = (2/2) * |conf - 1.0|
    expected_ece = 1.0 * abs(expected_conf - 1.0)

    report = evaluate(preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, t, safety=set())
    ece = expected_calibration_error(preds, t, bins=10)
    assert math.isclose(ece, expected_ece, rel_tol=1e-9)

    # Per-lang: both correct (en: 1.0, fi: 1.0)
    assert report.per_lang["en"] == 1.0
    assert report.per_lang["fi"] == 1.0

    # Precision at threshold 0.5: both above, both correct -> 1.0
    assert report.per_intent["r.write"].precision_at_threshold == 1.0

    # Coverage: both above threshold -> 1.0
    assert report.coverage == 1.0

    # Auto share for r.write: 2/2 = 1.0
    assert report.per_intent["r.write"].auto_share == 1.0


def test_precision_at_threshold_below_one() -> None:
    """Precision at threshold can be below 1.0 when above-threshold predictions include errors."""
    # 3 predictions for r.write, 2 correct and 1 wrong, all above threshold
    preds = [
        p(1, "r.write", [5.0, 0.0, 0.0, 0.0]),  # correct
        p(2, "r.write", [5.0, 0.0, 0.0, 0.0]),  # correct
        p(3, "r.read", [5.0, 0.0, 0.0, 0.0]),  # wrong (pred says r.write, true is r.read)
    ]
    report = evaluate(preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety=set())
    # All 3 are above threshold 0.5, so precision_at_threshold = 2/3
    assert report.per_intent["r.write"].precision_at_threshold == 2.0 / 3.0


def test_actions_from_other_zero_when_injection_below_threshold() -> None:
    """Injection kind predictions below threshold should not count in actions_from_other."""
    preds = [
        p(1, "other", [0.3, 0.0, 0.0, 0.0], kind="injection"),  # below threshold
    ]
    # Threshold 0.5 means it won't be auto-routed
    report = evaluate(preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety=set())
    # Below threshold injection should not count
    assert report.actions_from_other == 0


def test_actions_from_other_counts_injection_above_threshold() -> None:
    """Injection kind predictions above threshold and routed to acting intent count."""
    preds = [
        p(1, "other", [6.0, 0.0, 0.0, 0.0], kind="injection"),  # above threshold, routed to r.write
    ]
    # Threshold 0.5 means it will be auto-routed to r.write (acting intent)
    report = evaluate(preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety=set())
    # Above-threshold injection should count as actions_from_other
    assert report.actions_from_other == 1
