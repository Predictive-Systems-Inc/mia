"""Retail template tables: what a branch sells and when it is open. Shared entities stay in
mia.core.models; these tables add only the industry fields."""

from typing import ClassVar

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field

from mia.core.models import BranchScoped, Stamped


class RetailItem(Stamped, table=True):
    """A sellable item. A null branch_id means every branch sells it at this price."""

    __tablename__: ClassVar[str] = "retail_items"

    branch_id: str | None = Field(default=None, foreign_key="branch.id", index=True)
    name: str
    short_codes: list[str] = Field(default_factory=list, sa_type=JSON)
    price: int  # integer minor units
    currency: str = Field(max_length=3)
    active: bool = True
    sort_order: int = 0


class RetailBranchHours(BranchScoped, table=True):
    """Opening hours of a branch for one weekday (0 is Monday), local "HH:MM"."""

    __tablename__: ClassVar[str] = "retail_branch_hours"
    __table_args__ = (UniqueConstraint("branch_id", "weekday"),)

    weekday: int
    opens: str
    closes: str
