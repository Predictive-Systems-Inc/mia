"""The bookkeeper's read helpers on the seeded books (sales by tender, the petty and
undeposited balances, the seeded rows recomputed by the same functions), then the eleven tools
behind RBAC and the large expense approval with its handlers (negative tests first; the clock
pinned through bk_pin, never the wall clock)."""

import datetime as dt
import json
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.bookkeeper import MANIFEST, calc, tools
from mia.agents.bookkeeper.models import (
    CashCount,
    Deposit,
    Expense,
    Payout,
    Settlement,
    TaxFigure,
)
from mia.agents.bookkeeper.tools import (
    BalancesInput,
    CashCountInput,
    DepositInput,
    ExpenseInput,
    JournalInput,
    PayoutInput,
    ProfitInput,
    SettlementInput,
    TaxInput,
)
from mia.core import approvals, orgconfig, store
from mia.core.db import utcnow
from mia.core.models import (
    Actor,
    Approval,
    Branch,
    Event,
    Message,
    Payslip,
    Person,
    SalesCount,
    Thread,
)
from mia.core.money import format_money
from mia.core.rbac import PermissionDenied
from mia.i18n import t
from tests.conftest import BK_TODAY, Pin, single_kiosks
from tests.test_sales_tools import stall

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


# ---- the tools behind rbac and the large expense approval (Task 4) -------------------------

LIMIT = 500_000
OCTOBER = dt.date(2026, 10, 1)
ONE_DAY = dt.timedelta(days=1)
YESTERDAY = BK_TODAY - ONE_DAY
MNL = ZoneInfo("Asia/Manila")
BINDING = {b.tool_id: b for b in tools.BINDINGS}


def deps_for(session: Session, person: Person) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=BK_TODAY,
        lang=person.language or "en",
        manifest=MANIFEST,
    )


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), MNL)


def decide(session: Session, approval_id: str, who: Person, outcome: str) -> Approval:
    return approvals.decide(
        session, approval_id, Actor.person(who), outcome, stepped_up_at=approvals.utcnow()
    )


def expenses(session: Session) -> list[Expense]:
    return list(session.exec(select(Expense)).all())


def told(session: Session, person: Person) -> list[str]:
    threads = select(Thread.id).where(Thread.person_id == person.id)
    rows = session.exec(select(Message).where(col(Message.thread_id).in_(threads))).all()
    return [m.text for m in rows]


def expense(session: Session, who: Person, amount: int, call: str = "x1") -> dict[str, Any]:
    tool = "record_large_expense" if amount > LIMIT else "record_expense"
    args = ExpenseInput(category="repairs", amount=amount, receipt_no="88")
    return call_tool(deps_for(session, who), BINDING[f"{MANIFEST.id}.{tool}"], args, call)


def test_the_bindings_are_the_manifest_tools() -> None:
    assert {b.tool_id for b in tools.BINDINGS} == {t.id for t in MANIFEST.tools}
    assert MANIFEST.tool(tools.LARGE_EXPENSE).risk == "money"
    assert MANIFEST.tool(f"{MANIFEST.id}.monthly_profit").sensitive


def test_an_expense_over_the_limit_cannot_be_recorded_directly(
    session: Session, bk: Ferinos
) -> None:
    n = len(expenses(session))
    out = call_tool(
        deps_for(session, bk[1]["Marites"]),
        BINDING[f"{MANIFEST.id}.record_expense"],
        ExpenseInput(category="repairs", amount=LIMIT + 1),
        "x0",
    )
    assert out["status"] == "invalid" and len(expenses(session)) == n
    with pytest.raises(LookupError, match="over_limit"):  # nor around the guard
        tools.record_expense(
            deps_for(session, bk[1]["Marites"]),
            ExpenseInput(category="rent", amount=LIMIT + 1),
            "x",
        )
    petty = tools.PettyInput(kind="spend", amount=LIMIT + 1)
    assert (
        call_tool(
            deps_for(session, bk[1]["Marites"]), BINDING[f"{MANIFEST.id}.record_petty"], petty, "x3"
        )["status"]
        == "invalid"
    )
    assert len(expenses(session)) == n


