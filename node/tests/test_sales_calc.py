import datetime as dt
from zoneinfo import ZoneInfo

from mia.agents.sales_supervisor import calc

MNL = ZoneInfo("Asia/Manila")


NINE, NINE_PM, ELEVEN_PM = dt.time(9, 0), dt.time(21, 0), dt.time(23, 0)


def _day(hour: int, minute: int, closed_yesterday: dt.time) -> dt.date:
    at = dt.datetime(2026, 10, 20, hour, minute, tzinfo=MNL)
    return calc.business_date(at, "Asia/Manila", NINE, closed_yesterday)


def test_the_evening_after_closing_is_today() -> None:
    assert _day(21, 30, NINE_PM) == dt.date(2026, 10, 20)
    assert _day(15, 0, NINE_PM) == dt.date(2026, 10, 20)


def test_just_after_midnight_after_a_late_closing_is_yesterday() -> None:
    assert _day(0, 30, ELEVEN_PM) == dt.date(2026, 10, 19)
    assert _day(0, 59, ELEVEN_PM) == dt.date(2026, 10, 19)


def test_two_hours_after_yesterdays_closing_it_is_today() -> None:
    assert _day(1, 0, ELEVEN_PM) == dt.date(2026, 10, 20)
    assert _day(8, 0, ELEVEN_PM) == dt.date(2026, 10, 20)
    assert _day(0, 30, NINE_PM) == dt.date(2026, 10, 20)


def test_from_the_opening_it_is_today() -> None:
    at = dt.datetime(2026, 10, 20, 0, 30, tzinfo=MNL)
    assert calc.business_date(at, "Asia/Manila", dt.time(0, 15), ELEVEN_PM) == dt.date(2026, 10, 20)


def test_business_date_uses_the_branch_time_zone() -> None:
    at = dt.datetime(2026, 10, 19, 16, 30, tzinfo=dt.UTC)  # 00:30 on the 20th in Manila
    assert calc.business_date(at, "Asia/Manila", NINE, ELEVEN_PM) == dt.date(2026, 10, 19)


def test_month_target_share_uses_open_days() -> None:
    target = calc.Target(period="month", starts_on=dt.date(2026, 10, 1), amount=310000)
    weekdays_only = lambda d: d.weekday() < 5
    assert calc.day_share(target, dt.date(2026, 10, 19), weekdays_only) == round(310000 / 22)
    assert calc.day_share(target, dt.date(2026, 11, 2), weekdays_only) is None


def test_day_target_applies_to_its_day_only() -> None:
    target = calc.Target(period="day", starts_on=dt.date(2026, 10, 19), amount=3500)
    assert calc.day_share(target, dt.date(2026, 10, 19), lambda d: True) == 3500
    assert calc.day_share(target, dt.date(2026, 10, 20), lambda d: True) is None


def test_totals_skip_superseded_rows() -> None:
    rows = [
        calc.Count(item_id="a", quantity=3, amount=13500, superseded_by="x"),
        calc.Count(item_id="a", quantity=4, amount=18000, superseded_by=None),
        calc.Count(item_id="b", quantity=1, amount=4000, superseded_by=None),
    ]
    assert calc.totals(rows) == {"a": (4, 18000), "b": (1, 4000)}


def test_compare_percent() -> None:
    assert calc.compare(1200, 1000) == 20
    assert calc.compare(800, 1000) == -20
    assert calc.compare(800, None) is None
    assert calc.compare(800, 0) is None


def test_month_share_rounds_half_up() -> None:
    target = calc.Target(period="month", starts_on=dt.date(2026, 10, 1), amount=5)
    two_days = lambda d: d.day in (1, 2)
    assert calc.day_share(target, dt.date(2026, 10, 1), two_days) == 3
