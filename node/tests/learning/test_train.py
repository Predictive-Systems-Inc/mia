import hashlib
import shutil
from pathlib import Path

import pytest

from mia.settings import get_settings

pytestmark = [
    pytest.mark.learning,
    pytest.mark.filterwarnings(
        "ignore:You are using the legacy TorchScript-based ONNX export:DeprecationWarning",
        "ignore:The feature will be removed:DeprecationWarning",
        "ignore:Converting a tensor to a Python boolean:torch.jit.TracerWarning",
        "ignore:Exporting aten:UserWarning",
    ),
]
BASE = "optimum-intel-internal-testing/tiny-random-xlm-roberta"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "role_tiny" / "skill"


def test_tiny_role_trains_packages_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path / "models"))
    get_settings.cache_clear()
    from mia.learning.train import train_role

    folder = tmp_path / "skill"
    shutil.copytree(FIXTURE, folder)
    card = train_role(folder, seeds=(0,), epochs=1)
    out = tmp_path / "models" / "tiny" / card.version
    assert (
        (out / "model.onnx").exists()
        and (out / "tokenizer.json").exists()
        and (out / "card.json").exists()
    )
    assert card.labels[-1] == "other" and set(card.thresholds) == set(card.labels) - {"other"}
    assert "conversation.greeting" in card.thresholds
    assert (folder / "reports" / f"{card.version}.md").exists()
    assert card.slots == {"partial_day": ["morning", "none"]}
    assert set(card.artifacts) == {"model.onnx", "tokenizer.json"}
    for name, digest in card.artifacts.items():
        assert digest == hashlib.sha256((out / name).read_bytes()).hexdigest()
    from mia.learning.package import read_card

    assert read_card("tiny", card.version).artifacts == card.artifacts

    import numpy as np
    import onnxruntime as ort

    sess = ort.InferenceSession(str(out / "model.onnx"))
    assert [o.name for o in sess.get_outputs()] == [
        "intent_logits",
        "lang_logits",
        "slot_partial_day_logits",
    ]
    ids = np.ones((3, 7), dtype=np.int64)
    got = sess.run(None, {"input_ids": ids, "attention_mask": np.ones_like(ids)})
    assert [g.shape for g in got] == [(3, len(card.labels)), (3, 4), (3, 2)]
    get_settings.cache_clear()


def test_slot_targets_ignore_missing_and_unknown() -> None:
    from mia.learning.schema import Record
    from mia.learning.train import IGNORE, slot_targets

    def rec(slots: dict[str, str]) -> Record:
        return Record(
            id="x", role="t", intent="other", lang="en", text="hi", counterpart="c",
            style="terse", split="train", source="t", slots=slots,
        )  # fmt: skip

    batch = [rec({"p": "morning"}), rec({}), rec({"p": "evening"}), rec({"p": "none"})]
    assert slot_targets(batch, "p", ["morning", "none"]) == [0, IGNORE, IGNORE, 1]
    assert IGNORE == -100


def test_existing_version_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime as dt
    import types

    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path / "models"))
    get_settings.cache_clear()
    from mia.learning import train

    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz: dt.tzinfo | None = None) -> "Clock":
            return cls(2026, 1, 2, 3, 4, tzinfo=tz)

    monkeypatch.setattr(train, "dt", types.SimpleNamespace(datetime=Clock, UTC=dt.UTC))
    existing = tmp_path / "models" / "tiny" / "v202601020304"
    existing.mkdir(parents=True)
    (existing / "model.onnx").write_bytes(b"keep")
    folder = tmp_path / "skill"
    shutil.copytree(FIXTURE, folder)
    with pytest.raises(FileExistsError, match="tiny@v202601020304"):
        train.train_role(folder, seeds=(0,), epochs=1)
    assert (existing / "model.onnx").read_bytes() == b"keep"
    assert sorted(p.name for p in existing.iterdir()) == ["model.onnx"]
    get_settings.cache_clear()


def test_onnx_matches_torch_on_padded_context_batch(tmp_path: Path) -> None:
    import numpy as np
    import onnxruntime as ort
    import torch
    from transformers import AutoTokenizer

    from mia.learning import train
    from mia.learning.schema import Record

    tok = AutoTokenizer.from_pretrained(BASE)
    slots = {"partial_day": ["morning", "none"]}
    torch.manual_seed(0)
    model = train.Heads(BASE, 3, slots)
    batch = [
        Record(
            id="a", role="t", intent="other", lang="en", text="sick today", context="you: hi",
            counterpart="c", style="terse", split="train", source="t",
        ),
        Record(
            id="b", role="t", intent="other", lang="fi",
            text="oon kipee tänään enkä pääse töihin ollenkaan",
            context="sinä: huomenta, mitä kuuluu",
            counterpart="c", style="terse", split="train", source="t",
        ),
    ]  # fmt: skip
    enc = train._encode(tok, batch)
    assert enc["attention_mask"].sum(1).unique().numel() == 2  # really padded
    train._export(model, tok, tmp_path, slots)
    model.eval()
    with torch.no_grad():
        want = model(**enc)[0].numpy()
    sess = ort.InferenceSession(str(tmp_path / "model.onnx"))
    got = sess.run(
        ["intent_logits"],
        {"input_ids": enc["input_ids"].numpy(), "attention_mask": enc["attention_mask"].numpy()},
    )[0]
    assert float(np.abs(got - want).max()) < 1e-4
