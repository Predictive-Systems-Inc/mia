"""Replacement scoring: a pure function, no database and no model.

Eligible candidates are available at the visit time, within daily and weekly hour limits, not
absent and not double-booked. Ranking: knows the site (has done a visit there), has the
required skills, fewest hours this week, then name for a stable order. Travel time is not
modelled yet (no geodata in the seed); see docs/questions.md.
"""

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Slot:
    start: dt.datetime
    end: dt.datetime

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


@dataclass(frozen=True)
class Ranked:
    person_id: str
    name: str
    reasons: list[str]
    week_minutes: int


def _available(c: CandidateData, slot: Slot) -> bool:
    window = c.windows.get(slot.start.weekday())
    if window is None:
        return False
    same_day = slot.end.date() == slot.start.date()
    return same_day and window[0] <= slot.start.time() and slot.end.time() <= window[1]


def _minutes_on(c: CandidateData, day: dt.date) -> int:
    return sum(s.minutes for s in c.booked if s.start.date() == day)


def eligible(c: CandidateData, slot: Slot) -> bool:
    """Hard rules: available, not absent, not double-booked, within hour limits."""
    if slot.start.date() in c.absent_dates or not _available(c, slot):
        return False
    if any(s.overlaps(slot) for s in c.booked):
        return False
    if _minutes_on(c, slot.start.date()) + slot.minutes > c.max_daily_minutes:
        return False
    week = sum(s.minutes for s in c.booked)
    return week + slot.minutes <= c.max_weekly_minutes


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
        reasons = []
        if knows_site:
            reasons.append(f"knows the site ({c.site_visits} earlier visits)")
        if has_skills:
            reasons.append("has the required skills")
        else:
            reasons.append(
                "missing skills: " + ", ".join(sorted(set(required_skills) - set(c.skills)))
            )
        reasons.append(f"{week_minutes / 60:.1f} h booked this week")
        key = (not knows_site, not has_skills, week_minutes, c.name)
        scored.append((key, Ranked(c.person_id, c.name, reasons, week_minutes)))
    scored.sort(key=lambda item: item[0])
    return [r for _, r in scored[:top]]
