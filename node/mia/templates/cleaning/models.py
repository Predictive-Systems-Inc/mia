"""Cleaning template tables. Shared entities (location, job, visit) live in mia.core.models;
these tables add the industry fields that the data standard leaves to templates."""

from typing import Any, ClassVar

from sqlalchemy import JSON
from sqlmodel import Field

from mia.core.models import BranchScoped


class CleaningSite(BranchScoped, table=True):
    """Industry details for a location."""

    __tablename__: ClassVar[str] = "cleaning_sites"

    location_id: str = Field(foreign_key="location.id", index=True)
    site_type: str = "office"  # office, shop, home
    floor_area_m2: int | None = None


class CleaningChecklist(BranchScoped, table=True):
    __tablename__: ClassVar[str] = "cleaning_checklists"

    job_id: str = Field(foreign_key="job.id", index=True)
    items: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)


class StaffAvailability(BranchScoped, table=True):
    """Weekly availability window for a person (weekday 0 = Monday), local time "HH:MM"."""

    __tablename__: ClassVar[str] = "cleaning_availability"

    person_id: str = Field(foreign_key="person.id", index=True)
    weekday: int
    start: str
    end: str


class WorkLimit(BranchScoped, table=True):
    """Working-hour limits for a person, in minutes."""

    __tablename__: ClassVar[str] = "cleaning_work_limits"

    person_id: str = Field(foreign_key="person.id", index=True, unique=True)
    max_daily_minutes: int = 600
    max_weekly_minutes: int = 2400
