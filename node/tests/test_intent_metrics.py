"""The intent catalogue, the English intent dataset and the classification metrics (no model)."""

import re
from typing import get_args

import pytest

from mia.agents.dispatcher.agent import AGENT_DIR
from mia.agents.dispatcher.classifier import IntentName
from tests.evals.intents import (
    CATALOGUE_PATH,
    CONVERSATION,
    OTHER,
    ROLES,
    STYLES,
    Example,
    Result,
    catalogue_yaml,
    load_catalogue,
    load_dataset,
    macro_f1,
    parse_capabilities,
    report,
)

CATALOGUE = load_catalogue()
DATASET = load_dataset(lang="en")


def _result(gold: str, predicted: str, confidence: float = 0.9, role: str = "cleaner") -> Result:
    example = Example(
        id=f"{gold}/en/001", intent=gold, lang="en", text="x", role=role, style="terse"
    )
    return Result(example, predicted, confidence, 1.0)


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
    assert report([_result("hr.payslip", "conversation.greeting")], CATALOGUE)["invalid"] == 0
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
    for i in CATALOGUE.values():
        assert (i.label_en is not None) == i.by_message, i.id
        assert i.label_en is None or 0 < len(i.label_en) <= 20, i.id


def test_catalogue_yaml_is_generated_from_capabilities_md() -> None:
    expected = catalogue_yaml(parse_capabilities())
    assert CATALOGUE_PATH.read_text("utf-8") == expected, (
        "run: uv run python -m tests.evals.intents"
    )


def test_every_message_intent_has_15_messages_and_a_stratified_test_split() -> None:
    for intent in (i for i in CATALOGUE.values() if i.by_message):
        rows = [e for e in DATASET if e.intent == intent.id]
        assert sum(1 for e in rows if not e.negative_of) >= 15, intent.id
        tested = sum(1 for e in rows if e.split == "test")
        assert abs(tested - 0.3 * len(rows)) <= 1, intent.id


def test_examples_are_consistent_with_the_catalogue() -> None:
    labels = CATALOGUE.keys() | CONVERSATION.keys() | {OTHER}
    for e in DATASET:
        assert e.intent in CONVERSATION or e.intent == OTHER or CATALOGUE[e.intent].by_message, e
        assert e.id.startswith(f"{e.intent}/{e.lang}/"), e
        assert e.role in ROLES and e.style in STYLES, e
        assert e.intent not in CATALOGUE or e.role in CATALOGUE[e.intent].roles, e
        assert e.negative_of is None or e.negative_of in labels, e
        assert e.negative_of != e.intent, e
    assert len({e.id for e in DATASET}) == len(DATASET)
    assert sum(e.kind == "injection" for e in DATASET) >= 30
    assert sum(1 for e in DATASET if e.negative_of) >= 200
    share = sum(e.split == "test" for e in DATASET) / len(DATASET)
    assert 0.27 <= share <= 0.33


def test_dataset_does_not_copy_the_prompt_examples() -> None:
    quoted = re.findall(r'"([^"]+)"', (AGENT_DIR / "prompts" / "base.md").read_text("utf-8"))
    texts = {e.text.lower().strip() for e in DATASET}
    assert quoted and not texts & {q.lower().strip() for q in quoted}
    assert len(texts) == len(DATASET), "duplicate messages"
