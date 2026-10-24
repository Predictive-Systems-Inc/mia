"""A sales clerk's day at the Mall kiosk end to end (tests/day.py), from the first check-in to the
closing cash count and the night's tick, on RS_TODAY (a Wednesday: Ana 09:00 to 17:00, Liza
13:00 to 21:00). Every peso is computed here from the item prices of the day; a reply is read
only for the words, never for a number. Clerks write Filipino, the owner English.

The router is not exercised: each turn goes to the named agent as it would for a person with one
agent.

Steps no agent does today are left out, not faked (each named where it would be):
- no agent tells head staff of a slow day while the shop is open (the owner's end-of-day report
  and the branch manager's evening nudge to the clerks are the only target comparisons, sales
  supervisor spec section 3 scenarios 3 and 5);
- the closing summary head staff gets is the inventory manager's closing stock; the sales
  report goes to the owner (alerts.leads), never to head staff.
"""

import pytest
from sqlmodel import Session, col, select

from mia.agents.bookkeeper.models import CashCount
from mia.agents.customer_service.models import Customer, CustomerMessage
from mia.agents.sales_supervisor import tools as sales_tools
from mia.agents.shift_supervisor.rules import fmt_date, word_key
from mia.core import approvals, db, orgconfig, sales
from mia.core.models import (
    Actor,
    Approval,
    CustomerOrder,
    SalesCount,
    SalesPayment,
    SalesReceipt,
    SalesSession,
    StockEvent,
)
from mia.core.money import format_money
from mia.i18n import t
from mia.templates.retail import hours as retail_hours
from mia.templates.retail import items as retail_items
from mia.templates.retail.models import RetailItem
from tests.conftest import MNL, RS_TODAY, Shop
from tests.day import Day, Said
from tests.test_data_standard_1_7 import visit_of

FIL = "fil"
MILA = "+639170000101"  # the seeded customer Mila Reyes (fil)
SS, SH, IM, BK, CS, BM = (
    "sales_supervisor",
    "shift_supervisor",
    "inventory_manager",
    "bookkeeper",
    "customer_service",
    "branch_manager",
)
# who, clock, message, items (name, quantity), tender: the day's counts in the order sent
NOON = ("Ana", (12, 0), "sp 5 cl 8 ube 3", [("Special", 5), ("Classic", 8), ("Ube", 3)], "cash")
AFTERNOON = ("Ana", (17, 0), "sp 4 cl 6", [("Special", 4), ("Classic", 6)], "cash")
AFTERNOON_GCASH = ("Ana", (17, 1), "ube 2 gcash", [("Ube", 2)], "gcash")
EVENING = ("Liza", (20, 30), "sp 3 cl 5", [("Special", 3), ("Classic", 5)], "cash")
Count = tuple[str, tuple[int, int], str, list[tuple[str, int]], str]


@pytest.fixture
def day(session: Session, monkeypatch: pytest.MonkeyPatch, rs_shop: Shop) -> Day:
    return Day(session, monkeypatch, rs_shop)


def money(amount: int) -> str:
    return format_money(amount, "PHP", FIL)


def _item(session: Session, name: str) -> RetailItem:
    return session.exec(select(RetailItem).where(RetailItem.name == name)).one()


def price(day: Day, name: str) -> int:
    """The item's price at the Mall kiosk today (Special runs a seeded price experiment)."""
    return retail_items.price_on(day.session, _item(day.session, name), day.shop.kiosk.id, RS_TODAY)


def amount(day: Day, counts: list[Count], tender: str | None = None) -> int:
    """The pesos of the counts (by tender when given), quantity times today's price."""
    return sum(
        q * price(day, name)
        for *_, lines, paid in counts
        if tender in (None, paid)
        for name, q in lines
    )


def report(day: Day, count: Count) -> Said:
    """The clerk sends one count to the sales supervisor at its clock."""
    who, (hour, minute), text, lines, _ = count
    day.at(hour, minute)
    ids = {f"item_{k}": _item(day.session, name).id for k, (name, _) in enumerate(lines)}
    said = day.say(who, SS, text, "report_sales", conversation="other", **ids)
    assert said.actions().count("sales.counted") == len(lines)
    return said


def check_in(day: Day, who: str, hour: int, minute: int = 0) -> Said:
    day.at(hour, minute)
    said = day.say(who, SH, "nandito na ako", "check_in")
    assert "visit.checked_in" in said.actions()
    return said


