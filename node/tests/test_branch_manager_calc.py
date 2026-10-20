"""The branch manager's numbers as pure code: baseline and score, the tip rotation, the nudge,
the best day and the pairing, the strategy engine (one test per strategy) and its guard rails
(one test per rail); and the seeded experiments scored by the same functions."""

import datetime as dt
from dataclasses import asdict, replace

import pytest
from sqlmodel import Session, select

from mia.agents.branch_manager import calc, experiments, tools
from mia.agents.branch_manager import tips as bm_tips
from mia.agents.branch_manager.experiments import BranchNumbers, Day
from mia.agents.branch_manager.models import Experiment, Strategy
from mia.core.models import Branch, Person
from mia.templates.retail import items as retail_items
from mia.templates.retail.models import RetailItem
from tests.conftest import BM_TODAY as TODAY

Ferinos = tuple[Branch, dict[str, Person]]
START = dt.date(2026, 11, 2)  # a Monday
ONE_DAY = dt.timedelta(days=1)


def days_before(n: int) -> dict[dt.date, Day]:
    return {START - dt.timedelta(days=k): (10, 50000) for k in range(1, n + 1)}


def test_baseline_is_the_same_weekdays_of_the_previous_28_days() -> None:
    daily = days_before(29) | {START - dt.timedelta(days=29): (99, 999900)}
    assert experiments.baseline(daily, START, days=14) == experiments.Baseline(28, 280, 1400000)
    three = experiments.baseline(daily, START, days=3)
    assert three is not None and three.days == 12  # Mondays to Wednesdays only


def test_under_seven_baseline_days_is_not_enough_data() -> None:
    assert experiments.baseline(days_before(6), START, days=14) is None


def test_score_is_per_day_percent_rounded_half_up() -> None:
    during = {START + dt.timedelta(days=k): (12, 54000) for k in range(14)}
    out = experiments.score(experiments.Baseline(28, 280, 1400000), during)
    assert (out.units_pct, out.amount_pct, out.days) == (20, 8, 14)
    base = experiments.Baseline(8, 80, 400000)
    assert experiments.score(base, {START: (10, 50250)}).amount_pct == 1
    assert experiments.score(base, {}).units_pct is None  # nothing to compare


def test_a_tip_is_never_repeated_within_30_days() -> None:
    tips = [calc.TipRef("t1", "tip", None), calc.TipRef("t2", "tip", None)]
    assert calc.pick_tip(tips, {"t1": START - dt.timedelta(days=29)}, START) == "t2"
    old = {"t1": START - dt.timedelta(days=30), "t2": START - ONE_DAY}
    assert calc.pick_tip(tips, old, START) == "t1"  # the least recently given goes first
    assert calc.pick_tip(tips, {"t1": START, "t2": START}, START) is None


def test_the_items_tips_come_first_and_another_items_never() -> None:
    tips = [calc.TipRef("t1", "tip", None), calc.TipRef("t9", "tip", "ube")]
    assert calc.pick_tip(tips, {}, START, item_id="ube") == "t9"
    assert calc.pick_tip(tips, {}, START, item_id="special") == "t1"
    assert calc.pick_tip(tips, {"t1": START}, START) is None  # t9 is Ube's


def test_three_misses_in_a_row_and_never_two_nudges_in_a_week() -> None:
    assert calc.nudge_due([True, True, True], None, START, after=3)  # True is a missed day
    assert not calc.nudge_due([True, True, False, True], None, START, after=3)
    assert not calc.nudge_due([True] * 3, START - dt.timedelta(days=6), START, after=3)
    assert calc.nudge_due([True] * 3, START - dt.timedelta(days=7), START, after=3)


def test_a_personal_best_and_the_pairing() -> None:
    amounts = {START - dt.timedelta(days=91): 99999, START - ONE_DAY: 100, START: 200}
    assert calc.personal_best(amounts, START)
    assert not calc.personal_best({START: 200}, START)  # needs one earlier day
    baskets = [frozenset({"a", "b"}), frozenset({"a", "b", "c"}), frozenset({"b", "c"})]
    assert calc.pairing(baskets) == ("a", "b")
    assert calc.pairing([frozenset({"a"})]) is None
    assert calc.improved(5, 4) and not calc.improved(4, 4)


def test_the_suggestion_is_last_years_month_a_bundle_first() -> None:
    classic = RetailItem(name="Classic", price=4000, currency="PHP")
    box = RetailItem(name="Box of 4", price=16000, currency="PHP", components=[classic.id] * 4)
    assert experiments.suggestion({classic.id: 90, box.id: 10}, [classic, box]) is box
    assert experiments.suggestion({classic.id: 90}, [classic, box]) is classic
    assert experiments.suggestion({}, [classic, box]) is None
    assert experiments.suggested_price(4500) == 4000  # 10 percent off is 40.50: whole peso down


