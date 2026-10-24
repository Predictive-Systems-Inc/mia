"""Embedding contenders for the bake-off (spec embedding review section 4); learning group."""

import datetime as dt
import json
import random
import statistics
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from mia.learning import catalogue
from mia.learning.bakeoff import choose_winner, render_bakeoff
from mia.learning.embed import Embedder, export
from mia.learning.metrics import Prediction
from mia.learning.package import ModelCard
from mia.learning.pairs import triplets
from mia.learning.schema import OTHER, Record, load_role
from mia.learning.train import load_splits, new_package_dir, new_version, package, train_role
from mia.skills.knn import KnnClassifier, knn_logits
from mia.skills.onnx import OnnxClassifier
from mia.skills.runtime import embed_text

# Tests only: a tiny embedding model for every contender (encoder base model included).
# Production leaves it None and uses role.yaml (embedding_model) and the encoder's default.
EMBEDDING_OVERRIDE: str | None = None


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

    dev_preds, test_preds = preds(dev), preds(test)  # before the version dir exists
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
        dev_preds=dev_preds,
        test_preds=test_preds,
        curve={},
        out=out,
        version=version,
        with_real=with_real,
    )


class _Classify(nn.Module):  # type: ignore[misc,unused-ignore]  # Any when torch is not installed
    """Tuned pooled encoder plus linear head: (input_ids, attention_mask) -> intent logits."""

    def __init__(self, pooled: nn.Module, head: nn.Module) -> None:
        super().__init__()
        self.pooled = pooled
        self.head = head

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        logits: torch.Tensor = self.head(self.pooled(input_ids, attention_mask))
        return logits


def train_contrastive(
    folder: Path,
    embedding_model: str | None = None,
    steps: int = 200,
    head_epochs: int = 50,
    seed: int = 0,
    with_real: bool = False,
) -> ModelCard:
    """SetFit method without the library: triplet fine-tune of the embedding model on train,
    then a linear head on the frozen tuned embeddings. One output, intent_logits. Tuning stops
    early (or is skipped) when no triplet exists, for example a role with one labelled intent.
    Records whose intent left the label space count as other."""
    role, train, dev, test = load_splits(folder, with_real)
    labels = role.label_space([c.id for c in catalogue.conversation_intents()])
    name = embedding_model or role.embedding_model
    emb = Embedder(name)
    rng = random.Random(seed)
    torch.manual_seed(seed)
    by_label: dict[str, list[str]] = {}
    for r in train:  # Embedder.encode adds the prefix, as embed_text(card.prefix, ...) does
        by_label.setdefault(_label(r, labels), []).append(embed_text("", r.text, r.context))
    opt = torch.optim.AdamW(emb.model.parameters(), lr=2e-5)
    loss_fn = nn.TripletMarginWithDistanceLoss(
        distance_function=lambda a, b: 1 - nn.functional.cosine_similarity(a, b), margin=0.3
    )
    emb.model.train()
    for _ in range(steps):
        batch = triplets(by_label, 16, rng)
        if not batch:
            break
        a, p, n = (emb.model(**emb.encode(list(col))) for col in zip(*batch, strict=True))
        loss = loss_fn(a, p, n)
        opt.zero_grad()
        loss.backward()
        opt.step()
    emb.model.eval()
    index = {label: i for i, label in enumerate(labels)}

    def vectors(rs: list[Record]) -> torch.Tensor:
        return torch.from_numpy(emb([embed_text("", r.text, r.context) for r in rs]))

    x = vectors(train)
    y = torch.tensor([index[_label(r, labels)] for r in train])
    head = nn.Linear(x.shape[1], len(labels))
    hopt = torch.optim.Adam(head.parameters(), lr=1e-2)
    for _ in range(head_epochs):
        hl = nn.functional.cross_entropy(head(x), y)
        hopt.zero_grad()
        hl.backward()  # type: ignore[no-untyped-call,unused-ignore]
        hopt.step()
    head.eval()

    def preds(rs: list[Record]) -> list[Prediction]:
        with torch.no_grad():
            logits = head(vectors(rs))
        return [
            Prediction(
                record_id=r.id,
                intent=_label(r, labels),
                lang=r.lang,
                kind=r.kind,
                style=r.style,
                labels=labels,
                logits=row.tolist(),
            )
            for r, row in zip(rs, logits, strict=True)
        ]

    dev_preds, test_preds = preds(dev), preds(test)  # before the version dir exists
    version = new_version("contrastive")
    out = new_package_dir(role.id, version)
    export(_Classify(emb.model, head), emb.tok, out, output="intent_logits")
    return package(
        folder=folder,
        role=role,
        kind="contrastive",
        base=name,
        prefix=emb.prefix,
        labels=labels,
        slots={},
        train=train,
        dev=dev,
        test=test,
        dev_preds=dev_preds,
        test_preds=test_preds,
        curve={},
        out=out,
        version=version,
        with_real=with_real,
    )


def _latency_ms(card: ModelCard, texts: list[str]) -> float:
    """Median ms per classify over up to 20 texts through the node's runtime class; nan if none."""
    clf = KnnClassifier(card, set()) if card.kind == "knn" else OnnxClassifier(card, set())
    times = []
    for t in texts[:20]:
        start = time.perf_counter()
        clf.classify(t)
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times) if times else float("nan")


def bakeoff(
    folder: Path, encoder_epochs: int = 20, contrastive_steps: int = 200
) -> tuple[list[ModelCard], ModelCard | None]:
    """Trains the encoder, nearest-examples and contrastive contenders on the same splits and
    writes reports/bakeoff-<UTC>.md. Returns the cards in that order and the winner. Promotes
    nothing."""
    role = load_role(folder / "role.yaml")
    model = EMBEDDING_OVERRIDE or role.embedding_model
    cards = [
        train_role(
            folder,
            base_model=EMBEDDING_OVERRIDE,
            epochs=encoder_epochs,
            seeds=(0,) if EMBEDDING_OVERRIDE else (0, 1, 2),
        ),
        train_knn(folder, embedding_model=model),
        train_contrastive(folder, embedding_model=model, steps=contrastive_steps),
    ]
    has_slots = any(i.slots for i in role.intents)
    winner = choose_winner(cards, role_has_slots=has_slots)
    _, _, _, test = load_splits(folder)
    latency = {c.version: _latency_ms(c, [r.text for r in test]) for c in cards}
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")
    (folder / "reports").mkdir(exist_ok=True)
    (folder / "reports" / f"bakeoff-{stamp}.md").write_text(
        render_bakeoff(cards, winner, latency, role_has_slots=has_slots), encoding="utf-8"
    )
    return cards, winner
