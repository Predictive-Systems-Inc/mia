import datetime as dt
from zoneinfo import ZoneInfo

from mia.agents.sales_supervisor import calc

MNL = ZoneInfo("Asia/Manila")


def test_business_date_is_the_local_date() -> None:
    at = dt.datetime(2026, 10, 19, 14, 0, tzinfo=dt.UTC)  # 22:00 Manila
    assert calc.business_date(at, "Asia/Manila", dt.time(21, 0)) == (dt.date(2026, 10, 19), True)


def test_after_two_hours_past_closing_it_is_no_longer_ambiguous() -> None:
    at = dt.datetime(2026, 10, 19, 23, 30, tzinfo=MNL)
    assert calc.business_date(at, "Asia/Manila", dt.time(21, 0)) == (dt.date(2026, 10, 19), False)


def test_before_closing_is_not_ambiguous() -> None:
    at = dt.datetime(2026, 10, 19, 15, 0, tzinfo=MNL)
    assert calc.business_date(at, "Asia/Manila", dt.time(21, 0)) == (dt.date(2026, 10, 19), False)


def test_just_after_midnight_counts_as_after_a_late_closing() -> None:
    at = dt.datetime(2026, 10, 20, 0, 30, tzinfo=MNL)
    assert calc.business_date(at, "Asia/Manila", dt.time(23, 0)) == (dt.date(2026, 10, 20), True)


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


def test_a_stated_total_counts_only_when_close_to_the_sum() -> None:
    assert calc.reconcile_total(10000, None) == 10000
    assert calc.reconcile_total(10000, 10500) == 10500
    assert calc.reconcile_total(10000, 9500) == 9500
    assert calc.reconcile_total(10000, 10501) == 10000
    assert calc.reconcile_total(10000, 5000) == 10000


def test_after_midnight_uses_yesterdays_closing_time() -> None:
    monday_early = dt.datetime(2026, 10, 19, 0, 30, tzinfo=MNL)  # Sunday closed at 23:30
    late_sunday = calc.business_date(monday_early, "Asia/Manila", dt.time(21, 0), dt.time(23, 30))
    assert late_sunday == (dt.date(2026, 10, 19), True)
    assert calc.business_date(monday_early, "Asia/Manila", dt.time(21, 0), dt.time(21, 0)) == (
        dt.date(2026, 10, 19),
        False,
    )


def test_month_share_rounds_half_up() -> None:
    target = calc.Target(period="month", starts_on=dt.date(2026, 10, 1), amount=5)
    two_days = lambda d: d.day in (1, 2)
    assert calc.day_share(target, dt.date(2026, 10, 1), two_days) == 3
