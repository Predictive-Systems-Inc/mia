"""Nearest-examples classifier on the node: embed the message, compare with the package's
example matrix, score each label by its k most similar examples (spec embedding review 4B)."""

import json

import numpy as np
import onnxruntime
from tokenizers import Tokenizer

from mia.learning.package import ModelCard, package_dir, verify_artifacts
from mia.skills.runtime import Classification, ScoredClassifier, embed_text

SCALE = 20.0  # cosine to logit scale, so the card's temperature grid (0.5 to 5) fits


def knn_logits(sims: np.ndarray, example_labels: np.ndarray, n_labels: int, k: int) -> list[float]:
    """Per label: SCALE x mean of its k most similar examples; -SCALE for labels without one.
    A label with fewer than k examples is scored by the mean of fewer, higher similarities and
    is slightly favoured."""
    out = np.full(n_labels, -SCALE, dtype=np.float64)
    for label in np.unique(example_labels):
        top = np.sort(sims[example_labels == label])[::-1][:k]
        out[int(label)] = SCALE * float(top.mean())
    return [float(x) for x in out]


class KnnClassifier(ScoredClassifier):
    """Embedding model plus example matrix whose files match the card's digests."""

    def __init__(self, card: ModelCard, safety: set[str]) -> None:
        """Raises ValueError naming the file when a file or digest is missing or differs, before
        any model is loaded."""
        super().__init__(card, safety)
        verify_artifacts(card)
        folder = package_dir(card.role, card.version)
        self.session = onnxruntime.InferenceSession(
            str(folder / "model.onnx"), providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.examples = np.load(folder / "examples.npy")
        meta = json.loads((folder / "examples.json").read_text(encoding="utf-8"))
        self.example_labels = np.array(meta["labels"])
        self.k = int(meta["k"])

    def embed(self, text: str) -> np.ndarray:
        """One unit-length float32 row for the already prefixed text."""
        enc = self.tokenizer.encode(text)
        feeds = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }
        return np.asarray(self.session.run(["embedding"], feeds)[0][0], dtype=np.float32)

    def classify(self, text: str, context: str = "") -> Classification:
        """Scores labels from the examples; no language or slot heads, so both stay empty."""
        v = self.embed(embed_text(self.card.prefix, text, context))
        logits = knn_logits(self.examples @ v, self.example_labels, len(self.card.labels), self.k)
        return self.from_logits(logits, [], {})
