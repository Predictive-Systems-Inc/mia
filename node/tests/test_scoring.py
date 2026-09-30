"""Replacement scoring is pure code: eligibility rules and ranking order."""

import datetime as dt

from mia.agents.dispatcher.scoring import CandidateData, Slot, eligible, rank_candidates

TZ = dt.timezone(dt.timedelta(hours=3))
DAY = dt.date(2026, 10, 1)  # a Thursday


def at(hour: int, minute: int = 0, day: dt.date = DAY) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=TZ)


SLOT = Slot(at(6, 30), at(8, 30))
ALL_WEEK = {d: (dt.time(6), dt.time(20)) for d in range(7)}


def cand(name: str, **kw: object) -> CandidateData:
    base: dict[str, object] = {
        "person_id": name,
        "name": name,
        "skills": ["general"],
        "windows": ALL_WEEK,
        "max_daily_minutes": 600,
        "max_weekly_minutes": 2400,
    }
    base.update(kw)
    return CandidateData(**base)  # type: ignore[arg-type]


def test_available_candidate_is_eligible() -> None:
    assert eligible(cand("a"), SLOT)


def test_outside_availability_window() -> None:
    assert not eligible(cand("a", windows={3: (dt.time(10), dt.time(18))}), SLOT)
    assert not eligible(cand("a", windows={}), SLOT)


def test_double_booked() -> None:
    assert not eligible(cand("a", booked=[Slot(at(7), at(9))]), SLOT)
    assert eligible(cand("a", booked=[Slot(at(9), at(10))]), SLOT)


def test_absent_on_the_day() -> None:
    assert not eligible(cand("a", absent_dates={DAY}), SLOT)


def test_daily_and_weekly_limits() -> None:
    assert not eligible(cand("a", max_daily_minutes=100), SLOT)
    week = [
        Slot(at(12, 0, DAY - dt.timedelta(days=d)), at(20, 0, DAY - dt.timedelta(days=d)))
        for d in (1, 2, 3)
    ]
    assert not eligible(cand("a", booked=week, max_weekly_minutes=1500), SLOT)


def test_ranking_site_then_skills_then_fewest_hours() -> None:
    busy = [Slot(at(12), at(16))]
    ranked = rank_candidates(
        [
            cand("light", booked=[]),
            cand("knows_site", site_visits=2, booked=busy),
            cand("no_skill", skills=[], booked=[]),
            cand("busy", booked=busy),
        ],
        SLOT,
        ["general"],
    )
    assert [r.name for r in ranked] == ["knows_site", "light", "busy"]
    assert "knows the site" in ranked[0].reasons[0]


def test_nobody_available_returns_empty() -> None:
    assert rank_candidates([cand("a", absent_dates={DAY})], SLOT, []) == []


def test_missing_skills_are_reported() -> None:
    ranked = rank_candidates([cand("a", skills=[])], SLOT, ["windows"])
    assert "missing skills: windows" in ranked[0].reasons
