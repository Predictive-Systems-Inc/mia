"""Site problems over chat and the supervisor summary."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.agents.dispatcher import tools
from mia.agents.dispatcher.classifier import classify
from mia.agents.dispatcher.models import SiteProblem
from mia.api.main import app
from mia.chat.channels import NOTIFICATION
from mia.core import scheduling
from mia.core.models import Actor, Branch, Job, Message, Person, Thread, Visit
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
    row = session.exec(select(SiteProblem)).one()
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
    today = dt.datetime.now(dt.UTC).date()
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
