"""Load each role's active model and classify messages (spec section 5, runtime)."""

import importlib
import logging
from functools import lru_cache
from typing import Literal, Protocol

from pydantic import BaseModel

from mia.learning import catalogue
from mia.learning.metrics import softmax
from mia.learning.package import ModelCard, active_version, read_card
from mia.settings import get_settings

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


# ponytail: _status and the lru_cache in _load are not thread-safe. Two threads may load the
# same version twice (harmless: same files, one result kept) and the last status write wins.
# Add a lock if loading ever becomes expensive enough to matter.
_status: dict[str, dict[str, object]] = {}


def _fallback(role: str, version: str | None, exc: Exception) -> Classifier:
    log.warning("role %s model %s unusable, falling back: %s", role, version, exc)
    # /health is readable by anyone who can reach the node: keep absolute paths out of it.
    models_dir = str(get_settings().MIA_MODELS_DIR)
    error = f"{type(exc).__name__}: {str(exc).replace(models_dir, '<models>')}"[:200]
    _status[role] = {"status": "fallback", "version": version, "error": error}
    return NullClassifier()


def embed_text(prefix: str, text: str, context: str) -> str:
    """The single input string of the embedding contenders: prefix, text, then context."""
    return f"{prefix}{text}\n{context}" if context else f"{prefix}{text}"


@lru_cache
def _load(role: str, version: str) -> Classifier:
    """Load one version once; a broken package yields a cached NullClassifier (and a warning)."""
    try:
        card = read_card(role, version)
        if card.kind == "knn":
            # Task 6 adds the module; imported by name so mypy does not need it yet.
            knn = importlib.import_module("mia.skills.knn")
            classifier: Classifier = knn.KnnClassifier(card, safety=catalogue.safety_ids())
            return classifier
        from mia.skills.onnx import OnnxClassifier

        return OnnxClassifier(card, safety=catalogue.safety_ids())
    except Exception as exc:  # noqa: BLE001 - any broken package falls back, never breaks chat
        return _fallback(role, version, exc)


def get_classifier(role: str) -> Classifier:
    """Classifier for the role's current ACTIVE version, read on every call so a promotion made
    by another process takes effect; loaded once per (role, version). NullClassifier (with a
    warning) when there is no active version or the marker or package is unusable."""
    try:
        version = active_version(role)
    except Exception as exc:  # noqa: BLE001 - a broken ACTIVE marker must not break chat
        return _fallback(role, None, exc)
    if version is None:
        _status[role] = {"status": "none", "version": None}
        return NullClassifier()
    classifier = _load(role, version)
    if not isinstance(classifier, NullClassifier):
        _status[role] = {"status": "active", "version": version}
    return classifier


def reset_classifiers() -> None:
    """Drop cached classifiers and status so the next call reloads from disk."""
    _load.cache_clear()
    _status.clear()


def health() -> dict[str, dict[str, object]]:
    """Per role: status none, active or fallback, with the version and any load error."""
    return dict(_status)
