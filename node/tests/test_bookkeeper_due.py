"""The bookkeeper's due work on the tick at fixed clocks (bk_en, BK_TODAY a Tuesday, the Mall
kiosk 09:00 to 21:00 in Manila): the closing-count reminder, the petty and undeposited
reminders, the monthly profit, the quarter's tax figure and undecided large expenses closed."""

import datetime as dt
import json
from collections.abc import Iterator
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import call_tool
from mia.agents.bookkeeper import MANIFEST, due, replies, tools
from mia.agents.bookkeeper.models import TaxFigure
from mia.agents.bookkeeper.tools import (
    BalancesInput,
    CashCountInput,
    ExpenseInput,
    PettyInput,
    ProfitInput,
    TaxInput,
)
from mia.agents.sales_supervisor import MANIFEST as SALES
from mia.agents.shift_supervisor import alerts
from mia.channels import registry
from mia.channels.simulator import SimAdapter
from mia.core import orgconfig, store
from mia.core.models import (
    Actor,
    Approval,
    Branch,
    ChannelIdentity,
    ChannelOutbox,
    Event,
    Message,
    Payslip,
    Person,
    Thread,
)
from mia.core.money import format_money
from mia.core.orgconfig import ChannelConfig, OrgSettings
from mia.i18n import t
from tests.conftest import BK_TODAY, Pin
from tests.test_bookkeeper_tools import BINDING, deps_for
from tests.test_sales_tools import stall

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
EN = "en"
ONE_DAY = dt.timedelta(days=1)
OCTOBER = dt.date(2026, 10, 1)


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), MNL)


def _tick(session: Session, pin: Pin, moment: dt.datetime) -> int:
    return due.run_due(session, pin(moment))


def notifications(session: Session, person: Person) -> list[Message]:
    threads = select(Thread.id).where(Thread.person_id == person.id)
    stmt = select(Message).where(col(Message.thread_id).in_(threads))
    rows = session.exec(stmt.where(Message.role == "notification")).all()
    return [m for m in rows if m.agent_id == MANIFEST.id]


def texts(session: Session, person: Person) -> list[str]:
    return [m.text for m in notifications(session, person)]


def money(amount: int | None) -> str:
    assert amount is not None
    return format_money(amount, "PHP", EN)


def names(session: Session) -> dict[str, str]:
    return {b.id: b.name for b in session.exec(select(Branch))}


