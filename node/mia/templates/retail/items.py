"""Item services of the retail template: a branch's dated prices and an item's short codes.

retail_items.price is the default; a branch's retail_item_prices row is its price from the row's
effective date on. Every write goes through mia.core.store and emits an event.
"""

import datetime as dt

from sqlmodel import Session, col, select

from mia.core import store
from mia.core.db import utcnow
from mia.core.models import Actor, Branch
from mia.templates.retail.models import RetailItem, RetailItemPrice


def schedule_price(
    session: Session,
    item: RetailItem,
    branch_id: str,
    price: int,
    effective_on: dt.date,
    actor: Actor,
    *,
    approval_id: str | None = None,
    tool_call_id: str | None = None,
) -> RetailItemPrice:
    """Add the branch's price for the item from effective_on (event retail.item_price_scheduled).
    The row takes effect for price_on at once; apply_due stamps it when the day comes."""
    row = RetailItemPrice(
        branch_id=branch_id,
        item_id=item.id,
        price=price,
        currency=item.currency,
        effective_on=effective_on,
        approval_id=approval_id,
        set_by=actor.person_id or actor.principal.id,
    )
    return store.insert(
        session,
        row,
        actor,
        action="retail.item_price_scheduled",
        tool_call_id=tool_call_id,
        approval_id=approval_id,
    )


def price_on(session: Session, item: RetailItem, branch_id: str, day: dt.date) -> int:
    """The item's price at the branch on a local date: the branch's row with the latest
    effective_on not after day (the newest row on a tie), else the item's default price."""
    row = session.exec(
        select(RetailItemPrice)
        .where(RetailItemPrice.branch_id == branch_id)
        .where(RetailItemPrice.item_id == item.id)
        .where(col(RetailItemPrice.effective_on) <= day)
        .order_by(
            col(RetailItemPrice.effective_on).desc(),
            col(RetailItemPrice.created_at).desc(),
            col(RetailItemPrice.id).desc(),
        )
    ).first()
    return row.price if row else item.price


def apply_due(
    session: Session, branch: Branch, day: dt.date, actor: Actor
) -> list[RetailItemPrice]:
    """Stamp applied_at on the branch's rows effective on or before day that have none, each with
    event retail.item_price_changed (the row carries its effective date). Returns them, oldest
    effective date first; a second call on the same day returns nothing."""
    rows = session.exec(
        select(RetailItemPrice)
        .where(RetailItemPrice.branch_id == branch.id)
        .where(col(RetailItemPrice.effective_on) <= day)
        .where(col(RetailItemPrice.applied_at).is_(None))
        .order_by(col(RetailItemPrice.effective_on), col(RetailItemPrice.created_at))
    ).all()
    now = utcnow()
    return [
        store.update(session, row, {"applied_at": now}, actor, action="retail.item_price_changed")
        for row in rows
    ]


def set_short_codes(
    session: Session,
    item: RetailItem,
    codes: list[str],
    actor: Actor,
    tool_call_id: str | None,
) -> RetailItem:
    """Replace the item's short codes (event retail_items.updated). Clash checks are the
    caller's (the tool refuses a code another item or ingredient holds)."""
    return store.update(session, item, {"short_codes": codes}, actor, tool_call_id=tool_call_id)


def create_variant(
    session: Session,
    base: RetailItem,
    name: str,
    price: int,
    components: list[str],
    actor: Actor,
    tool_call_id: str | None,
) -> RetailItem:
    """A new item beside `base` (a premium variant, a bundle or a larger box) sold only at the
    actor's branch at `price` in base's currency, after it in the menu, inactive until its
    experiment starts (event retail.item_created). components lists a bundle's item ids."""
    item = RetailItem(
        branch_id=actor.branch_id,
        name=name,
        price=price,
        currency=base.currency,
        active=False,
        sort_order=base.sort_order,
        components=components,
    )
    return store.insert(
        session, item, actor, action="retail.item_created", tool_call_id=tool_call_id
    )
