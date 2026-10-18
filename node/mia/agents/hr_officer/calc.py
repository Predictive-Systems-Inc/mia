"""Glue between the stored timesheets and the pure pay rules: a person's approved minutes by
day in a period, split into pay kinds by ph.split_minutes. Unchecked: callers check the reads."""

import datetime as dt
from collections.abc import Mapping
from dataclasses import fields, replace

from sqlmodel import Session, col, select

from mia.agents.hr_officer.ph import REGULAR_MINUTES, Minutes, split_minutes
from mia.core.models import Timesheet


def _sum(parts: list[Minutes]) -> Minutes:
    """One day's shifts added up, regular minutes past eight hours moved to overtime."""
    total = Minutes(**{f.name: sum(getattr(p, f.name) for p in parts) for f in fields(Minutes)})
    extra = max(0, total.regular - REGULAR_MINUTES)
    return replace(total, regular=total.regular - extra, overtime=total.overtime + extra)


def minutes_by_day(
    session: Session,
    person_id: str,
    start: dt.date,
    end: dt.date,
    tz: dt.tzinfo,
    rest_day: int,
    holidays: Mapping[dt.date, str],
) -> list[Minutes]:
    """One Minutes per day from start to end inclusive with an approved timesheet of the
    person, oldest first; drafts are never counted."""
    stmt = (
        select(Timesheet)
        .where(Timesheet.person_id == person_id)
        .where(Timesheet.status == "approved")
        .where(col(Timesheet.date) >= start)
        .where(col(Timesheet.date) <= end)
    )
    days: dict[dt.date, list[Minutes]] = {}
    for sheet in session.exec(stmt):
        days.setdefault(sheet.date, []).append(
            split_minutes(sheet.start, sheet.end, tz, rest_day, holidays)
        )
    return [_sum(days[d]) for d in sorted(days)]
