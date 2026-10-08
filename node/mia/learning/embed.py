"""Sentence embeddings (learning group): mean-pooled, unit-length rows; ONNX export for the node."""

from pathlib import Path

import numpy as np
import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer, PreTrainedTokenizerBase

MAX_LEN = 96


def prefix_for(model_name: str) -> str:
    """e5 models expect "query: " before symmetric-task inputs; others take the text as is."""
    return "query: " if "e5" in model_name.lower() else ""


class Pooled(nn.Module):  # type: ignore[misc,unused-ignore]  # Any when torch is not installed
    """Encoder plus attention-masked mean pooling and L2 normalisation."""

    def __init__(self, encoder: nn.Module) -> None:
        super().__init__()
        self.encoder = encoder

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
        mean = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return nn.functional.normalize(mean, dim=-1)


class Embedder:
    """Callable text -> float32 unit rows. Adds the model's prefix to every text."""

    def __init__(self, model_name: str, max_len: int = MAX_LEN) -> None:
        self.tok: PreTrainedTokenizerBase = AutoTokenizer.from_pretrained(model_name)
        encoder = AutoModel.from_pretrained(model_name)
        self.dim = int(encoder.config.hidden_size)
        self.model = Pooled(encoder).eval()
        self.prefix = prefix_for(model_name)
        self.max_len = max_len

    def encode(self, texts: list[str]) -> dict[str, torch.Tensor]:
        enc = self.tok(
            [self.prefix + t for t in texts],
            truncation=True,
            max_length=self.max_len,
            padding=True,
            return_tensors="pt",
        )
        return {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"]}

    def __call__(self, texts: list[str], batch: int = 64) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), batch):
                out.append(self.model(**self.encode(texts[i : i + batch])).numpy())
        return np.concatenate(out).astype(np.float32)


def export(
    model: nn.Module,
    tok: PreTrainedTokenizerBase,
    out: Path,
    output: str = "embedding",
    max_len: int = MAX_LEN,
) -> None:
    """Writes model.onnx (inputs input_ids, attention_mask; one output named `output`) and
    tokenizer.json with truncation pinned at max_len, so the runtime needs neither torch nor
    transformers."""
    out.mkdir(parents=True, exist_ok=True)
    model.eval()
    sample = tok(["hello"], return_tensors="pt")
    torch.onnx.export(
        model,
        (sample["input_ids"], sample["attention_mask"]),
        out / "model.onnx",
        input_names=["input_ids", "attention_mask"],
        output_names=[output],
        dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}},
        opset_version=17,
        dynamo=False,
    )
    backend = getattr(tok, "backend_tokenizer", None)
    if backend is None:
        raise ValueError("embedding model has no fast tokenizer; tokenizer.json cannot be exported")
    backend.enable_truncation(max_length=max_len)
    backend.save(str(out / "tokenizer.json"))
