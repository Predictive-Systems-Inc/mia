"""Site problems over chat and the supervisor summary."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.agents.shift_supervisor import tools
from mia.agents.shift_supervisor.classifier import classify
from mia.api.main import app
from mia.chat.channels import NOTIFICATION
from mia.core import scheduling
from mia.core.models import Actor, Branch, Incident, Job, Message, Person, Thread, Visit
from tests.test_tools import deps_for

TODAY = dt.date(2026, 9, 30)


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("En pääse sisään, ovi on lukossa", "cannot_access_site"),
        ("Ovikoodi ei toimi", "cannot_access_site"),
        ("I can't get in, the code is wrong", "cannot_access_site"),
        ("The alarm went off when I opened the door", "cannot_access_site"),
        ("Täällä ei ole vettä", "site_problem"),
        ("No power at the site", "site_problem"),
        ("Asiakas on vielä paikalla", "site_problem"),
        ("The client is still here, can't start", "site_problem"),
        ("Mikä on ovikoodi?", "visit_details"),
        ("What's the door code?", "visit_details"),
    ],
)
def test_problem_intents(text: str, intent: str) -> None:
    assert classify(text, TODAY).name == intent


def _notes(session: Session, person: Person) -> list[Message]:
    session.expire_all()
    return list(
        session.exec(
            select(Message)
            .join(Thread, Thread.id == Message.thread_id)  # type: ignore[arg-type]
            .where(Thread.person_id == person.id)
            .where(Message.role == NOTIFICATION)
        ).all()
    )


def test_report_tool_records_and_tells_the_supervisor(
    session: Session, branch: Branch, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    juha, sanna = people["Juha"], people["Sanna"]
    deps = deps_for(session, branch, juha)
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    visit = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == deps.today)
    ).one()
    monkeypatch.setattr(tools, "utcnow", lambda: visit.planned_start)
    out = tools.report_site_problem(
        deps, tools.ReportProblemInput(kind="cannot_access", text="Ovikoodi ei toimi"), "c1"
    )
    assert out.status == "ok" and out.visit and out.visit.visit_id == visit.id
    row = session.exec(select(Incident)).one()
    assert (row.kind, row.status, row.person_id, row.visit_id) == (
        "cannot_access",
        "open",
        juha.id,
        visit.id,
    )
    note = _notes(session, sanna)[-1]
    assert "Juha" in note.text and "Kamppi shop" in note.text and "Ovikoodi ei toimi" in note.text


def test_report_tool_needs_a_visit_and_permission(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core import people as people_service
    from mia.core.rbac import PermissionDenied

    deps = deps_for(session, branch, people["Sanna"])  # no visits of her own
    out = tools.report_site_problem(
        deps, tools.ReportProblemInput(kind="site_problem", text="x"), "c1"
    )
    assert out.status == "invalid" and out.reason == "no_visit"
    viewer = people_service.add_person(
        session,
        Actor.person(people["Helena"]),
        branch_id=branch.id,
        name="Vilma Viewer",
        roles=["viewer"],
    )
    with pytest.raises(PermissionDenied):
        tools.report_site_problem(
            deps_for(session, branch, viewer),
            tools.ReportProblemInput(kind="site_problem", text="x"),
            "c2",
        )


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


def test_supervisor_summary_and_resolve(
    client: TestClient,
    session: Session,
    branch: Branch,
    people: dict[str, Person],
    login,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    juha, sanna = people["Juha"], people["Sanna"]
    today = dt.datetime.now(ZoneInfo("Europe/Helsinki")).date()
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    tomorrow = session.exec(
        select(Visit)
        .where(Visit.job_id == job.id)
        .where(Visit.date == today + dt.timedelta(days=1))
    ).one()
    scheduling.unassign(session, Actor.person(sanna), tomorrow, juha)
    visit = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == today)
    ).one()
    deps = deps_for(session, branch, juha)
    monkeypatch.setattr(tools, "utcnow", lambda: visit.planned_start)
    tools.report_site_problem(
        deps, tools.ReportProblemInput(kind="site_problem", text="No water"), "c1"
    )
    session.commit()
    from mia.api import supervisor as api

    monkeypatch.setattr(api, "utcnow", lambda: visit.planned_start + dt.timedelta(minutes=30))
    login(client, sanna)
    res = client.get("/supervisor/summary")
    assert res.status_code == 200, res.text
    body = res.json()
    assert tomorrow.id in [v["id"] for v in body["unfilled"]]
    assert visit.id in [v["id"] for v in body["late_check_ins"]]
    assert [p["text"] for p in body["open_problems"]] == ["No water"]
    assert body["open_problems"][0]["person"] == juha.name and isinstance(
        body["pending_approvals"], int
    )
    problem_id = body["open_problems"][0]["id"]
    staff = TestClient(app)
    login(staff, juha)
    assert staff.get("/supervisor/summary").status_code == 403
    assert staff.post(f"/problems/{problem_id}/resolve").status_code == 403
    assert client.post(f"/problems/{problem_id}/resolve").status_code == 200
    assert client.get("/supervisor/summary").json()["open_problems"] == []
    assert client.post("/problems/nope/resolve").status_code == 404


@pytest.mark.parametrize(
    "text",
    [
        "Myöhästyn, ovi oli lukossa kotona",
        "I can't come tomorrow, no key for the car",
        "Auto on lukossa, myöhästyn",
        "Hälytin soi kotona, myöhästyn",
        "I'm late, my car is locked out of the garage",
        "I set the alarm for 6 so I will be there",
        "Ovi oli lukossa mutta pääsin sisään, kaikki ok",
        "Remontti kotona, en tule huomenna",
        "No power at home, I'm running late",
        "Ei vettä kotona, tulen myöhässä",
        "I can't start before 9 tomorrow, running late",
        "Is there a renovation at Kamppi next week?",
        "Voinko ottaa avaimen huomenna?",
    ],
)
def test_everyday_messages_are_not_site_problems(text: str) -> None:
    """A problem report pages the supervisors: only anchored phrases trigger it, and an
    absence always wins."""
    assert classify(text, TODAY).name not in ("cannot_access_site", "site_problem"), text


def test_absence_wording_still_routes_to_absence() -> None:
    for text in ("Myöhästyn, ovi oli lukossa kotona", "Remontti kotona, en tule huomenna"):
        assert classify(text, TODAY).name == "report_absence", text


def test_long_problem_message_does_not_crash_the_turn(
    client: TestClient,
    session: Session,
    people: dict[str, Person],
    login,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    today = dt.datetime.now(ZoneInfo("Europe/Helsinki")).date()
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    visit = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == today)
    ).one()
    monkeypatch.setattr(tools, "utcnow", lambda: visit.planned_start)
    login(client, people["Juha"])
    res = client.post("/chat", json={"text": "En pääse sisään, ovi on lukossa. " + "x" * 600})
    assert res.status_code == 200, res.text
    row = session.exec(select(Incident)).one()
    assert len(row.text) <= 500


def test_problem_attaches_to_today_and_to_the_named_site(
    session: Session, branch: Branch, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    juha = people["Juha"]
    deps = deps_for(session, branch, juha)
    today_rows = sorted(
        (
            v
            for v in session.exec(select(Visit).where(Visit.date == deps.today))
            if juha.id in v.assigned_person_ids
        ),
        key=lambda v: v.planned_start,
    )
    assert len(today_rows) >= 2
    last = today_rows[-1]
    # After today's last visit ended: no "next visit today", so no_visit (never tomorrow's).
    monkeypatch.setattr(tools, "utcnow", lambda: last.planned_end + dt.timedelta(hours=1))
    out = tools.report_site_problem(
        deps, tools.ReportProblemInput(kind="site_problem", text="x"), "c1"
    )
    assert out.status == "invalid" and out.reason == "no_visit"
    # A named site wins over the nearest start.
    first = today_rows[0]
    monkeypatch.setattr(tools, "utcnow", lambda: first.planned_start + dt.timedelta(minutes=10))
    from mia.core.models import Location

    last_loc = session.get(Location, last.location_id)
    assert last_loc is not None
    out = tools.report_site_problem(
        deps,
        tools.ReportProblemInput(
            kind="cannot_access", text="x", location_name=last_loc.name.split()[0]
        ),
        "c2",
    )
    assert out.status == "ok" and out.visit and out.visit.visit_id == last.id


def test_reporting_supervisor_is_not_paged_about_themselves(
    session: Session, branch: Branch, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.core import store

    sanna = people["Sanna"]
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    today = dt.datetime.now(ZoneInfo("Europe/Helsinki")).date()
    visit = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == today)
    ).one()
    store.update(session, visit, {"assigned_person_ids": [sanna.id]}, Actor.person(sanna))
    deps = deps_for(session, branch, sanna)
    monkeypatch.setattr(tools, "utcnow", lambda: visit.planned_start)
    out = tools.report_site_problem(
        deps, tools.ReportProblemInput(kind="site_problem", text="x"), "c1"
    )
    assert out.status == "ok" and _notes(session, sanna) == []


def test_problem_of_another_branch_is_invisible(
    client: TestClient, session: Session, branch: Branch, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    from mia.core import store
    from mia.core.models import Branch as B

    other = store.insert(
        session, B(organisation_id=branch.organisation_id, name="B2"), Actor.system(branch.id)
    )
    stranger = store.insert(
        session, Person(branch_id=other.id, name="Outi", roles=["staff"]), Actor.system(other.id)
    )
    job = session.exec(select(Job)).first()
    assert job is not None
    visit = store.insert(
        session,
        Visit(
            branch_id=other.id,
            job_id=job.id,
            location_id=job.location_id,
            date=dt.date(2026, 1, 5),
            planned_start=dt.datetime(2026, 1, 5, 8, tzinfo=dt.UTC),
            planned_end=dt.datetime(2026, 1, 5, 9, tzinfo=dt.UTC),
        ),
        Actor.system(other.id),
    )
    problem = store.insert(
        session,
        Incident(
            branch_id=other.id,
            visit_id=visit.id,
            person_id=stranger.id,
            kind="site_problem",
            text="x",
        ),
        Actor.system(other.id),
    )
    session.commit()
    login(client, people["Sanna"])
    assert client.post(f"/problems/{problem.id}/resolve").status_code == 404
    assert client.get("/supervisor/summary").json()["open_problems"] == []
