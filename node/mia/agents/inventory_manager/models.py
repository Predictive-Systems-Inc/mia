"""Inventory manager tables (agent-owned, prefixed inventory_manager_, data standard rule 9).

Stock events are shared and live in mia/core/models.py (data standard 1.5)."""

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import JSON
from sqlmodel import Field

from mia.core.models import BranchScoped


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
