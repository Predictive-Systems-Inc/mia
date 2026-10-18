"""Schedule over the API and the CLI; daily generation on the ticker."""

import asyncio

import pytest
from sqlmodel import Session, select

from mia.cli import main
from mia.core.models import Visit


def test_cli_generate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    assert main(["schedule", "generate", "--days", "14"]) == 0
    assert "generated" in capsys.readouterr().out
    assert main(["schedule", "generate", "--days", "14"]) == 0
    assert "generated 0" in capsys.readouterr().out


def test_ticker_generates_once_a_day(
    session: Session, branch: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.api import main as api_main
    from mia.api.main import run_due_work

    noon = dt.datetime.now(ZoneInfo("Europe/Helsinki")).replace(hour=12, minute=0)
    monkeypatch.setattr(api_main, "utcnow", lambda: noon)  # generation runs from 03:00 local
    before = len(session.exec(select(Visit)).all())
    asyncio.run(run_due_work())
    session.expire_all()
    after = len(session.exec(select(Visit)).all())
    assert after > before
    asyncio.run(run_due_work())
    session.expire_all()
    assert len(session.exec(select(Visit)).all()) == after


import datetime as dt
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from mia.api.main import app
from mia.core import scheduling
from mia.core.models import Actor, Branch, Job, Person

TODAY = dt.datetime.now(ZoneInfo("Europe/Helsinki")).date()


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


def _visit_id(session: Session, branch: Branch, people: dict[str, Person], offset: int = 10) -> str:
    """The Kamppi visit `offset` days ahead, generated, with Aino freed for that day."""
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    scheduling.generate(session, Actor.system(branch.id), branch, days=14)
    day = TODAY + dt.timedelta(days=offset)
    aino = people["Aino"]
    for v in session.exec(select(Visit).where(Visit.date == day)).all():
        if aino.id in v.assigned_person_ids:
            scheduling.unassign(session, Actor.system(branch.id), v, aino)
    row = session.exec(select(Visit).where(Visit.job_id == job.id).where(Visit.date == day)).one()
    session.commit()
    return row.id


def test_week_view_and_permissions(
    client: TestClient, session: Session, branch: Branch, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Juha"])
    res = client.get("/schedule")
    assert res.status_code == 200, res.text
    cards = res.json()
    assert cards and all(people["Juha"].id in [a["id"] for a in c["assignees"]] for c in cards)
    keys = {"id", "date", "start", "end", "job", "location", "address", "assignees", "status"}
    assert keys <= set(cards[0])
    assert client.get(f"/schedule?person_id={people['Aino'].id}").status_code == 403
    sup = TestClient(app)
    login(sup, people["Sanna"])
    assert len(sup.get("/schedule").json()) >= len(cards)
    assert sup.get(f"/schedule?person_id={people['Aino'].id}").status_code == 200
    assert sup.get("/schedule?start=2026-13-01").status_code == 422


def test_assign_unassign_and_override_over_http(
    client: TestClient, session: Session, branch: Branch, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    visit_id = _visit_id(session, branch, people)
    aino, liisa = people["Aino"].id, people["Liisa"].id
    login(client, people["Juha"])
    assert client.post(f"/visits/{visit_id}/assign", json={"person_id": aino}).status_code == 403
    sup = TestClient(app)
    login(sup, people["Sanna"])
    res = sup.post(f"/visits/{visit_id}/assign", json={"person_id": aino})
    assert res.status_code == 200 and res.json()["approval_id"] is None, res.text
    res = sup.post(f"/visits/{visit_id}/assign", json={"person_id": liisa})
    assert res.status_code == 200 and res.json()["approval_id"] and res.json()["reasons"]
    approval_id = res.json()["approval_id"]
    assert sup.get("/approvals").json() == []  # a supervisor cannot decide it
    admin = TestClient(app)
    login(admin, people["Helena"], stepped_up=True)
    inbox = admin.get("/approvals").json()
    assert [a["id"] for a in inbox] == [approval_id]
    assert inbox[0]["type"] == "schedule.assignment_override"
    res = admin.post(f"/approvals/{approval_id}/decide", json={"outcome": "approved"})
    assert res.status_code == 200, res.text
    week = sup.get(f"/schedule?person_id={liisa}&start={TODAY + dt.timedelta(days=7)}").json()
    assert visit_id in [v["id"] for v in week]  # alongside her own Töölö visits
    assert sup.post(f"/visits/{visit_id}/unassign", json={"person_id": liisa}).status_code == 200
    res = sup.post(f"/visits/{visit_id}/unassign", json={"person_id": liisa})
    assert res.status_code == 409 and "not assigned" in res.json()["detail"]
    assert sup.post("/visits/nope/assign", json={"person_id": aino}).status_code == 404


def test_check_in_and_out_over_http(
    client: TestClient,
    session: Session,
    branch: Branch,
    people: dict[str, Person],
    login,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visit_id = _visit_id(session, branch, people)
    visit = session.get(Visit, visit_id)
    assert visit is not None
    scheduling.assign(session, Actor.person(people["Sanna"]), visit, people["Juha"])
    session.commit()
    from mia.api import schedule as api

    monkeypatch.setattr(api, "utcnow", lambda: visit.planned_start - dt.timedelta(minutes=10))
    login(client, people["Juha"])
    assert client.post(f"/visits/{visit_id}/check-in").status_code == 200
    other = TestClient(app)
    login(other, people["Aino"])
    assert other.post(f"/visits/{visit_id}/check-out").status_code == 403  # not her visit
    sup = TestClient(app)
    login(sup, people["Sanna"])
    monkeypatch.setattr(api, "utcnow", lambda: visit.planned_end)
    res = sup.post(f"/visits/{visit_id}/check-out", json={"person_id": people["Juha"].id})
    assert res.status_code == 200 and res.json()["status"] == "completed"
    assert client.post(f"/visits/{visit_id}/check-in").status_code == 409


def test_check_in_for_someone_else_records_both_people(
    client: TestClient,
    session: Session,
    branch: Branch,
    people: dict[str, Person],
    login,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mia.core.models import Event

    visit_id = _visit_id(session, branch, people)
    visit = session.get(Visit, visit_id)
    assert visit is not None
    scheduling.assign(session, Actor.person(people["Sanna"]), visit, people["Juha"])
    session.commit()
    from mia.api import schedule as api

    monkeypatch.setattr(api, "utcnow", lambda: visit.planned_start)
    sup = TestClient(app)
    login(sup, people["Sanna"])
    res = sup.post(f"/visits/{visit_id}/check-in", json={"person_id": people["Juha"].id})
    assert res.status_code == 200, res.text
    session.expire_all()
    ev = session.exec(select(Event).where(Event.action == "visit.checked_in")).one()
    assert (ev.actor_id, ev.on_behalf_of) == (people["Sanna"].id, people["Juha"].id)


def test_people_list_for_the_office_and_the_board_markup(
    client: TestClient, session: Session, branch: Branch, people: dict[str, Person], login
) -> None:  # type: ignore[no-untyped-def]
    from mia.core import store

    store.update(session, people["Liisa"], {"status": "left"}, Actor.person(people["Sanna"]))
    session.commit()
    login(client, people["Sanna"])
    rows = client.get("/schedule/people").json()
    assert {r["name"] for r in rows} >= {"Juha Laine", "Mikael Nieminen"}
    assert "Liisa Heikkinen" not in {r["name"] for r in rows}  # only active people
    assert all({"id", "name", "roles", "skills"} <= set(r) for r in rows)
    staff = TestClient(app)
    login(staff, people["Juha"])
    assert staff.get("/schedule/people").status_code == 403
    page = client.get("/").text
    assert 'id="board"' in page and 'id="summary"' in page and "/schedule/people" in page


def test_one_agents_failing_due_work_never_stops_the_rest(
    session: Session, branch: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses

    from mia.agents.registry import AGENTS, DEFAULT
    from mia.api import main as api_main
    from mia.chat import deferred

    ran: list[str] = []

    def broken(_s: Session, _now: object) -> int:
        raise RuntimeError("cover failed")

    def works(_s: Session, _now: object) -> int:
        ran.append("next")
        return 1

    async def retry(_now: object) -> int:
        ran.append("retry_due")
        return 0

    other = next(a for a in AGENTS if a != DEFAULT)
    monkeypatch.setitem(AGENTS, DEFAULT, dataclasses.replace(AGENTS[DEFAULT], run_due=broken))
    monkeypatch.setitem(AGENTS, other, dataclasses.replace(AGENTS[other], run_due=works))
    monkeypatch.setattr(deferred, "retry_due", retry)
    assert asyncio.run(api_main.run_due_work())[0] == 1
    assert ran == ["next", "retry_due"]