def check_out(day: Day, who: str, hour: int, minute: int = 0) -> None:
    day.at(hour, minute)
    assert "visit.checked_out" in day.say(who, SH, "uwi na ako", "check_out").actions()


def cash_count(day: Day, counted: int) -> Said:
    """Head staff types the closing count (whole pesos) at 21:10."""
    day.at(21, 10)
    return day.say("Marites", BK, f"bilang ng pera {counted // 100}", "cash_count", amount="p0")


def closing(day: Day) -> CashCount:
    rows = day.session.exec(select(CashCount).where(CashCount.business_date == RS_TODAY))
    (row,) = [r for r in rows if r.branch_id == day.shop.kiosk.id]
    return row


def the_counts(day: Day) -> list[tuple[str, str, int, str]]:
    """Today's live counts at the kiosk as (who, item, quantity, tender), sorted."""
    names = {p.id: n for n, p in day.people.items()}
    items = {i.id: i.name for i in day.session.exec(select(RetailItem))}
    rows = day.counts(RS_TODAY)
    return sorted((names[r.reported_by], items[r.item_id], r.quantity, r.tender) for r in rows)


def expected_rows(counts: list[Count]) -> list[tuple[str, str, int, str]]:
    return sorted((who, n, q, paid) for who, _, _, lines, paid in counts for n, q in lines)


def the_whole_day(day: Day) -> list[Count]:
    """Check-ins, the four counts and the check-outs of a plain day; returns the counts."""
    check_in(day, "Ana", 9)
    report(day, NOON)
    check_in(day, "Liza", 13)
    for count in (AFTERNOON, AFTERNOON_GCASH):
        report(day, count)
    check_out(day, "Ana", 17, 2)
    report(day, EVENING)
    check_out(day, "Liza", 21)
    return [NOON, AFTERNOON, AFTERNOON_GCASH, EVENING]


def kiosk_actions(day: Day, step: Said) -> list[str]:
    return [e.action for e in step.events if e.entity_id == day.shop.kiosk.id]


# ---- 1. a normal day --------------------------------------------------------------------------


