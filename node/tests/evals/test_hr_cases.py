"""The hr officer eval set is well formed (offline; the real-Jev run is
test_hr_officer_evals.py)."""

import re
from collections import Counter

from mia.agents.hr_officer.actions import ACTIONS, WHICH
from mia.agents.parsing import find_dates
from tests.evals.hr_officer_cases import CASES, GATED_LANGS, SCENARIOS, TODAY, on

SLOTS = {"file_leave": {"start", "end"}, "holiday_pay": {"day"}, "contributions": {"which"}}
OFFSET = re.compile(r"\+(\d+)d")


def test_ten_cases_per_language_and_scenario_five_per_half() -> None:
    counts = Counter((c.lang, c.scenario, c.half) for c in CASES)
    assert set(counts) == {
        (lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in ("tune", "gate")
    }
    assert set(counts.values()) == {5}


def test_no_text_appears_in_both_halves() -> None:
    tune = {c.text.casefold().strip() for c in CASES if c.half == "tune"}
    gate = {c.text.casefold().strip() for c in CASES if c.half == "gate"}
    assert not tune & gate, tune & gate


def test_no_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_expected_actions_roles_and_slots() -> None:
    for c in CASES:
        assert c.expected_action in ACTIONS, c
        assert c.role in {"clerk", "supervisor", "owner"}, c
        assert (c.role == "owner") == (c.expected_action == "certificate"), c
        assert set(c.expected_slots) == SLOTS.get(c.expected_action, set()), c
        if c.expected_action == "contributions":
            assert c.expected_slots["which"] in WHICH, c


def test_slot_offsets_parse_and_the_dates_are_candidates() -> None:
    """A leave's start and end are dates find_dates gives build_query (Jev picks among them);
    a holiday's day is one of the fourteen days h0..h13."""
    for c in CASES:
        if c.expected_action == "file_leave":
            found = {d.isoformat() for _, d in find_dates(c.text, TODAY, c.lang)}
            assert {on(c.expected_slots["start"]), on(c.expected_slots["end"])} <= found, c
        if c.expected_action == "holiday_pay":
            m = OFFSET.fullmatch(c.expected_slots["day"])
            assert m and int(m[1]) <= 13, c


def test_scoring() -> None:
    """Right needs the action and the expected inputs; another value is a wrong write."""
    from tests.evals.test_hr_officer_evals import _score

    leave = {"error": None, "expected_action": "file_leave", "missing": None, "confidence": 0.9}
    leave |= {"expected_slots": {"start": "+7d", "end": "+9d"}, "action": "file_leave"}
    good = leave | {"args": {"kind": "vacation", "start": on("+7d"), "end": on("+9d")}}
    assert _score(good) == "right"
    assert _score(good | {"args": {"start": on("+7d"), "end": on("+7d")}}) == "wrong"
    assert _score(good | {"action": "clarify"}) == "ask"
    assert _score(good | {"missing": "leave_start"}) == "ask"
    assert _score(good | {"action": "leave_balance"}) == "wrong"
    assert _score(good | {"action": "leave_balance", "confidence": 0.5}) == "other"
    assert _score(good | {"error": "boom"}) == "other"
    which = {"error": None, "expected_action": "contributions", "missing": None}
    which |= {"expected_slots": {"which": "sss"}, "action": "contributions", "confidence": 0.8}
    assert _score(which | {"args": {"which": "sss"}}) == "right"
    assert _score(which | {"args": {"which": "all"}}) == "wrong"
