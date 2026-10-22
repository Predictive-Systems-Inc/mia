"""Data standard 1.9 (D43, ADR 022): sales sessions, receipts, receipt lines and payments as core
tables, their services in mia/core/sales.py, and day_sales over the one source a kiosk uses."""

import datetime as dt
from collections.abc import Iterator
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from mia.agents.bookkeeper.tools import tender_sales
from mia.agents.sales_supervisor import calc
from mia.agents.sales_supervisor import tools as sales_tools
from mia.cli import _alembic_config
from mia.core import approvals, db, orgconfig, sales, store
from mia.core.db import get_engine
from mia.core.models import (
    STANDARD_VERSION,
    TENDERS,
    Actor,
    Branch,
    Event,
    Person,
    SalesPayment,
    SalesReceipt,
    SalesReceiptLine,
    SalesSession,
)
from mia.core.rbac import PermissionDenied
from mia.core.sales import LineIn, PaymentIn, SalesError
from mia.templates.retail.models import RetailItem
from tests.conftest import _ferinos_on

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
TABLES = ("sales_sessions", "sales_receipts", "sales_receipt_lines", "sales_payments")


TODAY = dt.date(2026, 10, 28)  # a Wednesday; the seed counts the 14 days before


@pytest.fixture
def ferinos(monkeypatch: pytest.MonkeyPatch, session: Session) -> Iterator[Ferinos]:
    """The Ferino's seed on TODAY with db.utcnow pinned to 10:00 Manila (conftest._ferinos_on)."""
    for shop in _ferinos_on(monkeypatch, session, TODAY):
        yield shop.kiosk, shop.people


def yesterday() -> dt.date:
    """The pinned clock's day before, a seeded counts day."""
    return db.utcnow().astimezone(MNL).date() - dt.timedelta(days=1)


def noon(day: dt.date, hh: int = 12) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hh), MNL)


def item(session: Session, name: str) -> RetailItem:
    return session.exec(select(RetailItem).where(RetailItem.name == name)).one()


def opened(session: Session, rs: Ferinos, who: str = "Ana") -> SalesSession:
    kiosk, people = rs
    s = sales.open_session(
        session, Actor.person(people[who]), kiosk.id, people[who].id, noon(yesterday(), 9), "PHP"
    )
    return s


def sell(
    session: Session, rs: Ferinos, s: SalesSession, no: str, pays: list[PaymentIn] | None = None
) -> SalesReceipt:
    """Two Classic (default 4000 each) and one Kape (2500), paid 8000 cash and 2500 GCash."""
    lines = [
        LineIn(item_id=item(session, "Classic").id, quantity=2),
        LineIn(item_id=item(session, "Kape").id, quantity=1),
    ]
    pays = pays or [PaymentIn(tender="cash", amount=8000), PaymentIn(tender="gcash", amount=2500)]
    clerk = Actor.person(rs[1]["Ana"])
    return sales.record_receipt(session, clerk, s, no, noon(yesterday(), 13), lines, pays)


def approve(
    session: Session,
    rs: Ferinos,
    kind: str,
    subject: str,
    role: str,
    by: str,
    evidence: dict[str, Any] | None = None,
) -> str:
    people = rs[1]
    a = approvals.request(
        session, kind, ("sales_receipts", subject), kind, Actor.person(people["Ana"]), [role],
        risk="money", evidence=evidence,
    )  # fmt: skip
    approvals.decide(session, a.id, Actor.person(people[by]), "approved", stepped_up_at=db.utcnow())
    return a.id


def written(session: Session) -> tuple[int, int, int, int]:
    return tuple(  # type: ignore[return-value]
        len(session.exec(select(m)).all())
        for m in (SalesReceipt, SalesReceiptLine, SalesPayment, Event)
    )


def test_the_standard_is_1_9_and_the_four_tables_are_core() -> None:
    models = (SalesSession, SalesReceipt, SalesReceiptLine, SalesPayment)
    assert STANDARD_VERSION == "1.9"
    assert tuple(m.__tablename__ for m in models) == TABLES
    assert {m.__module__ for m in models} == {"mia.core.models"}
    assert SalesReceipt.__redact__ == frozenset({"void_reason"})