def test_a_normal_day_at_the_mall_kiosk(day: Day, session: Session) -> None:
    ube = _item(session, "Ube")
    check_in(day, "Ana", 9)
    day.at(9, 5)
    day.tick()  # the morning work (the seed's late shift yesterday goes to Marites here)
    noon = report(day, NOON)
    total_noon = amount(day, [NOON])
    assert money(total_noon) not in noon.text() and "12:00" in noon.text()  # recorded and when
    check_in(day, "Liza", 13)
    day.at(13, 20)
    assert day.told("Marites", step=day.tick()) == []  # Liza checked in: no missed check-in

    # 14:00 Mila orders 10 Classic for 18:00 on WhatsApp; Marites confirms it through the app's decide path
    day.at(14)
    ordered = day.customer(MILA, "pa-order po 10 classic, pickup 6pm", "place_order", time="t0")
    assert "customer_service.order_placed" in ordered.actions()
    mila = session.exec(select(Customer).where(Customer.address == MILA)).one()
    order = session.exec(
        select(CustomerOrder)
        .where(CustomerOrder.customer_id == mila.id)
        .where(CustomerOrder.status == "waiting")
    ).one()
    classic = _item(session, "Classic")
    assert order.lines == [{"item_id": classic.id, "quantity": 10, "unit_price": classic.price}]
    assert order.total == 10 * classic.price
    asked = t(
        "cs.staff.new_order", FIL, items="10 Classic", time="18:00", name="Mila", last4="0101"
    )
    assert day.told("Marites", CS, step=ordered) == [asked]
    assert order.approval_id is not None
    marites = Actor.person(day.people["Marites"])
    approvals.decide(session, order.approval_id, marites, "approved", stepped_up_at=db.utcnow())
    session.commit()
    session.refresh(order)
    assert (order.status, order.decided_by) == ("confirmed", day.people["Marites"].id)
    out = session.exec(
        select(CustomerMessage)
        .where(CustomerMessage.customer_id == mila.id)
        .where(CustomerMessage.direction == "out")
    ).all()
    assert out[-1].text == t("cs.order_confirmed", FIL, time="18:00")

    # 16:00 Ana: the Ube is gone
    day.at(16)
    sold_out = day.say("Ana", IM, "ubos na ang ube", "report_stock", kind="sold_out", item=ube.id)
    assert sold_out.text() == t("stock.sold_out", FIL, item="Ube", time="16:00")
    (stock,) = session.exec(
        select(StockEvent)
        .where(StockEvent.kind == "sold_out")
        .where(StockEvent.business_date == RS_TODAY)
        .where(StockEvent.item_id == ube.id)
    ).all()
    assert stock.at.astimezone(MNL).strftime("%H:%M") == "16:00"

    for count in (AFTERNOON, AFTERNOON_GCASH):
        report(day, count)
    check_out(day, "Ana", 17, 2)
    report(day, EVENING)
    check_out(day, "Liza", 21)
    counts = [NOON, AFTERNOON, AFTERNOON_GCASH, EVENING]
    assert the_counts(day) == expected_rows(counts)

    # 21:10 Marites counts the drawer: 30 pesos short, within the threshold
    total, gcash = amount(day, counts), amount(day, counts, "gcash")
    cash = total - gcash  # the day's cash sales: total sales less the non-cash tender
    assert (total, cash) == (157_900, 148_900)  # the figures in docs/testing-ferinos.md
    counted = (cash // 100 - 30) * 100
    threshold = orgconfig.load().bookkeeper.threshold
    assert 0 < cash - counted <= threshold
    said = cash_count(day, counted)
    assert said.text() == t(
        "bk.count.within",
        FIL,
        counted=money(counted),
        expected=money(cash),
        difference=money(cash - counted),
    )
    row = closing(day)
    assert (row.counted, row.expected, row.difference) == (counted, cash, counted - cash)
    assert day.told("Rosa", BK) == []  # within the threshold: the owner is not told

    # 22:05 the tick: the owner's report, Marites's closing stock, nothing else for her
    day.at(22, 5)
    night = day.tick()
    assert not {"sales.missing_sent", "bookkeeper.count_reminded"} & set(kiosk_actions(day, night))
    (stock_summary,) = day.told("Marites", step=night)
    assert stock_summary in day.told("Marites", IM, step=night)
    assert t("stock.sold_out", FIL, item="Ube", time="16:00") in stock_summary
    owner = [m for m in day.told("Rosa", SS, step=night) if "Mall kiosk" in m]
    assert len(owner) == 1 and money(total) in owner[0]
    assert sum(r.amount for r in day.counts(RS_TODAY)) == total

    # one business date for every row of the day
    assert {r.business_date for r in day.counts(RS_TODAY)} == {RS_TODAY}
    assert (row.business_date, stock.business_date) == (RS_TODAY, RS_TODAY)
    assert order.pickup_at.astimezone(MNL).date() == RS_TODAY


# ---- 2. a short drawer ------------------------------------------------------------------------


def test_a_short_drawer_tells_the_owner_the_exact_amount(day: Day) -> None:
    counts = the_whole_day(day)
    cash = amount(day, counts, "cash")
    counted = (cash // 100 - 150) * 100  # 150 pesos and the centavos short
    short = cash - counted
    assert short > orgconfig.load().bookkeeper.threshold
    said = cash_count(day, counted)
    assert said.text() == t(
        "bk.count.short", FIL, counted=money(counted), expected=money(cash), short=money(short)
    )
    assert closing(day).difference == -short
    assert day.told("Rosa", BK, step=said) == [
        t(
            "bk.count.short_owner",
            FIL,
            branch="Mall kiosk",
            short=money(short),
            counted=money(counted),
            expected=money(cash),
        )
    ]
    assert day.told("Ana", BK) == day.told("Liza", BK) == []  # a clerk never hears of the drawer


# ---- 3. a correction --------------------------------------------------------------------------


def test_a_corrected_noon_count_carries_to_the_total_and_the_cash_count(
    day: Day, session: Session
) -> None:
    check_in(day, "Ana", 9)
    report(day, NOON)
    day.at(12, 10)
    ube = _item(session, "Ube")
    fixed = day.say("Ana", SS, "mali pala ube 4 dapat", "correct_sales", item_0=ube.id)
    assert "sales.corrected" in fixed.actions()
    old = session.exec(
        select(SalesCount).where(SalesCount.item_id == ube.id).where(SalesCount.quantity == 3)
    ).all()
    (replaced,) = [r for r in old if r.business_date == RS_TODAY]
    assert replaced.superseded_by is not None  # kept, marked superseded
    noon = (*NOON[:3], [("Special", 5), ("Classic", 8), ("Ube", 4)], "cash")
    for count in (AFTERNOON, AFTERNOON_GCASH, EVENING):
        report(day, count)
    counts: list[Count] = [noon, AFTERNOON, AFTERNOON_GCASH, EVENING]
    assert the_counts(day) == expected_rows(counts)
    total, cash = amount(day, counts), amount(day, counts, "cash")
    assert cash == amount(day, [NOON, AFTERNOON, EVENING], "cash") + price(day, "Ube")
    counted = (cash // 100) * 100
    cash_count(day, counted)
    assert (closing(day).expected, closing(day).difference) == (cash, counted - cash)
    day.at(22, 5)
    owner = [m for m in day.told("Rosa", SS, step=day.tick()) if "Mall kiosk" in m]
    assert len(owner) == 1 and money(total) in owner[0] and "6 Ube" in owner[0]  # 4 + 2


# ---- 4. a slow afternoon against the owner's target ------------------------------------------


def test_a_slow_day_is_compared_with_the_owners_day_target(day: Day) -> None:
    kiosk = day.shop.kiosk
    target = 500_000  # PHP 5,000.00
    day.at(8, 30)
    set_it = day.say(
        "Rosa",
        SS,
        "Target for today is 5,000 for the Mall kiosk",
        "set_target",
        target_period="day",
        target_start="today",
        branch=kiosk.id,
        amount="p0",
        item_0="none",
    )
    assert "sales.target_set" in set_it.actions()
    hours = retail_hours.load(day.session, kiosk.id)
    assert sales_tools._share(day.session, kiosk.id, hours, RS_TODAY) == target  # not the month's
    check_in(day, "Ana", 9)
    report(day, NOON)
    check_in(day, "Liza", 13)
    for count in (AFTERNOON, AFTERNOON_GCASH):
        report(day, count)
    so_far = amount(day, [NOON, AFTERNOON, AFTERNOON_GCASH])
    percent = round(so_far * 100 / target)
    day.at(17, 30)
    how = day.say("Marites", SS, "kumusta ang benta ngayon?", "sales_today", period="today")
    assert money(so_far) in how.text() and money(target) in how.text()
    assert f"({percent}%)" in how.text()
    check_out(day, "Ana", 17, 35)
    report(day, EVENING)
    check_out(day, "Liza", 21)
    total = amount(day, [NOON, AFTERNOON, AFTERNOON_GCASH, EVENING])
    assert total < target
    day.at(22, 5)
    night = day.tick()
    owner = [m for m in day.told("Rosa", SS, step=night) if "Mall kiosk" in m]
    assert len(owner) == 1 and money(total) in owner[0] and money(target) in owner[0]
    assert t("bm.nudge", FIL) in day.told("Ana", BM, step=night)
    # nobody tells head staff of the slow day (a step no agent does, see the module docstring)
    assert day.told("Marites", SS, step=night) == day.told("Marites", BM, step=night) == []


# ---- 5. a late clerk --------------------------------------------------------------------------


def test_a_late_clerk_is_reported_to_head_staff_once(day: Day, session: Session) -> None:
    liza = day.people["Liza"]
    check_in(day, "Ana", 9)
    day.at(9, 5)
    day.tick()  # the morning work (the seed's late shift yesterday goes to Marites here)
    day.at(12, 50)
    late = day.say(
        "Liza", SH, "late ako, 1:30 na ako makakarating", "record_absence", reason="late"
    )
    assert "absences.created" in late.actions() and "visit.checked_in" not in late.actions()
    shift = {
        "start": "13:00",
        "location": "Mall kiosk",
        "date": fmt_date(RS_TODAY.isoformat(), FIL),
    }
    notice = t("retail.alert.late", FIL, name=liza.name, time="13:30", **shift)
    assert day.told("Marites", step=late) == [notice]  # head staff told once, at the notice
    day.at(13, 15)
    alert = day.tick()
    key = word_key("alert.missed_check_in_supervisor")
    missed = t(key, FIL, name=liza.name, location="Mall kiosk", time="13:00")
    assert day.told("Marites", SH, step=alert) == []  # "no message and no check-in" only
    day.at(13, 20)
    assert day.told("Marites", step=day.tick()) == []
    check_in(day, "Liza", 13, 30)
    visit = visit_of(session, liza, RS_TODAY)
    assert visit.actual_start is not None
    assert (visit.status, visit.actual_start.astimezone(MNL).strftime("%H:%M")) == (
        "in_progress",
        "13:30",
    )
    liza_notices = [m for m in day.told("Marites") if liza.name in m]
    assert (liza_notices.count(notice), liza_notices.count(missed)) == (1, 0)


# ---- 6. a receipts day ------------------------------------------------------------------------


def test_a_receipts_day_at_the_mall_kiosk(day: Day, session: Session) -> None:
    """The Mall kiosk on receipts from RS_TODAY with a PHP 1,000.00 float: Ana's check-in opens
    her drawer, three receipts are rung in the chat, the third voided through head staff's card,
    and Marites's count closes the drawer. Assumes Q119 (the chat is the till until a POS
    exists). Liza's shift is not exercised: she opens no drawer here, so the count closes
    Ana's alone."""
    day.full = day.full.model_copy(deep=True)
    day.full.sales.receipts_from = {"Mall kiosk": RS_TODAY}
    day.full.sales.opening_float = {"Mall kiosk": 100_000}
    day._only(None)
    cash, gcash = t("bk.tender.cash", FIL), t("bk.tender.gcash", FIL)

    opened = check_in(day, "Ana", 9)
    assert "sales.session_opened" in opened.actions()
    assert t("retail.check_in.drawer", FIL, float=money(100_000)) in opened.text()

    rung = [
        ((10, 15), "resibo 2 cl 1 ube cash 125", ["Classic", "Ube"], "2 Classic, 1 Ube", 12_500, cash),
        ((11, 30), "2 classic 1 special gcash", ["Classic", "Special"], "2 Classic, 1 Special", 12_950, gcash),
        ((12, 5), "r 3 ube cash", ["Ube"], "3 Ube", 13_500, cash),
    ]  # fmt: skip
    for no, ((hour, minute), text, names, lines, total, tender) in enumerate(rung, start=1):
        day.at(hour, minute)
        ids = {f"item_{k}": _item(session, name).id for k, name in enumerate(names)}
        said = day.say("Ana", SS, text, "record_receipt", conversation="other", **ids)
        assert said.text() == t(
            "sales.receipt.recorded", FIL, no=str(no), lines=lines, total=money(total),
            tender=tender,
        )  # fmt: skip
    receipts = session.exec(select(SalesReceipt).order_by(col(SalesReceipt.receipt_no))).all()
    assert [(r.receipt_no, r.total) for r in receipts] == [
        ("1", 12_500), ("2", 12_950), ("3", 13_500),
    ]  # fmt: skip
    paid = {r.receipt_id: r.tender for r in session.exec(select(SalesPayment))}
    assert [paid[r.id] for r in receipts] == ["cash", "gcash", "cash"]

    day.at(12, 10)
    asked = day.say("Ana", SS, "void 3 mali", "void_receipt", conversation="other")
    card = t(
        "sales.void.card", FIL, who="Ana", no="3", lines="3 Ube", total=money(13_500),
        tender=cash, reason="void 3 mali",
    )  # fmt: skip
    assert day.told("Marites", step=asked) == [card]
    (approval,) = session.exec(select(Approval).where(Approval.type == sales.VOID)).all()
    day.at(12, 30)
    marites = Actor.person(day.people["Marites"])
    approvals.decide(session, approval.id, marites, "approved", stepped_up_at=db.utcnow())
    session.commit()
    third = receipts[2]
    session.refresh(third)
    assert third.status == "voided"
    assert day.told("Ana", SS)[-1] == t("sales.void.done", FIL, no="3")

    check_out(day, "Ana", 17, 2)
    day.at(17, 5)
    counted = day.say("Marites", BK, "bilang ng pera 1125", "cash_count", amount="p0")
    (drawer,) = session.exec(select(SalesSession)).all()
    assert (drawer.state, drawer.counted, drawer.expected, drawer.difference) == (
        "closed", 112_500, 112_500, 0,
    )  # fmt: skip
    assert counted.text() == t(
        "bk.count.drawer.within", FIL, clerk="Ana", counted=money(112_500),
        expected=money(112_500), float=money(100_000), cash=money(12_500), difference=money(0),
    )  # fmt: skip
    row = closing(day)
    assert (row.counted, row.expected, row.difference) == (112_500, 112_500, 0)

    day.at(22, 5)
    night = day.tick()
    owner = [m for m in day.told("Rosa", SS, step=night) if "Mall kiosk" in m]
    assert len(owner) == 1 and money(25_450) in owner[0]
    assert day.counts(RS_TODAY) == []
    kiosk = day.shop.kiosk.id
    assert sales.day_sales(session, kiosk, RS_TODAY).by_tender == {"cash": 12_500, "gcash": 12_950}
    assert {r.business_date for r in receipts} == {RS_TODAY}
