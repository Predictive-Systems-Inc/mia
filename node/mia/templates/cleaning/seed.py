"""Demo data for a Hype-like cleaning company in Helsinki.

One branch, an owner, one supervisor and five cleaners (with home bases), four located sites, six jobs, completed
visits for the past 14 days and planned visits for the next 7 days. All rows are written
through mia.core.store, so seeding appears in the events log like any other write.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.core import store
from mia.core.models import (
    Actor,
    Availability,
    Branch,
    Client,
    GeocodeCache,
    Job,
    Location,
    Organisation,
    Person,
    Visit,
    WorkLimit,
)
from mia.templates.cleaning.models import CleaningChecklist, CleaningSite

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

PERSONS = [
    # name, roles, skills, language, availability (start, end), weekly limit minutes
    ("Helena Hyppönen", ["owner"], [], "fi", None, 2400),
    ("Sanna Virtanen", ["supervisor"], ["general"], "fi", None, 2400),
    ("Juha Laine", ["staff"], ["general", "windows"], "fi", ("06:00", "20:00"), 2400),
    ("Mikael Nieminen", ["staff"], ["general", "floor_care"], "fi", ("06:00", "20:00"), 2400),
    ("Aino Korhonen", ["staff"], ["general"], "fi", ("06:00", "20:00"), 2400),
    ("Maria Mäkinen", ["staff"], ["general", "windows"], "fi", ("06:00", "20:00"), 2400),
    ("Liisa Heikkinen", ["staff"], ["general"], "en", ("10:00", "18:00"), 1200),
]

# Demo home bases and site coordinates (approximate, Helsinki). Seeded as already geocoded
# (provider "demo") so the demo never calls a geocoding service.
HOMES = {
    "Sanna Virtanen": ("Hämeentie 30, 00530 Helsinki", 60.1873, 24.9580),
    "Juha Laine": ("Vilhonvuorenkatu 11, 00500 Helsinki", 60.1865, 24.9610),
    "Mikael Nieminen": ("Mäkelänkatu 50, 00510 Helsinki", 60.1960, 24.9530),
    "Aino Korhonen": ("Fleminginkatu 20, 00510 Helsinki", 60.1880, 24.9500),
    "Maria Mäkinen": ("Lauttasaarentie 20, 00200 Helsinki", 60.1590, 24.8770),
    "Liisa Heikkinen": ("Munkkiniementie 30, 00330 Helsinki", 60.1990, 24.8790),
}
SITE_COORDS = {
    "kalasatama": (60.1875, 24.9770),
    "pasila": (60.1990, 24.9330),
    "kamppi": (60.1690, 24.9320),
    "toolo": (60.1810, 24.9220),
}

LOCATIONS = [
    # key, client, client type, location name, address, site type, instructions
    (
        "kalasatama",
        "Kalasatama Business Oy",
        "business",
        "Kalasatama office",
        "Kalasatamankatu 5, 00580 Helsinki",
        "office",
        "Start from the 3rd floor kitchen. Recycling room is next to the lift.",
    ),
    (
        "pasila",
        "Pasila Tower Oy",
        "business",
        "Pasila office",
        "Ratapihantie 11, 00520 Helsinki",
        "office",
        "Meeting rooms first. Do not move papers on desks.",
    ),
    (
        "kamppi",
        "Kampin Kukka Ky",
        "business",
        "Kamppi shop",
        "Urho Kekkosen katu 1, 00100 Helsinki",
        "shop",
        "Clean before opening at 10:00. Glass counters with the blue cloth.",
    ),
    (
        "toolo",
        "Perhe Lindholm",
        "residential",
        "Töölö home",
        "Runeberginkatu 40, 00260 Helsinki",
        "home",
        "Cat in the flat, keep the balcony door closed.",
    ),
]

JOBS = [
    # location key, name, rrule, start, minutes, skills, assignee, past-visit covers
    (
        "kalasatama",
        "Kalasatama morning clean",
        "FREQ=DAILY",
        "06:30",
        120,
        ["general"],
        "Juha Laine",
        "Mikael Nieminen",
    ),
    (
        "pasila",
        "Pasila window wash",
        "FREQ=WEEKLY;BYDAY=WE",
        "10:00",
        90,
        ["windows"],
        "Maria Mäkinen",
        None,
    ),
    (
        "pasila",
        "Pasila office clean",
        "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
        "07:00",
        180,
        ["general"],
        "Aino Korhonen",
        None,
    ),
    (
        "pasila",
        "Pasila floor care",
        "FREQ=WEEKLY;BYDAY=TU,TH",
        "17:00",
        120,
        ["floor_care"],
        "Mikael Nieminen",
        None,
    ),
    ("kamppi", "Kamppi shop clean", "FREQ=DAILY", "09:00", 60, ["general"], "Juha Laine", None),
    (
        "toolo",
        "Töölö home clean",
        "FREQ=WEEKLY;BYDAY=MO,TH",
        "13:00",
        150,
        ["general"],
        "Liisa Heikkinen",
        None,
    ),
]


def occurs_on(rrule: str, day: dt.date) -> bool:
    """True when a simple RRULE (FREQ=DAILY or FREQ=WEEKLY;BYDAY=..) has an occurrence on day."""
    parts = dict(p.split("=", 1) for p in rrule.split(";"))
    if parts.get("FREQ") == "DAILY":
        return True
    if parts.get("FREQ") == "WEEKLY":
        return WEEKDAYS[day.weekday()] in parts.get("BYDAY", "").split(",")
    raise ValueError(f"unsupported recurrence {rrule!r}")


def local_dt(day: dt.date, hhmm: str, tz: str) -> dt.datetime:
    hour, minute = map(int, hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=ZoneInfo(tz))


def _cache(
    session: Session, branch_id: str, address: str, lat: float, lon: float, actor: Actor
) -> None:
    row = GeocodeCache(branch_id=branch_id, address=address, provider="demo", lat=lat, lon=lon)
    store.insert(session, row, actor)


def is_seeded(session: Session) -> bool:
    return session.exec(select(Organisation).limit(1)).first() is not None


def seed(session: Session, today: dt.date | None = None) -> Branch:
    """Load the demo data. Returns the branch. Refuses to run twice on the same database."""
    if is_seeded(session):
        raise RuntimeError("database already has data; seed runs only on an empty database")
    org = Organisation(name="Hype Siivous (demo)", country="FI", default_language="fi")
    branch = Branch(organisation_id=org.id, name="Helsinki", timezone="Europe/Helsinki")
    actor = Actor.system(branch.id)
    store.insert(session, org, actor)
    store.insert(session, branch, actor)
    today = today or dt.datetime.now(ZoneInfo(branch.timezone)).date()

    people: dict[str, Person] = {}
    for name, roles, skills, lang, window, weekly in PERSONS:
        home = HOMES.get(name)
        person = store.insert(
            session,
            Person(
                branch_id=branch.id,
                name=name,
                roles=roles,
                skills=skills,
                language=lang,
                home_address=home[0] if home else "",
                home_lat=home[1] if home else None,
                home_lon=home[2] if home else None,
            ),
            actor,
        )
        if home:
            _cache(session, branch.id, home[0], home[1], home[2], actor)
        people[name] = person
        store.insert(
            session,
            WorkLimit(branch_id=branch.id, person_id=person.id, max_weekly_minutes=weekly),
            actor,
        )
        if window:
            for weekday in range(7):
                row = Availability(
                    branch_id=branch.id,
                    person_id=person.id,
                    weekday=weekday,
                    start=window[0],
                    end=window[1],
                )
                store.insert(session, row, actor)

    locations: dict[str, Location] = {}
    for key, client_name, ctype, loc_name, address, site_type, instructions in LOCATIONS:
        client = store.insert(
            session, Client(branch_id=branch.id, name=client_name, type=ctype), actor
        )
        loc = Location(
            branch_id=branch.id,
            client_id=client.id,
            name=loc_name,
            address=address,
            instructions=instructions,
            geofence={"radius_m": 100},
            lat=SITE_COORDS[key][0],
            lon=SITE_COORDS[key][1],
        )
        locations[key] = store.insert(session, loc, actor)
        _cache(session, branch.id, address, SITE_COORDS[key][0], SITE_COORDS[key][1], actor)
        store.insert(
            session,
            CleaningSite(branch_id=branch.id, location_id=loc.id, site_type=site_type),
            actor,
        )

    for loc_key, name, rrule, start, minutes, skills, assignee, cover in JOBS:
        loc = locations[loc_key]
        job = store.insert(
            session,
            Job(
                branch_id=branch.id,
                location_id=loc.id,
                name=name,
                recurrence=rrule,
                start_time=start,
                duration_minutes=minutes,
                required_skills=skills,
            ),
            actor,
        )
        store.insert(
            session,
            CleaningChecklist(
                branch_id=branch.id,
                job_id=job.id,
                items=[{"text": "Empty bins"}, {"text": "Wipe surfaces"}],
            ),
            actor,
        )
        for offset in range(-14, 8):
            day = today + dt.timedelta(days=offset)
            if not occurs_on(rrule, day):
                continue
            person = people[assignee]
            if offset < 0 and cover and offset % 4 == 0:
                person = people[cover]
            planned_start = local_dt(day, start, branch.timezone)
            store.insert(
                session,
                Visit(
                    branch_id=branch.id,
                    job_id=job.id,
                    location_id=loc.id,
                    date=day,
                    assigned_person_ids=[person.id],
                    planned_start=planned_start,
                    planned_end=planned_start + dt.timedelta(minutes=minutes),
                    status="completed" if offset < 0 else "planned",
                ),
                actor,
            )
    return branch