def test_the_closing_count_reminder_comes_an_hour_after_close(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    _tick(session, bk_pin, at(BK_TODAY, 21, 50))
    assert notifications(session, bk_en[1]["Marites"]) == []
    _tick(session, bk_pin, at(BK_TODAY, 22, 5))
    (note,) = notifications(session, bk_en[1]["Marites"])
    assert note.text == t("bk.count.reminder", EN)


def test_the_closing_count_reminder_is_not_held_by_quiet_hours(
    session: Session, bk_en: Ferinos, bk_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    marites = bk_en[1]["Marites"]
    saved = dict(registry._adapters)
    registry._adapters.clear()
    registry.register(SimAdapter())
    org = OrgSettings(agents=[MANIFEST.id], channels={"sim": ChannelConfig(enabled=True)})
    try:
        with monkeypatch.context() as m:
            m.setattr(orgconfig, "load", lambda org_name=None: org)
            identity = ChannelIdentity(
                branch_id=marites.branch_id,
                person_id=marites.id,
                channel="sim",
                address="639170000002",
            )
            store.insert(session, identity, Actor.person(marites), action="channel.linked")
            session.commit()
            assert _tick(session, bk_pin, at(BK_TODAY, 22, 5)) >= 1  # quiet since 21:00
        stmt = select(ChannelOutbox).where(ChannelOutbox.person_id == marites.id)
        rows = list(session.exec(stmt))
        assert rows and all(r.send_after is None for r in rows)  # urgent
    finally:
        registry._adapters.clear()
        registry._adapters.update(saved)


def test_the_closing_count_reminder_is_sent_once_per_branch_and_day(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    _tick(session, bk_pin, at(BK_TODAY, 22, 5))
    _tick(session, bk_pin, at(BK_TODAY, 22, 40))
    assert texts(session, bk_en[1]["Marites"]).count(t("bk.count.reminder", EN)) == 1


def test_a_branch_with_its_count_gets_no_reminder(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    bk_pin(at(BK_TODAY, 21, 30))
    tools.record_cash_count(deps_for(session, bk_en[1]["Marites"]), CashCountInput(counted=0), "c")
    _tick(session, bk_pin, at(BK_TODAY, 22, 5))
    assert t("bk.count.reminder", EN) not in texts(session, bk_en[1]["Marites"])


def test_a_reminder_after_midnight_keeps_the_closing_date(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    _tick(session, bk_pin, at(BK_TODAY + ONE_DAY, 0, 30))
    assert alerts._marked(session, due.COUNT_REMINDED, bk_en[0].id, BK_TODAY)


def test_the_petty_floor_reminder_waits_for_the_morning(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    bk_pin(at(BK_TODAY, 20, 0))
    tools.record_petty(
        deps_for(session, bk_en[1]["Marites"]), PettyInput(kind="spend", amount=50_000), "p"
    )
    _tick(session, bk_pin, at(BK_TODAY, 22, 5))
    low = t("bk.petty.low", EN, balance=money(30_000), floor=money(50_000))
    assert low not in texts(session, bk_en[1]["Marites"])
    _tick(session, bk_pin, at(BK_TODAY + ONE_DAY, 9, 10))
    _tick(session, bk_pin, at(BK_TODAY + ONE_DAY, 9, 40))
    assert texts(session, bk_en[1]["Marites"]).count(low) == 1


def test_a_branch_without_a_petty_fund_gets_no_petty_reminder(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    jun = bk_en[1]["Jun"]  # the street stall's supervisor; the stall has no petty fund
    assert tools.balance_days(session, stall(session).id, BK_TODAY + ONE_DAY)[0] == {}
    bk_pin(at(BK_TODAY, 20, 0))
    tools.record_petty(
        deps_for(session, bk_en[1]["Marites"]), PettyInput(kind="spend", amount=50_000), "p"
    )
    _tick(session, bk_pin, at(BK_TODAY + ONE_DAY, 6, 10))  # the stall's morning
    _tick(session, bk_pin, at(BK_TODAY + ONE_DAY, 9, 10))  # the kiosk's morning
    assert not any(m.startswith("Petty cash is at") for m in texts(session, jun))
    low = t("bk.petty.low", EN, balance=money(30_000), floor=money(50_000))
    assert low in texts(session, bk_en[1]["Marites"])


def test_a_lead_without_a_branch_row_does_not_stop_the_letters(
    session: Session, bk_en: Ferinos, bk_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    rosa = bk_en[1]["Rosa"]
    ghost = rosa.model_copy(update={"id": "01GHOSTGHOSTGHOSTGHOSTGHOS", "branch_id": "missing"})
    monkeypatch.setattr(alerts, "leads", lambda session, organisation_id: [ghost, rosa])
    _tick(session, bk_pin, at(dt.date(2026, 11, 2), 9, 10))
    _tick(session, bk_pin, at(dt.date(2027, 1, 20), 9, 10))
    head = t("bk.profit.head", EN, month="2026-10")
    assert any(head in m for m in texts(session, rosa))
    assert session.exec(select(TaxFigure).where(TaxFigure.branch_id == bk_en[0].id)).one()


def test_undeposited_cash_over_the_limit_two_days_reminds(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    for d in (0, 1):
        bk_pin(at(BK_TODAY + d * ONE_DAY, 21, 30))
        tools.record_cash_count(
            deps_for(session, bk_en[1]["Marites"]), CashCountInput(counted=2_100_000), f"c{d}"
        )
    _tick(session, bk_pin, at(BK_TODAY + 2 * ONE_DAY, 9, 10))
    out = tools.balances(deps_for(session, bk_en[1]["Rosa"]), BalancesInput(), "b")
    high = t("bk.undeposited.high", EN, amount=money(out.undeposited), days=2)
    assert high in texts(session, bk_en[1]["Rosa"])


def test_monthly_profit_per_branch_includes_payroll(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    _tick(session, bk_pin, at(dt.date(2026, 11, 2), 9, 10))  # the second open day of November
    out = tools.monthly_profit(deps_for(session, bk_en[1]["Rosa"]), ProfitInput(month=OCTOBER), "p")
    row = next(b for b in out.branches if b.branch_id == bk_en[0].id)
    slips = session.exec(
        select(Payslip)
        .where(Payslip.branch_id == bk_en[0].id)
        .where(col(Payslip.cutoff_end).between(OCTOBER, dt.date(2026, 10, 31)))
    ).all()
    assert row.payroll == sum(s.gross for s in slips) > 0
    assert row.profit == row.sales - row.fees - row.expenses - row.supplier - row.payroll
    assert replies.profit_text(out, names(session), EN) in texts(session, bk_en[1]["Rosa"])


def test_the_monthly_profit_keeps_payroll_off_the_chain(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    _tick(session, bk_pin, at(dt.date(2026, 11, 2), 9, 10))
    (note,) = [n for n in notifications(session, bk_en[1]["Rosa"]) if "Profit" in n.text]
    sent = session.exec(select(Event).where(Event.entity_id == note.id)).one()
    assert note.text not in json.dumps(sent.after)


def test_the_monthly_profit_goes_once_and_not_to_a_supervisor(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    _tick(session, bk_pin, at(dt.date(2026, 11, 2), 9, 10))
    _tick(session, bk_pin, at(dt.date(2026, 11, 2), 9, 40))
    head = t("bk.profit.head", EN, month="2026-10")
    assert len([m for m in texts(session, bk_en[1]["Rosa"]) if head in m]) == 1
    assert not any(head in m for m in texts(session, bk_en[1]["Marites"]))


def test_the_quarter_figure_comes_five_days_before_the_deadline(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    _tick(session, bk_pin, at(dt.date(2027, 1, 19), 9, 10))
    assert session.exec(select(TaxFigure)).all() == []
    _tick(session, bk_pin, at(dt.date(2027, 1, 20), 9, 10))
    row = session.exec(select(TaxFigure).where(TaxFigure.branch_id == bk_en[0].id)).one()
    assert (row.period_start, row.rate) == (dt.date(2026, 10, 1), 12)
    out = tools.tax_quarter(
        deps_for(session, bk_en[1]["Rosa"]), TaxInput(quarter_start=row.period_start), "q"
    )
    mine = tools.TaxOutput(branches=[b for b in out.branches if b.branch_id == row.branch_id])
    assert (mine.branches[0].due, mine.branches[0].gross) == (row.due, row.gross)
    assert replies.tax_text(mine, names(session), EN) in texts(session, bk_en[1]["Rosa"])
    _tick(session, bk_pin, at(dt.date(2027, 1, 21), 9, 10))  # the row is the marker
    assert len(session.exec(select(TaxFigure)).all()) == 1


def test_an_undecided_large_expense_expires_and_the_requester_is_told(
    session: Session, bk_en: Ferinos, bk_pin: Pin
) -> None:
    out = call_tool(
        deps_for(session, bk_en[1]["Marites"]),
        BINDING[f"{MANIFEST.id}.record_large_expense"],
        ExpenseInput(category="repairs", amount=750_000),
        "x",
    )
    for days in (2, 4):  # past the 24-hour TTL twice: escalated, then expired
        _tick(session, bk_pin, at(BK_TODAY + days * ONE_DAY, 9, 10))
    assert session.get(Approval, out["approval_id"]).status == "expired"
    expired = t("bk.expense.expired", EN, amount=money(750_000), category="repairs")
    assert expired in texts(session, bk_en[1]["Marites"])


@pytest.fixture
def without_bookkeeper(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    org = OrgSettings(agents=[SALES.id])
    with monkeypatch.context() as m:
        m.setattr(orgconfig, "load", lambda org_name=None: org)
        yield


def test_nothing_runs_when_the_org_does_not_use_the_bookkeeper(
    session: Session, bk_en: Ferinos, bk_pin: Pin, without_bookkeeper: None
) -> None:
    assert _tick(session, bk_pin, at(BK_TODAY, 22, 5)) == 0
    assert notifications(session, bk_en[1]["Marites"]) == []
