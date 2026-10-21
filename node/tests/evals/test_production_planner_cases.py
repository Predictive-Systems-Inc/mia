"""The production planner eval set is well formed (offline; the real-Jev run is
test_production_planner_evals.py)."""

import datetime as dt
from collections import Counter
from pathlib import Path

import pytest
from sqlmodel import Session, select

from mia.agents.production_planner import tools, words
from mia.agents.production_planner.actions import ACTIONS, DIRECTIONS, commissary
from mia.templates.retail.models import RetailIngredient, RetailItem
from mia.templates.retail.seed import BRANCHES
from tests.conftest import PP_TODAY, PP_TOMORROW, Shop
from tests.evals.production_planner_cases import CASES, GATED_LANGS, SCENARIOS, TODAY

# The inputs each action is scored on (beyond the action itself).
INPUTS = {
    "change_plan": {"item", "direction", "number"},
    "batch_sheet": {"item"},
    "set_recipe": {"item"},
    "record_batch": {"item"},
    "delivered": {"kiosk"},
    "capacity": {"item", "number"},
}


def test_ten_cases_per_language_scenario_and_half() -> None:
    """Per language and scenario: five tune and five gate seeds."""
    counts = Counter((c.lang, c.scenario, c.half) for c in CASES)
    halves = ("tune", "gate")
    assert set(counts) == {(lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in halves}
    assert set(counts.values()) == {5}


def test_every_spec_scenario_but_8_and_10_is_asked() -> None:
    assert {n for n, *_ in SCENARIOS.values()} == {1, 2, 3, 4, 5, 6, 7, 9}


def test_no_text_appears_in_both_halves() -> None:
    sets = {h: {c.text.casefold().strip() for c in CASES if c.half == h} for h in ("tune", "gate")}
    assert not sets["tune"] & sets["gate"], sets["tune"] & sets["gate"]
    pairs = [(c.lang, c.text) for c in CASES]
    assert len(pairs) == len(set(pairs)), Counter(pairs).most_common(3)


def test_no_case_names_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_expected_inputs_roles_and_previous() -> None:
    assert {c.expected_action for c in CASES} <= set(ACTIONS) - {"reply_only", "clarify"}
    roles = {"set_recipe": "owner", "capacity": "owner", "dispatch": "kiosk"}
    roles |= {"delivered": "driver"}
    for c in CASES:
        assert set(c.expected) == INPUTS.get(c.expected_action, set()), c
        assert c.role == roles.get(c.expected_action, "head"), c
        assert bool(c.previous) == (c.scenario == "confirm"), c
        assert c.expected.get("direction", "set") in DIRECTIONS, c
        assert c.expected.get("kiosk", "Mall kiosk") in {name for name, *_ in BRANCHES}, c


def test_numbers_and_batches_are_read_by_code() -> None:
    """Code reads every number Jev picks (rule 7): the expected number is a words.numbers
    candidate, and every batch report parses with words.batch."""
    for c in CASES:
        if "number" in c.expected:
            assert c.expected["number"] in words.numbers(c.text, TODAY, c.lang).values(), c
        if c.expected_action == "record_batch":
            assert words.batch(c.text) is not None, c


def test_the_run_day_is_pp_today() -> None:
    assert TODAY == PP_TODAY and TODAY.weekday() == 1


def test_recipes_parse_in_full_and_changed_items_are_planned(
    session: Session, pp_shop: Shop
) -> None:
    """Every recipe text is read in full (a yield, oven minutes, lines, no unknown part), and
    every added or removed item is a line of the drafted plan, so those decisions never ask
    for the recipe or the plan."""
    ingredients = session.exec(select(RetailIngredient)).all()
    for c in CASES:
        if c.expected_action == "set_recipe":
            p = words.recipe(c.text, ingredients)
            assert p and p.batch_yield and p.oven_minutes and p.lines and not p.unknown, c
    home = commissary(session, pp_shop.kiosk.organisation_id)
    assert home is not None
    plan = tools.draft_plan(session, home, PP_TOMORROW)
    names = {i.id: i.name for i in session.exec(select(RetailItem))}
    planned = {names[x["item_id"]] for x in plan.lines if x["batches"] > 0}
    for c in CASES:
        if c.expected.get("direction") in ("add", "remove"):
            assert c.expected["item"] in planned, (c, planned)


def test_scoring() -> None:
    """Right needs the action and its inputs; another input is a wrong write."""
    from tests.evals.test_production_planner_evals import _score

    base = {"error": None, "missing": None, "confidence": 0.9}
    change = base | {"expected_action": "change_plan", "action": "change_plan"}
    change |= {"expected": {"item": "Ube", "direction": "add", "number": 1}}
    want = {"item": "Ube", "kiosk": None, "direction": "add", "number": 1}
    assert _score(change | {"resolved": want}) == "right"
    assert _score(change | {"resolved": want | {"direction": "set"}}) == "wrong"
    assert _score(change | {"resolved": want | {"number": 2}}) == "wrong"
    assert _score(change | {"resolved": {}, "missing": "number"}) == "ask"
    assert _score(change | {"action": "clarify", "resolved": {}}) == "ask"
    assert _score(change | {"action": "capacity", "resolved": {}}) == "wrong"
    assert _score(change | {"action": "capacity", "confidence": 0.5, "resolved": {}}) == "other"
    assert _score(change | {"error": "boom"}) == "other"
    plan = base | {"expected_action": "plan", "action": "plan", "expected": {}}
    assert _score(plan | {"resolved": want}) == "right"


def test_resolved_reads_the_slot_picks() -> None:
    from mia.agents.production_planner.actions import Query
    from tests.evals.test_production_planner_evals import _resolved

    q = Query("m", "", "supervisor", TODAY, kiosks={"k1": "Mall kiosk"}, numbers={"n0": 2})
    answers = {
        "item": {"choice": "i1"},
        "kiosk": {"choice": "k1"},
        "direction": {"choice": "remove"},
        "number": {"choice": "n0"},
    }
    got = _resolved(answers, q, {"i1": "Ube"})
    assert got == {"item": "Ube", "kiosk": "Mall kiosk", "direction": "remove", "number": 2}
    unsaid = {k: {"choice": "not_stated"} for k in answers}
    assert set(_resolved(unsaid, q, {"i1": "Ube"}).values()) == {None}


def test_the_halves_are_selected_by_name() -> None:
    from tests.evals.test_production_planner_evals import _selected

    assert {c.half for c in _selected(CASES, "tune")} == {"tune"}
    assert {c.half for c in _selected(CASES, "gate")} == {"gate"}


def test_the_raw_report_is_named_by_local_minute_and_never_overwritten(tmp_path: Path) -> None:
    from tests.evals.test_production_planner_evals import _report_path

    now = dt.datetime(2026, 10, 21, 9, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    path = _report_path(now, tmp_path)
    assert path == tmp_path / "production-planner-2026-10-21-0905.raw.json"
    path.write_text("{}")
    with pytest.raises(FileExistsError, match="production-planner-2026-10-21-0905"):
        _report_path(now, tmp_path)


def test_the_gate_is_the_q40_bar() -> None:
    from tests.evals.gate import gate_failures
    from tests.evals.test_production_planner_evals import _row

    def gated(right: int, ask: int, wrong: int) -> dict[str, object]:
        n = {"right": right, "ask": ask, "wrong": wrong, "other": 100 - right - ask - wrong}
        rows = [{"score": s} for s, k in n.items() for _ in range(k)]
        return {"all": _row(rows), "by_language": {"fil": _row(rows)}}

    assert gate_failures(gated(80, 15, 2)) == []
    assert gate_failures(gated(80, 15, 3)) == ["wrong 0.03"]
    assert gate_failures(gated(79, 16, 0)) == ["fil right 0.79", "fil ask 0.16"]
