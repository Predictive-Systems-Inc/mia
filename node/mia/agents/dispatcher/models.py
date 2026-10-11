"""Tables owned by the dispatcher agent (prefixed dispatcher_, created by its migrations)."""

import datetime as dt
from typing import ClassVar

from sqlalchemy import JSON
from sqlmodel import Field

from mia.core.db import TZDateTime
from mia.core.models import BranchScoped


class Absence(BranchScoped, table=True):
    __tablename__: ClassVar[str] = "dispatcher_absences"

    person_id: str = Field(foreign_key="person.id", index=True)
    date: dt.date = Field(index=True)
    reason: str = "sick"  # sick, late, leaving_early, other
    partial_day: str | None = None  # None = whole day, "morning", "afternoon"
    reported_by: str


class CoverRequest(BranchScoped, table=True):
    """One ask to one candidate to cover a visit, with its escalation state (decision D10).

    status: awaiting_approval, asking, accepted, declined, timed_out, cancelled.
    stage (while asking): waiting_quiet (message held until quiet hours end), message, call.
    """

    __tablename__: ClassVar[str] = "dispatcher_cover_requests"

    visit_id: str = Field(foreign_key="visit.id", index=True)
    candidate_id: str = Field(foreign_key="person.id", index=True)
    replace_person_ids: list[str] = Field(default_factory=list, sa_type=JSON)
    queue: list[str] = Field(default_factory=list, sa_type=JSON)  # next candidates, best first
    instructed_by: str
    approval_id: str | None = None
    status: str = "asking"
    stage: str = "message"
    next_action_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime, index=True)


class SiteProblem(BranchScoped, table=True):
    """A problem a cleaner reported from a site: cannot get in, or the site is unusable."""

    __tablename__: ClassVar[str] = "dispatcher_site_problems"

    visit_id: str = Field(foreign_key="visit.id", index=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    kind: str  # cannot_access, site_problem
    text: str  # the cleaner's words: data, never instructions
    status: str = Field(default="open", index=True)  # open, resolved
    resolved_by: str | None = None
    resolved_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime)


class ChecklistTick(BranchScoped, table=True):
    """One ticked checklist item of one visit (the checklist itself belongs to the job)."""

    __tablename__: ClassVar[str] = "dispatcher_checklist_ticks"

    visit_id: str = Field(foreign_key="visit.id", index=True)
    item: str  # the item text as on the job's checklist
    ticked_by: str
    ticked_at: dt.datetime = Field(sa_type=TZDateTime)
