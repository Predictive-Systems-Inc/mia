"""The bookkeeper's read helpers on the seeded books: sales by tender, the petty and
undeposited balances, and the seeded rows recomputed by the same functions."""

import datetime as dt

from sqlmodel import Session, col, select

from mia.agents.bookkeeper import calc, tools
from mia.agents.bookkeeper.models import CashCount, Deposit, Payout, Settlement
from mia.core.models import Branch, Person, SalesCount
from tests.conftest import BK_TODAY

Ferinos = tuple[Branch, dict[str, Person]]


def test_tender_sales_sums_live_counts_by_tender(session: Session, bk: Ferinos) -> None:
    kiosk, day = bk[0].id, BK_TODAY - dt.timedelta(days=1)
    rows = session.exec(
        select(SalesCount).where(SalesCount.branch_id == kiosk, SalesCount.business_date == day)
    ).all()
    by_tender = {t: tools.tender_sales(session, kiosk, t, day, day) for t in ("cash", "gcash")}
    assert by_tender["cash"] == sum(r.amount for r in rows if r.tender == "cash")
    assert tools.tender_sales(session, kiosk, None, day, day) == sum(r.amount for r in rows)


def test_seeded_balances_follow_refills_spends_and_monday_deposits(
    session: Session, bk: Ferinos
) -> None:
    petty, undeposited = tools.balance_days(session, bk[0].id, BK_TODAY)
    assert petty[max(petty)] == 80_000  # a 2,000 peso refill less 1,200 of petty spends
    monday = dt.date(2026, 11, 2)
    assert (
        undeposited[monday]
        == session.exec(
            select(CashCount.counted).where(
                CashCount.branch_id == bk[0].id, CashCount.business_date == monday
            )
        ).one()
    )  # the Monday deposit took everything before it
    assert all(v >= 0 for v in undeposited.values())
    assert calc.days_over(undeposited, 2_000_000) == 0


def test_seeded_books_come_from_the_same_functions(session: Session, bk: Ferinos) -> None:
    counts = session.exec(
        select(CashCount)
        .where(CashCount.branch_id == bk[0].id)
        .order_by(col(CashCount.business_date))
    ).all()
    for c in counts:
        expected = tools.tender_sales(
            session, c.branch_id, "cash", c.business_date, c.business_date
        )
        assert (c.expected, c.difference) == (expected, c.counted - expected)
        assert abs(c.difference) <= 8_000 or c.difference == -15_000
    assert len(counts) == 14 and sum(c.difference == -15_000 for c in counts) == 1
    s = session.exec(select(Settlement).order_by(col(Settlement.period_start))).first()
    assert s is not None
    m = calc.match(
        s.amount,
        tools.tender_sales(session, s.branch_id, s.provider, s.period_start, s.period_end),
        2,
        10_000,
    )
    assert (s.expected, s.fee) == (m.expected, m.cut)
    for p in session.exec(select(Payout)).all():
        sales = tools.tender_sales(session, p.branch_id, p.provider, p.period_start, p.period_end)
        m = calc.match(p.amount, sales, 25, 10_000)
        assert (p.expected, p.commission, p.period_start.weekday()) == (m.expected, m.cut, 0)
    banks = {d.bank for d in session.exec(select(Deposit)).all()}
    assert banks == {"bdo", tools.PETTY}
