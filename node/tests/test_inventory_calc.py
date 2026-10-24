import datetime as dt
from zoneinfo import ZoneInfo

from mia.agents.inventory_manager.calc import Record, low, order_total, plan

MNL = ZoneInfo("Asia/Manila")
FRIDAY = dt.date(2026, 10, 16)  # tomorrow is a Saturday
CLOSES = dt.time(21, 0)


def saturdays(n: int) -> list[dt.date]:
    """The last n Saturdays before FRIDAY, newest first."""
    return [FRIDAY - dt.timedelta(days=6 + 7 * k) for k in range(n)]


def rec(kind: str, item: str, day: dt.date, hour: int, minute: int = 0) -> Record:
    at = dt.datetime.combine(day, dt.time(hour, minute), MNL)
    return Record(kind, item, at, day)


def test_two_early_sell_outs_in_four_weekdays_bake_more() -> None:
    sat = saturdays(4)
    records = [rec("sold_out", "special", sat[0], 14), rec("sold_out", "special", sat[3], 12)]
    assert plan(records, ["special", "classic"], FRIDAY, CLOSES) == {
        "special": "more",
        "classic": "same",
    }


def test_one_sell_out_or_a_late_one_is_not_enough() -> None:
    sat = saturdays(2)
    records = [rec("sold_out", "special", sat[0], 14), rec("sold_out", "special", sat[1], 19, 30)]
    assert plan(records, ["special"], FRIDAY, CLOSES) == {"special": "same"}


def test_only_the_last_four_same_weekdays_count() -> None:
    sat = saturdays(5)
    records = [rec("count", "ube", d, 10) for d in sat[:4]]
    records += [rec("sold_out", "special", sat[3], 14), rec("sold_out", "special", sat[4], 14)]
    assert plan(records, ["special"], FRIDAY, CLOSES) == {"special": "same"}


def test_two_leftovers_bake_fewer_and_other_weekdays_are_ignored() -> None:
    sat = saturdays(2)
    tuesday = FRIDAY - dt.timedelta(days=3)
    records = [rec("leftover", "classic", d, 20) for d in sat]
    records += [rec("sold_out", "classic", tuesday, 10), rec("leftover", "ube", tuesday, 20)]
    assert plan(records, ["classic", "ube"], FRIDAY, CLOSES) == {
        "classic": "fewer",
        "ube": "same",
    }


def test_no_records_plan_the_same() -> None:
    assert plan([], ["special"], FRIDAY, CLOSES) == {"special": "same"}


def test_low_lists_counts_at_the_reorder_point_and_todays_reports() -> None:
    reorder = {"eggs": 5, "lpg": 1, "flour": 10, "sugar": 5}
    assert low({"eggs": 6, "lpg": 1, "flour": 2}, reorder, {"sugar"}) == ["lpg", "flour", "sugar"]


def test_order_total_needs_every_price() -> None:
    assert order_total([(10, 25000), (4, 3500)]) == 264000
    assert order_total([(30, None), (10, 25000)]) is None


def test_order_total_prices_each_line_on_its_own() -> None:
    assert order_total([(10, 25000), (2, 25000)]) == 300000
