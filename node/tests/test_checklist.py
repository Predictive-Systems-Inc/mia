"""The visit checklist over chat: show and tick items for the current visit."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.agents.dispatcher import tools
from mia.agents.dispatcher.classifier import classify
from mia.api.main import app
from mia.core.models import Branch, Event, Job, Person, Visit
from mia.templates.cleaning.models import CleaningChecklistTick
from tests.test_tools import deps_for


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


TODAY = dt.date(2026, 9, 30)


@pytest.mark.parametrize(
    ("text", "intent", "item"),
    [
        ("Mikä on tarkistuslista?", "checklist", None),
        ("Näytä checklist", "checklist", None),
        ("What do I need to do here?", "checklist", None),
        ("Tehty: Empty bins", "checklist", "Empty bins"),
        ("Done: wipe surfaces", "checklist", "wipe surfaces"),
        ("Valmis: Empty bins", "checklist", "Empty bins"),
        ("Valmis, lähden nyt", "check_out", None),
        ("I'm done here", "check_out", None),
        ("Done: Replace bin liners", "checklist", "Replace bin liners"),
        ("Tehty: Korvaa pyyhkeet", "checklist", "Korvaa pyyhkeet"),
        ("Done: Lock up and leave early", "checklist", "Lock up and leave early"),
        ("Done: ", "other", None),
        ("Valmis:", "other", None),
    ],
)
def test_checklist_intents(text: str, intent: str, item: str | None) -> None:
    got = classify(text, TODAY)
    assert got.name == intent and got.item == item


def _visit(session: Session, deps: tools.AgentDeps, name: str = "Kamppi shop clean") -> Visit:
    job = session.exec(select(Job).where(Job.name == name)).one()
    return session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == deps.today)
    ).one()


def test_show_tick_and_repeat(
    session: Session, branch: Branch, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = deps_for(session, branch, people["Juha"])
    visit = _visit(session, deps)
    monkeypatch.setattr(tools, "utcnow", lambda: visit.planned_start)
    out = tools.checklist(deps, tools.ChecklistInput(), "c1")
    assert out.status == "ok" and out.visit and out.visit.visit_id == visit.id
    assert [(i.text, i.done) for i in out.items] == [
        ("Empty bins", False),
        ("Wipe surfaces", False),
    ]
    out = tools.checklist(deps, tools.ChecklistInput(item="empty"), "c2")
    assert out.status == "ok" and out.ticked == "Empty bins"
    assert [(i.text, i.done) for i in out.items] == [("Empty bins", True), ("Wipe surfaces", False)]
    again = tools.checklist(deps, tools.ChecklistInput(item="Empty bins"), "c3")
    assert again.ticked == "Empty bins"
    assert len(session.exec(select(CleaningChecklistTick)).all()) == 1  # ticking twice is a no-op
    unknown = tools.checklist(deps, tools.ChecklistInput(item="windows"), "c4")
    assert unknown.status == "ok" and unknown.ticked is None and unknown.unknown == "windows"
    assert session.exec(select(Event).where(Event.action == "checklist.ticked")).one()


def test_no_visit_and_no_checklist(
    session: Session, branch: Branch, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia.core import store
    from mia.core.models import Actor
    from mia.templates.cleaning.models import CleaningChecklist

    sanna = deps_for(session, branch, people["Sanna"])
    assert tools.checklist(sanna, tools.ChecklistInput(), "c1").reason == "no_visit"
    deps = deps_for(session, branch, people["Juha"])
    visit = _visit(session, deps)
    monkeypatch.setattr(tools, "utcnow", lambda: visit.planned_start)
    row = session.exec(
        select(CleaningChecklist).where(CleaningChecklist.job_id == visit.job_id)
    ).one()
    store.update(session, row, {"items": []}, Actor.person(people["Sanna"]))
    assert tools.checklist(deps, tools.ChecklistInput(), "c2").reason == "no_checklist"


def test_checklist_needs_permission(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core import people as people_service
    from mia.core.models import Actor
    from mia.core.rbac import PermissionDenied

    viewer = people_service.add_person(
        session,
        Actor.person(people["Helena"]),
        branch_id=branch.id,
        name="Vilma Viewer",
        roles=["viewer"],
    )
    with pytest.raises(PermissionDenied):
        tools.checklist(deps_for(session, branch, viewer), tools.ChecklistInput(), "c1")


def test_tick_reply_language_follows_the_prefix_word() -> None:
    assert classify("Tehty: Wipe the surfaces", TODAY).lang == "fi"
    assert classify("Done: Pyyhi pinnat", TODAY).lang == "en"


def _with_items(session: Session, visit: Visit, items: list[str]) -> None:
    from mia.core import store
    from mia.core.models import Actor
    from mia.templates.cleaning.models import CleaningChecklist

    row = session.exec(
        select(CleaningChecklist).where(CleaningChecklist.job_id == visit.job_id)
    ).one()
    store.update(
        session, row, {"items": [{"text": t} for t in items]}, Actor.system(visit.branch_id)
    )


def test_exact_match_wins_and_short_prefixes_do_not_tick(
    session: Session, branch: Branch, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = deps_for(session, branch, people["Juha"])
    visit = _visit(session, deps)
    _with_items(session, visit, ["Bins", "Bins and surfaces"])
    monkeypatch.setattr(tools, "utcnow", lambda: visit.planned_start)
    out = tools.checklist(deps, tools.ChecklistInput(item="Bins and surfaces"), "c1")
    assert out.ticked == "Bins and surfaces"
    out = tools.checklist(deps, tools.ChecklistInput(item="bins"), "c2")
    assert out.ticked == "Bins"
    for empty in ("", "  ", "b"):
        out = tools.checklist(deps, tools.ChecklistInput(item=empty), "c3")
        assert out.ticked is None, empty
    assert len(session.exec(select(CleaningChecklistTick)).all()) == 2


def test_long_lists_fit_the_quick_replies_and_long_items_do_not_crash(
    client,
    session: Session,
    branch: Branch,
    people: dict[str, Person],
    login,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    deps = deps_for(session, branch, people["Juha"])
    visit = _visit(session, deps)
    _with_items(session, visit, [f"Item {i}" for i in range(1, 9)])
    session.commit()
    monkeypatch.setattr(tools, "utcnow", lambda: visit.planned_start)
    login(client, people["Juha"])
    res = client.post("/chat", json={"text": "Mikä on tarkistuslista?"})
    assert res.status_code == 200, res.text
    quick = next(b for b in res.json()["blocks"] if b["type"] == "quick_replies")
    assert len(quick["options"]) == 6
    res = client.post("/chat", json={"text": "Done: " + "x" * 300})
    assert res.status_code == 200
