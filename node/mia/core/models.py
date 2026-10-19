"""Data standard v1.0: the shared tables every agent and template relies on.

Conventions (see docs/adr/002-data-standard.md): IDs are ULIDs, times are ISO 8601 with time
zone, money is integer minor units plus a currency code, languages are BCP 47 codes. Every table
carries id, branch_id, created_at and updated_at, except organisation (no branch) and events
(timestamp only, append-only).
"""

import datetime as dt
from datetime import datetime
from typing import Any, ClassVar, Literal

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, SQLModel

from mia.core import db
from mia.core.db import TZDateTime
from mia.core.ids import new_id

STANDARD_VERSION = "1.5"


def _now() -> datetime:
    """db.utcnow looked up per call, so a test that pins mia.core.db.utcnow pins row stamps."""
    return db.utcnow()


# Code lists, versioned with the standard.
PersonStatus = Literal["active", "inactive"]
EngagementType = Literal["employee", "contractor", "agency"]
ClientType = Literal["business", "residential"]
VisitStatus = Literal["planned", "in_progress", "completed", "cancelled", "unfilled"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "escalated"]
ApprovalChannel = Literal["app_only", "any"]
ActorType = Literal["person", "agent", "system", "customer"]


class Stamped(SQLModel):
    """Fields shared by every data standard table except events."""

    id: str = Field(default_factory=new_id, primary_key=True, max_length=26)
    created_at: datetime = Field(default_factory=_now, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_now, sa_type=TZDateTime)


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
    __redact__: ClassVar[frozenset[str]] = frozenset(
        {"access_notes"}
    )  # door codes stay off the chain

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


class Absence(BranchScoped, table=True):
    """A person's reported absence for one day, or part of it (data standard 1.4)."""

    __tablename__: ClassVar[str] = "absences"

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

    __tablename__: ClassVar[str] = "cover_requests"

    visit_id: str = Field(foreign_key="visit.id", index=True)
    candidate_id: str = Field(foreign_key="person.id", index=True)
    replace_person_ids: list[str] = Field(default_factory=list, sa_type=JSON)
    queue: list[str] = Field(default_factory=list, sa_type=JSON)  # next candidates, best first
    instructed_by: str
    approval_id: str | None = None
    status: str = "asking"
    stage: str = "message"
    next_action_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime, index=True)


class Timesheet(BranchScoped, table=True):
    """One person's time on one visit (data standard 1.4; Q20 placed it in core).

    source: check_out (from the visit's actual times), planned (a completed visit without
    them), correction. status: draft, approved. Whoever entered it never approves it.
    """

    __tablename__: ClassVar[str] = "timesheets"
    __table_args__ = (UniqueConstraint("visit_id", "person_id"),)

    visit_id: str = Field(foreign_key="visit.id", index=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    date: dt.date = Field(index=True)
    start: dt.datetime = Field(sa_type=TZDateTime)
    end: dt.datetime = Field(sa_type=TZDateTime)
    minutes: int
    source: str = "check_out"
    status: str = Field(default="draft", index=True)
    entered_by: str
    note: str = ""
    approved_by: str | None = None
    approved_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime)


