"""Replacement scoring: pure functions, no database and no model.

Eligible candidates are available at the visit time, not absent, not double-booked and within
daily and weekly hour limits. Ranking (plan, Replacement scoring): knows the site (has done a
visit there), has the required skills, least added travel, fewest hours this week, then name
for a stable order. Added travel is the extra straight-line distance of fitting the visit into
the candidate's day: from the previous visit that day (or the home base) to the site, and on to
the next visit, minus the direct leg it replaces. Unknown coordinates rank after known ones.
"""

import datetime as dt
import math
from dataclasses import dataclass, field

Point = tuple[float, float]  # (lat, lon)
EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class Slot:
    start: dt.datetime
    end: dt.datetime
    where: Point | None = None

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)

    def overlaps(self, other: "Slot") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass
class CandidateData:
    person_id: str
    name: str
    skills: list[str]
    windows: dict[int, tuple[dt.time, dt.time]]  # weekday -> (start, end), local time
    max_daily_minutes: int
    max_weekly_minutes: int
    booked: list[Slot] = field(default_factory=list)  # visits this week, local time
    absent_dates: set[dt.date] = field(default_factory=set)
    site_visits: int = 0  # completed visits at this location
    home: Point | None = None


@dataclass(frozen=True)
class Ranked:
    person_id: str
    name: str
    reasons: list[str]
    week_minutes: int
    travel_km: float | None


def distance_km(a: Point, b: Point) -> float:
    """Great-circle (haversine) distance."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def added_travel_km(c: CandidateData, slot: Slot) -> float | None:
    """Extra distance of inserting the visit into the candidate's day, or None if unknown."""
    if slot.where is None:
        return None
    day = sorted(
        (s for s in c.booked if s.start.date() == slot.start.date()), key=lambda s: s.start
    )
    before = [s for s in day if s.end <= slot.start]
    after = [s for s in day if s.start >= slot.end]
    origin = before[-1].where if before else c.home
    if origin is None:
        return None
    extra = distance_km(origin, slot.where)
    following = after[0].where if after else None
    if following is not None:
        extra += distance_km(slot.where, following) - distance_km(origin, following)
    return max(extra, 0.0)


def _available(c: CandidateData, slot: Slot) -> bool:
    window = c.windows.get(slot.start.weekday())
    if window is None:
        return False
    same_day = slot.end.date() == slot.start.date()
    return same_day and window[0] <= slot.start.time() and slot.end.time() <= window[1]


def _minutes_on(c: CandidateData, day: dt.date) -> int:
    return sum(s.minutes for s in c.booked if s.start.date() == day)


def ineligibility(c: CandidateData, slot: Slot) -> list[str]:
    """Every hard rule the candidate breaks for this slot (empty means eligible)."""
    reasons = []
    if slot.start.date() in c.absent_dates:
        reasons.append("absent that day")
    if not _available(c, slot):
        reasons.append("outside availability")
    if any(s.overlaps(slot) for s in c.booked):
        reasons.append("already booked at that time")
    if _minutes_on(c, slot.start.date()) + slot.minutes > c.max_daily_minutes:
        reasons.append("over the daily hour limit")
    if sum(s.minutes for s in c.booked) + slot.minutes > c.max_weekly_minutes:
        reasons.append("over the weekly hour limit")
    return reasons


def eligible(c: CandidateData, slot: Slot) -> bool:
    """Hard rules: available, not absent, not double-booked, within hour limits."""
    return not ineligibility(c, slot)


def rank_candidates(
    candidates: list[CandidateData], slot: Slot, required_skills: list[str], top: int = 3
) -> list[Ranked]:
    """Top candidates with reasons, best first. Deterministic for equal inputs."""
    scored = []
    for c in candidates:
        if not eligible(c, slot):
            continue
        knows_site = c.site_visits > 0
        has_skills = set(required_skills) <= set(c.skills)
        week_minutes = sum(s.minutes for s in c.booked)
        travel = added_travel_km(c, slot)
        reasons = []
        if knows_site:
            reasons.append(f"knows the site ({c.site_visits} earlier visits)")
        if has_skills:
            reasons.append("has the required skills")
        else:
            missing = sorted(set(required_skills) - set(c.skills))
            reasons.append("missing skills: " + ", ".join(missing))
        reasons.append(f"{travel:.1f} km added travel" if travel is not None else "travel unknown")
        reasons.append(f"{week_minutes / 60:.1f} h booked this week")
        travel_key = round(travel, 1) if travel is not None else math.inf
        key = (not knows_site, not has_skills, travel_key, week_minutes, c.name)
        scored.append((key, Ranked(c.person_id, c.name, reasons, week_minutes, travel)))
    scored.sort(key=lambda item: item[0])
    return [r for _, r in scored[:top]]
