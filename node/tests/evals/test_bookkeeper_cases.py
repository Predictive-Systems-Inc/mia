"""The bookkeeper eval set is well formed (offline; the real-Jev run is
test_bookkeeper_evals.py)."""

import datetime as dt
from collections import Counter
from pathlib import Path

import pytest

from mia.agents.bookkeeper import words
from mia.agents.bookkeeper.actions import ACTIONS, CATEGORIES, PETTY, PROVIDERS
from mia.agents.parsing import find_tender
from tests.conftest import BK_TODAY
from tests.evals.bookkeeper_cases import CASES, GATED_LANGS, SCENARIOS, TODAY

INPUTS = {
    "cash_count": {"amount"},
    "settlement": {"amount", "provider"},
    "payout": {"amount", "provider"},
    "expense": {"amount", "category"},
    "deposit": {"amount"},
}


def test_ten_cases_per_language_and_scenario_split_by_seed() -> None:
    """Per language and scenario: five tune and five gate seeds; security is tune-only, four
    per language."""
    counts = Counter((c.lang, c.scenario, c.half) for c in CASES if c.scenario != "security")
    halves = ("tune", "gate")
    assert set(counts) == {(lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in halves}
    assert set(counts.values()) == {5}
    security = Counter((c.lang, c.half) for c in CASES if c.scenario == "security")
    assert security == {(lang, "tune"): 4 for lang in GATED_LANGS}


def test_no_text_appears_in_both_halves_and_no_pair_repeats() -> None:
    sets = {h: {c.text.casefold().strip() for c in CASES if c.half == h} for h in ("tune", "gate")}
    assert not sets["tune"] & sets["gate"], sets["tune"] & sets["gate"]
    pairs = [(c.lang, c.text) for c in CASES]
    assert len(pairs) == len(set(pairs)), Counter(pairs).most_common(3)


def test_the_actions_are_the_planned_ones() -> None:
    planned = {action for action, _, _ in SCENARIOS.values()} | {"reply_only", "expense"}
    assert {c.expected_action for c in CASES} == planned
    assert planned <= set(ACTIONS)


def test_no_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_expected_inputs_and_roles() -> None:
    owner_asks = {"journal", "tax_quarter", "profit"}
    for c in CASES:
        want = INPUTS.get(c.expected_action, set())
        if c.expected_action == "petty_cash":
            want = {"amount", "kind"} | ({"category"} if c.expected["kind"] == "spend" else set())
            assert c.expected["kind"] in PETTY, c
        assert set(c.expected) == want, c
        assert c.role == ("owner" if c.expected_action in owner_asks else "supervisor"), c
        assert c.expected.get("category", "utilities") in CATEGORIES, c
        assert not c.previous, c


def test_amounts_and_providers_are_candidates() -> None:
    """Code reads every value Jev picks (rule 7): the expected amount is a words.amounts
    candidate and the expected provider is the tender word the text names."""
    for c in CASES:
        if "amount" in c.expected:
            assert c.expected["amount"] in words.amounts(c.text, c.lang).values(), c
        if "provider" in c.expected:
            assert c.expected["provider"] in PROVIDERS, c
            assert find_tender(c.text) == c.expected["provider"], c


def test_the_run_day_is_the_bk_fixtures_tuesday() -> None:
    assert TODAY == BK_TODAY and TODAY.weekday() == 1


def test_scoring() -> None:
    """Right needs the action and its inputs; another input is a wrong write."""
    from tests.evals.test_bookkeeper_evals import _score

    base = {"error": None, "missing": None, "confidence": 0.9}
    count = base | {"expected_action": "cash_count", "action": "cash_count"}
    count |= {"expected": {"amount": 1245000}, "args": {"counted": 1245000}}
    assert _score(count) == "right"
    assert _score(count | {"args": {"counted": 1254000}}) == "wrong"
    assert _score(count | {"missing": "amount"}) == "ask"
    assert _score(count | {"action": "clarify"}) == "ask"
    assert _score(count | {"action": "deposit"}) == "wrong"
    assert _score(count | {"action": "deposit", "confidence": 0.5}) == "other"
    assert _score(count | {"error": "boom"}) == "other"
    settle = base | {"expected_action": "settlement", "action": "settlement"}
    settle |= {"expected": {"amount": 321000, "provider": "gcash"}}
    assert _score(settle | {"args": {"amount": 321000, "provider": "gcash"}}) == "right"
    assert _score(settle | {"args": {"amount": 321000, "provider": "maya"}}) == "wrong"
    petty = base | {"expected_action": "petty_cash", "action": "petty_cash"}
    petty |= {"expected": {"amount": 200000, "kind": "refill"}}
    assert (
        _score(petty | {"args": {"amount": 200000, "kind": "refill", "category": "x"}}) == "right"
    )
    assert _score(petty | {"args": {"amount": 200000, "kind": "spend"}}) == "wrong"
    profit = base | {"expected_action": "profit", "action": "profit", "expected": {}}
    assert _score(profit | {"args": {"month": dt.date(2026, 10, 1)}}) == "right"


def test_the_halves_are_selected_by_name() -> None:
    from tests.evals.test_bookkeeper_evals import _selected

    assert {c.half for c in _selected(CASES, "tune")} == {"tune"}
    assert {c.half for c in _selected(CASES, "gate")} == {"gate"}


def test_the_raw_report_is_named_by_local_minute_and_never_overwritten(tmp_path: Path) -> None:
    from tests.evals.test_bookkeeper_evals import _report_path

    now = dt.datetime(2026, 10, 21, 9, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    path = _report_path(now, tmp_path)
    assert path == tmp_path / "bookkeeper-2026-10-21-0905.raw.json"
    path.write_text("{}")
    with pytest.raises(FileExistsError, match="bookkeeper-2026-10-21-0905"):
        _report_path(now, tmp_path)
