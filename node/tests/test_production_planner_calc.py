"""The production planner's numbers as pure code (rule 7): the forecast half up, demand, whole
batches and the split per kiosk, the dispatch split, capacity and the batch sheet's costs. Fixed
dates, no Session."""

import datetime as dt

from mia.agents.production_planner import capacity, forecast
from mia.agents.production_planner.tools import production_day
from mia.core.models import Branch
from mia.core.orgconfig import ProductionPlannerSettings

WED = dt.date(2026, 11, 11)


def weeks(*counts: int) -> list[tuple[dt.date, str, int]]:
    return [(WED - dt.timedelta(days=7 * k), "cl", n) for k, n in enumerate(counts, 1)]


def test_the_plan_is_forecast_plus_orders_minus_leftovers_in_batches() -> None:
    daily = forecast.units(
        [
            *weeks(20, 25, 22, 30),
            (WED - dt.timedelta(days=7), "b4", 2),
            (WED - dt.timedelta(days=1), "cl", 99),
        ],
        {"b4": ["cl"] * 4},
    )
    # (28 + 25 + 22 + 30) / 4 = 26.25: the Box of 4 as four Classic, Tuesday's 99 is no Wednesday
    assert forecast.mean_for(daily, "cl", WED) == 26
    line = forecast.plan_line(
        "cl",
        [
            forecast.Kiosk("mall", 26, orders=30, leftover=0),
            forecast.Kiosk("stall", 14, orders=0, leftover=5),
        ],
        batch_yield=48,
        more=False,
    )
    assert (line.batches, line.pieces, [k.demand for k in line.kiosks]) == (2, 96, [56, 9])
    assert [k.pieces for k in line.kiosks] == [87, 9]
    assert forecast.plan_line("cl", [forecast.Kiosk("mall", 26, 30, 0)], 48, more=True).batches == 3


def test_under_two_weekdays_is_not_enough_data() -> None:
    assert forecast.mean_for(forecast.units(weeks(20), {}), "cl", WED) is None
    assert forecast.mean_for(forecast.units(weeks(20, 21), {}), "cl", WED) == 21
    assert forecast.mean_for(forecast.units(weeks(20, 21, 0, 0, 50), {}), "cl", WED) == 10  # day 35
    assert (
        forecast.Kiosk("x", None, orders=12, leftover=0).demand,
        forecast.Kiosk("x", 2, 0, 5).demand,
    ) == (12, 0)


def test_the_surplus_goes_to_the_larger_forecast_or_evenly_without_any() -> None:
    def pieces(*kiosks: forecast.Kiosk, batches: int | None = None) -> list[int]:
        return [k.pieces for k in forecast.plan_line("cl", kiosks, 48, False, batches).kiosks]

    k = forecast.Kiosk
    assert pieces(k("a", 10, 0, 0), k("b", 10, 0, 0)) == [38, 10]  # a tie: the first
    assert pieces(k("a", 5, 0, 0), k("b", 10, 0, 0)) == [5, 43]
    assert pieces(k("a", None, 0, 0), k("b", None, 0, 0), batches=3) == [72, 72]
    assert pieces(k("a", None, 30, 0), k("b", None, 0, 0), batches=1) == [39, 9]
    assert pieces(k("a", None, 0, 0), k("b", 10, 0, 0)) == [0, 48]  # one None: not even
    assert pieces(k("a", 40, 0, 0), k("b", 30, 0, 0), batches=1) == [18, 30]  # fewer than asked
    assert pieces(k("a", None, 0, 0), batches=0) == [0]


def test_order_pieces_expand_bundles() -> None:
    lines = [{"item_id": "b4", "quantity": 2}, {"item_id": "cl", "quantity": 3}]
    assert forecast.order_pieces(lines, {"b4": ["cl"] * 4, "cl": []}) == {"cl": 11}


def test_a_short_yield_comes_off_the_larger_kiosk_first() -> None:
    split = forecast.dispatch_split
    assert (
        split(90, {"mall": 87, "stall": 9}),
        split(100, {"mall": 87, "stall": 9}),
        split(1, {"mall": 3, "stall": 2}),
    ) == ({"mall": 81, "stall": 9}, {"mall": 91, "stall": 9}, {"mall": 0, "stall": 1})
    assert (split(0, {}), split(136, {"mall": 72, "stall": 72})) == ({}, {"mall": 64, "stall": 72})


def test_capacity_minutes_are_ovens_times_the_window_less_planned_batches() -> None:
    assert (
        capacity.minutes_free(2, dt.time(3), dt.time(9), [(6, 45), (2, 30)]),
        capacity.minutes_free(2, dt.time(3), dt.time(9), [(17, 45)]),
        capacity.batches_free(390, 45),
    ) == (390, 0, 8)
    assert capacity.minutes_free(1, dt.time(22), dt.time(2), []) == 240  # past midnight


def test_a_sheet_costs_each_line_and_the_piece_half_up() -> None:
    s = forecast.sheet(
        [("rf", 2000), ("egg", 1000), ("coco", 6000)],
        {"rf": 6500, "egg": 25000, "coco": 3500},
        batches=2,
        batch_yield=48,
    )
    assert ([x.quantity_milli for x in s.lines], [x.cost for x in s.lines]) == (
        [4000, 2000, 12000],
        [26000, 50000, 42000],
    )
    assert (s.cost_per_batch, s.cost_per_piece) == (59000, 1229)
    gap = forecast.sheet([("rf", 2000), ("x", 500)], {"rf": 6500, "x": None}, 1, 48)
    assert ([x.cost for x in gap.lines], gap.cost_per_batch, gap.cost_per_piece) == (
        [13000, None],
        None,
        None,
    )
    assert (forecast.line_cost(333, 6500), forecast.yield_percent(45, 48)) == (2165, 94)
    assert forecast.yield_percent(0, 0) is None


def test_the_production_day_turns_at_the_end_of_production() -> None:
    comm = Branch(organisation_id="o", name="Commissary", timezone="Asia/Manila")
    s = ProductionPlannerSettings()
    mnl = dt.timezone(dt.timedelta(hours=8))
    days = [
        production_day(comm, s, dt.datetime(2026, 11, 10, h, 59, tzinfo=mnl)) for h in (0, 8, 9)
    ]
    assert days == [WED - dt.timedelta(days=1)] * 2 + [WED]
    assert (
        production_day(comm, s, dt.datetime(2026, 11, 10, 18, 0, tzinfo=dt.UTC)) == WED
    )  # 02:00 local
