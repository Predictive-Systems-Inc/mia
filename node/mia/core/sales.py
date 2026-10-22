"""Sales operations (data standard 1.9, ADR 022, D43): a clerk's session, receipts with their
lines and payments, voids and refunds, and the day's sales by item and tender over the one source
a kiosk uses (sales.receipts_from in the org settings).

Every write goes through store (one event per row). A refused call raises SalesError before any
row is written. Money is integer minor units; totals, the payment sum and the session's expected
cash are computed here, never by a model (rule 7). Callers check the tool permission first; only
receipts() checks data rights itself (the read the tables' rights are probed by)."""

import datetime as dt
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from mia.core import orgconfig, store
from mia.core.models import (
    DISCOUNT_REASONS,
    Actor,
    Approval,
    Branch,
    Person,
    SalesCount,
    SalesPayment,
    SalesReceipt,
    SalesReceiptLine,
    SalesSession,
    Tender,
)
from mia.core.rbac import Resource, get_rbac
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailItem, RetailItemPrice

VOID = "sales.void"  # approval type: head staff (supervisor) decides, money risk
REFUND = "sales.refund"  # approval type: the owner or an admin decides, money risk
VOID_ROLE, REFUND_ROLE = "supervisor", "admin"  # owner inherits admin, admin supervisor
RECEIPTS = Resource(kind="data", name="sales_receipts")


class SalesError(ValueError):
    """The write was refused; nothing was written. The message is a short reason code."""


class LineIn(BaseModel):
    """One line as the till sends it: the price is never sent, it is the dated price."""

    item_id: str
    quantity: int  # negative on a refund
    discount: int = Field(0, ge=0)  # minor units, sales only
    experiment_id: str | None = None
    refunded_line_id: str | None = None  # a refund line names the sale line it returns


class PaymentIn(BaseModel):
    """One tender, net of change; negative on a refund."""

    tender: Tender
    amount: int
    reference: str | None = Field(None, max_length=64)


class DaySales(BaseModel):
    """A branch's business date: the source read, (quantity, amount) by item id and amount by
    tender. On a receipts day item amounts are line totals (before a receipt-level discount)."""

    source: Literal["counts", "receipts"]
    by_item: dict[str, tuple[int, int]]
    by_tender: dict[str, int]


def _business_date(session: Session, branch_id: str, at: dt.datetime) -> dt.date:
    branch = session.get(Branch, branch_id)
    if branch is None:
        raise SalesError("branch")
    return retail_hours.business_date_at(branch, retail_hours.load(session, branch_id), at)


def _holds(person: Person, role: str) -> bool:
    enforcer = get_rbac().enforcer
    return any(
        r == role or role in enforcer.get_implicit_roles_for_user(r, "*") for r in person.roles
    )


def _approved(
    session: Session, approval_id: str | None, kind: str, role: str, subject_id: str, branch_id: str
) -> Approval:
    """The approval row: this branch, this type and subject, approved, money risk, decided by a
    person holding role, and not yet used by a receipt. SalesError("approval") otherwise."""
    a = session.get(Approval, approval_id) if approval_id else None
    ok = (
        a is not None
        and (a.branch_id, a.type, a.subject_id, a.status)
        == (branch_id, kind, subject_id, "approved")
        and a.evidence.get("risk") == "money"
    )
    decider = session.get(Person, a.decided_by or "") if a is not None and ok else None
    if a is None or decider is None or not _holds(decider, role):
        raise SalesError("approval")
    if session.exec(select(SalesReceipt).where(SalesReceipt.approval_id == a.id)).first():
        raise SalesError("approval")  # one approval, one void or refund
    return a