def test_the_migration_creates_the_tables_and_their_unique_rules() -> None:
    command.upgrade(_alembic_config(), "head")
    with get_engine().connect() as conn:
        db = inspect(conn)
        assert set(TABLES) <= set(db.get_table_names())
        open_ix = {i["name"]: i for i in db.get_indexes("sales_sessions")}["ux_sales_sessions_open"]
        uniques = [u["column_names"] for u in db.get_unique_constraints("sales_receipts")]
    assert (open_ix["unique"], open_ix["column_names"]) == (1, ["branch_id", "person_id"])
    assert uniques == [["branch_id", "receipt_no"]]


def test_a_clerk_cannot_read_another_branchs_receipts(session: Session, ferinos: Ferinos) -> None:
    kiosk, people = ferinos
    sell(session, ferinos, opened(session, ferinos), "M-1")
    pao = Actor.person(people["Pao"])  # a clerk at the Street stall
    with pytest.raises(PermissionDenied):
        sales.receipts(session, pao, kiosk.id, yesterday())
    ana, liza = Actor.person(people["Ana"]), Actor.person(people["Liza"])
    assert [r.receipt_no for r in sales.receipts(session, ana, kiosk.id, yesterday())] == ["M-1"]
    assert sales.receipts(session, liza, kiosk.id, yesterday()) == []  # read_own: not Ana's
    rosa = Actor.person(people["Rosa"])
    assert len(sales.receipts(session, rosa, kiosk.id, yesterday())) == 1


def test_one_open_session_per_clerk(session: Session, ferinos: Ferinos) -> None:
    kiosk, people = ferinos
    first = opened(session, ferinos)
    with pytest.raises(SalesError, match="session_open"):
        opened(session, ferinos)
    again = SalesSession(
        branch_id=kiosk.id,
        person_id=people["Ana"].id,
        business_date=yesterday(),
        opened_at=noon(yesterday()),
        currency="PHP",
    )
    with pytest.raises(IntegrityError):  # the partial unique index, past the service check
        store.insert(session, again, Actor.system(kiosk.id))
    session.rollback()
    assert opened(session, ferinos, "Liza").person_id != first.person_id


def test_payments_must_sum_to_the_total(session: Session, ferinos: Ferinos) -> None:
    s = opened(session, ferinos)
    before = written(session)
    short = [PaymentIn(tender="cash", amount=10_000)]
    with pytest.raises(SalesError, match="payments"):
        sell(session, ferinos, s, "M-1", short)
    assert written(session) == before


def test_a_receipt_records_lines_payments_and_its_events(
    session: Session, ferinos: Ferinos
) -> None:
    receipt = sell(session, ferinos, opened(session, ferinos), "M-1")
    lines = session.exec(select(SalesReceiptLine)).all()
    assert (receipt.subtotal, receipt.total, receipt.business_date) == (10_500, 10_500, yesterday())
    assert sorted((ln.quantity, ln.unit_price, ln.line_total) for ln in lines) == [
        (1, 2500, 2500),
        (2, 4000, 8000),
    ]
    actions = [e.action for e in session.exec(select(Event)) if e.action.startswith("sales.")]
    assert actions == [
        "sales.session_opened",
        "sales.receipt_recorded",
        "sales.payment_recorded",
        "sales.payment_recorded",
    ]
    assert {p.tender for p in session.exec(select(SalesPayment))} <= set(TENDERS)


def test_a_void_needs_head_staffs_approval(session: Session, ferinos: Ferinos) -> None:
    receipt = sell(session, ferinos, opened(session, ferinos), "M-1")
    pending = approvals.request(
        session, sales.VOID, ("sales_receipts", receipt.id), "void",
        Actor.person(ferinos[1]["Ana"]), ["supervisor"], risk="money",
    )  # fmt: skip
    wrong_type = approve(session, ferinos, sales.REFUND, receipt.id, "admin", "Rosa")
    before = written(session)
    for approval_id in (pending.id, wrong_type, "nope"):
        with pytest.raises(SalesError, match="approval"):
            sales.void_receipt(session, Actor.system(receipt.branch_id), receipt, approval_id, "x")
    assert (written(session), receipt.status) == (before, "paid")
    ok = approve(session, ferinos, sales.VOID, receipt.id, "supervisor", "Marites")
    sales.void_receipt(session, Actor.system(receipt.branch_id), receipt, ok, "wrong item")
    assert (receipt.status, receipt.voided_by) == ("voided", ferinos[1]["Marites"].id)


