"""The intent catalogue, the English intent dataset and the classification metrics (no model)."""

import re
from collections import Counter
from typing import get_args

import pytest

from mia.agents.dispatcher.agent import AGENT_DIR
from mia.agents.dispatcher.classifier import IntentName
from tests.evals.intents import (
    OTHER,
    ROLES,
    Example,
    Result,
    load_catalogue,
    load_dataset,
    macro_f1,
    report,
)

CATALOGUE = load_catalogue()
DATASET = load_dataset()


def _result(gold: str, predicted: str, confidence: float = 0.9, role: str = "cleaner") -> Result:
    return Result(Example(intent=gold, role=role, text="x"), predicted, confidence, 1.0)


def test_macro_f1() -> None:
    assert macro_f1([("a", "a"), ("b", "b")]) == 1.0
    # a: tp 1, fn 1 -> 2/3; b: tp 1, fp 1 -> 2/3
    assert macro_f1([("a", "a"), ("a", "b"), ("b", "b")]) == pytest.approx(0.6667, abs=1e-4)
    assert macro_f1([("a", "b")]) == 0.0
    assert macro_f1([]) == 0.0


def test_report() -> None:
    results = [
        _result("dispatcher.report_absence", "dispatcher.report_absence", 0.95),
        _result("dispatcher.report_absence", "dispatcher.absence_scope", 0.9),
        _result("hr.payslip", "hr.payslip", 0.5, role="office"),
        _result("hr.payslip", "made.up", 0.85, role="office"),
    ]
    rep = report(results, CATALOGUE)
    assert rep["n"] == 4 and rep["accuracy"] == 0.5
    assert rep["area_accuracy"] == 0.75  # absence_scope is still the dispatcher
    assert rep["invalid"] == 1
    assert rep["by_area"]["dispatcher"] == {"n": 2, "correct": 1, "accuracy": 0.5}
    assert rep["by_role"]["office"]["correct"] == 1
    assert rep["confusions"][0][2] == 1 and len(rep["confusions"]) == 2
    assert rep["calibration"]["confident_share"] == 0.75
    assert rep["calibration"]["confident_accuracy"] == pytest.approx(1 / 3, abs=1e-4)
    assert rep["latency_s"]["mean"] == 1.0
    assert [w[0] for w in rep["weakest_intents"]] == ["dispatcher.report_absence", "hr.payslip"]


def test_catalogue_has_the_built_dispatcher_intents_exactly() -> None:
    built = {i.id for i in CATALOGUE.values() if i.agent == "dispatcher" and i.built == "yes"}
    assert built == {f"dispatcher.{n}" for n in get_args(IntentName) if n != OTHER}
    assert 150 <= len(CATALOGUE) <= 250


def test_every_message_intent_has_8_to_12_messages() -> None:
    primary = Counter(e.intent for e in DATASET if not e.near)
    for intent in (i for i in CATALOGUE.values() if i.by_message):
        assert 8 <= primary[intent.id] <= 12, intent.id
        tested = sum(1 for e in DATASET if e.intent == intent.id and e.split == "test")
        assert tested >= 2, intent.id


def test_examples_are_consistent_with_the_catalogue() -> None:
    for e in DATASET:
        assert e.intent == OTHER or CATALOGUE[e.intent].by_message, e
        assert e.role in ROLES, e
        assert e.intent == OTHER or e.role in CATALOGUE[e.intent].roles, e
        assert e.near is None or e.near in CATALOGUE or e.near == OTHER, e
        assert e.split in ("train", "test") and e.kind in (None, "injection"), e
    assert sum(e.kind == "injection" for e in DATASET) >= 15
    assert sum(1 for e in DATASET if e.near) >= 100
    share = sum(e.split == "test" for e in DATASET) / len(DATASET)
    assert 0.25 <= share <= 0.35


def test_dataset_does_not_copy_the_prompt_examples() -> None:
    quoted = re.findall(r'"([^"]+)"', (AGENT_DIR / "prompts" / "base.md").read_text("utf-8"))
    texts = {e.text.lower().strip() for e in DATASET}
    assert quoted and not texts & {q.lower().strip() for q in quoted}
    assert len(texts) == len(DATASET), "duplicate messages"
