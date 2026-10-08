import math
from types import SimpleNamespace

import numpy as np
import pytest

from mia.learning.metrics import softmax
from mia.skills.knn import SCALE, KnnClassifier, knn_logits
from tests.learning.helpers import card as make_card


def test_knn_logits_mean_of_top_k_per_label_and_floor_for_missing_labels() -> None:
    sims = np.array([0.9, 0.7, 0.2, 0.8], dtype=np.float32)
    labels = np.array([0, 0, 1, 0])
    out = knn_logits(sims, labels, n_labels=3, k=2)
    assert np.allclose(out, [SCALE * 0.85, SCALE * 0.2, -SCALE])


def test_knn_logits_k_larger_than_examples_uses_all() -> None:
    out = knn_logits(np.array([0.5], dtype=np.float32), np.array([1]), n_labels=2, k=5)
    assert np.allclose(out, [-SCALE, SCALE * 0.5])


def test_knn_cards_join_prefix_and_score_through_from_logits() -> None:
    seen: list[tuple[str, ...]] = []

    class FakeTokenizer:
        def encode(self, *args: str) -> SimpleNamespace:
            seen.append(args)
            return SimpleNamespace(ids=[1, 2], attention_mask=[1, 1])

    class FakeSession:
        def run(self, names: list[str], feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
            assert names == ["embedding"]
            assert feeds["input_ids"].tolist() == [[1, 2]]
            return [np.array([[1.0, 0.0, 0.0]], dtype=np.float32)]

    labels = ["r.a", "conversation.emergency", "other"]
    card = make_card().model_copy(
        update={
            "kind": "knn",
            "prefix": "query: ",
            "labels": labels,
            "temperature": 5.0,
            "thresholds": {"r.a": 0.5},
        }
    )
    clf = object.__new__(KnnClassifier)
    clf.card, clf.safety = card, {"conversation.emergency"}
    clf.tokenizer, clf.session = FakeTokenizer(), FakeSession()  # type: ignore[assignment]
    clf.examples = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    clf.example_labels, clf.k = np.array([0, 1]), 1
    c = clf.classify("hi", "ctx")
    assert seen == [("query: hi\nctx",)]
    probs = softmax(knn_logits(np.array([1.0, 0.0]), np.array([0, 1]), 3, 1), 5.0)
    assert (c.intent, c.band, c.lang, c.version) == ("r.a", "high", None, card.version)
    assert c.confidence == pytest.approx(probs[0])
    assert c.safety == pytest.approx(probs[1])
    # at the threshold is high, just past it is medium
    clf.card = card.model_copy(update={"thresholds": {"r.a": c.confidence}})
    assert clf.classify("hi", "ctx").band == "high"
    clf.card = card.model_copy(update={"thresholds": {"r.a": math.nextafter(c.confidence, 1)}})
    assert clf.classify("hi", "ctx").band == "medium"