def open_session(
    session: Session,
    actor: Actor,
    branch_id: str,
    person_id: str,
    opened_at: dt.datetime,
    currency: str,
    *,
    visit_id: str | None = None,
    opening_float: int | None = None,
) -> SalesSession:
    """Open the person's session at the branch (event sales.session_opened). The float defaults
    to the branch's last closed session's counted cash, else 0. SalesError("session_open") when
    the person already has an open session there."""
    open_ = select(SalesSession).where(
        SalesSession.branch_id == branch_id,
        SalesSession.person_id == person_id,
        SalesSession.state == "open",
    )
    if session.exec(open_).first():
        raise SalesError("session_open")
    if opening_float is None:
        last = session.exec(
            select(SalesSession)
            .where(SalesSession.branch_id == branch_id, SalesSession.state == "closed")
            .order_by(col(SalesSession.closed_at).desc())
        ).first()
        opening_float = (last.counted or 0) if last else 0
    row = SalesSession(
        branch_id=branch_id,
        person_id=person_id,
        visit_id=visit_id,
        business_date=_business_date(session, branch_id, opened_at),
        opened_at=opened_at,
        opening_float=opening_float,
        currency=currency,
    )
    return store.insert(session, row, actor, action="sales.session_opened")


def expected_cash(session: Session, sales_session: SalesSession) -> int:
    """The opening float plus the session's cash payments on paid receipts (refunds negative)."""
    paid = select(SalesPayment.amount).join(
        SalesReceipt, col(SalesReceipt.id) == col(SalesPayment.receipt_id)
    )
    paid = paid.where(
        SalesPayment.session_id == sales_session.id,
        SalesPayment.tender == "cash",
        SalesReceipt.status == "paid",
    )
    return sales_session.opening_float + sum(session.exec(paid))


def close_session(
    session: Session,
    actor: Actor,
    sales_session: SalesSession,
    counted: int,
    closed_by: str,
    closed_at: dt.datetime,
) -> SalesSession:
    """Close an open session with head staff's count (event sales.session_closed), freezing
    expected (expected_cash) and difference (counted less expected)."""
    if sales_session.state != "open":
        raise SalesError("session_closed")
    expected = expected_cash(session, sales_session)
    changes = {
        "state": "closed",
        "counted": counted,
        "expected": expected,
        "difference": counted - expected,
        "closed_by": closed_by,
        "closed_at": closed_at,
    }
    return store.update(session, sales_session, changes, actor, action="sales.session_closed")


def _price(
    session: Session, item: RetailItem, branch_id: str, day: dt.date
) -> tuple[int, str | None]:
    """The dated price and its retail_item_prices id (items.price_on's rule), else the default."""
    row = session.exec(
        select(RetailItemPrice)
        .where(RetailItemPrice.branch_id == branch_id, RetailItemPrice.item_id == item.id)
        .where(col(RetailItemPrice.effective_on) <= day)
        .order_by(
            col(RetailItemPrice.effective_on).desc(),
            col(RetailItemPrice.created_at).desc(),
            col(RetailItemPrice.id).desc(),
        )
    ).first()
    return (row.price, row.id) if row else (item.price, None)


def _sale_line(session: Session, line: LineIn, s: SalesSession, day: dt.date) -> SalesReceiptLine:
    item = session.get(RetailItem, line.item_id)
    if item is None or item.branch_id not in (None, s.branch_id) or item.currency != s.currency:
        raise SalesError("item")
    if line.quantity <= 0 or line.refunded_line_id is not None:
        raise SalesError("quantity")
    price, price_id = _price(session, item, s.branch_id, day)
    if line.discount > line.quantity * price:
        raise SalesError("discount")
    return SalesReceiptLine(
        branch_id=s.branch_id,
        receipt_id="",
        item_id=item.id,
        quantity=line.quantity,
        unit_price=price,
        price_id=price_id,
        experiment_id=line.experiment_id,
        discount=line.discount,
        line_total=line.quantity * price - line.discount,
        currency=s.currency,
    )


