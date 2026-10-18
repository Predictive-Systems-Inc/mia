"""Master data import for the rollout (plan Sprint 5): people, clients, sites and jobs from a
YAML file, validated before anything is written (Pydantic at the boundary), then inserted
through store (rule 1) and skipped when a row of that name already exists in the branch, so
the file can be re-run as it grows. Coordinates come later from `mia geocode`.
"""

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlmodel import Session, select

from mia.core import scheduling, store
from mia.core.models import (
    Actor,
    Availability,
    Branch,
    Client,
    Job,
    Location,
    Organisation,
    Person,
    WorkLimit,
)
from mia.core.people import HUMAN_ROLES
from mia.i18n import SUPPORTED
from mia.templates.cleaning.models import CleaningChecklist, CleaningSite

ROLES = HUMAN_ROLES


def _supported_language(value: str) -> str:
    """Guarantee the language is one of mia.i18n.SUPPORTED."""
    if value not in SUPPORTED:
        raise ValueError(f"language must be one of {', '.join(SUPPORTED)}")
    return value


HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


def _clean_name(name: str) -> str:
    return " ".join(name.split())  # as `mia person add` stores it, so re-runs match


class AvailabilityIn(BaseModel):
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    days: list[int] = Field(default=[0, 1, 2, 3, 4, 5, 6], min_length=1)

    @field_validator("days")
    @classmethod
    def _weekdays(cls, days: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in days):
            raise ValueError("days are 0 (Monday) to 6 (Sunday)")
        return sorted(set(days))

    @model_validator(mode="after")
    def _ordered(self) -> "AvailabilityIn":
        if self.end <= self.start:
            raise ValueError("the end must come after the start (before means never available)")
        return self


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    roles: list[Literal[ROLES]] = Field(min_length=1)  # type: ignore[valid-type]
    skills: list[str] = []
    language: str = "fi"
    home_address: str = Field(default="", max_length=300)
    availability: AvailabilityIn | None = None
    max_weekly_minutes: int = Field(default=2400, ge=0, le=7 * 24 * 60)
    max_daily_minutes: int = Field(default=600, ge=0, le=24 * 60)

    _names = field_validator("name")(_clean_name)
    _language = field_validator("language")(_supported_language)


class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=300)
    site_type: Literal["office", "shop", "home"] = "office"
    instructions: str = Field(default="", max_length=4000)
    access_notes: str = Field(default="", max_length=2000)
    geofence_radius_m: int = Field(default=100, ge=10, le=5000)

    _names = field_validator("name")(_clean_name)


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: Literal["business", "home", "public"] = "business"
    locations: list[LocationIn] = []

    _names = field_validator("name")(_clean_name)


class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    location: str
    recurrence: str
    start_time: str = Field(pattern=HHMM)
    duration_minutes: int = Field(ge=5, le=24 * 60)
    required_skills: list[str] = []
    checklist: list[str] = []

    _names = field_validator("name", "location")(_clean_name)

    @field_validator("recurrence")
    @classmethod
    def _supported_rrule(cls, rule: str) -> str:
        try:
            scheduling.validate_rule(rule)
        except (KeyError, ValueError, IndexError) as exc:
            raise ValueError(
                f"unsupported recurrence {rule!r} (FREQ=DAILY or FREQ=WEEKLY;BYDAY=MO,...)"
            ) from exc
        return rule

    @model_validator(mode="after")
    def _same_day(self) -> "JobIn":
        hour, minute = map(int, self.start_time.split(":"))
        if hour * 60 + minute + self.duration_minutes > 24 * 60:
            raise ValueError("a visit must end before midnight (availability is per day)")
        return self


class OrganisationIn(BaseModel):
    name: str = Field(min_length=1)
    country: str = "FI"
    default_language: str = "fi"

    _language = field_validator("default_language")(_supported_language)


class BranchIn(BaseModel):
    name: str = Field(min_length=1)
    timezone: str = "Europe/Helsinki"

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, tz: str) -> str:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone {tz!r}") from exc
        return tz


class ImportFile(BaseModel):
    organisation: OrganisationIn | None = None
    branch: BranchIn | None = None
    people: list[PersonIn] = []
    clients: list[ClientIn] = []
    jobs: list[JobIn] = []

    @model_validator(mode="after")
    def _unique_names(self) -> "ImportFile":
        for what, names in (
            ("person", [p.name for p in self.people]),
            ("client", [c.name for c in self.clients]),
            ("job", [j.name for j in self.jobs]),
        ):
            seen: set[str] = set()
            for name in names:
                if name in seen:
                    raise ValueError(f"{what} {name!r} appears twice")
                seen.add(name)
        sites: dict[str, str] = {}
        for c in self.clients:
            for loc in c.locations:
                if loc.name in sites:
                    raise ValueError(f"site {loc.name!r} appears under two clients")
                sites[loc.name] = c.name
        return self


class Counts(BaseModel):
    people: int = 0
    clients: int = 0
    locations: int = 0
    jobs: int = 0