# The engine: the seeded catalogue (Task 1's params) over plain items and numbers.
CATALOGUE = {
    key: Strategy(name_key=key, kind=kind, params=params, source=source)
    for key, kind, params, source in bm_tips.STRATEGIES
}


def proposals(key: str, numbers: BranchNumbers, menu: list[RetailItem]) -> list[tuple[str, int]]:
    out = experiments.propose(numbers, menu, [CATALOGUE[key]], START)
    assert all(p.strategy_id == CATALOGUE[key].id for p in out)
    return [(p.item_id, p.to_price) for p in out]


@pytest.fixture
def menu() -> list[RetailItem]:
    classic = RetailItem(name="Classic", price=4000, currency="PHP", cost=2400)
    special = RetailItem(name="Special", price=4500, currency="PHP", cost=2800)
    ube = RetailItem(name="Ube", price=4500, currency="PHP")
    kape = RetailItem(name="Kape", price=2549, currency="PHP")
    box = RetailItem(name="Box of 4", price=16000, currency="PHP", components=[classic.id] * 4)
    return [classic, special, ube, kape, box]


def ids(menu: list[RetailItem]) -> dict[str, str]:
    return {i.name: i.id for i in menu}


def test_charm_tests_a_round_price_one_peso_under(menu: list[RetailItem]) -> None:
    n = ids(menu)
    numbers = BranchNumbers(open_days=14, units={n["Ube"]: 90, n["Classic"]: 50})
    assert proposals("bm.strategy.charm", numbers, menu) == [(n["Ube"], 4400)]
    assert proposals("bm.strategy.charm", numbers, [menu[3]]) == []  # 25.49 is not round


def test_anchor_adds_a_premium_beside_a_one_size_item(menu: list[RetailItem]) -> None:
    n = ids(menu)
    numbers = BranchNumbers(open_days=14, units={n["Classic"]: 99, n["Special"]: 50})
    # Classic has a box, so Special (one size) gets the premium at 20 percent above.
    assert proposals("bm.strategy.anchor", numbers, menu) == [(n["Special"], 5400)]


def test_bundle_prices_the_usual_pair_below_its_sum(menu: list[RetailItem]) -> None:
    n = ids(menu)
    pair = frozenset({n["Classic"], n["Kape"]})
    numbers = BranchNumbers(open_days=14, baskets=[pair, pair, frozenset({n["Ube"]})])
    [p] = experiments.propose(numbers, menu, [CATALOGUE["bm.strategy.bundle"]], START)
    assert (p.kind, p.from_price, p.to_price) == ("bundle", 6549, 5800)  # 10 off, peso down
    assert set(p.rationale["pair"]) == set(pair) and p.rationale["share"] == 66
    rare = replace(numbers, baskets=[pair, *[frozenset({n["Ube"]})] * 3])  # 25 percent
    assert proposals("bm.strategy.bundle", rare, menu) == []


def test_volume_tiers_when_multi_piece_orders_are_common(menu: list[RetailItem]) -> None:
    n = ids(menu)
    numbers = BranchNumbers(open_days=14, order_pieces={n["Classic"]: [1, 3, 5]})
    assert proposals("bm.strategy.volume", numbers, menu) == [(n["Classic"], 3600)]
    few = BranchNumbers(open_days=14, order_pieces={n["Classic"]: [1, 1, 1, 4]})
    assert proposals("bm.strategy.volume", few, menu) == []  # 25 percent


def test_markdown_clears_the_leftover_and_never_goes_below_cost(menu: list[RetailItem]) -> None:
    n = ids(menu)
    left = {START - dt.timedelta(days=k): 4 for k in (1, 3)}
    numbers = BranchNumbers(open_days=14, units={n["Ube"]: 168}, leftovers={n["Ube"]: left})
    # 4 left of 12 sold plus 4 made: 25 percent, capped at 20: 45 to 36 pesos.
    [p] = experiments.propose(numbers, menu, [CATALOGUE["bm.strategy.markdown"]], START)
    assert (p.item_id, p.to_price, p.rationale["off_percent"]) == (n["Ube"], 3600, 20)
    costly = [replace_cost(menu[2], 4000)]
    assert proposals("bm.strategy.markdown", numbers, costly) == [(n["Ube"], 4000)]
    once = BranchNumbers(
        open_days=14, units={n["Ube"]: 168}, leftovers={n["Ube"]: dict([*left.items()][:1])}
    )
    assert proposals("bm.strategy.markdown", once, menu) == []  # one leftover day


def replace_cost(item: RetailItem, cost: int) -> RetailItem:
    return RetailItem(id=item.id, name=item.name, price=item.price, currency="PHP", cost=cost)