def test_a_large_expense_never_runs_without_its_approval(session: Session, bk: Ferinos) -> None:
    with pytest.raises(LookupError):
        tools.record_large_expense(
            deps_for(session, bk[1]["Marites"]),
            ExpenseInput(category="repairs", amount=LIMIT + 1, business_date=BK_TODAY),
            "x",
        )
    assert expense(session, bk[1]["Marites"], LIMIT, "x2").get("status", "ok") == "ok"  # no refusal
    under = call_tool(
        deps_for(session, bk[1]["Marites"]),
        BINDING[tools.LARGE_EXPENSE],
        ExpenseInput(category="repairs", amount=LIMIT),
        "x3",
    )
    assert under["status"] == "invalid" and "under_limit" in under["message"]


def test_a_clerk_cannot_record_an_expense(session: Session, bk: Ferinos) -> None:
    assert expense(session, bk[1]["Ana"], 12_000)["status"] == "denied"
    assert expense(session, bk[1]["Ana"], LIMIT + 1)["status"] == "denied"


def test_a_supervisor_cannot_decide_their_own_large_expense(session: Session, bk: Ferinos) -> None:
    out = expense(session, bk[1]["Marites"], LIMIT + 1)
    with pytest.raises(approvals.ApprovalError):
        decide(session, out["approval_id"], bk[1]["Marites"], "approved")


def test_a_supervisor_never_sees_a_payslip_total(session: Session, bk: Ferinos) -> None:
    out = call_tool(
        deps_for(session, bk[1]["Marites"]),
        BINDING[f"{MANIFEST.id}.monthly_profit"],
        ProfitInput(month=OCTOBER),
        "p1",
    )
    assert out["status"] == "denied" and "payroll" not in tools.BalancesOut.model_fields
    with pytest.raises(PermissionDenied):
        tools.monthly_profit(deps_for(session, bk[1]["Marites"]), ProfitInput(month=OCTOBER), "p")


def test_a_supervisor_reads_their_branch_only(session: Session, bk: Ferinos) -> None:
    single_kiosks(session)  # D50: no supervisor is assigned to the other kiosk here
    with pytest.raises(PermissionDenied):
        tools.balances(
            deps_for(session, bk[1]["Marites"]), BalancesInput(branch_id=stall(session).id), "b1"
        )
    assert (
        tools.balances(
            deps_for(session, bk[1]["Rosa"]), BalancesInput(branch_id=stall(session).id), "b2"
        ).branch_id
        == stall(session).id
    )


def test_an_expense_over_the_limit_waits_for_an_approval(session: Session, bk: Ferinos) -> None:
    n = len(expenses(session))
    out = expense(session, bk[1]["Marites"], LIMIT + 1)
    assert out["status"] == "approval_required" and len(expenses(session)) == n
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None and approval.channel == "app_only"
    assert approval.evidence["input"]["business_date"] == BK_TODAY.isoformat()
    assert expense(session, bk[1]["Marites"], LIMIT, "x2").get("status", "ok") == "ok"  # no refusal


def test_the_approved_expense_is_the_one_requested(session: Session, bk: Ferinos) -> None:
    out = expense(session, bk[1]["Marites"], 750_000)
    decide(session, out["approval_id"], bk[1]["Rosa"], "approved")
    (row,) = session.exec(select(Expense).where(Expense.approval_id == out["approval_id"])).all()
    assert (row.amount, row.category, row.receipt_no, row.recorded_by) == (
        750_000, "repairs", "88", bk[1]["Marites"].id,
    )  # fmt: skip
    assert len(told(session, bk[1]["Marites"])) == 1  # bk.expense.approved
    deps = deps_for(session, bk[1]["Marites"])
    deps.approved = {out["approval_id"]}
    args = ExpenseInput(category="repairs", amount=750_000, business_date=BK_TODAY)
    assert tools.record_large_expense(deps, args, "again").id == row.id  # one row per approval


