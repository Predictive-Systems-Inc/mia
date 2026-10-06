import hashlib
import shutil
from pathlib import Path

import pytest
from sqlmodel import Session

from mia.core.models import Actor, Person
from mia.learning.package import ModelCard, promote, write_card
from mia.settings import get_settings
from mia.skills.onnx import OnnxClassifier
from mia.skills.runtime import NullClassifier, get_classifier, health, reset_classifiers
from tests.learning.helpers import card as make_card

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "role_tiny" / "skill"
sha = lambda b: hashlib.sha256(b).hexdigest()


def _package(artifacts: dict[str, str]) -> ModelCard:
    card = make_card().model_copy(update={"artifacts": artifacts})
    folder = get_settings().MIA_MODELS_DIR / "r" / "v1"
    write_card(card)
    (folder / "model.onnx").write_bytes(b"not a model")
    (folder / "tokenizer.json").write_bytes(b"{}")
    return card


def test_wrong_hash_is_refused_before_loading_and_falls_back() -> None:
    reset_classifiers()
    card = _package({"model.onnx": sha(b"other"), "tokenizer.json": sha(b"{}")})
    with pytest.raises(ValueError, match=r"^model\.onnx: sha256 does not match card artifacts$"):
        OnnxClassifier(card, safety=set())
    (get_settings().MIA_MODELS_DIR / "r" / "ACTIVE").write_text("v1")
    assert isinstance(get_classifier("r"), NullClassifier)
    h = health()["r"]
    assert h["status"] == "fallback"
    assert h["error"] == "ValueError: model.onnx: sha256 does not match card artifacts"


def test_tokenizer_hash_mismatch_names_the_tokenizer() -> None:
    card = _package({"model.onnx": sha(b"not a model"), "tokenizer.json": sha(b"x")})
    with pytest.raises(ValueError, match=r"^tokenizer\.json: sha256 does not match"):
        OnnxClassifier(card, safety=set())


@pytest.mark.parametrize("artifacts", [{}, {"model.onnx": sha(b"not a model")}])
def test_missing_digest_is_refused(artifacts: dict[str, str]) -> None:
    card = _package(artifacts)
    missing = "model.onnx" if not artifacts else "tokenizer.json"
    with pytest.raises(ValueError, match=rf"^{missing}: no sha256 in card artifacts$"):
        OnnxClassifier(card, safety=set())


@pytest.mark.learning
@pytest.mark.filterwarnings(
    "ignore:You are using the legacy TorchScript-based ONNX export:DeprecationWarning",
    "ignore:The feature will be removed:DeprecationWarning",
    "ignore:Converting a tensor to a Python boolean:torch.jit.TracerWarning",
    "ignore:Exporting aten:UserWarning",
)
def test_trained_package_classifies_on_cpu_with_pair_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: Session, people: dict[str, Person]
) -> None:
    import numpy as np

    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path / "models"))
    get_settings.cache_clear()
    reset_classifiers()
    from mia.learning.train import train_role

    folder = tmp_path / "skill"
    shutil.copytree(FIXTURE, folder)
    card = train_role(folder, seeds=(0,), epochs=1)
    promote(session, Actor.person(people["Helena"]), "tiny", card.version, signed_by="test")
    clf = get_classifier("tiny")
    assert isinstance(clf, OnnxClassifier)
    text = "oon kipee tänään"
    c = clf.classify(text)
    assert c.version == card.version and c.intent in card.labels
    assert c.band in ("high", "medium", "low") and c.lang in ("en", "fi", "fil", "mixed")
    assert health()["tiny"]["status"] == "active"

    # Parity with training: same input_ids as the pair-encoded HF tokenizer, same logits.
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(card.base_model)
    hf = tok([text], [""], truncation=True, max_length=96, padding=True, return_tensors="np")
    assert clf.tokenizer.truncation is not None
    assert clf.tokenizer.truncation["max_length"] == 96
    enc = clf.tokenizer.encode(text, "")
    assert enc.ids == hf["input_ids"][0].tolist()
    assert enc.ids != clf.tokenizer.encode(text).ids
    feeds = {
        "input_ids": hf["input_ids"].astype(np.int64),
        "attention_mask": hf["attention_mask"].astype(np.int64),
    }
    logits = clf.session.run(["intent_logits"], feeds)[0][0].tolist()
    from mia.learning.metrics import softmax

    expected = softmax(logits, card.temperature)
    assert c.confidence == pytest.approx(max(expected), abs=1e-6)
    get_settings.cache_clear()


def test_contrastive_cards_encode_one_joined_text() -> None:
    import numpy as np

    seen: list[tuple[str, ...]] = []

    class Tok:
        def encode(self, *texts: str) -> object:
            seen.append(texts)
            return type("E", (), {"ids": [0, 1], "attention_mask": [1, 1]})()

    class Sess:
        def run(self, names: list[str], feeds: dict[str, object]) -> list[object]:
            return [np.array([[2.0, 0.0, 0.0]])]

    clf = object.__new__(OnnxClassifier)
    clf.card = make_card().model_copy(
        update={
            "kind": "contrastive",
            "prefix": "query: ",
            "labels": ["r.a", "conversation.greeting", "other"],
            "thresholds": {"r.a": 0.5},
        }
    )
    clf.safety = set()
    clf.tokenizer = Tok()  # type: ignore[assignment]
    clf.session = Sess()  # type: ignore[assignment]
    clf.outputs = ["intent_logits"]
    c = clf.classify("hi", "ctx")
    assert seen == [("query: hi\nctx",)]
    assert c.intent == "r.a" and c.lang is None
