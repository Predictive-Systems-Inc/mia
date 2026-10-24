"""The payroll calendar as pure code (rule 7): semi-monthly cutoffs, paydays, working days,
leave days and the service incentive leave balance. Holidays are a mapping of date to kind
("regular" or "special") from config/org/<org>/holidays.yaml; a rest day is a weekday number
(0 is Monday). Q60 holds the cutoff and payday rule.
"""

import datetime as dt
from collections.abc import Iterable, Mapping

SUNDAY = 6
SIL_DAYS = 5  # service incentive leave days per year of service
SIL_KINDS = ("vacation", "sick")  # the leave kinds the service incentive leave pays for


def _month_end(day: dt.date) -> dt.date:
    first_next = (day.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return first_next - dt.timedelta(days=1)


def cutoff(day: dt.date) -> tuple[dt.date, dt.date]:
    """The cutoff holding the day: the 1st to the 15th, or the 16th to the month's end."""
    if day.day <= 15:
        return day.replace(day=1), day.replace(day=15)
    return day.replace(day=16), _month_end(day)


def previous_cutoff(day: dt.date) -> tuple[dt.date, dt.date]:
    """The cutoff just before the one holding the day."""
    return cutoff(cutoff(day)[0] - dt.timedelta(days=1))


def next_cutoff_end(day: dt.date) -> dt.date:
    """The first cutoff end on or after the day (the end of the cutoff holding it)."""
    return cutoff(day)[1]


def payday(cutoff_end: dt.date, lag_days: int, holidays: Mapping[dt.date, str]) -> dt.date:
    """The cutoff end plus the lag, moved back while it is a Sunday or a holiday (Q60). A
    Saturday stays."""
    day = cutoff_end + dt.timedelta(days=lag_days)
    while day.weekday() == SUNDAY or day in holidays:
        day -= dt.timedelta(days=1)
    return day


def working_days(
    start: dt.date, end: dt.date, rest_day: int, holidays: Mapping[dt.date, str]
) -> int:
    """The days from start to end inclusive that are not the rest day or a regular holiday
    (a special day counts as a working day). 0 when end is before start."""
    days = (start + dt.timedelta(days=i) for i in range((end - start).days + 1))
    return sum(d.weekday() != rest_day and holidays.get(d) != "regular" for d in days)


def leave_days(start: dt.date, end: dt.date, rest_day: int, holidays: Mapping[dt.date, str]) -> int:
    """The leave days a request from start to end inclusive uses: its working days."""
    return working_days(start, end, rest_day, holidays)


def leave_dates(
    spans: Iterable[tuple[dt.date, dt.date]], rest_day: int, holidays: Mapping[dt.date, str]
) -> set[dt.date]:
    """The leave days of the spans (first and last day inclusive): each day that is a working
    day (working_days), so a rest day or a regular holiday inside a leave is no leave day."""
    return {
        start + dt.timedelta(days=i)
        for start, end in spans
        for i in range((end - start).days + 1)
        if working_days(
            start + dt.timedelta(days=i), start + dt.timedelta(days=i), rest_day, holidays
        )
    }


def _working_day_before(day: dt.date, rest_day: int, holidays: Mapping[dt.date, str]) -> dt.date:
    """The last working day before the day, back over the rest day and regular holidays."""
    day -= dt.timedelta(days=1)
    while not working_days(day, day, rest_day, holidays):
        day -= dt.timedelta(days=1)
    return day


def unworked_regular_holidays(
    start: dt.date,
    end: dt.date,
    rest_day: int,
    holidays: Mapping[dt.date, str],
    worked: set[dt.date],
    on_leave: set[dt.date],
) -> list[dt.date]:
    """The regular holidays from start to end paid at 100% though not worked: not worked, not
    on the rest day, and the working day before was worked or on paid leave. A special day
    not worked pays nothing (no work, no pay)."""
    # ponytail: an unworked regular holiday on the rest day pays nothing; ask the accountant
    # whether the contract pays it (Q61).
    days = (start + dt.timedelta(days=i) for i in range((end - start).days + 1))
    return [
        d
        for d in days
        if holidays.get(d) == "regular"
        and d.weekday() != rest_day
        and d not in worked
        and _working_day_before(d, rest_day, holidays) in worked | on_leave
    ]


def _anniversary(start: dt.date, year: int) -> dt.date:
    """The start date's day in the year (28 February for a 29 February start)."""
    try:
        return start.replace(year=year)
    except ValueError:
        return start.replace(year=year, day=28)


def service_year(start: dt.date, day: dt.date) -> tuple[dt.date, dt.date]:
    """The service year holding the day: from the last anniversary on or before it (the start
    date in the first year) to the day before the next one."""
    begin = _anniversary(start, day.year)
    if begin > day:
        begin = _anniversary(start, day.year - 1)
    begin = max(begin, start)
    return begin, _anniversary(start, begin.year + 1) - dt.timedelta(days=1)


def sil_balance(start_date: dt.date, today: dt.date, used: int) -> int:
    """Service incentive leave left: 0 before one year of service; from each service
    anniversary, five days credited in full less the days used in the current service year,
    never negative (Q63)."""
    months = (today.year - start_date.year) * 12 + today.month - start_date.month
    months -= today.day < start_date.day
    if months < 12:
        return 0
    return max(0, SIL_DAYS - used)
