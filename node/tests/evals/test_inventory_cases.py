"""The inventory manager eval set is well formed (offline; the real-Jev run is
test_inventory_manager_evals.py)."""

from collections import Counter

from mia.agents.inventory_manager.actions import ACTIONS
from mia.agents.parsing import menu_tokens, pre_parse, strip_times
from mia.templates.retail.seed import INGREDIENTS, ITEMS
from tests.evals.inventory_manager_cases import CASES, GATED_LANGS, SCENARIOS, SYNONYMS

ROWS = [(name, codes) for name, codes, *_ in ITEMS] + [(n, c) for n, c, *_ in INGREDIENTS]
NAMES = {name for name, _ in ROWS}
COUNTED = ("report_stock", "place_order", "receive")


def test_ten_cases_per_language_scenario_and_half() -> None:
    counts = Counter((c.lang, c.scenario, c.half) for c in CASES)
    assert set(counts) == {
        (lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in ("tune", "gate")
    }
    assert set(counts.values()) == {10}


def test_no_text_appears_in_both_halves() -> None:
    tune = {c.text.casefold().strip() for c in CASES if c.half == "tune"}
    gate = {c.text.casefold().strip() for c in CASES if c.half == "gate"}
    assert not tune & gate, tune & gate


def test_no_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_expected_actions_kinds_and_names() -> None:
    for c in CASES:
        assert c.expected_action in ACTIONS, c
        assert bool(c.expected_items) == (c.expected_action in COUNTED), c
        assert bool(c.expected_kind) == (c.expected_action == "report_stock"), c
        assert {name for name, _ in c.expected_items} <= NAMES, c


def test_counts_parse_to_the_expected_groups() -> None:
    """Code splits the numbers (rule 7): a counted case gives one group per expected pair, in
    order, with its quantity and a word of that item; a pair without a quantity is a message
    with no number (Jev's `item` question), so exactly one pair and no group."""
    tokens = menu_tokens(ROWS)
    words = {name: menu_tokens([(name, codes)]) | SYNONYMS.get(name, set()) for name, codes in ROWS}
    for c in CASES:
        if c.expected_action not in COUNTED:
            continue
        groups, _ = pre_parse(strip_times(c.text), tokens)  # as build_query
        if c.expected_items[0][1] is None:
            assert len(c.expected_items) == 1 and not groups, (c, groups)
            continue
        assert len(groups) == len(c.expected_items), (c, groups)
        for group, (name, quantity) in zip(groups, c.expected_items, strict=True):
            assert group.quantity == quantity, (c, group)
            assert words[name] & set(group.words.split()), (c, group)


def test_scoring() -> None:
    """The harness scoring offline: a waste without a reason is right when Mia asks it, a
    guessed reason or another item is a wrong write, a sure other action is wrong."""
    from tests.evals.test_inventory_manager_evals import _score

    base = {"error": None, "expected_action": "report_stock", "expected_kind": "waste"}
    base |= {"expected_items": [("Ube", 4)], "expected_missing": "reason", "confidence": 0.9}
    asked = base | {"action": "clarify", "raw_action": "report_stock", "missing": "reason"}
    asked |= {"found_kind": "waste", "found_items": [("Ube", 4)]}
    assert _score(asked) == "right"
    assert _score(asked | {"confidence": 0.5}) == "ask"
    assert _score(asked | {"action": "report_stock", "missing": None}) == "wrong_items"
    assert _score(asked | {"found_items": [("Classic", 4)]}) == "wrong_items"
    assert _score(asked | {"missing": "item_0"}) == "ask"
    other = asked | {"action": "place_order", "raw_action": "place_order", "missing": None}
    assert _score(other) == "wrong"
    assert _score(asked | {"error": "boom"}) == "other"
