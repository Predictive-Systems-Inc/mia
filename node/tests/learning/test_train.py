import hashlib
import shutil
from pathlib import Path

import pytest

from mia.settings import get_settings

pytestmark = pytest.mark.learning
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
    assert card.labels[-1] == "other" and set(card.thresholds) == {"tiny.absence", "tiny.visits"}
    assert (folder / "reports" / f"{card.version}.md").exists()
    assert card.slots == {"partial_day": ["none"]}
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
    assert [g.shape for g in got] == [(3, len(card.labels)), (3, 4), (3, 1)]
    get_settings.cache_clear()