def test_a_void_after_the_close_is_refused(session: Session, ferinos: Ferinos) -> None:
    s = opened(session, ferinos)
    receipt = sell(session, ferinos, s, "M-1")
    marites = ferinos[1]["Marites"]
    sales.close_session(session, Actor.person(marites), s, 8000, marites.id, noon(yesterday(), 18))
    ok = approve(session, ferinos, sales.VOID, receipt.id, "supervisor", "Marites")
    with pytest.raises(SalesError, match="session_closed"):
        sales.void_receipt(session, Actor.person(marites), receipt, ok, "x")


def test_a_refund_needs_an_owner_or_admin_approval(session: Session, ferinos: Ferinos) -> None:
    s = opened(session, ferinos)
    sale = sell(session, ferinos, s, "M-1")
    kape = session.exec(select(SalesReceiptLine).where(SalesReceiptLine.unit_price == 2500)).one()
    back = [LineIn(item_id=kape.item_id, quantity=-1, refunded_line_id=kape.id)]
    pay = [PaymentIn(tender="cash", amount=-2500)]
    by_head = approve(session, ferinos, sales.REFUND, sale.id, "supervisor", "Marites")
    before = written(session)
    clerk = Actor.person(ferinos[1]["Ana"])
    for approval_id in (None, by_head):
        with pytest.raises(SalesError, match="approval"):
            sales.record_receipt(
                session, clerk, s, "M-2", noon(yesterday(), 14), back, pay,
                refund_of=sale.id, approval_id=approval_id,
            )  # fmt: skip
    assert written(session) == before
    ok = approve(session, ferinos, sales.REFUND, sale.id, "admin", "Rosa")
    refund = sales.record_receipt(
        session, clerk, s, "M-2", noon(yesterday(), 14), back, pay, refund_of=sale.id,
        approval_id=ok,
    )  # fmt: skip
    assert (refund.kind, refund.total) == ("refund", -2500)
    assert sales.expected_cash(session, s) == 8000 - 2500  # opening float 0


def test_day_sales_on_a_counts_kiosk_equals_the_count_totals(
    session: Session, ferinos: Ferinos
) -> None:
    kiosk, day = ferinos[0], yesterday()
    got = sales.day_sales(session, kiosk.id, day)
    assert got.source == "counts"
    live = sales_tools._live_counts(session, [kiosk.id], day, day)
    assert sales_tools._live_counts is sales.live_counts  # one query, in core
    assert got.by_item == calc.totals(sales_tools._plain(live))
    want = {t: tender_sales(session, kiosk.id, t, day, day) for t in got.by_tender}
    assert got.by_tender == want and sum(want.values()) > 0


def receipts_from(monkeypatch: pytest.MonkeyPatch, day: dt.date) -> None:
    settings = orgconfig.load().model_copy(deep=True)
    settings.sales.receipts_from = {"Mall kiosk": day}
    monkeypatch.setattr(orgconfig, "load", lambda org=None: settings)


