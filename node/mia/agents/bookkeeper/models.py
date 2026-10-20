"""The bookkeeper's tables (agent-owned, prefixed bookkeeper_, data standard rule 9).

Money is integer minor units with a currency; every amount was typed by a person and parsed by
code (rule 7). Sales, supplier orders and payslips are core tables (data standard 1.6)."""

import datetime as dt
from typing import ClassVar

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from mia.core.models import BranchScoped


class CashCount(BranchScoped, table=True):
    """The closing cash count of a business date: counted, expected from the cash sales and
    difference (counted less expected). The latest count of a date wins."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "bookkeeper_cash_counts"

    business_date: dt.date = Field(index=True)
    counted: int
    expected: int
    difference: int
    currency: str = Field(max_length=3)
    counted_by: str = Field(foreign_key="person.id")
    note: str = ""


class Settlement(BranchScoped, table=True):
    """A GCash or Maya settlement for a period, matched to the period's sales by that tender:
    amount received, expected (sales less fee) and fee."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "bookkeeper_settlements"

    provider: str
    period_start: dt.date
    period_end: dt.date
    amount: int
    expected: int
    fee: int
    currency: str = Field(max_length=3)
    matched_by: str = Field(foreign_key="person.id")


class Payout(BranchScoped, table=True):
    """A Grab or Foodpanda payout for a period: amount received, expected (sales less
    commission) and commission."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "bookkeeper_payouts"

    provider: str
    period_start: dt.date
    period_end: dt.date
    amount: int
    expected: int
    commission: int
    currency: str = Field(max_length=3)
    recorded_by: str = Field(foreign_key="person.id")


class Expense(BranchScoped, table=True):
    """An expense of a business date: category, amount, the VAT amount and receipt number when
    typed, source cash, petty or bank, and the approval of one over the expense limit."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "bookkeeper_expenses"

    business_date: dt.date = Field(index=True)
    category: str
    amount: int
    currency: str = Field(max_length=3)
    vat_amount: int | None = None
    receipt_no: str | None = Field(default=None, max_length=32)
    source: str  # cash, petty or bank
    approval_id: str | None = Field(default=None, foreign_key="approval.id")
    recorded_by: str = Field(foreign_key="person.id")


class Deposit(BranchScoped, table=True):
    """Cash taken from the drawer on a business date: to a bank, or to the petty box (bank
    petty, a petty refill)."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "bookkeeper_deposits"

    business_date: dt.date = Field(index=True)
    bank: str
    amount: int
    currency: str = Field(max_length=3)
    reference: str | None = None
    recorded_by: str = Field(foreign_key="person.id")


class TaxFigure(BranchScoped, table=True):
    """The tax figure of a branch, regime and period (vat or percentage): gross sales, taxable
    base, rate (integer percent), input tax and the amount due (negative is an excess carried
    over). One row per branch, regime and period start."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "bookkeeper_tax"
    __table_args__ = (UniqueConstraint("branch_id", "regime", "period_start"),)

    regime: str
    period_start: dt.date
    period_end: dt.date
    gross: int
    taxable: int
    rate: int
    input_tax: int
    due: int
    currency: str = Field(max_length=3)
