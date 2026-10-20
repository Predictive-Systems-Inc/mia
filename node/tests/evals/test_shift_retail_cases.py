"""The retail shift supervisor eval set is well formed (offline; the real-Jev run is
test_shift_retail_evals.py)."""

import datetime as dt
from collections import Counter
from pathlib import Path

import pytest

from mia.agents.parsing import find_times
from mia.agents.shift_supervisor import roster
from mia.agents.shift_supervisor.actions import RETAIL_ACTIONS, RETAIL_PROBLEM_KINDS
from tests.conftest import RS_TODAY
from tests.evals.shift_retail_cases import CASES, GATED_LANGS, SCENARIOS, TODAY

# The inputs each action is scored on (beyond the action itself).
INPUTS = {
    "record_absence": {"date", "person"},
    "find_replacements": {"date"},
    "assign_cover": {"person"},
    "swap": {"person", "date"},
    "correct_time": {"date", "time", "person"},
    "report_site_problem": {"kind"},
    "close_day": {"date"},
}
# Ferino's people by first name and the Mall kiosk's hours, as build_query hands them to code.
PEOPLE = {f"p{n}": name for n, name in enumerate(("Rosa", "Marites", "Jun", "Ana", "Liza", "Pao"))}
OPENS, CLOSES = dt.time(9), dt.time(21)


def test_ten_cases_per_language_scenario_and_half() -> None:
    """Per language and scenario: five tune and five gate seeds."""
    counts = Counter((c.lang, c.scenario, c.half) for c in CASES)
    halves = ("tune", "gate")
    assert set(counts) == {(lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in halves}
    assert set(counts.values()) == {5}


def test_no_text_appears_in_both_halves() -> None:
    sets = {h: {c.text.casefold().strip() for c in CASES if c.half == h} for h in ("tune", "gate")}
    assert not sets["tune"] & sets["gate"], sets["tune"] & sets["gate"]
    pairs = [(c.lang, c.text) for c in CASES]
    assert len(pairs) == len(set(pairs)), Counter(pairs).most_common(3)


def test_the_actions_are_retail_actions() -> None:
    assert {c.expected_action for c in CASES} <= set(RETAIL_ACTIONS)
    assert "checklist" not in RETAIL_ACTIONS  # Q109: no checklists at a kiosk


def test_no_case_names_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_expected_inputs_and_roles() -> None:
    dates = {(TODAY + dt.timedelta(days=n)).isoformat() for n in range(14)}  # actions._dates
    for c in CASES:
        assert set(c.expected) == INPUTS.get(c.expected_action, set()), c
        assert c.expected.get("date", TODAY.isoformat()) in dates, c
        assert c.expected.get("kind", "equipment") in RETAIL_PROBLEM_KINDS, c
        assert c.expected.get("person") in (None, "Ana", "Liza", "Pao"), c
        assert bool(c.previous) == (c.expected_action == "assign_cover"), c
        clerk_asks = c.expected_action not in ("set_roster", "close_day")
        clerk_asks &= c.expected_action not in ("find_replacements", "assign_cover")
        assert (c.role == "clerk") == clerk_asks, c


def test_every_roster_pattern_is_read_by_code() -> None:
    """Code reads the pattern (rule 7): every set_roster text parses in full within the Mall
    kiosk's hours, so a set_roster decision has its shifts and never asks for the pattern."""
    for c in CASES:
        if c.expected_action == "set_roster":
            pattern = roster.parse_pattern(c.text, PEOPLE, OPENS, CLOSES)
            assert pattern.clauses and not pattern.unclear, (c.lang, c.text, pattern.unclear)


def test_corrected_times_are_candidates() -> None:
    for c in CASES:
        if "time" in c.expected:
            times = {at.strftime("%H:%M") for _, at in find_times(c.text)}
            assert c.expected["time"] in times, c


def test_the_run_day_is_rs_today() -> None:
    assert TODAY == RS_TODAY and TODAY.weekday() == 2


def test_scoring() -> None:
    """Right needs the action and its inputs; another input is a wrong write."""
    from tests.evals.test_shift_retail_evals import _score

    base = {"error": None, "missing": None, "confidence": 0.9}
    swap = base | {"expected_action": "swap", "action": "swap"}
    swap |= {"expected": {"person": "Liza", "date": "2026-10-31"}}
    assert _score(swap | {"resolved": {"person": "Liza", "date": "2026-10-31"}}) == "right"
    assert _score(swap | {"resolved": {"person": "Liza", "date": "2026-11-01"}}) == "wrong"
    assert _score(swap | {"resolved": {}, "missing": "person"}) == "ask"
    assert _score(swap | {"action": "clarify", "resolved": {}}) == "ask"
    assert _score(swap | {"action": "swap_reply", "resolved": {}}) == "wrong"
    assert _score(swap | {"action": "swap_reply", "confidence": 0.5, "resolved": {}}) == "other"
    assert _score(swap | {"error": "boom"}) == "other"
    own = base | {"expected_action": "record_absence", "action": "record_absence"}
    own |= {"expected": {"date": "2026-10-28", "person": None}}
    assert _score(own | {"resolved": {"date": "2026-10-28", "person": None}}) == "right"
    assert _score(own | {"resolved": {"date": "2026-10-28", "person": "Liza"}}) == "wrong"


def test_resolved_reads_names_and_visit_dates() -> None:
    from tests.evals.test_shift_retail_evals import _resolved

    names, dates = {"p4": "Liza"}, {"v1": "2026-10-29"}
    assert _resolved({"visit_id": "v1", "candidate_id": "p4"}, names, dates) == {
        "person": "Liza",
        "date": "2026-10-29",
        "kind": None,
        "time": None,
    }
    got = _resolved({"person_name": "Liza", "date": "2026-10-31", "end": "21:00"}, names, dates)
    assert got == {"person": "Liza", "date": "2026-10-31", "kind": None, "time": "21:00"}
    assert _resolved({"person_name": None}, names, dates)["person"] is None


def test_the_halves_are_selected_by_name() -> None:
    from tests.evals.test_shift_retail_evals import _selected

    assert {c.half for c in _selected(CASES, "tune")} == {"tune"}
    assert {c.half for c in _selected(CASES, "gate")} == {"gate"}


def test_the_raw_report_is_named_by_local_minute_and_never_overwritten(tmp_path: Path) -> None:
    from tests.evals.test_shift_retail_evals import _report_path

    now = dt.datetime(2026, 10, 21, 9, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    path = _report_path(now, tmp_path)
    assert path == tmp_path / "shift-supervisor-retail-2026-10-21-0905.raw.json"
    path.write_text("{}")
    with pytest.raises(FileExistsError, match="shift-supervisor-retail-2026-10-21-0905"):
        _report_path(now, tmp_path)
