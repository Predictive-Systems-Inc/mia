"""Master data import for the rollout (plan Sprint 5): people, clients, sites and jobs from a
YAML file, validated before anything is written (Pydantic at the boundary), then inserted
through store (rule 1) and skipped when a row of that name already exists in the branch, so
the file can be re-run as it grows. Coordinates come later from `mia geocode`.
"""

import datetime as dt
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator
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
from mia.templates.cleaning.models import CleaningChecklist, CleaningSite

ROLES = ("owner", "admin", "supervisor", "staff", "accountant", "viewer")
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


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


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    roles: list[Literal[ROLES]] = Field(min_length=1)  # type: ignore[valid-type]
    skills: list[str] = []
    language: Literal["fi", "en"] = "fi"
    home_address: str = ""
    availability: AvailabilityIn | None = None
    max_weekly_minutes: int = Field(default=2400, ge=0, le=7 * 24 * 60)
    max_daily_minutes: int = Field(default=600, ge=0, le=24 * 60)


class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1)
    site_type: Literal["office", "shop", "home"] = "office"
    instructions: str = ""
    access_notes: str = ""
    geofence_radius_m: int = Field(default=100, ge=10, le=5000)


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: Literal["business", "home", "public"] = "business"
    locations: list[LocationIn] = []


class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    location: str
    recurrence: str
    start_time: str = Field(pattern=HHMM)
    duration_minutes: int = Field(ge=5, le=24 * 60)
    required_skills: list[str] = []
    checklist: list[str] = []

    @field_validator("recurrence")
    @classmethod
    def _supported_rrule(cls, rule: str) -> str:
        try:
            day = dt.date(2026, 1, 5)  # any date: only the parser's verdict matters
            scheduling.occurs_on(rule, day, day)
        except (KeyError, ValueError, IndexError) as exc:
            raise ValueError(
                f"unsupported recurrence {rule!r} (DAILY or WEEKLY;BYDAY=...)"
            ) from exc
        return rule


class OrganisationIn(BaseModel):
    name: str = Field(min_length=1)
    country: str = "FI"
    default_language: Literal["fi", "en"] = "fi"


class BranchIn(BaseModel):
    name: str = Field(min_length=1)
    timezone: str = "Europe/Helsinki"


class ImportFile(BaseModel):
    organisation: OrganisationIn | None = None
    branch: BranchIn | None = None
    people: list[PersonIn] = []
    clients: list[ClientIn] = []
    jobs: list[JobIn] = []


class Counts(BaseModel):
    people: int = 0
    clients: int = 0
    locations: int = 0
    jobs: int = 0


def parse(text: str) -> ImportFile:
    """The validated file. Raises ValueError (with every problem) before anything is written;
    a job must name a site in the file or already in the branch, checked in `load`."""
    data = yaml.safe_load(text) or {}
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


def load(session: Session, data: ImportFile, branch: Branch) -> Counts:
    """Insert what the branch does not have yet, by name. Raises ValueError when a job names a
    site that is neither in the file nor in the branch (nothing is written then: check first)."""
    actor = Actor.system(branch.id)
    sites = {
        loc.name: loc
        for loc in session.exec(select(Location).where(Location.branch_id == branch.id)).all()
    }
    pending = {loc.name for c in data.clients for loc in c.locations}
    missing = [
        j.location for j in data.jobs if j.location not in sites and j.location not in pending
    ]
    if missing:
        raise ValueError(f"jobs name unknown sites: {', '.join(sorted(set(missing)))}")
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
        counts.people += 1
    clients = {
        c.name: c for c in session.exec(select(Client).where(Client.branch_id == branch.id)).all()
    }
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
        counts.jobs += 1
    return counts
