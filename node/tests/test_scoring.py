"""Replacement scoring is pure code: eligibility rules and ranking order."""

import datetime as dt

import pytest

from mia.agents.dispatcher.scoring import (
    CandidateData,
    Slot,
    added_travel_km,
    distance_km,
    eligible,
    ineligibility,
    rank_candidates,
)

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
    assert [r.name for r in ranked] == ["knows_site", "light", "busy"]  # travel unknown for all
    assert "knows the site" in ranked[0].reasons[0]


def test_nobody_available_returns_empty() -> None:
    assert rank_candidates([cand("a", absent_dates={DAY})], SLOT, []) == []


def test_missing_skills_are_reported() -> None:
    ranked = rank_candidates([cand("a", skills=[])], SLOT, ["windows"])
    assert "missing skills: windows" in ranked[0].reasons


SITE = (60.1875, 24.9770)  # Kalasatama
NEAR = (60.1865, 24.9610)  # about 0.9 km away
FAR = (60.1590, 24.8770)  # Lauttasaari, about 6.4 km away


def test_distance() -> None:
    assert distance_km(SITE, SITE) == 0
    assert 0.8 < distance_km(SITE, NEAR) < 1.0
    assert 6.0 < distance_km(SITE, FAR) < 6.8


def test_added_travel_from_home_or_previous_visit() -> None:
    slot = Slot(at(10), at(11), SITE)
    assert added_travel_km(cand("a"), slot) is None  # no home base, no earlier visit
    assert added_travel_km(cand("a", home=NEAR), Slot(at(10), at(11))) is None  # site unknown
    from_home = added_travel_km(cand("a", home=FAR), slot)
    assert from_home is not None and 6.0 < from_home < 6.8
    earlier_near = cand("a", home=FAR, booked=[Slot(at(8), at(9), NEAR)])
    nearby = added_travel_km(earlier_near, slot)
    assert nearby is not None and nearby < 1.0
    # A later visit at the same site costs nothing extra beyond reaching it.
    later_here = cand("a", home=FAR, booked=[Slot(at(12), at(13), SITE)])
    assert added_travel_km(later_here, slot) == pytest.approx(0.0, abs=1e-9)


def test_travel_ranks_after_site_and_skills_before_hours() -> None:
    slot = Slot(at(10), at(11), SITE)
    busy = [Slot(at(13), at(17), SITE)]
    ranked = rank_candidates(
        [cand("far_free", home=FAR), cand("near_busy", home=NEAR, booked=busy), cand("unknown")],
        slot,
        ["general"],
    )
    assert [r.name for r in ranked] == ["near_busy", "far_free", "unknown"]
    assert "km added travel" in ranked[0].reasons[1] and "travel unknown" in ranked[2].reasons


def test_ineligibility_lists_every_broken_rule() -> None:
    c = cand("a", windows={}, absent_dates={DAY}, booked=[Slot(at(7), at(9))], max_daily_minutes=60)
    assert ineligibility(c, SLOT) == [
        "absent that day",
        "outside availability",
        "already booked at that time",
        "over the daily hour limit",
    ]
