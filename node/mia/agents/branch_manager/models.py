"""The branch manager's tables (agent-owned, prefixed branch_manager_, data standard rule 9)."""

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import JSON
from sqlmodel import Field

from mia.core.models import BranchScoped, Stamped


class Strategy(Stamped, table=True):
    """One pricing strategy of the curated catalogue (spec section 13): name_key is its i18n
    label, kind the experiment kind it proposes (price, promo, bundle), params the rule's numbers
    read by experiments.py, source the published work it rests on, description the fixed English
    line Jev reads to match a request to it. Seeded, never staff text."""

    __tablename__: ClassVar[str] = "branch_manager_strategies"

    name_key: str = Field(unique=True)
    kind: str
    params: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    source: str
    description: str
    active: bool = True


class Experiment(BranchScoped, table=True):
    """A 14-day price, promo or bundle test of one item at a branch (money in minor units).
    status is approved, running, done, rejected or kept; a proposal is the pending Approval and
    has no row. baseline and result hold days, units and amount; rationale holds the branch's
    numbers the strategy's condition read. approval_id is None for seeded rows."""

    __tablename__: ClassVar[str] = "branch_manager_experiments"

    kind: str
    strategy_id: str = Field(foreign_key="branch_manager_strategies.id", index=True)
    item_id: str = Field(foreign_key="retail_items.id", index=True)
    from_price: int
    to_price: int
    currency: str = Field(max_length=3)
    starts_on: dt.date
    ends_on: dt.date
    baseline: dict[str, int] | None = Field(default=None, sa_type=JSON)
    result: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    rationale: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    status: str
    approval_id: str | None = None
    proposed_by: str
    decided_by: str | None = None


class Tip(Stamped, table=True):
    """A selling tip or a quote (kind tip or quote) in one language, for one item or general
    (item_id None), with its source. Seeded from tips.py; no staff or model text lands here."""

    __tablename__: ClassVar[str] = "branch_manager_tips"

    language: str = Field(index=True)
    kind: str
    item_id: str | None = Field(default=None, foreign_key="retail_items.id")
    text: str
    source: str
    active: bool = True


class Coaching(BranchScoped, table=True):
    """One coaching message sent to a person (kind morning, cheer, nudge or tip) on a local
    date; a nudge is stored as its kind only, so nothing here is sensitive."""

    __redact__: ClassVar[frozenset[str]] = frozenset()
    __tablename__: ClassVar[str] = "branch_manager_coaching"

    person_id: str = Field(foreign_key="person.id", index=True)
    kind: str
    sent_on: dt.date
    tip_id: str | None = Field(default=None, foreign_key="branch_manager_tips.id")
    message_id: str | None = None
