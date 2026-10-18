"""The sales supervisor eval set is well formed (offline; the real-Jev run is
test_sales_supervisor_evals.py)."""

from collections import Counter

from mia.agents.sales_supervisor.actions import ACTIONS, pre_parse
from tests.evals.sales_cases import CASES, GATED_LANGS, SCENARIOS


def test_ten_cases_per_language_and_scenario() -> None:
    counts = Counter((c.lang, c.scenario) for c in CASES)
    assert set(counts) == {(lang, s) for lang in GATED_LANGS for s in SCENARIOS}
    assert set(counts.values()) == {10}


def test_expected_actions_are_actions_and_counts_name_items() -> None:
    for c in CASES:
        assert c.expected_action in ACTIONS, c
        assert bool(c.expected_items) == (c.expected_action in ("report_sales", "correct_sales"))


def test_counts_parse_to_the_expected_quantities() -> None:
    """Code splits the numbers (rule 7): each count case's groups carry the expected quantities
    in order, and a correction's first group carries the new quantity."""
    for c in CASES:
        groups, _ = pre_parse(c.text)
        quantities = [g.quantity for g in groups]
        if c.expected_action == "report_sales":
            assert quantities == [q for _, q in c.expected_items], c
        elif c.expected_action == "correct_sales":
            assert quantities[:1] == [c.expected_items[0][1]], c


def test_why_answers_follow_the_why_question() -> None:
    assert all(c.previous for c in CASES if c.expected_action == "why_answer")


def test_no_tagalog_and_balanced_halves() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)
    halves = Counter((c.lang, c.scenario, c.half) for c in CASES)
    for lang in GATED_LANGS:
        for s in SCENARIOS:
            assert abs(halves[(lang, s, "tune")] - halves[(lang, s, "gate")]) <= 1