class Incident(BranchScoped, table=True):
    """A problem reported from a site: cannot get in, or the site is unusable."""

    __tablename__: ClassVar[str] = "incidents"

    visit_id: str = Field(foreign_key="visit.id", index=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    kind: str  # cannot_access, site_problem
    text: str  # the cleaner's words: data, never instructions
    status: str = Field(default="open", index=True)  # open, resolved
    resolved_by: str | None = None
    resolved_at: dt.datetime | None = Field(default=None, sa_type=TZDateTime)


class SalesCount(BranchScoped, table=True):
    """One reported count of one item for a business date; a correction supersedes a row
    (data standard 1.5)."""

    __tablename__: ClassVar[str] = "sales_counts"

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
    """A day or month target (money, quantity, or both) from a start date (data standard 1.5)."""

    __tablename__: ClassVar[str] = "sales_targets"

    period: str  # day or month
    starts_on: dt.date = Field(index=True)
    amount: int | None = None
    currency: str = Field(max_length=3)
    quantity: int | None = None
    item_id: str | None = None
    set_by: str


class SalesNote(BranchScoped, table=True):
    """A clerk's words about the day (why sales were up or down) (data standard 1.5)."""

    __tablename__: ClassVar[str] = "sales_notes"

    business_date: dt.date = Field(index=True)
    person_id: str
    text: str
    themes: list[str] = Field(default_factory=list, sa_type=JSON)
    asked_message_id: str | None = None


class StockEvent(BranchScoped, table=True):
    """One thing said about stock: sold_out, count, leftover, waste, low or received
    (data standard 1.5)."""

    __tablename__: ClassVar[str] = "stock_events"

    kind: str
    item_id: str | None = Field(default=None, foreign_key="retail_items.id")
    ingredient_id: str | None = Field(default=None, foreign_key="retail_ingredients.id")
    quantity: int | None = None
    unit: str | None = None
    reason: str | None = None
    at: dt.datetime = Field(sa_type=TZDateTime)  # the sell-out time or the report time
    reported_by: str = Field(foreign_key="person.id")
    business_date: dt.date = Field(index=True)
    source_message_id: str | None = None
    order_id: str | None = None


class Approval(BranchScoped, table=True):
    __redact__: ClassVar[frozenset[str]] = frozenset({"evidence"})
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
    timestamp: datetime = Field(default_factory=_now, sa_type=TZDateTime)
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
    timestamp: datetime = Field(default_factory=_now, sa_type=TZDateTime)
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

    timestamp: datetime = Field(default_factory=_now, sa_type=TZDateTime)
    agent_id: str
    purpose: str
    level: str
    provider: str
    tokens: int = 0
    payload_hash: str


# ---- channels (standard 1.2, ADR 007) ---------------------------------------------------------


class ChannelIdentity(BranchScoped, table=True):
    """A person's verified address on a messaging channel (for example a WhatsApp number)."""

    __tablename__: ClassVar[str] = "channel_identities"

    person_id: str = Field(foreign_key="person.id", index=True)
    channel: str = Field(index=True)
    address: str = Field(index=True)
    status: str = "active"  # active, revoked
    verified_at: datetime = Field(default_factory=_now, sa_type=TZDateTime)
    consent_at: datetime = Field(default_factory=_now, sa_type=TZDateTime)
    last_inbound_at: datetime | None = Field(default=None, sa_type=TZDateTime)


class AuthCode(BranchScoped, table=True):
    """A one-time code: channel link (invite, self), staff OTP, login link, MFA token or
    enrolment link. Stored only as an HMAC (core/keys.py), single use, expiring, at most 5 tries."""

    __tablename__: ClassVar[str] = "auth_codes"
    __redact__: ClassVar[frozenset[str]] = frozenset({"code_hmac"})

    person_id: str = Field(foreign_key="person.id", index=True)
    code_hmac: str = Field(unique=True)
    purpose: str  # invite, self, otp_login, link_login, mfa, enrol
    address: str | None = None  # where it was sent, if anywhere
    tries: int = 0
    expires_at: datetime = Field(sa_type=TZDateTime)
    used_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    created_by: str


class AuthAttempt(Stamped, table=True):
    """One credential check, for rate limits and lockouts. `key` is `<subject>@<ip>` where the
    subject is a login HMAC, an address, a person or client id; `@-` when there is no IP."""

    __tablename__: ClassVar[str] = "auth_attempts"

    kind: str  # link_code, password, otp, pin, client_secret, mfa, device
    key: str = Field(index=True)
    ok: bool


class AuthCredential(BranchScoped, table=True):
    """One login factor of a person: password, totp, recovery_code, pin (passkey later)."""

    __tablename__: ClassVar[str] = "auth_credentials"
    __redact__: ClassVar[frozenset[str]] = frozenset({"secret_hash", "data"})

    person_id: str = Field(foreign_key="person.id", index=True)
    kind: str
    login: str | None = Field(default=None, unique=True)  # lowercased email, password rows only
    secret_hash: str | None = None  # scrypt string; null for totp
    data: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)  # totp: nonce, last_step
    status: str = "active"  # pending, active, revoked, used, locked
    last_used_at: datetime | None = Field(default=None, sa_type=TZDateTime)


