import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.learning
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "role_tiny" / "skill"
TINY = "optimum-intel-internal-testing/tiny-random-xlm-roberta"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "skill")
    return tmp_path / "skill"


def test_knn_contender_packages_and_classifies(folder: Path) -> None:
    from mia.learning.contenders import train_knn
    from mia.learning.package import package_dir, verify_artifacts
    from mia.skills.knn import KnnClassifier

    card = train_knn(folder, embedding_model=TINY)
    assert card.kind == "knn" and card.version.endswith("-knn") and card.slots == {}
    verify_artifacts(card)
    assert sorted(p.name for p in package_dir("tiny", card.version).iterdir()) == [
        "card.json",
        "examples.json",
        "examples.npy",
        "model.onnx",
        "tokenizer.json",
    ]
    c = KnnClassifier(card, safety=set()).classify("sick today, cant come")
    assert c.intent in card.labels and c.version == card.version
    report = (folder / "reports" / f"{card.version}.md").read_text(encoding="utf-8")
    assert report.splitlines()[2].startswith("Kind: knn. Base model: " + TINY + ". Data hash: ")
    assert "Learning curve" not in report


def test_report_prints_the_curve_only_when_there_is_one(folder: Path) -> None:
    from mia.learning.contenders import train_knn
    from mia.learning.train import _report

    card = train_knn(folder, embedding_model=TINY)
    line = "Learning curve (share of train: test accuracy): 50%: 0.250, 100%: 0.500"
    assert line in _report(card, {50: 0.25, 100: 0.5}).splitlines()
    assert not any(x.startswith("Learning curve") for x in _report(card, {}).splitlines())


def test_stale_intents_score_as_other(folder: Path) -> None:
    from mia.learning.contenders import train_knn

    # One stale record per split: the train index, dev calibration and test scoring all map it.
    for split in ("train", "dev", "test"):
        path = folder / "data" / f"{split}.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        assert '"tiny.absence"' in lines[0]
        lines[0] = lines[0].replace('"tiny.absence"', '"tiny.removed_intent"', 1)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    card = train_knn(folder, embedding_model=TINY)
    assert "tiny.removed_intent" not in card.report.per_intent
    assert all("tiny.removed_intent" not in (a, b) for a, b, _ in card.report.confusions)


def test_versions_differ_per_kind() -> None:
    from mia.learning.train import new_version

    assert new_version("knn").endswith("-knn")
    assert "-" not in new_version()


LONG = "sick today, cant come in, the bus broke down and my kid has a fever as well " * 8
CONTEXT = "Mia: Your next visit is at 9 at the office."


def _spy_logits(clf: object, monkeypatch: pytest.MonkeyPatch) -> list[list[float]]:
    """Records the intent logits each classify call hands to from_logits."""
    seen: list[list[float]] = []
    real = clf.from_logits  # type: ignore[attr-defined]

    def spy(intent: list[float], lang: list[float], slots: dict[str, list[float]]) -> object:
        seen.append(intent)
        return real(intent, lang, slots)

    monkeypatch.setattr(clf, "from_logits", spy)
    return seen


