# node/tests/skills/test_runtime.py
import sys
from types import SimpleNamespace

import pytest

from mia.learning.gate import GateResult
from mia.learning.metrics import EvalReport
from mia.learning.package import ModelCard, write_card
from mia.settings import get_settings
from mia.skills.runtime import (
    NullClassifier,
    ScoredClassifier,
    get_classifier,
    health,
    reset_classifiers,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_classifiers()


def card(**over: object) -> ModelCard:
    rep = EvalReport(
        accuracy=1,
        macro_f1=1,
        coverage=1,
        ece=0,
        per_intent={},
        per_lang={},
        safety_recall=1,
        actions_from_other=0,
        confusions=[],
    )
    base = ModelCard(
        role="r",
        version="v1",
        base_model="m",
        data_hash="h",
        temperature=1.0,
        medium_floor=0.35,
        safety_floor=0.2,
        labels=["r.a", "r.b", "conversation.emergency", "other"],
        langs=["en", "fi"],
        slots={},
        thresholds={"r.a": 0.8, "r.b": 0.8},
        report=rep,
        gate=GateResult(passed=True),
    )
    return base.model_copy(update=over)


def test_no_package_means_null_classifier() -> None:
    c = get_classifier("dispatcher").classify("im sick")
    assert (c.intent, c.band, c.version) == ("other", "low", None)
    assert isinstance(get_classifier("dispatcher"), NullClassifier)


def test_corrupt_package_falls_back_and_health_says_so() -> None:
    root = get_settings().MIA_MODELS_DIR / "r"
    root.mkdir(parents=True)
    (root / "ACTIVE").write_text("v9")
    assert isinstance(get_classifier("r"), NullClassifier)
    assert health()["r"]["status"] == "fallback"


def test_bands_from_card() -> None:
    sc = ScoredClassifier(card(), safety={"conversation.emergency"})
    high = sc.from_logits([6, 0, 0, 0], [3, 0], {})
    medium = sc.from_logits([1.2, 1.0, 0, 0], [3, 0], {})
    low = sc.from_logits([0.1, 0.1, 0.1, 0.1], [3, 0], {})
    assert (high.band, medium.band, low.band) == ("high", "medium", "low")
    assert [a.intent for a in medium.alternatives][:2] == ["r.a", "r.b"]
    assert high.lang == "en"
    alarm = sc.from_logits([2, 0, 1.5, 0], [3, 0], {})
    assert alarm.safety >= 0.2


def test_valid_card_without_onnx_module_falls_back() -> None:
    write_card(card())
    (get_settings().MIA_MODELS_DIR / "r" / "ACTIVE").write_text("v1")
    assert isinstance(get_classifier("r"), NullClassifier)
    h = health()["r"]
    assert (h["status"], h["version"]) == ("fallback", "v1")
    assert "mia.skills.onnx" in str(h["error"])


def test_health_error_does_not_leak_the_models_path() -> None:
    write_card(card())
    pkg = get_settings().MIA_MODELS_DIR / "r" / "v1"
    (pkg / "card.json").write_text("{bad", encoding="utf-8")
    (get_settings().MIA_MODELS_DIR / "r" / "ACTIVE").write_text("v1")
    get_classifier("r")
    error = str(health()["r"]["error"])
    assert str(get_settings().MIA_MODELS_DIR) not in error
    assert error.startswith("ValidationError: ")


def test_status_none_and_reset() -> None:
    get_classifier("dispatcher")
    assert health() == {"dispatcher": {"status": "none", "version": None}}
    reset_classifiers()
    assert health() == {}


def two(threshold: float, floor: float) -> ScoredClassifier:
    c = card(labels=["r.a", "other"], thresholds={"r.a": threshold}, medium_floor=floor)
    return ScoredClassifier(c, safety=set())


def test_threshold_boundaries() -> None:
    # equal logits give confidence exactly 0.5
    assert two(0.5, 0.35).from_logits([0, 0], [], {}).band == "high"
    assert two(0.5 + 1e-6, 0.35).from_logits([0, 0], [], {}).band == "medium"
    assert two(0.9, 0.5).from_logits([0, 0], [], {}).band == "medium"
    assert two(0.9, 0.5 + 1e-6).from_logits([0, 0], [], {}).band == "low"


def test_other_is_never_medium_and_not_an_alternative() -> None:
    c = two(0.9, 0.35).from_logits([0, 1], [], {})
    assert (c.intent, c.band, c.alternatives[0].intent) == ("other", "low", "r.a")
    assert len(c.alternatives) == 1


def test_lang_and_slots_and_version() -> None:
    sc = ScoredClassifier(card(slots={"size": ["s", "l"]}), safety=set())
    c = sc.from_logits([6, 0, 0, 0], [0, 3], {"size": [0, 2], "unknown": [1]})
    assert (c.lang, c.slots, c.version) == ("fi", {"size": "l"}, "v1")
    assert sc.from_logits([6, 0, 0, 0], [], {}).lang is None


def test_safety_sums_probability_of_safety_intents() -> None:
    sc = ScoredClassifier(card(), safety={"conversation.emergency", "r.b"})
    c = sc.from_logits([0, 0, 0, 0], [], {})
    assert c.safety == pytest.approx(0.5)


class _Stub(ScoredClassifier):
    pass


def test_active_switch_is_picked_up_without_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    import mia.skills.runtime as rt

    loads: list[str] = []

    def fake_read(role: str, version: str) -> ModelCard:
        loads.append(version)
        return card(version=version)

    monkeypatch.setattr(rt, "read_card", fake_read)
    monkeypatch.setitem(
        sys.modules,
        "mia.skills.onnx",
        SimpleNamespace(OnnxClassifier=_Stub),
    )
    root = get_settings().MIA_MODELS_DIR / "r"
    root.mkdir(parents=True)
    (root / "ACTIVE").write_text("v1")
    first = get_classifier("r")
    assert isinstance(first, _Stub) and first.card.version == "v1"
    assert get_classifier("r") is first and loads == ["v1"]
    (root / "ACTIVE").write_text("v2")
    second = get_classifier("r")
    assert isinstance(second, _Stub) and second.card.version == "v2"
    assert health()["r"] == {"status": "active", "version": "v2"}
    (root / "ACTIVE").write_text("")
    assert isinstance(get_classifier("r"), NullClassifier)
    assert health()["r"] == {"status": "none", "version": None}


def test_broken_active_marker_falls_back() -> None:
    root = get_settings().MIA_MODELS_DIR / "r"
    (root / "ACTIVE").mkdir(parents=True)
    assert isinstance(get_classifier("r"), NullClassifier)
    assert health()["r"]["status"] == "fallback"
    (root / "ACTIVE").rmdir()
    (root / "ACTIVE").write_bytes(b"\xff\xfe")
    assert isinstance(get_classifier("r"), NullClassifier)
    assert health()["r"]["status"] == "fallback"