def test_increase_on_an_item_that_sells_out(menu: list[RetailItem]) -> None:
    n = ids(menu)
    numbers = BranchNumbers(open_days=14, sold_out_days={n["Special"]: 8, n["Classic"]: 6})
    assert proposals("bm.strategy.increase", numbers, menu) == [(n["Special"], 5000)]
    kape = BranchNumbers(open_days=10, sold_out_days={n["Kape"]: 9})
    # 25.49 up 5 percent is 26.76: the next 5 pesos (30) is past 12 percent, so 27.
    assert proposals("bm.strategy.increase", kape, menu) == [(n["Kape"], 2700)]


def test_seasonal_promotes_last_years_best_seller_ahead(menu: list[RetailItem]) -> None:
    n = ids(menu)
    november = {11: {n["Classic"]: 300, n["Box of 4"]: 20}}
    numbers = BranchNumbers(open_days=14, last_year=november)
    assert proposals("bm.strategy.seasonal", numbers, menu) == [(n["Box of 4"], 14400)]
    early = replace(numbers, last_year={12: november[11]})  # 14 days ahead is still November
    assert proposals("bm.strategy.seasonal", early, menu) == []


def test_decoy_makes_the_box_the_one_to_sell(menu: list[RetailItem]) -> None:
    n = ids(menu)
    [p] = experiments.propose(
        BranchNumbers(open_days=14), menu, [CATALOGUE["bm.strategy.decoy"]], START
    )
    assert (p.item_id, p.to_price, p.rationale["pieces"]) == (n["Box of 4"], 14000, 3)


def test_an_inactive_strategy_proposes_nothing(menu: list[RetailItem]) -> None:
    off = Strategy(name_key="bm.strategy.decoy", kind="price", params={"variants": 3}, source="x")
    off.active = False
    assert experiments.propose(BranchNumbers(open_days=14), menu, [off], START) == []


def test_a_proposal_that_fails_a_rail_falls_to_the_next_item(menu: list[RetailItem]) -> None:
    n = ids(menu)
    numbers = BranchNumbers(
        open_days=14,
        units={n["Ube"]: 90, n["Classic"]: 50},
        since_experiment={n["Ube"]: 10},
    )
    [p] = experiments.propose(numbers, menu, [CATALOGUE["bm.strategy.charm"]], START)
    assert (p.item_id, p.floor, p.ceiling) == (n["Classic"], 3200, 4800)


def test_the_guard_refuses_the_price_in_force() -> None:
    assert experiments.guard(4500, None, 4500, [], None) == "unchanged"


def test_the_guard_refuses_more_than_20_percent_from_the_price() -> None:
    assert experiments.guard(4500, None, 3500, [], None) == "too_far"
    assert experiments.guard(4500, None, 5500, [], None) == "too_far"
    assert experiments.guard(4500, None, 3600, [], None) is None  # exactly 20 percent


def test_the_guard_refuses_a_price_below_cost() -> None:
    assert experiments.guard(4000, 3900, 3800, [], None) == "below_cost"
    assert experiments.guard(4000, 3800, 3800, [], None) is None


def test_the_guard_refuses_steps_that_drift_past_20_percent() -> None:
    assert experiments.guard(5000, None, 5900, [4500], None) == "drift"
    assert experiments.guard(5000, None, 5400, [4500], None) is None


def test_the_guard_refuses_a_second_experiment_on_the_item_within_28_days() -> None:
    assert experiments.guard(4500, None, 4400, [], 27) == "recent_experiment"
    assert experiments.guard(4500, None, 4400, [], 28) is None


def test_seeded_experiments_are_scored_by_the_same_functions(session: Session, bm: Ferinos) -> None:
    running = session.exec(select(Experiment).where(Experiment.status == "running")).one()
    start = running.starts_on
    daily = tools.daily(
        session, running.branch_id, running.item_id, start - dt.timedelta(days=28), start - ONE_DAY
    )
    base = experiments.baseline(daily, start, 14)
    assert base is not None and running.baseline == asdict(base)
    assert (start, running.from_price, running.to_price) == (TODAY - 4 * ONE_DAY, 4500, 5000)
    special = session.get(RetailItem, running.item_id)
    assert special is not None and special.name == "Special"
    assert retail_items.price_on(session, special, running.branch_id, start) == 5000
    assert (
        retail_items.price_on(session, special, running.branch_id, running.ends_on + ONE_DAY)
        == 4500
    )
    during = tools.daily(session, running.branch_id, running.item_id, start, TODAY - ONE_DAY)
    assert {a // u for u, a in during.values()} == {5000}  # counts priced by the price rows
    done = session.exec(select(Experiment).where(Experiment.status == "done")).one()
    assert done.result is not None and done.baseline is not None
    # Its daily totals are seed-only (no counts before the seed's 14 days): the shape is Score's.
    assert set(done.result) == set(
        asdict(experiments.score(experiments.Baseline(**done.baseline), {}))
    )
    assert done.result["days"] == 14
    strategies = {s.id: s.name_key for s in session.exec(select(Strategy))}
    assert strategies[running.strategy_id] == "bm.strategy.increase"
    assert strategies[done.strategy_id] == "bm.strategy.charm" and done.to_price == 3900
