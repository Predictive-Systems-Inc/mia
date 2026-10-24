import datetime as dt

from mia.agents.hr_officer.calendar import (
    cutoff,
    leave_dates,
    leave_days,
    next_cutoff_end,
    payday,
    previous_cutoff,
    sil_balance,
    unworked_regular_holidays,
    working_days,
)

D = dt.date
SUNDAY = 6


def test_cutoffs_at_month_ends() -> None:
    assert cutoff(D(2026, 10, 15)) == (D(2026, 10, 1), D(2026, 10, 15))
    assert cutoff(D(2026, 10, 16)) == (D(2026, 10, 16), D(2026, 10, 31))
    assert cutoff(D(2026, 2, 20)) == (D(2026, 2, 16), D(2026, 2, 28))
    assert cutoff(D(2028, 2, 29)) == (D(2028, 2, 16), D(2028, 2, 29))
    assert cutoff(D(2026, 12, 31)) == (D(2026, 12, 16), D(2026, 12, 31))
    assert previous_cutoff(D(2026, 3, 2)) == (D(2026, 2, 16), D(2026, 2, 28))
    assert previous_cutoff(D(2026, 1, 5)) == (D(2025, 12, 16), D(2025, 12, 31))
    assert previous_cutoff(D(2026, 10, 20)) == (D(2026, 10, 1), D(2026, 10, 15))
    assert next_cutoff_end(D(2026, 4, 16)) == D(2026, 4, 30)


def test_payday_moves_back_from_a_sunday_and_a_holiday_but_not_a_saturday() -> None:
    assert payday(D(2026, 10, 15), 5, {}) == D(2026, 10, 20)  # a Tuesday
    assert payday(D(2026, 10, 31), 5, {}) == D(2026, 11, 5)
    # 2026-11-15 is a Sunday: back to Saturday the 14th.
    assert payday(D(2026, 11, 10), 5, {}) == D(2026, 11, 14)
    # 2026-11-30 (Bonifacio Day, a Monday) and the Sunday before: back to Saturday.
    assert payday(D(2026, 11, 25), 5, {D(2026, 11, 30): "regular"}) == D(2026, 11, 28)
    # A special day moves it too (Q60: any holiday).
    assert payday(D(2026, 12, 19), 5, {D(2026, 12, 24): "special"}) == D(2026, 12, 23)
    assert payday(D(2026, 10, 19), 5, {}) == D(2026, 10, 24)  # a Saturday stays


def test_leave_days_skip_the_rest_day_and_a_regular_holiday() -> None:
    holidays = {D(2026, 11, 30): "regular", D(2026, 12, 8): "special"}
    # Mon 2026-11-30 to Sun 2026-12-06: the holiday and the Sunday rest day are skipped.
    assert leave_days(D(2026, 11, 30), D(2026, 12, 6), SUNDAY, holidays) == 5
    # A special day counts.
    assert leave_days(D(2026, 12, 7), D(2026, 12, 8), SUNDAY, holidays) == 2
    assert working_days(D(2026, 10, 1), D(2026, 10, 15), SUNDAY, {}) == 13
    assert working_days(D(2026, 10, 2), D(2026, 10, 1), SUNDAY, {}) == 0


def test_sil_balance_five_days_at_each_anniversary_less_used() -> None:
    start = D(2025, 4, 19)
    assert sil_balance(start, D(2026, 3, 19), 0) == 0  # eleven months
    assert sil_balance(start, D(2026, 4, 18), 0) == 0  # a day short of one year
    assert sil_balance(start, D(2026, 4, 19), 0) == 5  # exactly one year
    assert sil_balance(start, D(2027, 4, 19), 2) == 3  # two years, 2 used this year
    assert sil_balance(start, D(2027, 4, 19), 7) == 0  # never negative


def test_leave_dates_are_the_working_days_of_each_leave() -> None:
    holidays = {D(2026, 8, 31): "regular", D(2026, 8, 21): "special"}
    spans = [(D(2026, 8, 20), D(2026, 8, 24)), (D(2026, 8, 31), D(2026, 8, 31))]
    # Sunday the 23rd and the regular holiday are no leave days; the special day is one.
    assert leave_dates(spans, SUNDAY, holidays) == {
        D(2026, 8, 20), D(2026, 8, 21), D(2026, 8, 22), D(2026, 8, 24),
    }  # fmt: skip


def test_an_unworked_regular_holiday_pays_after_a_day_worked_or_on_leave() -> None:
    """National Heroes Day, Monday 31 August 2026; the working day before is Saturday the 29th
    (Sunday the 30th is the rest day)."""
    heroes, saturday = D(2026, 8, 31), D(2026, 8, 29)
    holidays = {heroes: "regular", D(2026, 8, 21): "special"}
    start, end = D(2026, 8, 16), D(2026, 8, 31)

    def paid(worked: set[dt.date], on_leave: set[dt.date] | None = None) -> list[dt.date]:
        return unworked_regular_holidays(start, end, SUNDAY, holidays, worked, on_leave or set())

    assert paid({saturday}) == [heroes]
    assert paid(set(), {saturday}) == [heroes]  # on paid leave the day before
    assert paid({D(2026, 8, 28)}) == []  # absent on the working day before
    assert paid({saturday, heroes}) == []  # worked: paid as worked time (200%) instead
    assert unworked_regular_holidays(start, end, 0, holidays, {saturday}, set()) == []  # rest day


def test_an_unworked_special_day_pays_nothing() -> None:
    holidays = {D(2026, 8, 21): "special"}
    worked = {D(2026, 8, 20)}
    assert (
        unworked_regular_holidays(D(2026, 8, 16), D(2026, 8, 31), SUNDAY, holidays, worked, set())
        == []
    )