def _refund_line(session: Session, line: LineIn, sale: SalesReceipt) -> SalesReceiptLine:
    """A negative line at the price paid, its total in proportion to the sale line's total."""
    orig = session.get(SalesReceiptLine, line.refunded_line_id or "")
    if orig is None or orig.receipt_id != sale.id or orig.item_id != line.item_id:
        raise SalesError("refunded_line")
    returned = session.exec(
        select(SalesReceiptLine.quantity)
        .join(SalesReceipt, col(SalesReceipt.id) == col(SalesReceiptLine.receipt_id))
        .where(SalesReceiptLine.refunded_line_id == orig.id, SalesReceipt.status == "paid")
    )
    if line.quantity >= 0 or line.discount or -line.quantity - sum(returned) > orig.quantity:
        raise SalesError("quantity")
    total = -(orig.line_total * -line.quantity // orig.quantity)
    return SalesReceiptLine(
        branch_id=orig.branch_id,
        receipt_id="",
        item_id=orig.item_id,
        quantity=line.quantity,
        unit_price=orig.unit_price,
        price_id=orig.price_id,
        experiment_id=orig.experiment_id,
        discount=line.quantity * orig.unit_price - total,
        line_total=total,
        refunded_line_id=orig.id,
        currency=orig.currency,
    )


def record_receipt(
    session: Session,
    actor: Actor,
    sales_session: SalesSession,
    receipt_no: str,
    sold_at: dt.datetime,
    lines: Sequence[LineIn],
    payments: Sequence[PaymentIn],
    *,
    discount: int = 0,
    discount_reason: str | None = None,
    customer_id: str | None = None,
    order_id: str | None = None,
    refund_of: str | None = None,
    approval_id: str | None = None,
    source: Literal["pos", "chat"] = "pos",
    source_message_id: str | None = None,
) -> SalesReceipt:
    """Record a sale, or with refund_of a refund (an owner or admin REFUND approval of that
    receipt), with its lines and payments in one flush: events sales.receipt_recorded or
    sales.refund_recorded, one per line and sales.payment_recorded per payment. Checked first,
    nothing written on a refusal: an open session, a new receipt_no at the branch, the dated
    prices, total = subtotal less discount (a reason when there is one), payments summing to
    the total with the receipt's sign. The caller commits."""
    s = sales_session
    if s.state != "open":
        raise SalesError("session_closed")
    if not lines:
        raise SalesError("lines")
    taken = select(SalesReceipt).where(
        SalesReceipt.branch_id == s.branch_id, SalesReceipt.receipt_no == receipt_no
    )
    if session.exec(taken).first():
        raise SalesError("receipt_no")
    day = _business_date(session, s.branch_id, sold_at)
    sign = 1
    if refund_of is None:
        if approval_id is not None:
            raise SalesError("approval")
        rows = [_sale_line(session, line, s, day) for line in lines]
    else:
        sign = -1
        sale = session.get(SalesReceipt, refund_of)
        if (
            sale is None
            or sale.branch_id != s.branch_id
            or (sale.kind, sale.status)
            != (
                "sale",
                "paid",
            )
        ):
            raise SalesError("refund_of")
        _approved(session, approval_id, REFUND, REFUND_ROLE, sale.id, s.branch_id)
        rows = [_refund_line(session, line, sale) for line in lines]
    subtotal = sum(r.line_total for r in rows)
    total = subtotal - discount
    if discount * sign < 0 or abs(discount) > abs(subtotal):
        raise SalesError("discount")
    if bool(discount) != (discount_reason is not None) or (
        discount_reason is not None and discount_reason not in DISCOUNT_REASONS
    ):
        raise SalesError("discount_reason")
    if sum(p.amount for p in payments) != total or any(p.amount * sign <= 0 for p in payments):
        raise SalesError("payments")
    receipt = SalesReceipt(
        branch_id=s.branch_id,
        session_id=s.id,
        receipt_no=receipt_no,
        business_date=day,
        sold_at=sold_at,
        clerk_id=s.person_id,
        customer_id=customer_id,
        order_id=order_id,
        kind="sale" if refund_of is None else "refund",
        refund_of=refund_of,
        subtotal=subtotal,
        discount=discount,
        discount_reason=discount_reason,
        total=total,
        currency=s.currency,
        approval_id=approval_id,
        source=source,
        source_message_id=source_message_id,
    )
    action = "sales.receipt_recorded" if refund_of is None else "sales.refund_recorded"
    store.insert(session, receipt, actor, action=action, approval_id=approval_id)
    for row in rows:
        row.receipt_id = receipt.id
        store.insert(session, row, actor)
    for p in payments:
        payment = SalesPayment(
            branch_id=s.branch_id,
            receipt_id=receipt.id,
            session_id=s.id,
            tender=p.tender,
            amount=p.amount,
            currency=s.currency,
            paid_at=sold_at,
            reference=p.reference,
        )
        store.insert(session, payment, actor, action="sales.payment_recorded")
    return receipt


def void_receipt(
    session: Session, actor: Actor, receipt: SalesReceipt, approval_id: str, reason: str
) -> SalesReceipt:
    """Void a paid receipt of an open session with head staff's VOID approval of it (event
    sales.receipt_voided; voided_by is the approver). After the close only a refund is possible.
    SalesError and nothing written otherwise."""
    s = session.get(SalesSession, receipt.session_id)
    if s is None or s.state != "open":
        raise SalesError("session_closed")
    if receipt.status != "paid":
        raise SalesError("status")
    a = _approved(session, approval_id, VOID, VOID_ROLE, receipt.id, receipt.branch_id)
    changes = {
        "status": "voided",
        "voided_by": a.decided_by,
        "void_reason": reason,
        "approval_id": a.id,
    }
    return store.update(
        session, receipt, changes, actor, action="sales.receipt_voided", approval_id=a.id
    )


def receipts(
    session: Session, actor: Actor, branch_id: str, business_date: dt.date
) -> list[SalesReceipt]:
    """The branch's receipts of a business date the actor may read: another branch needs
    read_all, a clerk (read_own) sees only their own. PermissionDenied otherwise."""
    rbac = get_rbac()
    if branch_id != actor.branch_id:
        rbac.require(actor, RECEIPTS, "read_all", session=session)
    stmt = select(SalesReceipt).where(
        SalesReceipt.branch_id == branch_id, SalesReceipt.business_date == business_date
    )
    if not rbac.check(actor, RECEIPTS, "read"):
        own = Resource(kind="data", name=RECEIPTS.name, owner_id=actor.person_id)
        rbac.require(actor, own, "read", session=session)
        stmt = stmt.where(SalesReceipt.clerk_id == actor.person_id)
    return list(session.exec(stmt.order_by(col(SalesReceipt.sold_at))))


def day_sales(session: Session, branch_id: str, business_date: dt.date) -> DaySales:
    """The branch's sales of one business date from its one source (SalesSettings.source): on a
    counts day the live sales_counts (superseded rows skipped, as the sales supervisor reads
    them); on a receipts day the paid receipts' lines by item and payments by tender, refunds
    as negatives. Never both. Unchecked: callers check their own read rights."""
    branch = session.get(Branch, branch_id)
    if branch is None:
        raise SalesError("branch")
    source = orgconfig.load().sales.source(branch.name, business_date)
    items: dict[str, tuple[int, int]] = {}
    tenders: dict[str, int] = defaultdict(int)

    def add(item_id: str, quantity: int, amount: int) -> None:
        q, a = items.get(item_id, (0, 0))
        items[item_id] = (q + quantity, a + amount)

    if source == "counts":
        counts = session.exec(
            select(SalesCount)
            .where(SalesCount.branch_id == branch_id, SalesCount.business_date == business_date)
            .where(col(SalesCount.superseded_by).is_(None))
        )
        for c in counts:
            add(c.item_id, c.quantity, c.amount)
            tenders[c.tender] += c.amount
    else:
        paid = (SalesReceipt.branch_id == branch_id, SalesReceipt.business_date == business_date)
        lines = session.exec(
            select(SalesReceiptLine)
            .join(SalesReceipt, col(SalesReceipt.id) == col(SalesReceiptLine.receipt_id))
            .where(*paid, SalesReceipt.status == "paid")
        )
        for line in lines:
            add(line.item_id, line.quantity, line.line_total)
        pays = session.exec(
            select(SalesPayment)
            .join(SalesReceipt, col(SalesReceipt.id) == col(SalesPayment.receipt_id))
            .where(*paid, SalesReceipt.status == "paid")
        )
        for p in pays:
            tenders[p.tender] += p.amount
    return DaySales(source=source, by_item=items, by_tender=dict(tenders))
