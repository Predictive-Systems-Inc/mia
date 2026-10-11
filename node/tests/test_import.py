"""`mia import`: real master data (people, clients, sites, jobs) from a YAML file, through the
service layer, idempotent by name; the rollout's data entry until the office app exists."""

from pathlib import Path

import pytest
from sqlmodel import Session, select

from mia.cli import main
from mia.core.models import Availability, Branch, Client, Event, Job, Location, Person, WorkLimit
from mia.templates.cleaning import importer
from mia.templates.cleaning.models import CleaningChecklist, CleaningSite

FILE = """
people:
  - name: Pekka Uusi
    roles: [staff]
    skills: [general, windows]
    language: fi
    home_address: Esimerkkikatu 1, 00100 Helsinki
    availability: {start: "07:00", end: "16:00", days: [0, 1, 2, 3, 4]}
    max_weekly_minutes: 1800
clients:
  - name: Uusi Asiakas Oy
    locations:
      - name: Uusi toimisto
        address: Uusikatu 2, 00100 Helsinki
        site_type: office
        instructions: Avain vastaanotosta.
        access_notes: Koodi 1234
        geofence_radius_m: 150
jobs:
  - name: Uusi toimisto, iltasiivous
    location: Uusi toimisto
    recurrence: FREQ=WEEKLY;BYDAY=MO,WE,FR
    start_time: "17:00"
    duration_minutes: 90
    required_skills: [general]
    checklist: [Roskat, Pinnat]
"""


def test_import_adds_people_sites_and_jobs_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], session: Session, branch: Branch
) -> None:
    path = tmp_path / "hype.yaml"
    path.write_text(FILE, encoding="utf-8")
    assert main(["import", str(path)]) == 0
    out = capsys.readouterr().out
    assert "1 person" in out and "1 client" in out and "1 location" in out and "1 job" in out
    session.expire_all()
    pekka = session.exec(select(Person).where(Person.name == "Pekka Uusi")).one()
    assert pekka.roles == ["staff"] and pekka.skills == ["general", "windows"]
    assert pekka.home_address.startswith("Esimerkkikatu") and pekka.home_lat is None
    limit = session.exec(select(WorkLimit).where(WorkLimit.person_id == pekka.id)).one()
    assert limit.max_weekly_minutes == 1800
    days = session.exec(select(Availability).where(Availability.person_id == pekka.id)).all()
    assert sorted(a.weekday for a in days) == [0, 1, 2, 3, 4] and days[0].start == "07:00"
    client = session.exec(select(Client).where(Client.name == "Uusi Asiakas Oy")).one()
    loc = session.exec(select(Location).where(Location.name == "Uusi toimisto")).one()
    assert loc.client_id == client.id and loc.geofence == {"radius_m": 150}
    assert loc.access_notes == "Koodi 1234" and loc.lat is None  # `mia geocode` fills it
    site = session.exec(select(CleaningSite).where(CleaningSite.location_id == loc.id)).one()
    assert site.site_type == "office"
    job = session.exec(select(Job).where(Job.name == "Uusi toimisto, iltasiivous")).one()
    assert (job.location_id, job.start_time, job.duration_minutes) == (loc.id, "17:00", 90)
    checklist = session.exec(
        select(CleaningChecklist).where(CleaningChecklist.job_id == job.id)
    ).one()
    assert [i["text"] for i in checklist.items] == ["Roskat", "Pinnat"]
    ev = session.exec(select(Event).where(Event.action == "data.imported")).one()
    assert ev.after == {"people": 1, "clients": 1, "locations": 1, "jobs": 1, "file": "hype.yaml"}
    # Again: nothing doubles, names are the key.
    assert main(["import", str(path)]) == 0
    assert "0 person" in capsys.readouterr().out
    session.expire_all()
    assert len(session.exec(select(Person).where(Person.name == "Pekka Uusi")).all()) == 1
    assert len(session.exec(select(Job).where(Job.name == "Uusi toimisto, iltasiivous")).all()) == 1


def test_import_refuses_bad_data_before_writing(
    tmp_path: Path, session: Session, branch: Branch
) -> None:
    bad = FILE.replace("FREQ=WEEKLY;BYDAY=MO,WE,FR", "FREQ=MONTHLY")
    path = tmp_path / "bad.yaml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["import", str(path)])
    session.expire_all()
    assert session.exec(select(Person).where(Person.name == "Pekka Uusi")).first() is None
    orphan = FILE.replace("location: Uusi toimisto", "location: Tuntematon")
    path.write_text(orphan, encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["import", str(path)])
    with pytest.raises(ValueError):
        importer.parse("people: [{name: X, roles: [king]}]")


def test_import_creates_the_organisation_on_an_empty_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["migrate"]) == 0
    text = (
        "organisation: {name: Hype Siivous Oy, country: FI, default_language: fi}\n"
        "branch: {name: Helsinki, timezone: Europe/Helsinki}\n" + FILE
    )
    path = tmp_path / "first.yaml"
    path.write_text(text, encoding="utf-8")
    assert main(["import", str(path)]) == 0
    assert "Helsinki" in capsys.readouterr().out
    bare = tmp_path / "bare.yaml"
    bare.write_text(FILE, encoding="utf-8")
    assert main(["import", str(bare)]) == 0  # the only branch is the default from then on
