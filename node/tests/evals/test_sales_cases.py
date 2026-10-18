"""The sales supervisor eval set is well formed (offline; the real-Jev run is
test_sales_supervisor_evals.py)."""

from collections import Counter

from mia.agents.sales_supervisor.actions import ACTIONS, menu_tokens, pre_parse
from mia.templates.retail.seed import ITEMS as MENU
from tests.evals.sales_cases import CASES, GATED_LANGS, SCENARIOS


def test_ten_cases_per_language_scenario_and_half() -> None:
    counts = Counter((c.lang, c.scenario, c.half) for c in CASES)
    assert set(counts) == {
        (lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in ("tune", "gate")
    }
    assert set(counts.values()) == {10}


def test_no_text_appears_in_both_halves() -> None:
    """The gate half is fresh: none of its texts (casefolded) is in the tune half."""
    tune = {c.text.casefold().strip() for c in CASES if c.half == "tune"}
    gate = {c.text.casefold().strip() for c in CASES if c.half == "gate"}
    assert not tune & gate, tune & gate


def test_expected_actions_are_actions_and_counts_name_items() -> None:
    for c in CASES:
        assert c.expected_action in ACTIONS, c
        assert bool(c.expected_items) == (c.expected_action in ("report_sales", "correct_sales"))


# Words in the cases that name an item but are no name word or short code: Jev maps them.
SYNONYMS = {"Box of 4": {"boxes", "kahon"}}


def test_counts_parse_to_the_expected_groups() -> None:
    """Code splits the numbers (rule 7): each count case gives one group per expected item, in
    order, with the expected quantity and a word of that item (a name word or a short code); a
    correction gives exactly one group, the new quantity."""
    tokens = menu_tokens((name, codes) for name, codes, _ in MENU)
    of_item = {
        name: menu_tokens([(name, codes)]) | SYNONYMS.get(name, set()) for name, codes, _ in MENU
    }
    for c in CASES:
        if c.expected_action not in ("report_sales", "correct_sales"):
            continue
        groups, _ = pre_parse(c.text, tokens)
        assert len(groups) == len(c.expected_items), c
        for group, (item, quantity) in zip(groups, c.expected_items, strict=True):
            assert group.quantity == quantity, c
            assert of_item[item] & set(group.words.split()), (c, group)


def test_why_answers_follow_the_why_question() -> None:
    assert all(c.previous for c in CASES if c.expected_action == "why_answer")


def test_no_tagalog_and_balanced_halves() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)
    halves = Counter((c.lang, c.scenario, c.half) for c in CASES)
    for lang in GATED_LANGS:
        for s in SCENARIOS:
            assert abs(halves[(lang, s, "tune")] - halves[(lang, s, "gate")]) <= 1
