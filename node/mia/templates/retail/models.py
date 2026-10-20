"""Retail template tables: what a branch sells and when it is open. Shared entities stay in
mia.core.models; these tables add only the industry fields."""

import datetime as dt
from typing import ClassVar

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field

from mia.core.db import TZDateTime
from mia.core.models import BranchScoped, Stamped


class RetailItem(Stamped, table=True):
    """A sellable item. A null branch_id means every branch sells it at this price (the
    default; a branch's dated retail_item_prices row wins from its effective date). components
    lists the item ids a bundle holds (an id once per piece), empty for a single item; cost is
    the unit cost in minor units when the owner gave one."""

    __tablename__: ClassVar[str] = "retail_items"

    branch_id: str | None = Field(default=None, foreign_key="branch.id", index=True)
    name: str
    short_codes: list[str] = Field(default_factory=list, sa_type=JSON)
    price: int  # integer minor units
    currency: str = Field(max_length=3)
    active: bool = True
    sort_order: int = 0
    components: list[str] = Field(default_factory=list, sa_type=JSON)
    cost: int | None = None  # integer minor units


class RetailItemPrice(BranchScoped, table=True):
    """A branch's price for an item from effective_on (a local date) on; applied_at is set
    when the change took effect (items.apply_due). The newest row wins on the same date."""

    __tablename__: ClassVar[str] = "retail_item_prices"

    item_id: str = Field(foreign_key="retail_items.id", index=True)
    price: int  # integer minor units
    currency: str = Field(max_length=3)
    effective_on: dt.date = Field(index=True)
    approval_id: str | None = None
    set_by: str
    applied_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime)


class RetailBranchHours(BranchScoped, table=True):
    """Opening hours of a branch for one weekday (0 is Monday), local "HH:MM"."""

    __tablename__: ClassVar[str] = "retail_branch_hours"
    __table_args__ = (UniqueConstraint("branch_id", "weekday"),)

    weekday: int
    opens: str
    closes: str


class RetailIngredient(Stamped, table=True):
    """A stocked ingredient. A null branch_id means every branch stocks it."""

    __tablename__: ClassVar[str] = "retail_ingredients"

    branch_id: str | None = Field(default=None, foreign_key="branch.id", index=True)
    name: str
    short_codes: list[str] = Field(default_factory=list, sa_type=JSON)
    unit: str  # tray, kg, pack, tank or pcs
    reorder_point: int
    supplier: str | None = None
    pack_price: int | None = None  # integer minor units
    currency: str = Field(max_length=3)
    active: bool = True
