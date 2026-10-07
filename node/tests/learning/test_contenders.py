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