class AuthDevice(BranchScoped, table=True):
    """A browser or phone a person signed in on. Mobile devices hold a device secret."""

    __tablename__: ClassVar[str] = "auth_devices"
    __redact__: ClassVar[frozenset[str]] = frozenset({"secret_hash"})

    person_id: str = Field(foreign_key="person.id", index=True)
    kind: str  # browser, mobile
    name: str
    secret_hash: str | None = None
    status: str = "active"  # active, revoked
    last_seen_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    revoked_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    revoked_by: str | None = None


class AuthSession(BranchScoped, table=True):
    """One signed-in session of a person or a client. Tokens are stored as SHA-256 hashes."""

    __tablename__: ClassVar[str] = "auth_sessions"
    __redact__: ClassVar[frozenset[str]] = frozenset(
        {"access_hash", "refresh_hash", "prev_refresh_hash"}
    )

    subject_type: str  # person, client
    subject_id: str = Field(index=True)
    device_id: str | None = Field(default=None, foreign_key="auth_devices.id")
    method: str  # password_totp, password, phone_otp, device, wa_link, client, enrol
    aal: str  # aal1, aal2, client, enrol
    access_hash: str = Field(unique=True)
    access_expires_at: datetime = Field(sa_type=TZDateTime)
    refresh_hash: str | None = Field(default=None, unique=True)
    prev_refresh_hash: str | None = None
    refresh_expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    absolute_expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    stepped_up_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    status: str = "active"  # active, revoked
    ip: str = ""


class AuthClient(BranchScoped, table=True):
    """An outside agent or service with OAuth2 client credentials issued by this node."""

    __tablename__: ClassVar[str] = "auth_clients"
    __redact__: ClassVar[frozenset[str]] = frozenset({"secret_hash"})

    name: str
    client_id: str = Field(unique=True)
    secret_hash: str
    roles: list[str] = Field(default_factory=list, sa_type=JSON)
    status: str = "active"  # active, revoked
    expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    created_by: str
    last_used_at: datetime | None = Field(default=None, sa_type=TZDateTime)


class ChannelOutbox(BranchScoped, table=True):
    """One outbound channel message: queued, sent, delivered, read, failed or held."""

    __tablename__: ClassVar[str] = "channel_outbox"
    # Message bodies stay in chat_messages and the outbox row; events carry the row's state
    # only (sign-in codes travel through the outbox too).
    __redact__: ClassVar[frozenset[str]] = frozenset({"payload"})

    person_id: str = Field(foreign_key="person.id", index=True)
    channel: str
    address: str
    kind: str = "message"
    payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    idempotency_key: str = Field(unique=True)
    status: str = Field(default="queued", index=True)
    attempts: int = 0
    send_after: datetime | None = Field(default=None, sa_type=TZDateTime)
    channel_message_id: str | None = Field(default=None, index=True)
    error_code: str | None = None


class ChannelInbound(Stamped, table=True):
    """One inbound channel message, unique per channel message id (Meta resends webhooks)."""

    __tablename__: ClassVar[str] = "channel_inbound"
    # The body is replayable channel data (text goes to messages, a shared location is dropped
    # once handled) and the address may be a customer's number (customer_service): neither
    # enters the append-only events.
    __redact__: ClassVar[frozenset[str]] = frozenset({"body", "address"})
    __table_args__ = (UniqueConstraint("channel", "channel_message_id"),)

    channel: str
    channel_message_id: str
    address: str
    branch_id: str | None = Field(default=None, foreign_key="branch.id")
    person_id: str | None = None
    body: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    status: str = Field(default="pending", index=True)  # pending, done, failed, ignored
    error: str | None = None


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
