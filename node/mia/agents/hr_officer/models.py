"""The hr officer's tables (agent-owned, prefixed hr_officer_, data standard rule 9)."""

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field

from mia.core.db import TZDateTime
from mia.core.models import BranchScoped


class Contract(BranchScoped, table=True):
    """One person's terms: employment type (regular, probationary, part_time), daily rate in
    minor units, rest day (weekday number), start and optional end date."""

    __redact__: ClassVar[frozenset[str]] = frozenset(
        {"daily_rate"}
    )  # pay and leave stay off the chain
    __tablename__: ClassVar[str] = "hr_officer_contracts"

    person_id: str = Field(foreign_key="person.id", index=True)
    employment_type: str
    daily_rate: int
    currency: str = Field(max_length=3)
    rest_day: int
    start_date: dt.date
    end_date: dt.date | None = None
    position: str
    set_by: str


class Payslip(BranchScoped, table=True):
    """One issued payslip per person and cutoff. lines carry kind, minutes or days, rate and
    amount; deductions carry kind and amount; money is in minor units."""

    __redact__: ClassVar[frozenset[str]] = frozenset(
        {"lines", "gross", "deductions", "net"}
    )  # pay and leave stay off the chain
    __tablename__: ClassVar[str] = "hr_officer_payslips"
    __table_args__ = (UniqueConstraint("person_id", "cutoff_start"),)

    person_id: str = Field(foreign_key="person.id", index=True)
    cutoff_start: dt.date
    cutoff_end: dt.date
    pay_date: dt.date
    lines: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    gross: int
    deductions: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    net: int
    currency: str = Field(max_length=3)
    issued_at: dt.datetime = Field(sa_type=TZDateTime)
    message_id: str | None = None


class Leave(BranchScoped, table=True):
    """A leave request or grant: kind vacation, sick or unpaid; status requested, approved or
    rejected. reason is free text and is stored as data."""

    __redact__: ClassVar[frozenset[str]] = frozenset(
        {"kind", "reason"}
    )  # pay and leave stay off the chain
    __tablename__: ClassVar[str] = "hr_officer_leave"

    person_id: str = Field(foreign_key="person.id", index=True)
    kind: str
    start_date: dt.date
    end_date: dt.date
    days: int
    status: str
    approval_id: str | None = None
    reason: str = ""
