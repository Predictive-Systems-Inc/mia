"""Sales supervisor tables (agent-owned, prefixed sales_supervisor_, data standard rule 9)."""

import datetime as dt
from typing import ClassVar

from sqlalchemy import JSON
from sqlmodel import Field

from mia.core.db import TZDateTime
from mia.core.models import BranchScoped


class SalesCount(BranchScoped, table=True):
    """One reported count of one item for a business date; a correction supersedes a row."""

    __tablename__: ClassVar[str] = "sales_supervisor_counts"

    item_id: str = Field(foreign_key="retail_items.id", index=True)
    quantity: int
    amount: int  # integer minor units
    currency: str = Field(max_length=3)
    reported_at: dt.datetime = Field(sa_type=TZDateTime)
    reported_by: str = Field(foreign_key="person.id", index=True)
    business_date: dt.date = Field(index=True)
    supersedes: str | None = None
    superseded_by: str | None = None
    source_message_id: str | None = None


class SalesTarget(BranchScoped, table=True):
    """A day or month target (money, quantity, or both) from a start date."""

    __tablename__: ClassVar[str] = "sales_supervisor_targets"

    period: str  # day or month
    starts_on: dt.date = Field(index=True)
    amount: int | None = None
    currency: str = Field(max_length=3)
    quantity: int | None = None
    item_id: str | None = None
    set_by: str


class SalesNote(BranchScoped, table=True):
    """A clerk's words about the day (why sales were up or down)."""

    __tablename__: ClassVar[str] = "sales_supervisor_notes"

    business_date: dt.date = Field(index=True)
    person_id: str
    text: str
    themes: list[str] = Field(default_factory=list, sa_type=JSON)
    asked_message_id: str | None = None