def test_day_sales_on_a_receipts_kiosk_reads_the_receipts(
    session: Session, ferinos: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = opened(session, ferinos)
    sell(session, ferinos, s, "M-1")
    voided = sell(session, ferinos, s, "M-2")
    ok = approve(session, ferinos, sales.VOID, voided.id, "supervisor", "Marites")
    sales.void_receipt(session, Actor.system(s.branch_id), voided, ok, "x")
    receipts_from(monkeypatch, yesterday())
    got = sales.day_sales(session, ferinos[0].id, yesterday())
    classic, kape = item(session, "Classic").id, item(session, "Kape").id
    assert got.source == "receipts"
    assert got.by_item == {classic: (2, 8000), kape: (1, 2500)}  # the voided receipt left out
    assert got.by_tender == {"cash": 8000, "gcash": 2500}


def test_the_same_day_is_never_counted_twice_when_the_setting_flips(
    session: Session, ferinos: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    kiosk, day = ferinos[0], yesterday()
    sell(session, ferinos, opened(session, ferinos), "M-1")  # the day also has seeded counts
    counts = sales.day_sales(session, kiosk.id, day)
    receipts_from(monkeypatch, day + dt.timedelta(days=1))  # from tomorrow: still counts
    assert sales.day_sales(session, kiosk.id, day) == counts
    receipts_from(monkeypatch, day)
    flipped = sales.day_sales(session, kiosk.id, day)
    assert sum(flipped.by_tender.values()) == 10_500  # the receipt alone, no counts added
    stall = session.exec(select(Branch).where(Branch.name == "Street stall")).one()
    assert sales.day_sales(session, stall.id, day).source == "counts"  # per kiosk


def test_closing_freezes_expected_and_difference(session: Session, ferinos: Ferinos) -> None:
    s = opened(session, ferinos)
    sell(session, ferinos, s, "M-1")
    marites = ferinos[1]["Marites"]
    sales.close_session(session, Actor.person(marites), s, 7900, marites.id, noon(yesterday(), 18))
    assert (s.state, s.expected, s.difference) == ("closed", 8000, -100)
    with pytest.raises(SalesError, match="session_closed"):
        sell(session, ferinos, s, "M-2")
    assert opened(session, ferinos).opening_float == 7900  # the last close's counted


def classic_and_kape(session: Session) -> tuple[SalesReceiptLine, SalesReceiptLine]:
    """The sale's Classic line (2 at 4000) and Kape line (1 at 2500)."""
    lines = sorted(session.exec(select(SalesReceiptLine)).all(), key=lambda ln: ln.unit_price)
    return lines[1], lines[0]


def refund(
    session: Session,
    rs: Ferinos,
    s: SalesSession,
    sale: SalesReceipt,
    back: list[LineIn],
    amount: int,
    approval_id: str | None,
    no: str = "M-9",
) -> SalesReceipt:
    pay = [PaymentIn(tender="cash", amount=amount)]
    return sales.record_receipt(
        session, Actor.person(rs[1]["Ana"]), s, no, noon(yesterday(), 15), back, pay,
        refund_of=sale.id, approval_id=approval_id,
    )  # fmt: skip


@pytest.mark.parametrize("quantities", [(-1, -1), (-2, -1)], ids=["repeated", "split"])
def test_a_refund_names_each_sale_line_once(
    session: Session, ferinos: Ferinos, quantities: tuple[int, int]
) -> None:
    s = opened(session, ferinos)
    sale = sell(session, ferinos, s, "M-1")
    classic, _ = classic_and_kape(session)
    ok = approve(session, ferinos, sales.REFUND, sale.id, "admin", "Rosa")
    back = [
        LineIn(item_id=classic.item_id, quantity=q, refunded_line_id=classic.id) for q in quantities
    ]
    before = written(session)
    with pytest.raises(SalesError, match="refunded_line"):
        refund(session, ferinos, s, sale, back, 4000 * sum(quantities), ok)
    assert written(session) == before


def test_a_discounted_sale_is_refunded_at_the_price_paid(
    session: Session, ferinos: Ferinos
) -> None:
    s = opened(session, ferinos)
    lines = [
        LineIn(item_id=item(session, "Classic").id, quantity=2),
        LineIn(item_id=item(session, "Kape").id, quantity=1),
    ]
    pays = [PaymentIn(tender="cash", amount=9450)]
    sale = sales.record_receipt(
        session, Actor.person(ferinos[1]["Ana"]), s, "M-1", noon(yesterday(), 13), lines, pays,
        discount=1050, discount_reason="senior",
    )  # fmt: skip
    _, kape = classic_and_kape(session)
    back = [LineIn(item_id=kape.item_id, quantity=-1, refunded_line_id=kape.id)]
    ok = approve(session, ferinos, sales.REFUND, sale.id, "admin", "Rosa")
    before = written(session)
    with pytest.raises(SalesError, match="payments"):  # the full price is not the price paid
        refund(session, ferinos, s, sale, back, -2500, ok)
    assert written(session) == before
    assert refund(session, ferinos, s, sale, back, -2250, ok).total == -2250  # 2500 * 9450/10500


def test_a_refund_above_the_approved_amount_is_refused(session: Session, ferinos: Ferinos) -> None:
    s = opened(session, ferinos)
    sale = sell(session, ferinos, s, "M-1")
    _, kape = classic_and_kape(session)
    back = [LineIn(item_id=kape.item_id, quantity=-1, refunded_line_id=kape.id)]
    small = approve(session, ferinos, sales.REFUND, sale.id, "admin", "Rosa", {"amount": 1000})
    before = written(session)
    with pytest.raises(SalesError, match="approved_amount"):
        refund(session, ferinos, s, sale, back, -2500, small)
    assert written(session) == before


def test_an_approval_is_used_once(session: Session, ferinos: Ferinos) -> None:
    s = opened(session, ferinos)
    sale = sell(session, ferinos, s, "M-1")
    classic, kape = classic_and_kape(session)
    ok = approve(session, ferinos, sales.REFUND, sale.id, "admin", "Rosa")
    refund(session, ferinos, s, sale, [LineIn(item_id=kape.item_id, quantity=-1, refunded_line_id=kape.id)], -2500, ok)  # fmt: skip
    back = [LineIn(item_id=classic.item_id, quantity=-1, refunded_line_id=classic.id)]
    before = written(session)
    with pytest.raises(SalesError, match="approval"):  # two calls in a row
        refund(session, ferinos, s, sale, back, -4000, ok, "M-10")
    assert written(session) == before
    other = sell(session, ferinos, s, "M-2")
    void_ok = approve(session, ferinos, sales.VOID, other.id, "supervisor", "Marites")
    first_use = SalesReceipt(  # a concurrent writer's receipt, committed first
        branch_id=s.branch_id, session_id=s.id, receipt_no="X-1", business_date=yesterday(),
        sold_at=noon(yesterday()), clerk_id=s.person_id, subtotal=0, total=0, currency="PHP",
        approval_id=void_ok,
    )  # fmt: skip
    store.insert(session, first_use, Actor.system(s.branch_id))
    before = written(session)
    with pytest.raises(SalesError, match="approval"):
        sales.void_receipt(session, Actor.system(s.branch_id), other, void_ok, "x")
    assert (written(session), other.status) == (before, "paid")


def test_money_is_never_reversed_twice(session: Session, ferinos: Ferinos) -> None:
    s = opened(session, ferinos)
    sale = sell(session, ferinos, s, "M-1")
    _, kape = classic_and_kape(session)
    back = [LineIn(item_id=kape.item_id, quantity=-1, refunded_line_id=kape.id)]
    ok = approve(session, ferinos, sales.REFUND, sale.id, "admin", "Rosa")
    returned = refund(session, ferinos, s, sale, back, -2500, ok)
    void_sale = approve(session, ferinos, sales.VOID, sale.id, "supervisor", "Marites")
    void_refund = approve(session, ferinos, sales.VOID, returned.id, "supervisor", "Marites")
    again = approve(session, ferinos, sales.REFUND, returned.id, "admin", "Rosa")
    before = written(session)
    with pytest.raises(SalesError, match="refunded"):  # a sale with a paid refund
        sales.void_receipt(session, Actor.system(s.branch_id), sale, void_sale, "x")
    with pytest.raises(SalesError, match="kind"):  # a refund is never voided
        sales.void_receipt(session, Actor.system(s.branch_id), returned, void_refund, "x")
    with pytest.raises(SalesError, match="refund_of"):  # a refund of a refund
        refund(session, ferinos, s, returned, back, 2500, again, "M-10")
    assert written(session) == before
    other = sell(session, ferinos, s, "M-2")
    gone = approve(session, ferinos, sales.VOID, other.id, "supervisor", "Marites")
    sales.void_receipt(session, Actor.system(s.branch_id), other, gone, "x")
    late = approve(session, ferinos, sales.REFUND, other.id, "admin", "Rosa")
    before = written(session)
    with pytest.raises(SalesError, match="refund_of"):  # a refund of a voided sale
        refund(session, ferinos, s, other, back, -2500, late, "M-11")
    assert written(session) == before


def test_an_approval_references_one_receipt_structurally(
    session: Session, ferinos: Ferinos
) -> None:
    s = opened(session, ferinos)
    sale = sell(session, ferinos, s, "M-1")
    ok = approve(session, ferinos, sales.VOID, sale.id, "supervisor", "Marites")
    for no in ("X-1", "X-2"):  # past the service check: the partial unique index refuses
        row = SalesReceipt(
            branch_id=s.branch_id, session_id=s.id, receipt_no=no, business_date=yesterday(),
            sold_at=noon(yesterday()), clerk_id=s.person_id, subtotal=0, total=0,
            currency="PHP", approval_id=ok,
        )  # fmt: skip
        if no == "X-2":
            with pytest.raises(IntegrityError):
                store.insert(session, row, Actor.system(s.branch_id))
        else:
            store.insert(session, row, Actor.system(s.branch_id))


def test_only_head_staff_close_a_session(session: Session, ferinos: Ferinos) -> None:
    s = opened(session, ferinos)
    liza = ferinos[1]["Liza"]
    before = written(session)
    with pytest.raises(SalesError, match="closed_by"):
        sales.close_session(session, Actor.person(liza), s, 0, liza.id, noon(yesterday(), 18))
    assert (written(session), s.state) == (before, "open")
