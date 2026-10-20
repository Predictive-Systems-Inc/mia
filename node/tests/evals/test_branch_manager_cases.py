"""The branch manager eval set is well formed (offline; the real-Jev run is
test_branch_manager_evals.py)."""

import datetime as dt
from collections import Counter
from itertools import combinations
from pathlib import Path

import pytest

from mia.agents.branch_manager.actions import ACTIONS, KINDS, code_candidates
from mia.agents.branch_manager.tips import STRATEGIES
from mia.agents.parsing import find_dates, find_prices
from mia.templates.retail.models import RetailItem
from mia.templates.retail.seed import ITEMS
from tests.conftest import BM_TODAY
from tests.evals.branch_manager_cases import CASES, GATED_LANGS, SCENARIOS, TODAY

NAMES = {name.casefold() for name, _, _ in ITEMS}
MENU = [RetailItem(name=n, short_codes=c, price=p, currency="PHP") for n, c, p in ITEMS]
HALVES = ("tune", "spent", "gate")
STRATEGY_NAMES = {key.rsplit(".", 1)[1] for key, *_ in STRATEGIES}
WRITES = {
    "how_to_sell": {"item"},
    "propose_experiment": {"item", "price", "kind", "strategy"},
    "change_price": {"item", "price"},
    "set_short_code": {"item", "code"},
    "decide_experiment_result": {"keep"},
}


def test_ten_cases_per_language_scenario_and_half() -> None:
    """Per language and scenario: ten seeds (five tune, five in the spent gate half of run 1)
    and five fresh gate seeds."""
    counts = Counter((c.lang, c.scenario, c.half) for c in CASES)
    assert set(counts) == {(lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in HALVES}
    assert set(counts.values()) == {5}


def test_no_text_appears_in_both_halves() -> None:
    """The tune half, the spent gate half and the fresh gate half share no text (casefolded)."""
    sets = {h: {c.text.casefold().strip() for c in CASES if c.half == h} for h in HALVES}
    for a, b in combinations(HALVES, 2):
        assert not sets[a] & sets[b], (a, b, sets[a] & sets[b])


def test_no_pair_repeats_and_the_actions_are_the_planned_ones() -> None:
    pairs = [(c.lang, c.text) for c in CASES]
    assert len(pairs) == len(set(pairs)), Counter(pairs).most_common(3)
    planned = set(WRITES) | {"coaching_who", "weekly_summary", "monthly_letter"}
    assert {c.expected_action for c in CASES} == planned
    assert planned <= set(ACTIONS)


def test_no_tagalog_and_no_bibingka_as_an_item() -> None:
    """Filipino, never Tagalog; items as clerks type them, never "bibingka" alone."""
    assert not any("tagalog" in c.text.casefold() for c in CASES)
    assert not any("bibingka" in c.text.casefold() for c in CASES)


def test_expected_inputs_and_roles() -> None:
    for c in CASES:
        assert set(c.expected) == WRITES.get(c.expected_action, set()), c
        assert c.role in {"clerk", "supervisor", "owner"}, c
        assert (c.role == "clerk") == (c.expected_action == "how_to_sell"), c
        if "item" in c.expected:
            assert c.expected["item"].casefold() in NAMES, c
            assert c.expected["item"].casefold() in c.text.casefold(), c
        if "kind" in c.expected:
            assert c.expected["kind"] in set(KINDS), c
            assert c.expected["strategy"] in STRATEGY_NAMES | {""}, c
        assert bool(c.previous) == (c.expected_action == "decide_experiment_result"), c


def test_every_strategy_and_kind_has_a_typed_experiment() -> None:
    experiments = [c.expected for c in CASES if c.expected_action == "propose_experiment"]
    assert {e["strategy"] for e in experiments} == STRATEGY_NAMES | {""}
    assert {e["kind"] for e in experiments} == {"price", "promo", "bundle"}


def test_prices_dates_and_codes_are_candidates() -> None:
    """Code reads every value Jev picks (rule 7): the expected price is a find_prices candidate,
    a price change names a find_dates day, and the short code is build_query's first word."""
    for c in CASES:
        if "price" in c.expected:
            assert c.expected["price"] in dict(find_prices(c.text, c.lang)).values(), c
        if c.expected_action == "change_price":
            assert find_dates(c.text, TODAY, c.lang), c
        if "code" in c.expected:
            assert code_candidates(c.text, MENU)[:1] == [c.expected["code"]], c


def test_the_run_day_is_the_bm_fixtures_monday() -> None:
    assert TODAY == BM_TODAY and TODAY.weekday() == 0


def test_scoring() -> None:
    """Right needs the action and its inputs; another input is a wrong write."""
    from tests.evals.test_branch_manager_evals import _score

    base = {"error": None, "missing": None, "confidence": 0.9}
    propose = base | {"expected_action": "propose_experiment", "action": "propose_experiment"}
    propose |= {"expected": {"item": "Classic", "price": 3900, "kind": "price", "strategy": ""}}
    good = propose | {"item": "Classic", "args": {"item_id": "i1", "to_price": 3900}}
    assert _score(good) == "right"
    assert _score(good | {"args": {"item_id": "i1", "to_price": 5000}}) == "wrong"
    assert _score(good | {"item": "Ube"}) == "wrong"
    assert _score(good | {"item": None, "args": {}}) == "ask"
    assert _score(good | {"missing": "price"}) == "ask"
    assert _score(good | {"action": "clarify"}) == "ask"
    assert _score(good | {"action": "change_price"}) == "wrong"
    assert _score(good | {"action": "change_price", "confidence": 0.5}) == "other"
    assert _score(good | {"error": "boom"}) == "other"
    keep = base | {"expected_action": "decide_experiment_result"}
    keep |= {"action": "decide_experiment_result", "expected": {"keep": False}, "item": None}
    assert _score(keep | {"args": {"keep": False}}) == "right"
    assert _score(keep | {"args": {"keep": True}}) == "wrong"
    code = base | {"expected_action": "set_short_code", "action": "set_short_code"}
    code |= {"expected": {"item": "Kape", "code": "kp"}, "item": "Kape"}
    assert _score(code | {"args": {"item_id": "k", "code": "kp"}}) == "right"
    assert _score(code | {"args": {"item_id": "k", "code": "add"}}) == "wrong"
    weekly = base | {"expected_action": "weekly_summary", "action": "weekly_summary"}
    assert _score(weekly | {"expected": {}, "args": {}, "item": None}) == "right"


def test_the_halves_are_selected_by_name_and_the_spent_half_never() -> None:
    from tests.evals.test_branch_manager_evals import _selected

    assert {c.half for c in _selected(CASES, "tune")} == {"tune"}
    assert {c.half for c in _selected(CASES, "gate")} == {"gate"}
    assert not any(c.half == "spent" for c in _selected(CASES, "tune,gate,spent"))


def test_the_raw_report_is_named_by_local_minute_and_never_overwritten(tmp_path: Path) -> None:
    from tests.evals.test_branch_manager_evals import _report_path

    now = dt.datetime(2026, 10, 20, 23, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    path = _report_path(now, tmp_path)
    assert path == tmp_path / "branch-manager-2026-10-20-2305.raw.json"
    path.write_text("{}")
    with pytest.raises(FileExistsError, match="branch-manager-2026-10-20-2305"):
        _report_path(now, tmp_path)
