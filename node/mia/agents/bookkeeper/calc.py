"""The bookkeeper's numbers as pure code (rule 7): fees and commissions, matching an amount to
the sales it settles, running balances and the monthly profit. No Session and no clock: the
tools load rows and pass plain values in. Money is integer minor units, percents integers."""

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction


def half_up(value: Fraction) -> int:
    """The nearest integer, a half rounded up (toward positive infinity)."""
    return int((value * 2 + 1) // 2)


def percent_of(amount: int, percent: int) -> int:
    """percent of amount in minor units, rounded half up (exact, no float)."""
    return half_up(Fraction(amount * percent, 100))


@dataclass(frozen=True)
class Match:
    """An amount matched to its sales: expected (sales less the cut), the cut (fee or
    commission), the gap (amount less expected) and whether the gap is over the threshold."""

    expected: int
    cut: int
    gap: int
    flagged: bool


def match(amount: int, sales: int, percent: int, threshold: int) -> Match:
    """Match a typed amount to the sales it covers: the cut is percent of sales (half up), the
    expected amount is sales less the cut, flagged only when abs(gap) > threshold. The cash
    count passes percent 0."""
    cut = percent_of(sales, percent)
    expected = sales - cut
    gap = amount - expected
    return Match(expected=expected, cut=cut, gap=gap, flagged=abs(gap) > threshold)


def running(
    ins: Mapping[dt.date, int], outs: Mapping[dt.date, int], upto: dt.date
) -> dict[dt.date, int]:
    """The balance after each date with a movement up to upto (inclusive), oldest first: the
    sum of every in less every out on or before that date."""
    balance, out = 0, {}
    for day in sorted(set(ins) | set(outs)):
        if day > upto:
            break
        balance += ins.get(day, 0) - outs.get(day, 0)
        out[day] = balance
    return out


def days_over(balances: Mapping[dt.date, int], limit: int) -> int:
    """How many of the latest dates in a row have a balance above limit (0 when the latest is
    not above it)."""
    count = 0
    for day in sorted(balances, reverse=True):
        if balances[day] <= limit:
            break
        count += 1
    return count


@dataclass(frozen=True)
class Profit:
    """A cash basis profit: the lines and the profit. cost_of_goods (None while any sold item
    has no cost) and waste at cost are shown, not subtracted (supplier spend paid for them)."""

    sales: int
    fees: int
    expenses: int
    supplier: int
    payroll: int
    cost_of_goods: int | None
    waste: int
    profit: int


def profit(
    *,
    sales: int,
    fees: int,
    expenses: int,
    supplier: int,
    payroll: int,
    cost_of_goods: int | None,
    waste: int,
) -> Profit:
    """Sales less fees and commissions, expenses, supplier spend and payroll (Q90)."""
    return Profit(
        sales=sales,
        fees=fees,
        expenses=expenses,
        supplier=supplier,
        payroll=payroll,
        cost_of_goods=cost_of_goods,
        waste=waste,
        profit=sales - fees - expenses - supplier - payroll,
    )
