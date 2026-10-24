"""The production planner's tables (agent-owned, prefixed production_planner_, data standard
rule 9). Recipes, plans and batches are on the commissary branch; a dispatch is on the kiosk it
goes to (from_branch_id is the commissary), so a kiosk supervisor reads it by branch.

Quantities are integers (pieces, or thousandths of an ingredient's unit), times are aware; no
free text from a customer is stored here."""

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field

from mia.core.db import TZDateTime
from mia.core.models import BranchScoped


class Recipe(BranchScoped, table=True):
    """The recipe of one single item (never a bundle), entered by the owner: pieces per batch,
    oven minutes per batch and lines `[{"ingredient_id", "quantity_milli"}]` in thousandths of
    the ingredient's unit for one batch. keeps_overnight: a leftover is sold the next day (Q93)."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "production_planner_recipes"

    item_id: str = Field(foreign_key="retail_items.id", index=True)
    batch_yield: int
    oven_minutes: int
    lines: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    keeps_overnight: bool = False
    active: bool = True
    set_by: str = Field(foreign_key="person.id")


class Plan(BranchScoped, table=True):
    """The production plan of one date: status draft or confirmed; lines per item `{"item_id",
    "batches", "pieces", "more", "changed_by", "change_note", "kiosks": [{"branch_id",
    "forecast", "orders", "leftover", "demand", "pieces"}]}`. One row per commissary and date."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "production_planner_plans"
    __table_args__ = (UniqueConstraint("branch_id", "production_date"),)

    production_date: dt.date
    status: str = "draft"
    lines: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    confirmed_by: str | None = Field(default=None, foreign_key="person.id")


class Batch(BranchScoped, table=True):
    """One batch of an item in a plan: planned yield, good pieces, waste and its reason (burnt,
    undercooked, dropped or other). A repeated batch number updates its row (a correction); one
    row per plan, item and batch number."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "production_planner_batches"
    __table_args__ = (UniqueConstraint("plan_id", "item_id", "batch_no"),)

    plan_id: str = Field(foreign_key="production_planner_plans.id", index=True)
    item_id: str = Field(foreign_key="retail_items.id")
    batch_no: int
    planned_yield: int
    good: int
    waste: int
    reason: str | None = None
    recorded_by: str = Field(foreign_key="person.id")
    at: dt.datetime = Field(sa_type=TZDateTime)


class Dispatch(BranchScoped, table=True):
    """What the commissary sends one kiosk (branch_id) for a business date: lines `[{"item_id",
    "quantity"}]`; status packed, delivered, matched or short; received holds the kiosk's
    received quantities after the match. One row per kiosk and date."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "production_planner_dispatches"
    __table_args__ = (UniqueConstraint("branch_id", "business_date"),)

    from_branch_id: str = Field(foreign_key="branch.id", max_length=26)
    plan_id: str = Field(foreign_key="production_planner_plans.id")
    business_date: dt.date = Field(index=True)
    lines: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    status: str = "packed"
    delivered_by: str | None = Field(default=None, foreign_key="person.id")
    delivered_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime)
    received: list[dict[str, Any]] | None = Field(default=None, sa_type=JSON)
