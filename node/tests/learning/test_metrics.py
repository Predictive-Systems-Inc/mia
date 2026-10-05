import math

from mia.learning.metrics import (
    EvalReport,
    Prediction,
    choose_thresholds,
    evaluate,
    expected_calibration_error,
    fit_temperature,
    softmax,
)
from mia.learning.schema import IntentSpec, RoleSpec, Targets

LABELS = ["r.write", "r.read", "conversation.emergency", "other"]
CONV = {"conversation.emergency": "emergency"}
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
    thr = choose_thresholds(preds, ROLE, 1.0, CONV)
    above = [x for x in preds if softmax(x.logits)[0] >= thr["r.write"]]
    assert all(x.intent == "r.write" for x in above)
    only_wrong = [p(i, "r.read", [5, 0, 0, 0]) for i in range(5)]
    assert choose_thresholds(only_wrong, ROLE, 1.0, CONV)["r.write"] > 1.0


def test_evaluate_counts_actions_from_other_and_safety_recall() -> None:
    preds = [
        p(1, "r.write", [6, 0, 0, 0]),
        p(2, "other", [6, 0, 0, 0], kind="injection"),  # routed to a template action: bad
        p(3, "conversation.emergency", [0, 0, 6, 0], kind="safety"),
        p(4, "r.read", [0, 6, 0, 0], lang="fi"),
    ]
    report = evaluate(
        preds,
        ROLE,
        {"r.write": 0.5, "r.read": 0.5},
        1.0,
        safety={"conversation.emergency"},
        conversation=CONV,
    )
    assert report.actions_from_other == 1
    assert report.safety_recall == 1.0
    assert report.false_emergency == 0.0
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
    thr = choose_thresholds(preds, ROLE, 1.0, CONV)
    # With 99% precision target for write, we can't accept both at the tie
    assert thr["r.write"] > 1.0  # unreachable when all predictions have same confidence

    # Stricter case: require accepting only when precision can be met
    preds2 = [
        p(1, "r.write", [2.0, 0.0, 0.0, 0.0]),  # correct
        p(2, "r.write", [2.0, 0.0, 0.0, 0.0]),  # correct
        p(3, "r.read", [1.0, 0.0, 0.0, 0.0]),  # wrong
    ]
    thr2 = choose_thresholds(preds2, ROLE, 1.0, CONV)
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
    report = evaluate(
        preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety=set(), conversation=CONV
    )
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

    report = evaluate(
        preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, t, safety=set(), conversation=CONV
    )
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
    report = evaluate(
        preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety=set(), conversation=CONV
    )
    # All 3 are above threshold 0.5, so precision_at_threshold = 2/3
    assert report.per_intent["r.write"].precision_at_threshold == 2.0 / 3.0


def test_actions_from_other_zero_when_injection_below_threshold() -> None:
    """Injection kind predictions below threshold should not count in actions_from_other."""
    preds = [
        p(1, "other", [0.3, 0.0, 0.0, 0.0], kind="injection"),  # below threshold
    ]
    # Threshold 0.5 means it won't be auto-routed
    report = evaluate(
        preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety=set(), conversation=CONV
    )
    # Below threshold injection should not count
    assert report.actions_from_other == 0


def test_actions_from_other_counts_injection_above_threshold() -> None:
    """Injection kind predictions above threshold and routed to acting intent count."""
    preds = [
        p(1, "other", [6.0, 0.0, 0.0, 0.0], kind="injection"),  # above threshold, routed to r.write
    ]
    # Threshold 0.5 means it will be auto-routed to r.write (acting intent)
    report = evaluate(
        preds, ROLE, {"r.write": 0.5, "r.read": 0.5}, 1.0, safety=set(), conversation=CONV
    )
    # Above-threshold injection should count as actions_from_other
    assert report.actions_from_other == 1


GREET_LABELS = ["r.write", "r.read", "conversation.greeting", "other"]
AT_09 = [0.0, 0.0, math.log(27.0), 0.0]  # greeting top at exactly 27 / 30 = 0.9


def g(i: int, intent: str, kind: str = "normal") -> Prediction:
    return Prediction(
        record_id=str(i),
        intent=intent,
        lang="en",
        kind=kind,
        style="informal",
        labels=GREET_LABELS,
        logits=AT_09,
    )


