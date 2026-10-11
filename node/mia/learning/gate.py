"""Promotion gate (spec section 6). A failure is a normal result with reasons, not an exception."""

from pydantic import BaseModel, Field

from mia.learning.metrics import EvalReport
from mia.learning.schema import RoleSpec

TOLERANCE = 0.005  # regression noise allowed against the active version
EPS = 1e-9  # epsilon for float comparisons to avoid precision issues


class GateResult(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


def check_gate(report: EvalReport, role: RoleSpec, previous: EvalReport | None) -> GateResult:
    t = role.targets
    fails: list[str] = []
    for intent in role.intents:
        score = report.per_intent.get(intent.id)
        if score is None or score.support == 0:
            fails.append(f"precision: {intent.id} has no test records")
            continue
        need = t.precision_for(intent)
        if score.precision_at_threshold < need - EPS:
            fails.append(f"precision: {intent.id} {score.precision_at_threshold:.3f} < {need}")
    if report.coverage < t.coverage - EPS:
        fails.append(f"coverage: {report.coverage:.2f} < {t.coverage}")
    if report.per_lang:
        best = max(report.per_lang.values())
        for lang, acc in report.per_lang.items():
            if best - acc > t.language_gap + EPS:
                fails.append(
                    f"language: {lang} {acc:.3f} more than {t.language_gap} below best {best:.3f}"
                )
    # Check for languages in role but missing from report
    for lang in role.languages:
        if lang not in report.per_lang:
            fails.append(f"language: {lang} has no test records")
    if report.safety_recall < t.safety_recall - EPS:
        fails.append(f"safety: recall {report.safety_recall:.3f} < {t.safety_recall}")
    if report.actions_from_other:
        fails.append(
            f"other: {report.actions_from_other} out-of-scope or injection messages would act"
        )
    if report.ece > t.ece + EPS:
        fails.append(f"calibration: ECE {report.ece:.3f} > {t.ece}")
    if previous is not None:
        for lang, acc in previous.per_lang.items():
            if report.per_lang.get(lang, 0.0) < acc - TOLERANCE - EPS:
                fails.append(
                    f"regression: language {lang} worse than active "
                    f"({report.per_lang.get(lang, 0.0):.3f} < {acc:.3f})"
                )
        for iid, old in previous.per_intent.items():
            new = report.per_intent.get(iid)
            if new is not None and new.f1 < old.f1 - TOLERANCE - EPS:
                fails.append(
                    f"regression: intent {iid} worse than active (F1 {new.f1:.3f} < {old.f1:.3f})"
                )
    return GateResult(passed=not fails, failures=fails)
