"""Inventory manager tables (agent-owned, prefixed inventory_manager_, data standard rule 9)."""

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import JSON
from sqlmodel import Field

from mia.core.db import TZDateTime
from mia.core.models import BranchScoped


class StockEvent(BranchScoped, table=True):
    """One thing said about stock: sold_out, count, leftover, waste, low or received."""

    __tablename__: ClassVar[str] = "inventory_manager_stock_events"

    kind: str
    item_id: str | None = Field(default=None, foreign_key="retail_items.id")
    ingredient_id: str | None = Field(default=None, foreign_key="retail_ingredients.id")
    quantity: int | None = None
    unit: str | None = None
    reason: str | None = None
    at: dt.datetime = Field(sa_type=TZDateTime)  # the sell-out time or the report time
    reported_by: str = Field(foreign_key="person.id")
    business_date: dt.date = Field(index=True)
    source_message_id: str | None = None
    order_id: str | None = None


class SupplierOrder(BranchScoped, table=True):
    """A supplier order: draft, approved, rejected or received. Lines carry ingredient_id,
    quantity, unit and unit_price (minor units); total is in minor units."""

    __tablename__: ClassVar[str] = "inventory_manager_orders"

    supplier: str
    lines: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    currency: str = Field(max_length=3)
    total: int | None = None
    status: str
    approval_id: str | None = None
    requested_by: str
    business_date: dt.date
