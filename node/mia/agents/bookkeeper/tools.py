"""The bookkeeper's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store. The read helpers below take no actor: a tool checks rights before
it calls them. Each new tool is a manifest entry plus a binding here."""

import datetime as dt
from collections import defaultdict

from sqlmodel import Session, col, select

from mia.agents.base import ToolBinding
from mia.agents.bookkeeper import calc
from mia.agents.bookkeeper.models import CashCount, Deposit, Expense
from mia.agents.sales_supervisor.tools import _live_counts

PETTY = "petty"  # the bank of a petty refill and the source of a petty spend

BINDINGS: list[ToolBinding] = []


def tender_sales(
    session: Session, branch_id: str, tender: str | None, start: dt.date, end: dt.date
) -> int:
    """The branch's live sales amount from start to end (inclusive) paid by tender (None: every
    tender), in minor units."""
    rows = _live_counts(session, [branch_id], start, end)
    return sum(r.amount for r in rows if tender is None or r.tender == tender)


def balance_days(
    session: Session, branch_id: str, upto: dt.date
) -> tuple[dict[dt.date, int], dict[dt.date, int]]:
    """The petty and undeposited cash balances after each business date with a movement up to
    upto (calc.running). Petty: refills (deposits to bank petty) less petty spends.
    Undeposited: counted cash (the latest count of a date wins) less every deposit, petty
    refills included, less cash spends."""
    counts = session.exec(
        select(CashCount)
        .where(CashCount.branch_id == branch_id)
        .order_by(col(CashCount.created_at), col(CashCount.id))
    )
    counted = {c.business_date: c.counted for c in counts}  # later rows overwrite earlier
    refills: dict[dt.date, int] = defaultdict(int)
    out_cash: dict[dt.date, int] = defaultdict(int)
    out_petty: dict[dt.date, int] = defaultdict(int)
    for d in session.exec(select(Deposit).where(Deposit.branch_id == branch_id)):
        out_cash[d.business_date] += d.amount
        if d.bank == PETTY:
            refills[d.business_date] += d.amount
    for e in session.exec(select(Expense).where(Expense.branch_id == branch_id)):
        if e.source == "cash":
            out_cash[e.business_date] += e.amount
        elif e.source == PETTY:
            out_petty[e.business_date] += e.amount
    return calc.running(refills, out_petty, upto), calc.running(counted, out_cash, upto)
