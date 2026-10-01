"""Data standard v1.0: the shared tables every agent and template relies on.

Conventions (see docs/adr/002-data-standard.md): IDs are ULIDs, times are ISO 8601 with time
zone, money is integer minor units plus a currency code, languages are BCP 47 codes. Every table
carries id, branch_id, created_at and updated_at, except organisation (no branch) and events
(timestamp only, append-only).
"""

import datetime as dt
from datetime import datetime
from typing import Any, ClassVar, Literal

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

from mia.core.db import TZDateTime, utcnow
from mia.core.ids import new_id

STANDARD_VERSION = "1.1"

# Code lists, versioned with the standard.
PersonStatus = Literal["active", "inactive"]
EngagementType = Literal["employee", "contractor", "agency"]
ClientType = Literal["business", "residential"]
VisitStatus = Literal["planned", "in_progress", "completed", "cancelled", "unfilled"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "escalated"]
ApprovalChannel = Literal["app_only", "any"]
ActorType = Literal["person", "agent", "system"]


class Stamped(SQLModel):
    """Fields shared by every data standard table except events."""

    id: str = Field(default_factory=new_id, primary_key=True, max_length=26)
    created_at: datetime = Field(default_factory=utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=utcnow, sa_type=TZDateTime)


class BranchScoped(Stamped):
    branch_id: str = Field(foreign_key="branch.id", index=True, max_length=26)


class Organisation(Stamped, table=True):
    name: str
    country: str = Field(max_length=2)
    default_language: str = "fi"


class Branch(Stamped, table=True):
    organisation_id: str = Field(foreign_key="organisation.id", index=True)
    name: str
    timezone: str = "Europe/Helsinki"


class Person(BranchScoped, table=True):
    name: str
    status: str = "active"
    roles: list[str] = Field(default_factory=list, sa_type=JSON)
    skills: list[str] = Field(default_factory=list, sa_type=JSON)
    engagement_type: str = "employee"
    language: str = "fi"
    # Home base (standard 1.1). Contact details: encrypted when field encryption lands.
    home_address: str = ""
    home_lat: float | None = None
    home_lon: float | None = None
    accepts_calls: bool = True


class Availability(BranchScoped, table=True):
    """Weekly availability window for a person (weekday 0 = Monday), local time "HH:MM"."""

    __tablename__: ClassVar[str] = "availability"

    person_id: str = Field(foreign_key="person.id", index=True)
    weekday: int
    start: str
    end: str


class WorkLimit(BranchScoped, table=True):
    """Working-hour limits for a person, in minutes."""

    __tablename__: ClassVar[str] = "work_limits"

    person_id: str = Field(foreign_key="person.id", index=True, unique=True)
    max_daily_minutes: int = 600
    max_weekly_minutes: int = 2400


class Client(BranchScoped, table=True):
    name: str
    type: str = "business"
    status: str = "active"


class Location(BranchScoped, table=True):
    client_id: str = Field(foreign_key="client.id", index=True)
    name: str
    address: str
    geofence: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    lat: float | None = None
    lon: float | None = None
    instructions: str = ""
    # Encrypted in a later build (field-level encryption with the node master key).
    access_notes: str = ""


class Job(BranchScoped, table=True):
    location_id: str = Field(foreign_key="location.id", index=True)
    name: str
    recurrence: str  # RFC 5545 RRULE, for example "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    start_time: str  # local wall clock time "HH:MM" in the branch time zone
    duration_minutes: int
    required_skills: list[str] = Field(default_factory=list, sa_type=JSON)
    resources: list[str] = Field(default_factory=list, sa_type=JSON)


class Visit(BranchScoped, table=True):
    job_id: str = Field(foreign_key="job.id", index=True)
    location_id: str = Field(foreign_key="location.id", index=True)
    date: dt.date = Field(index=True)
    assigned_person_ids: list[str] = Field(default_factory=list, sa_type=JSON)
    planned_start: datetime = Field(sa_type=TZDateTime)
    planned_end: datetime = Field(sa_type=TZDateTime)
    actual_start: datetime | None = Field(default=None, sa_type=TZDateTime)
    actual_end: datetime | None = Field(default=None, sa_type=TZDateTime)
    status: str = "planned"
    proof_refs: list[str] = Field(default_factory=list, sa_type=JSON)


