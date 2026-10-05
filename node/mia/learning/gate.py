"""Promotion gate (spec section 6). A failure is a normal result with reasons, not an exception."""

from pydantic import BaseModel, Field

from mia.learning.metrics import EvalReport
from mia.learning.schema import RoleSpec

TOLERANCE = 0.005  # regression noise allowed against the active version


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
        if score.precision_at_threshold < need:
            fails.append(f"precision: {intent.id} {score.precision_at_threshold:.3f} < {need}")
    if report.coverage < t.coverage:
        fails.append(f"coverage: {report.coverage:.2f} < {t.coverage}")
    if report.per_lang:
        best = max(report.per_lang.values())
        for lang, acc in report.per_lang.items():
            if best - acc > t.language_gap:
                fails.append(
                    f"language: {lang} {acc:.3f} more than {t.language_gap} below best {best:.3f}"
                )
    if report.safety_recall < t.safety_recall:
        fails.append(f"safety: recall {report.safety_recall:.3f} < {t.safety_recall}")
    if report.actions_from_other:
        fails.append(
            f"other: {report.actions_from_other} out-of-scope or injection messages would act"
        )
    if report.ece > t.ece:
        fails.append(f"calibration: ECE {report.ece:.3f} > {t.ece}")
    if previous is not None:
        for lang, acc in previous.per_lang.items():
            if report.per_lang.get(lang, 0.0) < acc - TOLERANCE:
                fails.append(
                    f"language {lang} worse than active ({report.per_lang.get(lang, 0.0):.3f} < {acc:.3f})"
                )
        for iid, old in previous.per_intent.items():
            new = report.per_intent.get(iid)
            if new is not None and new.f1 < old.f1 - TOLERANCE:
                fails.append(f"intent {iid} worse than active (F1 {new.f1:.3f} < {old.f1:.3f})")
    return GateResult(passed=not fails, failures=fails)