def test_template_conversation_intent_gets_threshold_and_counts_as_action() -> None:
    conf = softmax(AT_09)[2]
    assert math.isclose(conf, 0.9)
    template = {"conversation.greeting": "template"}
    thr = choose_thresholds([g(1, "conversation.greeting")], ROLE, 1.0, template)
    assert thr == {"r.write": 1.01, "r.read": 1.01, "conversation.greeting": conf}
    preds = [g(1, "conversation.greeting"), g(2, "other", kind="injection")]
    report = evaluate(preds, ROLE, thr, 1.0, safety=set(), conversation=template)
    assert report.coverage == 1.0
    assert report.actions_from_other == 1
    brief = {"conversation.greeting": "model_brief"}
    assert evaluate(preds, ROLE, thr, 1.0, safety=set(), conversation=brief).actions_from_other == 0


def test_conversation_precision_target_follows_handling() -> None:
    """19 of 20 right is precision 0.95: enough to read (0.95), not to act (0.99)."""
    dev = [g(i, "conversation.greeting") for i in range(19)] + [g(19, "other")]
    conf = softmax(AT_09)[2]
    read = choose_thresholds(dev, ROLE, 1.0, {"conversation.greeting": "model_brief"})
    act = choose_thresholds(dev, ROLE, 1.0, {"conversation.greeting": "template"})
    assert read["conversation.greeting"] == conf
    assert act["conversation.greeting"] == 1.01
    just_below = dev[:18] + [g(18, "other"), g(19, "other")]  # 18 / 20 = 0.90 < 0.95
    assert (
        choose_thresholds(just_below, ROLE, 1.0, {"conversation.greeting": "kb_company"})[
            "conversation.greeting"
        ]
        == 1.01
    )
    assert "other" not in read


SAFETY = {"conversation.emergency", "conversation.chemical_exposure"}
SAFE_LABELS = [
    "r.write",
    "r.read",
    "conversation.greeting",
    "conversation.thanks",
    "conversation.emergency",
    "conversation.chemical_exposure",
    "other",
]
# Two safety labels at 0.12 each under a 0.3 role argmax: mass 0.24.
SPREAD = [math.log(x) for x in (0.3, 0.115, 0.115, 0.115, 0.12, 0.12, 0.115)]
# One safety label as argmax at 0.19, the other near zero: mass 0.19.
ALONE = [math.log(x) for x in (0.162, 0.162, 0.162, 0.162, 0.19, 1e-30, 0.162)]


def s(i: int, intent: str, logits: list[float]) -> Prediction:
    return Prediction(
        record_id=str(i),
        intent=intent,
        lang="en",
        kind="safety" if intent in SAFETY else "normal",
        style="informal",
        labels=SAFE_LABELS,
        logits=logits,
    )


def floor_role(floor: float) -> RoleSpec:
    return ROLE.model_copy(update={"targets": Targets(safety_floor=floor)})


def safety_report(preds: list[Prediction], floor: float = 0.2) -> EvalReport:
    return evaluate(preds, floor_role(floor), {}, 1.0, SAFETY, conversation={})


def test_safety_recall_uses_safety_mass_against_the_floor() -> None:
    assert softmax(SPREAD)[0] == max(softmax(SPREAD))
    assert softmax(ALONE)[4] == max(softmax(ALONE))
    preds = [
        s(1, "conversation.emergency", SPREAD),  # mass 0.24 >= 0.2: recalled
        s(2, "conversation.chemical_exposure", ALONE),  # mass 0.19 < 0.2: missed
        s(3, "r.write", SPREAD),  # false emergency
        s(4, "r.read", ALONE),
        s(5, "other", ALONE),
    ]
    report = safety_report(preds)
    assert report.safety_recall == 0.5
    assert report.false_emergency == 1 / 3


def test_safety_floor_boundary() -> None:
    probs = softmax(SPREAD)
    mass = probs[4] + probs[5]
    row = [s(1, "conversation.emergency", SPREAD)]
    assert safety_report(row, floor=mass).safety_recall == 1.0
    assert safety_report(row, floor=mass + 1e-6).safety_recall == 0.0


def test_no_safety_rows_means_recall_zero() -> None:
    report = safety_report([s(1, "r.write", SPREAD), s(2, "r.read", ALONE)])
    assert report.safety_recall == 0.0
    assert report.false_emergency == 0.5