def test_knn_runtime_matches_training_embeddings(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np

    from mia.learning.contenders import train_knn
    from mia.learning.embed import Embedder
    from mia.learning.train import load_splits
    from mia.skills.knn import KnnClassifier, knn_logits
    from mia.skills.runtime import embed_text

    monkeypatch.setattr("mia.learning.embed.prefix_for", lambda _n: "query: ")
    card = train_knn(folder, embedding_model=TINY)
    assert card.prefix == "query: "
    clf = KnnClassifier(card, safety=set())
    emb = Embedder(TINY)
    assert len(emb.tok(embed_text("", LONG, CONTEXT))["input_ids"]) > 96
    v = clf.embed(embed_text(card.prefix, LONG, CONTEXT))
    assert np.allclose(v, emb([embed_text("", LONG, CONTEXT)])[0], atol=1e-5)
    r0 = load_splits(folder)[1][0]
    first = clf.embed(embed_text(card.prefix, r0.text, r0.context))
    assert np.allclose(clf.examples[0], first, atol=1e-5)
    seen = _spy_logits(clf, monkeypatch)
    clf.classify(LONG, CONTEXT)
    assert seen == [knn_logits(clf.examples @ v, clf.example_labels, len(card.labels), clf.k)]


def test_contrastive_contender_packages_and_runs_on_onnx(folder: Path) -> None:
    from mia.learning.contenders import train_contrastive
    from mia.learning.package import package_dir, verify_artifacts
    from mia.skills.onnx import OnnxClassifier

    card = train_contrastive(folder, embedding_model=TINY, steps=4, head_epochs=2)
    assert card.kind == "contrastive" and card.version.endswith("-contrastive")
    assert card.slots == {}
    verify_artifacts(card)
    assert sorted(p.name for p in package_dir("tiny", card.version).iterdir()) == [
        "card.json",
        "model.onnx",
        "tokenizer.json",
    ]
    clf = OnnxClassifier(card, safety=set())
    assert clf.outputs == ["intent_logits"]
    c = clf.classify("sick today, cant come")
    assert c.intent in card.labels and c.lang is None and c.version == card.version


def test_contrastive_onnx_matches_the_torch_head(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np
    import torch

    from mia.learning import contenders
    from mia.skills.onnx import OnnxClassifier
    from mia.skills.runtime import embed_text

    exported: list[tuple[torch.nn.Module, object]] = []
    real_export = contenders.export

    def capture(model: torch.nn.Module, tok: object, out: Path, **kw: object) -> None:
        exported.append((model, tok))
        real_export(model, tok, out, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(contenders, "export", capture)
    monkeypatch.setattr("mia.learning.embed.prefix_for", lambda _n: "query: ")
    card = contenders.train_contrastive(folder, embedding_model=TINY, steps=4, head_epochs=2)
    assert card.prefix == "query: "
    model, tok = exported[0]
    enc = tok(  # type: ignore[operator]
        [embed_text(card.prefix, LONG, CONTEXT)],
        truncation=True,
        max_length=96,
        return_tensors="pt",
    )
    assert enc["input_ids"].shape[1] == 96
    with torch.no_grad():
        expected = model(enc["input_ids"], enc["attention_mask"])[0].numpy()
    clf = OnnxClassifier(card, safety=set())
    seen = _spy_logits(clf, monkeypatch)
    clf.classify(LONG, CONTEXT)
    assert np.allclose(np.array(seen[0]), expected, atol=1e-4)


def test_contrastive_skips_tuning_when_no_triplet_exists(folder: Path) -> None:
    import re

    from mia.learning.contenders import train_contrastive

    # Every train record becomes absence: one labelled intent, so triplets returns [] at once.
    path = folder / "data" / "train.jsonl"
    text = re.sub(r'"intent": "[^"]*"', '"intent": "tiny.absence"', path.read_text("utf-8"))
    path.write_text(text, encoding="utf-8")
    assert set(re.findall(r'"intent": "[^"]*"', text)) == {'"intent": "tiny.absence"'}
    card = train_contrastive(folder, embedding_model=TINY, steps=4, head_epochs=2)
    assert card.kind == "contrastive"


@pytest.mark.parametrize("trainer", ["train_knn", "train_contrastive"])
def test_a_failed_prediction_leaves_no_version_dir(
    folder: Path, monkeypatch: pytest.MonkeyPatch, trainer: str
) -> None:
    from mia.learning import contenders
    from mia.settings import get_settings

    def boom(**_: object) -> None:
        raise RuntimeError("prediction failed")

    monkeypatch.setattr(contenders, "Prediction", boom)
    with pytest.raises(RuntimeError, match="^prediction failed$"):
        kw = {"steps": 4, "head_epochs": 2} if trainer == "train_contrastive" else {}
        getattr(contenders, trainer)(folder, embedding_model=TINY, **kw)
    assert not (get_settings().MIA_MODELS_DIR / "tiny").exists()


def test_bakeoff_trains_three_and_writes_the_report(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.learning import contenders
    from mia.learning.bakeoff import choose_winner, render_bakeoff
    from mia.learning.package import active_version

    timed: list[str] = []
    real_latency = contenders._latency_ms

    def latency(card: object, texts: list[str]) -> float:
        timed.append(card.kind)  # type: ignore[attr-defined]
        assert len(texts) == 14  # every test record of the fixture
        real_latency(card, texts)  # type: ignore[arg-type]
        return 1.0

    monkeypatch.setattr(contenders, "EMBEDDING_OVERRIDE", TINY)  # tiny model in tests
    monkeypatch.setattr(contenders, "_latency_ms", latency)
    cards, winner = contenders.bakeoff(folder, encoder_epochs=1, contrastive_steps=4)
    assert [c.kind for c in cards] == ["encoder", "knn", "contrastive"]
    assert all(c.base_model == TINY for c in cards)
    assert timed == ["encoder", "knn", "contrastive"]
    assert winner is choose_winner(cards, role_has_slots=True)  # the fixture has a slot intent
    reports = list((folder / "reports").glob("bakeoff-*.md"))
    assert len(reports) == 1
    expected = render_bakeoff(cards, winner, {c.version: 1.0 for c in cards}, role_has_slots=True)
    assert reports[0].read_text(encoding="utf-8") == expected
    assert active_version("tiny") is None
