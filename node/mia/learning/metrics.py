"""Calibration, thresholds and evaluation in pure Python (spec section 5, steps 3 and 4)."""

import math
from collections import Counter, defaultdict

from pydantic import BaseModel

from mia.learning.schema import OTHER, RoleSpec


class Prediction(BaseModel):
    record_id: str
    intent: str  # the true label
    lang: str
    kind: str
    style: str
    labels: list[str]
    logits: list[float]


class IntentScore(BaseModel):
    support: int
    precision_at_threshold: float
    recall: float
    f1: float
    auto_share: float


class EvalReport(BaseModel):
    accuracy: float
    macro_f1: float
    coverage: float
    ece: float
    per_intent: dict[str, IntentScore]
    per_lang: dict[str, float]
    safety_recall: float
    false_emergency: float
    actions_from_other: int
    confusions: list[tuple[str, str, int]]


def softmax(logits: list[float], temperature: float = 1.0) -> list[float]:
    scaled = [x / temperature for x in logits]
    top = max(scaled)
    exps = [math.exp(x - top) for x in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def _top(pred: Prediction, temperature: float) -> tuple[str, float]:
    probs = softmax(pred.logits, temperature)
    i = max(range(len(probs)), key=probs.__getitem__)
    return pred.labels[i], probs[i]


def _safety_mass(pred: Prediction, temperature: float, safety: set[str]) -> float:
    """Summed probability of the safety labels, as the runtime computes it."""
    probs = softmax(pred.logits, temperature)
    return sum(pr for label, pr in zip(pred.labels, probs, strict=True) if label in safety)


def fit_temperature(preds: list[Prediction]) -> float:
    """Grid search on dev; NLL of the true label."""

    def nll(t: float) -> float:
        return -sum(
            math.log(max(softmax(p.logits, t)[p.labels.index(p.intent)], 1e-12)) for p in preds
        )

    grid = [0.5 + 0.05 * i for i in range(91)]
    return min(grid, key=nll)


def expected_calibration_error(
    preds: list[Prediction], temperature: float, bins: int = 10
) -> float:
    buckets: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for p in preds:
        label, conf = _top(p, temperature)
        buckets[min(int(conf * bins), bins - 1)].append((conf, label == p.intent))
    n = len(preds) or 1
    return sum(
        len(b) / n * abs(sum(c for c, _ in b) / len(b) - sum(ok for _, ok in b) / len(b))
        for b in buckets.values()
    )


def _targets(role: RoleSpec, conversation: dict[str, str]) -> dict[str, float]:
    """Precision target per label except `other`: role intents by risk; conversation intents
    with template handling act (precision_write), the rest only read (precision_read)."""
    t = role.targets
    out = {i.id: t.precision_for(i) for i in role.intents}
    for cid, handling in conversation.items():
        out[cid] = t.precision_write if handling == "template" else t.precision_read
    return out


def choose_thresholds(
    preds: list[Prediction], role: RoleSpec, temperature: float, conversation: dict[str, str]
) -> dict[str, float]:
    """Lowest confidence per label (role and conversation intents, never `other`) at which
    precision meets the label's target on dev; 1.01 (never automatic) when none does.
    `conversation` maps catalogue id to handling."""
    out: dict[str, float] = {}
    tops = [(_top(p, temperature), p.intent) for p in preds]
    for label, target in _targets(role, conversation).items():
        mine = sorted(((conf, truth) for (top, conf), truth in tops if top == label), reverse=True)
        best = 1.01  # unreachable: never automatic
        correct = 0
        for k, (conf, truth) in enumerate(mine, start=1):
            correct += truth == label
            # Only accept threshold at end of group of equal confidences
            is_end_of_group = k == len(mine) or mine[k][0] != conf
            if correct / k >= target and is_end_of_group:
                best = conf
        out[label] = best
    return out


def evaluate(
    preds: list[Prediction],
    role: RoleSpec,
    thresholds: dict[str, float],
    temperature: float,
    safety: set[str],
    conversation: dict[str, str],
) -> EvalReport:
    """Score the test split once (gate metrics plus confusions). Template conversation intents
    act like role intents that act (`conversation` maps catalogue id to handling)."""
    acting = {i.id for i in role.intents if i.acts} | {
        cid for cid, handling in conversation.items() if handling == "template"
    }
    rows = [(p, *_top(p, temperature)) for p in preds]
    auto = [(p, label) for p, label, conf in rows if conf >= thresholds.get(label, 1.01)]
    per_intent: dict[str, IntentScore] = {}
    for intent in role.intents:
        tp = sum(1 for p, label, _ in rows if label == intent.id and p.intent == intent.id)
        pred_n = sum(1 for _, label, _ in rows if label == intent.id)
        support = sum(1 for p in preds if p.intent == intent.id)
        auto_mine = [p for p, label in auto if label == intent.id]
        precision = (
            (sum(p.intent == intent.id for p in auto_mine) / len(auto_mine)) if auto_mine else 1.0
        )
        recall = tp / support if support else 0.0
        prec_all = tp / pred_n if pred_n else 0.0
        f1 = 2 * prec_all * recall / (prec_all + recall) if prec_all + recall else 0.0
        per_intent[intent.id] = IntentScore(
            support=support,
            precision_at_threshold=precision,
            recall=recall,
            f1=f1,
            auto_share=len(auto_mine) / support if support else 0.0,
        )
    by_lang: dict[str, list[bool]] = defaultdict(list)
    for p, label, _ in rows:
        by_lang[p.lang].append(label == p.intent)
    # Safety as the runtime sees it: summed safety probability against the role's floor.
    floor = role.targets.safety_floor
    alarms = [(p.intent in safety, _safety_mass(p, temperature, safety) >= floor) for p in preds]
    safety_hits = [alarm for is_safety, alarm in alarms if is_safety]
    false_alarms = [alarm for is_safety, alarm in alarms if not is_safety]
    confusions = Counter((p.intent, label) for p, label, _ in rows if label != p.intent)
    # Macro F1: average only intents with support > 0
    f1s_nonzero = [
        per_intent[intent.id].f1 for intent in role.intents if per_intent[intent.id].support > 0
    ]
    return EvalReport(
        accuracy=sum(label == p.intent for p, label, _ in rows) / (len(rows) or 1),
        macro_f1=sum(f1s_nonzero) / (len(f1s_nonzero) or 1),
        coverage=len(auto) / (len(rows) or 1),
        ece=expected_calibration_error(preds, temperature),
        per_intent=per_intent,
        per_lang={k: sum(v) / len(v) for k, v in by_lang.items()},
        safety_recall=sum(safety_hits) / len(safety_hits) if safety_hits else 0.0,
        false_emergency=sum(false_alarms) / len(false_alarms) if false_alarms else 0.0,
        actions_from_other=sum(
            1
            for p, label in auto
            # A correctly classified template reply (e.g. system_probe) is not a misroute.
            if (p.intent == OTHER or p.kind in ("injection", "other"))
            and label in acting
            and label != p.intent
        ),
        confusions=[(a, b, n) for (a, b), n in confusions.most_common(20)],
    )