def parse(text: str) -> ImportFile:
    """The validated file. Raises ValueError (with every problem) before anything is written;
    a job must name a site in the file or already in the branch, checked in `load`."""
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError("the file must be a mapping of people, clients and jobs")
    try:
        return ImportFile.model_validate(data)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise ValueError(str(exc)) from exc


def bootstrap(session: Session, data: ImportFile) -> Branch:
    """The organisation and branch of an empty database (the file names both)."""
    if data.organisation is None or data.branch is None:
        raise ValueError("an empty database needs `organisation` and `branch` in the file")
    org = Organisation(
        name=data.organisation.name,
        country=data.organisation.country,
        default_language=data.organisation.default_language,
    )
    branch = Branch(organisation_id=org.id, name=data.branch.name, timezone=data.branch.timezone)
    actor = Actor.system(branch.id)
    store.insert(session, org, actor)
    store.insert(session, branch, actor)
    return branch


def _site_owners(
    session: Session, data: ImportFile, branch: Branch
) -> tuple[dict[str, Client], dict[str, Location], dict[str, str]]:
    """Clients and sites of the branch by name, and each site's client (branch and file), or
    ValueError when a site name would belong to two clients or a job names an unknown site."""
    clients = {
        c.name: c for c in session.exec(select(Client).where(Client.branch_id == branch.id)).all()
    }
    by_id = {c.id: c.name for c in clients.values()}
    sites: dict[str, Location] = {}
    owner: dict[str, str] = {}
    for loc in session.exec(select(Location).where(Location.branch_id == branch.id)).all():
        sites[loc.name] = loc
        owner[loc.name] = by_id.get(loc.client_id, "?")
    for c in data.clients:
        for site in c.locations:
            if owner.get(site.name, c.name) != c.name:
                raise ValueError(
                    f"site {site.name!r} would belong to two clients ({owner[site.name]!r}, {c.name!r})"
                )
            owner[site.name] = c.name
    missing = sorted({j.location for j in data.jobs if j.location not in owner})
    if missing:
        raise ValueError(f"jobs name unknown sites: {', '.join(missing)}")
    return clients, sites, owner


def load(session: Session, data: ImportFile, branch: Branch) -> Counts:
    """Insert what the branch does not have yet, by name (a changed row is left alone). Raises
    ValueError, before any write, when the file names another branch, a site under two
    clients, or a job's site that is neither in the file nor in the branch."""
    actor = Actor.system(branch.id)
    if data.branch is not None and data.branch.name != branch.name:
        raise ValueError(
            f"the file is for branch {data.branch.name!r}, the database has {branch.name!r}"
        )
    clients, sites, _owner = _site_owners(session, data, branch)
    counts = Counts()
    known = {p.name for p in session.exec(select(Person).where(Person.branch_id == branch.id))}
    for p in data.people:
        if p.name in known:
            continue
        person = store.insert(
            session,
            Person(
                branch_id=branch.id,
                name=p.name,
                roles=list(p.roles),
                skills=p.skills,
                language=p.language,
                home_address=p.home_address,
            ),
            actor,
        )
        store.insert(
            session,
            WorkLimit(
                branch_id=branch.id,
                person_id=person.id,
                max_daily_minutes=p.max_daily_minutes,
                max_weekly_minutes=p.max_weekly_minutes,
            ),
            actor,
        )
        if p.availability:
            for weekday in p.availability.days:
                row = Availability(
                    branch_id=branch.id,
                    person_id=person.id,
                    weekday=weekday,
                    start=p.availability.start,
                    end=p.availability.end,
                )
                store.insert(session, row, actor)
        known.add(p.name)
        counts.people += 1
    for c in data.clients:
        client = clients.get(c.name)
        if client is None:
            client = store.insert(
                session, Client(branch_id=branch.id, name=c.name, type=c.type), actor
            )
            clients[c.name] = client
            counts.clients += 1
        for site in c.locations:
            if site.name in sites:
                continue
            loc = store.insert(
                session,
                Location(
                    branch_id=branch.id,
                    client_id=client.id,
                    name=site.name,
                    address=site.address,
                    instructions=site.instructions,
                    access_notes=site.access_notes,
                    geofence={"radius_m": site.geofence_radius_m},
                ),
                actor,
                redact=("access_notes",),  # a door code never enters the append-only log
            )
            store.insert(
                session,
                CleaningSite(branch_id=branch.id, location_id=loc.id, site_type=site.site_type),
                actor,
            )
            sites[site.name] = loc
            counts.locations += 1
    jobs = {j.name for j in session.exec(select(Job).where(Job.branch_id == branch.id))}
    for j in data.jobs:
        if j.name in jobs:
            continue
        job = store.insert(
            session,
            Job(
                branch_id=branch.id,
                location_id=sites[j.location].id,
                name=j.name,
                recurrence=j.recurrence,
                start_time=j.start_time,
                duration_minutes=j.duration_minutes,
                required_skills=j.required_skills,
            ),
            actor,
        )
        if j.checklist:
            store.insert(
                session,
                CleaningChecklist(
                    branch_id=branch.id, job_id=job.id, items=[{"text": t} for t in j.checklist]
                ),
                actor,
            )
        jobs.add(j.name)
        counts.jobs += 1
    return counts