class Approval(BranchScoped, table=True):
    type: str
    requester_type: str
    requester_id: str
    requester_on_behalf_of: str | None = None
    subject_type: str
    subject_id: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    approver_roles: list[str] = Field(default_factory=list, sa_type=JSON)
    channel: str = "any"
    expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    escalate_to: list[str] = Field(default_factory=list, sa_type=JSON)
    status: str = "pending"
    decided_by: str | None = None
    decided_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    reason: str | None = None


class Thread(BranchScoped, table=True):
    __tablename__: ClassVar[str] = "chat_threads"

    person_id: str = Field(foreign_key="person.id", index=True)
    agent_id: str | None = None
    title: str = ""


class Message(BranchScoped, table=True):
    __tablename__: ClassVar[str] = "chat_messages"

    thread_id: str = Field(foreign_key="chat_threads.id", index=True)
    role: str  # "user" or "assistant"
    sender_id: str
    text: str = ""
    blocks: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    agent_id: str | None = None
    # Pydantic AI messages of the run that produced this message, for conversation history.
    model_messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)


class Event(SQLModel, table=True):
    """One row of the append-only, hash-chained events log. Never updated or deleted."""

    __tablename__: ClassVar[str] = "events"

    id: str = Field(default_factory=new_id, primary_key=True, max_length=26)
    timestamp: datetime = Field(default_factory=utcnow, sa_type=TZDateTime)
    branch_id: str = Field(index=True, max_length=26)
    actor_type: str
    actor_id: str
    on_behalf_of: str | None = None
    action: str = Field(index=True)
    entity_type: str
    entity_id: str
    before: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    after: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    tool_call_id: str | None = None
    approval_id: str | None = None
    prev_hash: str
    hash: str


class UsageCloudRequest(BranchScoped, table=True):
    __tablename__: ClassVar[str] = "usage_cloud_requests"

    organisation_id: str
    agent_id: str
    subagent_id: str | None = None
    task: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_minor: int = 0
    currency: str = "EUR"
    timestamp: datetime = Field(default_factory=utcnow, sa_type=TZDateTime)
    result: str = "success"  # success, error, retried


class GeocodeCache(BranchScoped, table=True):
    """One geocoded address, so each address leaves the node at most once per provider."""

    __tablename__: ClassVar[str] = "geocode_cache"

    address: str = Field(index=True)
    provider: str
    lat: float
    lon: float
    label: str = ""


class EgressLog(BranchScoped, table=True):
    __tablename__: ClassVar[str] = "egress_log"

    timestamp: datetime = Field(default_factory=utcnow, sa_type=TZDateTime)
    agent_id: str
    purpose: str
    level: str
    provider: str
    tokens: int = 0
    payload_hash: str


class Principal(SQLModel):
    """A person, an agent or the system. Not a table: carried on every action."""

    type: str  # ActorType
    id: str
    roles: list[str] = Field(default_factory=list)


class Actor(SQLModel):
    """actor = principal + on_behalf_of. Both are logged and both are permission checked."""

    principal: Principal
    on_behalf_of: Principal | None = None
    branch_id: str

    @property
    def person_id(self) -> str | None:
        """The human behind the action, if any."""
        if self.principal.type == "person":
            return self.principal.id
        return self.on_behalf_of.id if self.on_behalf_of else None

    @property
    def ids(self) -> set[str]:
        """Every principal id involved (for no-self-approval checks)."""
        return {self.principal.id} | ({self.on_behalf_of.id} if self.on_behalf_of else set())

    @classmethod
    def system(cls, branch_id: str) -> "Actor":
        return cls(
            principal=Principal(type="system", id="system", roles=["owner"]), branch_id=branch_id
        )

    @classmethod
    def person(cls, person: Person) -> "Actor":
        principal = Principal(type="person", id=person.id, roles=list(person.roles))
        return cls(principal=principal, branch_id=person.branch_id)

    def as_agent(self, agent_role: str) -> "Actor":
        """The same request, now performed by an agent on behalf of this actor's person."""
        return Actor(
            principal=Principal(type="agent", id=agent_role, roles=[agent_role]),
            on_behalf_of=self.principal,
            branch_id=self.branch_id,
        )
