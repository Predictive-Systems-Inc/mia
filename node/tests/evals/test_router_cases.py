"""Offline shape of the router eval set: every gated language covers every agent and group,
and the tuning and gate halves are balanced. No model is called."""

from collections import Counter, defaultdict
from pathlib import Path

from mia.agents.registry import AGENTS
from tests.evals.router_cases import CASES, GATED_LANGS, PENDING, REPORTED_LANGS, Case


def _grouped(cases: list[Case]) -> dict[tuple[str, str], list[Case]]:
    groups: dict[tuple[str, str], list[Case]] = defaultdict(list)
    for c in cases:
        groups[(c.lang, c.group)].append(c)
    return groups


def test_every_gated_language_covers_every_agent_and_group() -> None:
    for lang in GATED_LANGS:
        single = [c for c in CASES if c.lang == lang and c.group == "single"]
        by_agent = Counter(c.expected for c in single)
        assert all(by_agent[a] >= 10 for a in AGENTS if a not in PENDING), (lang, by_agent)
        assert sum(1 for c in CASES if c.lang == lang and c.group == "follow_up") >= 10
        assert sum(1 for c in CASES if c.lang == lang and c.group == "switch") >= 10


def test_reported_languages_have_single_cases() -> None:
    for lang in REPORTED_LANGS:
        assert sum(1 for c in CASES if c.lang == lang and c.group == "single") >= 30, lang


def test_expected_values_are_agents_any_or_small_talk() -> None:
    assert {c.expected for c in CASES} <= {*AGENTS, "any", "small_talk"}


def test_context_cases_name_an_active_agent() -> None:
    assert all(c.active in AGENTS for c in CASES if c.group != "single")


def test_halves_are_balanced_per_language_and_group() -> None:
    for (lang, group), cases in _grouped(CASES).items():
        halves = Counter(c.half for c in cases)
        assert abs(halves["tune"] - halves["gate"]) <= 1, (lang, group, halves)


def test_no_text_appears_in_both_halves() -> None:
    """The gate half is fresh: no text (casefolded) of it is in the tune half, and every
    language of one seed falls in one half."""
    halves: dict[str, set[str]] = defaultdict(set)
    for c in CASES:
        halves[c.half].add(c.text.casefold().strip())
    assert not halves["tune"] & halves["gate"], halves["tune"] & halves["gate"]


def test_gate_context_texts_are_not_singles() -> None:
    """In the gate half a text belongs to one group only."""
    gate = [c for c in CASES if c.half == "gate"]
    singles = {c.text for c in gate if c.group == "single"}
    assert not singles & {c.text for c in gate if c.group != "single"}


def test_no_case_names_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_small_talk_is_right_for_greetings_and_a_miss_for_real_messages() -> None:
    from tests.evals.test_router_eval import _score

    def r(kind: str, expected: str, agent: str = "sales_supervisor") -> str:
        return _score({"kind": kind, "expected": expected, "agent": agent})

    assert r("small_talk", "any") == "right"
    assert r("small_talk", "small_talk") == "right"
    assert r("small_talk", "sales_supervisor") == "small_talk"
    assert r("chosen", "bookkeeper") == "wrong"
    assert r("keep", "bookkeeper") == "other"


def test_gated_summary_ignores_reported_languages_and_the_tune_half() -> None:
    from tests.evals.test_router_eval import _gated

    def row(lang: str, half: str, score: str, expected: str = "bookkeeper") -> dict[str, object]:
        return {
            "lang": lang,
            "half": half,
            "score": score,
            "kind": "chosen",
            "tokens": 0,
            "expected": expected,
        }

    results = [row("en", "gate", "right")] * 10 + [row("fi", "gate", "wrong")] * 90
    results += [row("en", "tune", "wrong")] * 5 + [row("en", "gate", "ask", "any")] * 2
    gated = _gated(results)
    assert gated["all"]["n"] == 12 and gated["all"]["wrong"] == 0
    assert set(gated["by_language"]) == {"en"}
    assert gated["by_language"]["en"]["right"] == 1.0  # greetings are reported apart
    assert gated["any"]["n"] == 2 and gated["any"]["ask"] == 1.0


def test_the_gate_is_the_q40_bar() -> None:
    from tests.evals.gate import gate_failures

    def gated(wrong: float, right: float, ask: float) -> dict[str, object]:
        return {"all": {"wrong": wrong}, "by_language": {"en": {"right": right, "ask": ask}}}

    assert gate_failures(gated(0.02, 0.80, 0.15)) == []
    assert gate_failures(gated(0.021, 0.80, 0.15)) == ["wrong 0.021"]
    assert gate_failures(gated(0.0, 0.79, 0.16)) == ["en right 0.79", "en ask 0.16"]


def test_the_raw_report_is_named_by_local_minute_and_never_overwritten(tmp_path: Path) -> None:
    import datetime as dt

    import pytest

    from tests.evals.test_router_eval import _report_path

    now = dt.datetime(2026, 10, 19, 23, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    path = _report_path(now, tmp_path)
    assert path == tmp_path / "router-2026-10-19-2305.raw.json"  # local date, not UTC (15:05)
    path.write_text("{}")
    with pytest.raises(FileExistsError, match="router-2026-10-19-2305"):
        _report_path(now, tmp_path)
