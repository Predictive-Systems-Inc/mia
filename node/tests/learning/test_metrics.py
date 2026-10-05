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
    )  # type: ignore[arg-type]


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
