"""Run a promoted package on the CPU (onnxruntime); about 20 ms per message."""

import numpy as np
import onnxruntime
from tokenizers import Tokenizer

from mia.learning.package import ModelCard, package_dir, verify_artifacts
from mia.skills.runtime import Classification, ScoredClassifier


class OnnxClassifier(ScoredClassifier):
    """Classifier over a package whose model and tokenizer match the card's sha256 digests."""

    def __init__(self, card: ModelCard, safety: set[str]) -> None:
        """Raises ValueError naming the file when a file or digest is missing or differs, before
        any model is loaded."""
        super().__init__(card, safety)
        verify_artifacts(card)
        folder = package_dir(card.role, card.version)
        self.session = onnxruntime.InferenceSession(
            str(folder / "model.onnx"), providers=["CPUExecutionProvider"]
        )
        # Truncation (max 96, pinned at export) and padding come from tokenizer.json.
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.outputs = [o.name for o in self.session.get_outputs()]

    def classify(self, text: str, context: str = "") -> Classification:
        """Training always encodes (text, context) as a pair, even with empty context; so do we."""
        enc = self.tokenizer.encode(text, context)
        feeds = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }
        values = dict(zip(self.outputs, self.session.run(self.outputs, feeds), strict=True))
        slots = {
            name.removeprefix("slot_").removesuffix("_logits"): v[0].tolist()
            for name, v in values.items()
            if name.startswith("slot_")
        }
        return self.from_logits(
            values["intent_logits"][0].tolist(), values["lang_logits"][0].tolist(), slots
        )
