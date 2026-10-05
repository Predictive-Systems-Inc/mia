"""Load each role's active model and classify messages (spec section 5, runtime)."""

import logging
from functools import lru_cache
from typing import Literal, Protocol

from pydantic import BaseModel

from mia.learning import catalogue
from mia.learning.metrics import softmax
from mia.learning.package import ModelCard, active_version, read_card

log = logging.getLogger(__name__)
Band = Literal["high", "medium", "low"]


class Alternative(BaseModel):
    intent: str
    confidence: float


class Classification(BaseModel):
    intent: str
    confidence: float
    band: Band
    alternatives: list[Alternative]
    lang: str | None
    slots: dict[str, str]
    safety: float
    version: str | None


class Classifier(Protocol):
    def classify(self, text: str, context: str = "") -> Classification: ...


class NullClassifier:
    """No active package: every message is low band, so the agent runs as it does today."""

    def classify(self, text: str, context: str = "") -> Classification:
        return Classification(
            intent="other",
            confidence=0.0,
            band="low",
            alternatives=[],
            lang=None,
            slots={},
            safety=0.0,
            version=None,
        )


class ScoredClassifier:
    """Turns model scores into a Classification using the card's calibration and thresholds."""

    def __init__(self, card: ModelCard, safety: set[str]) -> None:
        self.card = card
        self.safety = safety

    def from_logits(
        self,
        intent_logits: list[float],
        lang_logits: list[float],
        slot_logits: dict[str, list[float]],
    ) -> Classification:
        c = self.card
        probs = softmax(intent_logits, c.temperature)
        ranked = sorted(zip(c.labels, probs, strict=True), key=lambda x: x[1], reverse=True)
        intent, conf = ranked[0]
        if conf >= c.thresholds.get(intent, 1.01):
            band: Band = "high"
        elif conf >= c.medium_floor and intent != "other":
            band = "medium"
        else:
            band = "low"
        lang_probs = softmax(lang_logits) if lang_logits else []
        lang = (
            c.langs[max(range(len(lang_probs)), key=lang_probs.__getitem__)] if lang_probs else None
        )
        slots = {
            name: c.slots[name][max(range(len(v)), key=v.__getitem__)]
            for name, v in slot_logits.items()
            if name in c.slots and v
        }
        return Classification(
            intent=intent,
            confidence=conf,
            band=band,
            alternatives=[
                Alternative(intent=i, confidence=p) for i, p in ranked[:3] if i != "other"
            ],
            lang=lang,
            slots=slots,
            safety=sum(p for i, p in ranked if i in self.safety),
            version=c.version,
        )


_status: dict[str, dict[str, object]] = {}


@lru_cache
def get_classifier(role: str) -> Classifier:
    """Cached classifier for a role; NullClassifier (with a warning) when none or unusable."""
    version = active_version(role)
    if version is None:
        _status[role] = {"status": "none", "version": None}
        return NullClassifier()
    try:
        card = read_card(role, version)
        # Task 15 adds this module; until then the import fails and we fall back.
        from mia.skills.onnx import (  # type: ignore[import-not-found,import-untyped,unused-ignore]
            OnnxClassifier,
        )

        classifier: Classifier = OnnxClassifier(card, safety=catalogue.safety_ids())
    except Exception as exc:  # noqa: BLE001 - any broken package falls back, never breaks chat
        log.warning("role %s model %s unusable, falling back: %s", role, version, exc)
        _status[role] = {"status": "fallback", "version": version, "error": str(exc)[:200]}
        return NullClassifier()
    _status[role] = {"status": "active", "version": version}
    return classifier


def reset_classifiers() -> None:
    """Drop cached classifiers and status so the next call reloads from disk."""
    get_classifier.cache_clear()
    _status.clear()


def health() -> dict[str, dict[str, object]]:
    """Per role: status none, active or fallback, with the version and any load error."""
    return dict(_status)
