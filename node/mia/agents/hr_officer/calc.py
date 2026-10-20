"""Glue between the stored rows and the pure pay rules: a person's approved minutes by day in
a period (split into pay kinds by ph.split_minutes) and a cutoff's payslip (cutoff_pay, the one
helper the tick and the seed use). Unchecked: callers check the reads."""

import datetime as dt
from collections.abc import Mapping
from dataclasses import fields, replace

from sqlmodel import Session, col, select

from mia.agents.hr_officer import calendar, ph
from mia.agents.hr_officer.ph import REGULAR_MINUTES, Minutes, split_minutes
from mia.core import orgconfig
from mia.core.models import Contract, Leave, Timesheet

# How far before a cutoff the working day before a regular holiday is looked for (a rest day
# and a run of holidays, as in Holy Week, stay well inside a week).
LOOKBACK = dt.timedelta(days=7)


def holidays() -> dict[dt.date, str]:
    """The organisation's holidays: date to kind (regular or special)."""
    return {h.date: h.kind for h in orgconfig.load().holidays}


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
    days: dict[dt.date, list[Minutes]] = {}
    for sheet in _approved(session, person_id, start, end):
        days.setdefault(sheet.date, []).append(
            split_minutes(sheet.start, sheet.end, tz, rest_day, holidays)
        )
    return [_sum(days[d]) for d in sorted(days)]


def _approved(session: Session, person_id: str, start: dt.date, end: dt.date) -> list[Timesheet]:
    return list(
        session.exec(
            select(Timesheet)
            .where(Timesheet.person_id == person_id)
            .where(Timesheet.status == "approved")
            .where(col(Timesheet.date) >= start)
            .where(col(Timesheet.date) <= end)
        )
    )


def paid_days(
    session: Session,
    contract: Contract,
    kind: str,
    start: dt.date,
    days: int,
    leave_id: str = "~",
) -> int:
    """How many of a leave's days are paid: none for unpaid leave; for vacation or sick, at
    most the SIL balance at its start (calendar.sil_balance) less the days of the person's
    approved vacation and sick leaves that start before it in that service year (by start,
    then id; "~" sorts after every id, for a leave not yet written)."""
    if kind not in calendar.SIL_KINDS:
        return 0
    begin, _ = calendar.service_year(contract.start_date, start)
    stmt = (
        select(Leave)
        .where(Leave.person_id == contract.person_id)
        .where(Leave.status == "approved")
        .where(col(Leave.kind).in_(calendar.SIL_KINDS))
        .where(col(Leave.start_date) >= begin)
        .where(col(Leave.start_date) <= start)
    )
    used = sum(r.days for r in session.exec(stmt) if (r.start_date, r.id) < (start, leave_id))
    return min(days, calendar.sil_balance(contract.start_date, start, used))


def _leave_split(
    session: Session, contract: Contract, start: dt.date, end: dt.date, days: Mapping[dt.date, str]
) -> tuple[set[dt.date], set[dt.date]]:
    """The person's approved vacation and sick leave days (calendar.leave_dates) from start to
    end, split into paid and unpaid: the first paid_days of each leave are paid, the rest not."""
    stmt = (
        select(Leave)
        .where(Leave.person_id == contract.person_id)
        .where(Leave.status == "approved")
        .where(col(Leave.kind).in_(calendar.SIL_KINDS))
        .where(col(Leave.start_date) <= end)
        .where(col(Leave.end_date) >= start)
    )
    paid: set[dt.date] = set()
    unpaid: set[dt.date] = set()
    for row in session.exec(stmt):
        dates = sorted(
            calendar.leave_dates([(row.start_date, row.end_date)], contract.rest_day, days)
        )
        n = paid_days(session, contract, row.kind, row.start_date, len(dates), row.id)
        paid.update(dates[:n])
        unpaid.update(dates[n:])
    return {d for d in paid if start <= d <= end}, {d for d in unpaid if start <= d <= end}


def cutoff_pay(
    session: Session,
    contract: Contract,
    start: dt.date,
    end: dt.date,
    tz: dt.tzinfo,
    days: Mapping[dt.date, str],
) -> ph.PayslipCalc | None:
    """The cutoff's payslip for the contract's person (ph.payslip at the contract's rate): the
    approved minutes by day, the leave days in the cutoff (paid within the SIL balance, the
    rest shown unpaid; paid_days) and its unworked regular holidays whose working day before
    was worked or on paid leave (calendar). None when there is nothing to pay (no approved
    time, paid leave or holiday pay)."""
    person, rest = contract.person_id, contract.rest_day
    minutes = minutes_by_day(session, person, start, end, tz, rest, days)
    worked = {sheet.date for sheet in _approved(session, person, start - LOOKBACK, end)}
    paid, unpaid = _leave_split(session, contract, start - LOOKBACK, end, days)
    leave_days = sum(start <= d <= end for d in paid)
    unworked = calendar.unworked_regular_holidays(start, end, rest, days, worked, paid)
    if not (minutes or leave_days or unworked):
        return None
    rate = contract.daily_rate
    return ph.payslip(
        minutes,
        rate,
        ph.monthly_basic(rate),
        leave_days=leave_days,
        holidays=len(unworked),
        unpaid_leave_days=sum(start <= d <= end for d in unpaid),
    )
