import datetime as dt

from mia.agents.hr_officer.calendar import (
    cutoff,
    leave_days,
    next_cutoff_end,
    payday,
    previous_cutoff,
    sil_balance,
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


def test_sil_balance_pro_rata_and_never_negative() -> None:
    start = D(2025, 4, 19)
    assert sil_balance(start, D(2026, 4, 18), 0) == 0  # a day short of one year
    assert sil_balance(start, D(2026, 4, 19), 0) == 0  # the year done, no month yet
    assert sil_balance(start, D(2026, 10, 19), 0) == 2  # six months: 5 * 6 // 12
    assert sil_balance(start, D(2026, 10, 18), 0) == 2  # five months: 25 // 12
    assert sil_balance(start, D(2027, 3, 19), 1) == 3  # eleven months: 4, one used
    assert sil_balance(start, D(2026, 10, 19), 5) == 0