def test_an_owners_own_large_expense_is_decided_by_the_owner_with_step_up(
    session: Session, bk: Ferinos
) -> None:
    out = expense(session, bk[1]["Rosa"], 750_000)
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(session, out["approval_id"], Actor.person(bk[1]["Rosa"]), "approved")
    decide(session, out["approval_id"], bk[1]["Rosa"], "approved")
    stmt = select(Expense).where(Expense.approval_id == out["approval_id"])
    assert session.exec(stmt).one().amount == 750_000


def test_the_approval_checks_the_limit_again(
    session: Session, bk: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = expense(session, bk[1]["Marites"], 750_000)
    raised = orgconfig.load().model_copy(
        update={"bookkeeper": orgconfig.BookkeeperSettings(expense_limit=1_000_000)}
    )
    monkeypatch.setattr(orgconfig, "load", lambda org=None: raised)
    with pytest.raises(LookupError, match="under_limit"):
        decide(session, out["approval_id"], bk[1]["Rosa"], "approved")
    session.rollback()
    approvals.close_refused(session, out["approval_id"], Actor.person(bk[1]["Rosa"]), "under_limit")
    assert (
        session.exec(select(Expense).where(Expense.approval_id == out["approval_id"])).all() == []
    )
    assert session.get(Approval, out["approval_id"]).status == "expired"
    assert len(told(session, bk[1]["Marites"])) == 1  # bk.expense.expired


def test_a_large_expense_expiring_at_the_decision_tells_the_requester(
    session: Session, bk: Ferinos
) -> None:
    out = expense(session, bk[1]["Marites"], 750_000)
    row = session.get(Approval, out["approval_id"])
    assert row is not None
    system, past = Actor.system(row.branch_id), {"expires_at": utcnow() - dt.timedelta(seconds=1)}
    row = approvals.expire_if_due(session, store.update(session, row, past, system), system)
    assert row.status == "escalated"
    store.update(session, row, past, system)  # past the escalation's TTL too
    with pytest.raises(approvals.ApprovalError, match="expired"):
        decide(session, row.id, bk[1]["Rosa"], "approved")
    marites = bk[1]["Marites"]
    lang = marites.language or "en"
    expired = t(
        "bk.expense.expired",
        lang,
        amount=format_money(750_000, "PHP", lang),
        category=t("bk.category.repairs", lang),
    )
    assert told(session, marites) == [expired]
    assert session.exec(select(Expense).where(Expense.approval_id == row.id)).all() == []


def test_a_rejected_large_expense_writes_nothing_and_tells_the_requester(
    session: Session, bk: Ferinos
) -> None:
    n = len(expenses(session))
    out = expense(session, bk[1]["Marites"], 750_000)
    decide(session, out["approval_id"], bk[1]["Rosa"], "rejected")
    assert len(expenses(session)) == n and len(told(session, bk[1]["Marites"])) == 1


def test_a_closing_count_uses_the_branch_business_date(
    session: Session, bk: Ferinos, bk_pin: Pin
) -> None:
    bk_pin(at(BK_TODAY, 15, 0))  # open: today's count
    out = tools.record_cash_count(
        deps_for(session, bk[1]["Marites"]), CashCountInput(counted=100_000), "c1"
    )
    assert out.business_date == BK_TODAY


def test_a_count_after_midnight_belongs_to_the_closing_date(
    session: Session, bk: Ferinos, bk_pin: Pin
) -> None:
    """The Mall kiosk closes at 21:00; a count at 00:40 (the reminder still asks until the next
    opening) is Monday's, against Monday's cash sales: no false alert."""
    monday = BK_TODAY - ONE_DAY
    cash = tools.tender_sales(session, bk[0].id, "cash", monday, monday)
    assert cash > 0
    bk_pin(at(BK_TODAY, 0, 40))
    out = tools.record_cash_count(
        deps_for(session, bk[1]["Marites"]), CashCountInput(counted=cash), "c1"
    )
    assert (out.business_date, out.expected, out.flagged) == (monday, cash, False)
    assert told(session, bk[1]["Rosa"]) == []
    bk_pin(at(BK_TODAY, 8, 59))  # still before the opening
    late = tools.record_cash_count(
        deps_for(session, bk[1]["Marites"]), CashCountInput(counted=cash), "c2"
    )
    assert late.business_date == monday


def test_a_bill_paid_from_the_drawer_before_closing_is_no_short(
    session: Session, bk: Ferinos, bk_pin: Pin
) -> None:
    """Expected cash is the day's cash sales less the cash spends and petty refills of the
    date (tools.drawer_out, Q99), and the undeposited balance does not take them out again."""
    bk_pin(at(BK_TODAY, 15, 0))
    deps = deps_for(session, bk[1]["Marites"])
    before = tools.balances(deps, BalancesInput(), "b0").undeposited
    tools.record_expense(deps, ExpenseInput(category="utilities", amount=15_000), "e1")
    tools.record_petty(deps, tools.PettyInput(kind="refill", amount=5_000), "p1")
    from tests.test_bookkeeper_chat import counted_today

    cash = counted_today(session, bk)
    bk_pin(at(BK_TODAY, 21, 30))
    out = tools.record_cash_count(deps, CashCountInput(counted=cash - 20_000), "c1")
    assert (out.expected, out.difference, out.flagged) == (cash - 20_000, 0, False)
    assert told(session, bk[1]["Rosa"]) == []
    after = tools.balances(deps, BalancesInput(), "b1").undeposited
    assert after == before + cash - 20_000  # the count holds what is left, once


def test_a_short_count_tells_the_leads_urgent(session: Session, bk: Ferinos, bk_pin: Pin) -> None:
    bk_pin(at(BK_TODAY, 21, 30))
    deps = deps_for(session, bk[1]["Marites"])
    expected = tools.tender_sales(session, bk[0].id, "cash", BK_TODAY, BK_TODAY)
    out = tools.record_cash_count(deps, CashCountInput(counted=expected + 20_000), "c1")
    assert (out.difference, out.flagged) == (20_000, True)
    assert len(told(session, bk[1]["Rosa"])) == 1 and told(session, bk[1]["Ana"]) == []
    within = tools.record_cash_count(deps, CashCountInput(counted=expected + 10_000), "c2")
    assert not within.flagged
    _, withdrawn = told(session, bk[1]["Rosa"])  # the corrected count withdraws the alert
    assert withdrawn == t(
        "bk.count.withdrawn",
        bk[1]["Rosa"].language or "en",
        branch=bk[0].name,
        date=BK_TODAY.isoformat(),
        counted=format_money(expected + 10_000, "PHP", bk[1]["Rosa"].language or "en"),
    )


def test_a_settlement_and_a_payout_are_matched_with_the_cut(session: Session, bk: Ferinos) -> None:
    deps = deps_for(session, bk[1]["Marites"])
    sales = tools.tender_sales(session, bk[0].id, "gcash", YESTERDAY, YESTERDAY)
    s = tools.record_settlement(
        deps, SettlementInput(provider="gcash", amount=sales, start=YESTERDAY, end=YESTERDAY), "s"
    )
    assert (s.sales, s.cut, s.gap) == (sales, calc.percent_of(sales, 2), calc.percent_of(sales, 2))
    p = tools.record_payout(
        deps, PayoutInput(provider="grab", amount=0, start=OCTOBER, end=YESTERDAY), "p"
    )
    grab = tools.tender_sales(session, bk[0].id, "grab", OCTOBER, YESTERDAY)
    assert p.cut == calc.percent_of(grab, 25) and p.gap == -(grab - p.cut)
    with pytest.raises(LookupError):
        tools.record_payout(
            deps, PayoutInput(provider="grab", amount=0, start=YESTERDAY, end=OCTOBER), "p2"
        )


def test_petty_and_deposits_move_the_balances(session: Session, bk: Ferinos, bk_pin: Pin) -> None:
    bk_pin(at(BK_TODAY, 15, 0))
    deps = deps_for(session, bk[1]["Marites"])
    before = tools.balances(deps, BalancesInput(), "b")
    spend = tools.record_petty(deps, tools.PettyInput(kind="spend", amount=50_000), "p1")
    assert (spend.balance, spend.below_floor) == (before.petty - 50_000, True)
    refill = tools.record_petty(deps, tools.PettyInput(kind="refill", amount=20_000), "p2")
    assert refill.balance == before.petty - 30_000
    dep = tools.record_deposit(deps, DepositInput(bank="bdo", amount=10_000), "d1")
    assert dep.undeposited == before.undeposited - 20_000 - 10_000  # the refill left the drawer


def test_the_journal_and_the_quarter_tax_come_from_the_counts(
    session: Session, bk: Ferinos
) -> None:
    rosa = deps_for(session, bk[1]["Rosa"])
    journal = tools.sales_journal(rosa, JournalInput(month=OCTOBER), "j")
    assert journal.total == tools.tender_sales(
        session, bk[0].id, None, OCTOBER, dt.date(2026, 10, 31)
    )
    out = tools.tax_quarter(rosa, TaxInput(quarter_start=OCTOBER), "t")
    assert {b.branch_id for b in out.branches} == {bk[0].id, stall(session).id}
    kiosk = next(b for b in out.branches if b.branch_id == bk[0].id)
    gross = tools.tender_sales(session, bk[0].id, None, OCTOBER, dt.date(2026, 12, 31))
    assert (kiosk.gross, kiosk.rate, kiosk.deadline) == (gross, 12, dt.date(2027, 1, 25))
    assert kiosk.due == kiosk.output_tax - kiosk.input_tax and kiosk.input_tax > 0
    denied = call_tool(
        deps_for(session, bk[1]["Marites"]), BINDING[f"{MANIFEST.id}.tax_quarter"], TaxInput(), "t2"
    )
    assert denied["status"] == "denied"


def test_the_previous_quarters_vat_excess_carries_into_the_next(
    session: Session, bk: Ferinos
) -> None:
    rosa = deps_for(session, bk[1]["Rosa"])
    kiosk = bk[0].id
    plain = next(
        b for b in tools.tax_quarter(rosa, TaxInput(quarter_start=OCTOBER), "t0").branches
        if b.branch_id == kiosk
    )  # fmt: skip
    july = dt.date(2026, 7, 1)
    excess = TaxFigure(
        branch_id=kiosk, regime="vat", period_start=july, period_end=dt.date(2026, 9, 30),
        gross=112_000, taxable=100_000, rate=12, input_tax=20_000, due=-8_000, currency="PHP",
    )  # fmt: skip
    store.insert(session, excess, Actor.system(kiosk), action=f"{MANIFEST.id}.tax_figured")
    carried = next(
        b for b in tools.tax_quarter(rosa, TaxInput(quarter_start=OCTOBER), "t1").branches
        if b.branch_id == kiosk
    )  # fmt: skip
    assert (carried.input_tax, carried.due) == (plain.input_tax + 8_000, plain.due - 8_000)
    assert carried.due == carried.output_tax - carried.input_tax


def test_monthly_profit_sums_payslip_totals_off_the_chain(session: Session, bk: Ferinos) -> None:
    out = call_tool(
        deps_for(session, bk[1]["Rosa"]),
        BINDING[f"{MANIFEST.id}.monthly_profit"],
        ProfitInput(month=OCTOBER),
        "p1",
    )
    kiosk = next(b for b in out["branches"] if b["branch_id"] == bk[0].id)
    slips = session.exec(
        select(Payslip)
        .where(Payslip.branch_id == bk[0].id)
        .where(col(Payslip.cutoff_end).between(OCTOBER, dt.date(2026, 10, 31)))
    ).all()
    assert kiosk["payroll"] == sum(s.gross for s in slips) > 0
    assert kiosk["profit"] == (
        kiosk["sales"] - kiosk["fees"] - kiosk["expenses"] - kiosk["supplier"] - kiosk["payroll"]
    )
    stmt = select(Event).where(Event.tool_call_id == "p1", Event.action == "tool.called")
    (logged,) = session.exec(stmt).all()
    assert str(kiosk["payroll"]) not in json.dumps(logged.after)
