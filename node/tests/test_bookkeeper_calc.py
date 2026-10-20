"""The bookkeeper's numbers as pure code: fees half up, matching with a threshold, running
balances, the cash basis profit and the dated VAT and percentage tax table."""

import datetime as dt

import pytest

from mia.agents.bookkeeper import calc, tax

OCT_1, D = dt.date(2026, 10, 1), [dt.date(2026, 10, 30) + dt.timedelta(days=k) for k in range(3)]


def test_a_fee_is_a_percent_rounded_half_up() -> None:
    assert (calc.percent_of(3_275, 2), calc.percent_of(3_225, 2), calc.percent_of(890_000, 25)) == (
        66,
        65,
        222_500,
    )


def test_a_match_flags_a_gap_beyond_the_threshold_only() -> None:
    assert calc.match(320_000, 330_000, 2, 10_000) == calc.Match(
        expected=323_400, cut=6_600, gap=-3_400, flagged=False
    )
    assert calc.match(1_234_500, 1_245_000, 0, 10_000).flagged
    assert not calc.match(1_235_000, 1_245_000, 0, 10_000).flagged


def test_running_balances_and_days_over_the_limit() -> None:
    run = calc.running({D[0]: 1_500_000, D[1]: 1_000_000, D[2]: 500_000}, {D[1]: 200_000}, D[2])
    assert run == {D[0]: 1_500_000, D[1]: 2_300_000, D[2]: 2_800_000}
    assert calc.days_over(run, 2_000_000) == 2
    assert calc.running({D[0]: 100, D[2]: 100}, {}, D[1]) == {D[0]: 100}
    assert calc.days_over({D[0]: 3_000_000, D[1]: 100}, 2_000_000) == 0


def test_profit_subtracts_fees_expenses_supplier_and_payroll() -> None:
    p = calc.profit(
        sales=10_000_000,
        fees=300_000,
        expenses=1_000_000,
        supplier=2_500_000,
        payroll=3_000_000,
        cost_of_goods=None,
        waste=40_000,
    )
    assert (p.profit, p.waste, p.cost_of_goods) == (3_200_000, 40_000, None)


def test_the_dated_table_picks_the_rate_in_force() -> None:
    assert (
        tax.rate_on("vat", OCT_1),
        tax.rate_on("percentage", dt.date(2022, 1, 1)),
        tax.rate_on("percentage", OCT_1),
    ) == (12, 1, 3)
    assert (
        tax.quarter_tax("percentage", OCT_1, 224_000, input_tax=5_000).due,
        tax.quarter_of(dt.date(2026, 11, 3)),
    ) == (6_720, (OCT_1, dt.date(2026, 12, 31)))
    assert tax.quarter_of(dt.date(2024, 2, 29)) == (dt.date(2024, 1, 1), dt.date(2024, 3, 31))
    with pytest.raises(LookupError):
        tax.rate_on("percentage", dt.date(2020, 6, 30))


def test_quarterly_vat_is_computed_from_the_journal_and_receipts() -> None:
    rows = [
        (OCT_1, "cash", 100_000),
        (OCT_1, "gcash", 12_000),
        (dt.date(2026, 11, 2), "grab", 112_000),
    ]
    assert tax.journal(rows)[OCT_1] == {"cash": 100_000, "gcash": 12_000}
    out = tax.quarter_tax("vat", OCT_1, sum(a for *_, a in rows), input_tax=5_000)
    assert (out.rate, out.taxable, out.output_tax, out.due, tax.deadline(out.end)) == (
        12,
        200_000,
        24_000,
        19_000,
        dt.date(2027, 1, 25),
    )
    assert tax.quarter_tax("vat", OCT_1, 112_000, input_tax=20_000).due == -8_000  # carried over
