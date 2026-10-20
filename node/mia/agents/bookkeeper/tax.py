"""Philippine sales taxes as pure code (rule 7): the dated rate table, quarters and their BIR
deadlines, the sales journal and the quarterly VAT or percentage tax figure.

The rates are dated constants (TABLES_AS_OF) written from memory; verify them with the
accountant before a real return is filed (Q61). Money is integer minor units, rates integer
percents. Q88 assumed: every sale is VAT-able. Q89 assumed: a receipt without a typed VAT
amount carries no input VAT.
"""

import datetime as dt
from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from mia.agents.bookkeeper.calc import half_up

TABLES_AS_OF = "2026-01"
DEADLINE_DAYS = 25  # BIR 2550Q and 2551Q: the 25th day after the quarter's end


@dataclass(frozen=True)
class Rate:
    """A rate in force for a regime from since on (integer percent)."""

    regime: str
    since: dt.date
    percent: int


RATES = (
    Rate("vat", dt.date(2006, 2, 1), 12),
    Rate("percentage", dt.date(2020, 7, 1), 1),
    Rate("percentage", dt.date(2023, 7, 1), 3),
)


def rate_on(regime: str, day: dt.date) -> int:
    """The regime's percent in force on day (the latest row since on or before day). Raises
    LookupError for an unknown regime or a day before its first row."""
    rows = [r for r in RATES if r.regime == regime and r.since <= day]
    if not rows:
        raise LookupError(f"no {regime} rate on {day}")
    return max(rows, key=lambda r: r.since).percent


def quarter_of(day: dt.date) -> tuple[dt.date, dt.date]:
    """The first and last day of the calendar quarter holding day."""
    month = (day.month - 1) // 3 * 3 + 1
    last = month + 2
    return dt.date(day.year, month, 1), dt.date(day.year, last, monthrange(day.year, last)[1])


def deadline(quarter_end: dt.date) -> dt.date:
    """The filing and payment deadline of a quarter: its end plus DEADLINE_DAYS."""
    return quarter_end + dt.timedelta(days=DEADLINE_DAYS)


def journal(rows: Iterable[tuple[dt.date, str, int]]) -> dict[dt.date, dict[str, int]]:
    """The sales journal: gross by day and tender from (day, tender, amount) rows, days sorted."""
    out: dict[dt.date, dict[str, int]] = {}
    for day, tender, amount in sorted(rows, key=lambda r: r[0]):
        by_tender = out.setdefault(day, {})
        by_tender[tender] = by_tender.get(tender, 0) + amount
    return out


@dataclass(frozen=True)
class QuarterTax:
    """A quarter's tax figure. VAT: output tax on VAT-inclusive gross, due output less input
    (negative is an excess carried over). Percentage tax: output on gross, input ignored (0)."""

    regime: str
    start: dt.date
    end: dt.date
    gross: int
    taxable: int
    rate: int
    output_tax: int
    input_tax: int
    due: int


def quarter_tax(regime: str, start: dt.date, gross: int, input_tax: int) -> QuarterTax:
    """The figure of the quarter starting on start at the rate in force on start. VAT: output
    is half up gross times rate over 100 plus rate, taxable gross less output, due output less
    input. Percentage: output and due are half up gross times rate over 100, taxable is gross."""
    first, end = quarter_of(start)
    rate = rate_on(regime, first)
    if regime == "vat":
        output = half_up(Fraction(gross * rate, 100 + rate))
        due = output - input_tax
        return QuarterTax(regime, first, end, gross, gross - output, rate, output, input_tax, due)
    output = half_up(Fraction(gross * rate, 100))
    return QuarterTax(regime, first, end, gross, gross, rate, output, 0, output)
