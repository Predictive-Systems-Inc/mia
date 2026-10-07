"""Embedding contenders for the bake-off (spec embedding review section 4); learning group."""

import json
from pathlib import Path

import numpy as np

from mia.learning import catalogue
from mia.learning.embed import Embedder, export
from mia.learning.metrics import Prediction
from mia.learning.package import ModelCard
from mia.learning.schema import OTHER, Record
from mia.learning.train import load_splits, new_package_dir, new_version, package
from mia.skills.knn import knn_logits
from mia.skills.runtime import embed_text


def _label(r: Record, labels: list[str]) -> str:
    return r.intent if r.intent in labels else OTHER


def train_knn(
    folder: Path, embedding_model: str | None = None, k: int = 3, with_real: bool = False
) -> ModelCard:
    """Frozen embeddings of the train records as the example matrix; no slots, no language.
    Records whose intent left the label space count as other."""
    role, train, dev, test = load_splits(folder, with_real)
    labels = role.label_space([c.id for c in catalogue.conversation_intents()])
    name = embedding_model or role.embedding_model
    emb = Embedder(name)

    def vectors(rs: list[Record]) -> np.ndarray:
        return emb([embed_text("", r.text, r.context) for r in rs])  # Embedder adds the prefix

    x = vectors(train)
    index = {label: i for i, label in enumerate(labels)}
    ex_labels = np.array([index[_label(r, labels)] for r in train])

    def preds(rs: list[Record]) -> list[Prediction]:
        return [
            Prediction(
                record_id=r.id,
                intent=_label(r, labels),
                lang=r.lang,
                kind=r.kind,
                style=r.style,
                labels=labels,
                logits=knn_logits(x @ v, ex_labels, len(labels), k),
            )
            for r, v in zip(rs, vectors(rs), strict=True)
        ]

    version = new_version("knn")
    out = new_package_dir(role.id, version)
    export(emb.model, emb.tok, out)
    np.save(out / "examples.npy", x.astype(np.float32))
    (out / "examples.json").write_text(
        json.dumps({"labels": ex_labels.tolist(), "k": k}), encoding="utf-8"
    )
    return package(
        folder=folder,
        role=role,
        kind="knn",
        base=name,
        prefix=emb.prefix,
        labels=labels,
        slots={},
        train=train,
        dev=dev,
        test=test,
        dev_preds=preds(dev),
        test_preds=preds(test),
        curve={},
        out=out,
        version=version,
    )
