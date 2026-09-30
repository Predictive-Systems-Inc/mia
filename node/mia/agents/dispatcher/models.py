"""Tables owned by the dispatcher agent (prefixed dispatcher_, created by its migrations)."""

import datetime as dt
from typing import ClassVar

from sqlmodel import Field

from mia.core.models import BranchScoped


class Absence(BranchScoped, table=True):
    __tablename__: ClassVar[str] = "dispatcher_absences"

    person_id: str = Field(foreign_key="person.id", index=True)
    date: dt.date = Field(index=True)
    reason: str = "sick"  # sick, late, leaving_early, other
    partial_day: str | None = None  # None = whole day, "morning", "afternoon"
    reported_by: str
