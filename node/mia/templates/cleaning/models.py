"""Cleaning template tables. Shared entities (location, job, visit) and all employee data
(availability, working-hour limits, home base) live in mia.core.models; these tables add only
the industry fields that the data standard leaves to templates."""

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
