"""The customer service's tables (agent-owned, prefixed customer_service_, data standard rule 9).
Customer identity (name, address) and customer text stay in these rows, never on the hash chain."""

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field

from mia.core.db import TZDateTime
from mia.core.models import BranchScoped


class Customer(BranchScoped, table=True):
    """One member of the public on one channel address (unique per channel). name is as the
    channel gave it; last_inbound_at opens the 24-hour reply window; held_until is set by the
    message throttle."""

    __redact__: ClassVar[frozenset[str]] = frozenset({"name", "address"})
    __tablename__: ClassVar[str] = "customer_service_customers"
    __table_args__ = (UniqueConstraint("channel", "address"),)

    channel: str
    address: str
    name: str | None = None
    language: str
    first_seen_at: dt.datetime = Field(sa_type=TZDateTime)
    last_inbound_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime)
    held_until: dt.datetime | None = Field(default=None, sa_type=TZDateTime)


class Order(BranchScoped, table=True):
    """A customer order. lines carry item_id, quantity and unit_price (minor units); total is
    the lines plus any delivery fee. fulfilment pickup or delivery; status waiting, confirmed,
    ready, picked_up, cancelled or rejected; decided_by is the person who approved or rejected."""

    __redact__: ClassVar[frozenset[str]] = frozenset({"delivery_note"})
    __tablename__: ClassVar[str] = "customer_service_orders"

    customer_id: str = Field(foreign_key="customer_service_customers.id", index=True)
    lines: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    total: int
    currency: str = Field(max_length=3)
    fulfilment: str
    pickup_at: dt.datetime = Field(sa_type=TZDateTime)
    delivery_area: str | None = None
    delivery_note: str | None = None
    status: str
    approval_id: str | None = None
    decided_by: str | None = None
    source_message_id: str | None = None


class CustomerMessage(BranchScoped, table=True):
    """One message in (from the customer) or out (to the customer). status queued, sending, sent,
    failed (the channel refused it; never resent) or skipped (outside the 24-hour window);
    inbound rows are stored as sent. decision holds the action and confidence only
    (pseudonymised)."""

    __redact__: ClassVar[frozenset[str]] = frozenset({"text", "blocks"})
    __tablename__: ClassVar[str] = "customer_service_messages"

    customer_id: str = Field(foreign_key="customer_service_customers.id", index=True)
    direction: str
    text: str = ""
    blocks: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    at: dt.datetime = Field(sa_type=TZDateTime)
    status: str = "sent"
    channel_message_id: str | None = None
    decision: dict[str, Any] | None = Field(default=None, sa_type=JSON)


class Complaint(BranchScoped, table=True):
    """A customer complaint, optionally about one order; status open or resolved."""

    __redact__: ClassVar[frozenset[str]] = frozenset({"text"})
    __tablename__: ClassVar[str] = "customer_service_complaints"

    customer_id: str = Field(foreign_key="customer_service_customers.id", index=True)
    text: str
    order_id: str | None = Field(default=None, foreign_key="customer_service_orders.id")
    status: str = "open"
    resolved_by: str | None = None
    resolved_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime)
