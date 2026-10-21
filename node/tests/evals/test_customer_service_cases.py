"""The customer service eval set is well formed (offline; the real-Jev run is
test_customer_service_evals.py)."""

from collections import Counter
from itertools import combinations
from pathlib import Path

from mia.agents.customer_service.actions import CUSTOMER, STAFF, Query
from mia.agents.customer_service.decider import _lines
from mia.agents.parsing import find_dates, find_times, menu_tokens, pre_parse, strip_times
from mia.i18n import SUPPORTED
from mia.templates.retail.seed import ITEMS
from tests.conftest import TODAY as SEEDED
from tests.evals import gate
from tests.evals.customer_service_cases import (
    CASES,
    GATED_LANGS,
    SCENARIOS,
    TODAY,
    TUNE_ONLY_SCENARIOS,
    UNGATED,
    on,
)

HALVES = ("tune", "spent", "gate")
MENU = {name: (name, *codes) for name, codes, _ in ITEMS}  # id is the name here
LONG = [c for c in CASES if c.half != "short"]
SHORT = [c for c in CASES if c.half == "short"]


def test_ten_per_language_and_scenario_five_per_half() -> None:
    """Scenarios 1 to 8: ten messages per language (five tune, five in the spent gate half) and
    five fresh gate messages; the cases outside them are in the tune half only (the staff
    side's staff_resolve_complaint too, added after both gate runs)."""
    late = [c for c in LONG if c.expected_action == "staff_resolve_complaint"]
    assert late and {(c.scenario, c.half) for c in late} == {("staff", "tune")}
    counts = Counter((c.lang, c.scenario, c.half) for c in LONG if c not in late)
    halves = ("tune", "spent", "gate")
    gated = {(lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in halves}
    extra = {(lang, s, "tune") for lang in GATED_LANGS for s in TUNE_ONLY_SCENARIOS}
    assert set(counts) == gated | extra
    assert {counts[k] for k in gated} == {5}


def test_no_text_appears_in_two_sets() -> None:
    """The tune half, the spent gate half and the fresh gate half share no text (casefolded)."""
    sets = {h: {c.text.casefold().strip() for c in CASES if c.half == h} for h in HALVES}
    for a, b in combinations(HALVES, 2):
        assert not sets[a] & sets[b], (a, b, sets[a] & sets[b])


def test_no_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_no_pair_repeats_and_every_action_but_clarify_has_cases() -> None:
    pairs = [(c.lang, c.text) for c in CASES]
    assert len(pairs) == len(set(pairs)), Counter(pairs).most_common(3)
    assert {c.expected_action for c in LONG} == (CUSTOMER | STAFF) - {"clarify"}
    gate = {c.expected_action for c in CASES if c.half == "gate"}
    assert gate == (CUSTOMER | STAFF) - {"clarify"} - UNGATED


def test_each_side_expects_its_own_actions_and_senders() -> None:
    for c in LONG:
        staff = c.scenario == "staff"
        assert c.expected_action in (STAFF if staff else CUSTOMER), c
        assert (c.role in {"clerk", "supervisor"}) if staff else c.role == "customer", c
        assert bool(c.expected_lines) == (c.expected_action == "place_order"), c
        assert bool(c.expected_language) == (c.expected_action == "language_switch"), c
        assert not c.expected_language or c.expected_language in SUPPORTED, c


def test_the_spent_gate_half_is_never_run() -> None:
    from tests.evals.test_customer_service_evals import _selected

    assert not any(c.half == "spent" for c in _selected(CASES, "tune,gate,spent"))
    assert {c.half for c in _selected(CASES, "tune")} == {"tune"}
    assert {c.half for c in _selected(CASES, "tune,gate")} == {"tune", "gate"}
    assert {c.half for c in _selected(CASES, "short")} == {"short"}


def test_the_short_half_is_short_and_new() -> None:
    """D42: twelve en and twelve fil, two asks each, short and unpunctuated, an offered action
    of the sender's side, an order's item seeded and typed with its count, no text in another
    half or a raw file."""
    first = [c.expected_lines[0] if c.expected_lines else ("", None) for c in SHORT]
    rows = [
        (c.lang, c.text, c.expected_action, i, None, n)
        for c, (i, n) in zip(SHORT, first, strict=True)
    ]
    assert not gate.short_failures("customer_service", rows)
    assert not gate.short_reused(c.text for c in SHORT)
    for c in SHORT:
        side = CUSTOMER if c.role == "customer" else STAFF
        assert c.expected_action in side | {"ask"} and c.role in {"customer", "clerk"}, c
        assert bool(c.expected_language) == (c.expected_action == "language_switch"), c


def test_the_run_day_is_the_seeded_tuesday() -> None:
    assert TODAY == SEEDED and TODAY.weekday() == 1


def test_orders_parse_to_the_expected_lines_time_and_day() -> None:
    """Code reads the lines, the clock time and the day (rule 7): each order's lines come out of
    the decider's own line reader, its time is a find_times candidate, and its day a find_dates
    candidate (or, when the message names no day, today, the decider's default). A short order
    may name no time (Mia asks it)."""
    tokens = menu_tokens((name, codes) for name, *codes in MENU.values())
    for c in CASES:
        if c.expected_action != "place_order":
            continue
        groups, _ = pre_parse(strip_times(c.text), tokens)
        q = Query(c.text, "", "customer", TODAY, groups=groups, items=MENU, lang=c.lang)
        lines = [(ln["item_id"], ln["quantity"]) for ln in _lines(q) or []]
        assert lines == list(c.expected_lines), c
        times = {at.strftime("%H:%M") for _, at in find_times(c.text)}
        assert c.expected_time in times or (c.half == "short" and not c.expected_time), c
        days = {d.isoformat() for _, d in find_dates(c.text, TODAY, c.lang)}
        assert on(c.expected_day) in days or (not days and c.expected_day == "+0d"), c


def test_scoring() -> None:
    """Right needs the action and, for an order, the lines, the time and the day."""
    from tests.evals.test_customer_service_evals import _score

    order = {"error": None, "expected_action": "place_order", "missing": None, "confidence": 0.9}
    order |= {"expected_lines": (("Classic", 10),), "expected_time": "08:00"}
    order |= {"expected_day": "+1d", "action": "place_order", "lines": [["Classic", 10]]}
    good = order | {"args": {"time": "08:00", "day": on("+1d")}}
    assert _score(good) == "right"
    assert _score(good | {"lines": [["Classic", 12]]}) == "wrong"
    assert _score(good | {"args": {"time": "20:00", "day": on("+1d")}}) == "wrong"
    assert _score(good | {"args": {"time": "08:00", "day": on("+0d")}}) == "wrong"
    assert _score(good | {"missing": "pickup_time"}) == "ask"
    assert _score(good | {"action": "clarify"}) == "ask"
    assert _score(good | {"action": "prices"}) == "wrong"
    assert _score(good | {"action": "prices", "confidence": 0.5}) == "other"
    assert _score(good | {"error": "boom"}) == "other"
    hours = {"error": None, "expected_action": "hours", "missing": None, "confidence": 0.7}
    assert _score(hours | {"action": "hours", "args": {}}) == "right"
    switch = hours | {"expected_action": "language_switch", "expected_language": "en"}
    assert _score(switch | {"action": "language_switch", "args": {"language": "en"}}) == "right"
    assert _score(switch | {"action": "language_switch", "args": {"language": "fil"}}) == "wrong"


def test_the_raw_report_is_named_by_local_minute_and_never_overwritten(tmp_path: Path) -> None:
    import datetime as dt

    import pytest

    from tests.evals.test_customer_service_evals import _report_path

    now = dt.datetime(2026, 10, 20, 23, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    path = _report_path(now, tmp_path)
    assert path == tmp_path / "customer-service-2026-10-20-2305.raw.json"
    path.write_text("{}")
    with pytest.raises(FileExistsError, match="customer-service-2026-10-20-2305"):
        _report_path(now, tmp_path)
