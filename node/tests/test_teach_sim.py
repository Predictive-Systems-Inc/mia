"""Teach Mia on the phones page (/sim) and phrases as eval rows (spec teach-mia, 4 and 6)."""

import csv
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from mia.api.main import app
from mia.chat import phrases
from mia.core.models import Actor, Event, Person
from mia.settings import get_settings
from tests.evals.cases import FOLDER, HEADER

ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("get", "/sim/phones/x/teach", None),
    ("post", "/sim/teach", {"person_id": "x", "text": "a", "agent_id": "a", "action": "a"}),
    ("get", "/sim/phrases", None),
    ("post", "/sim/phrases/retire", {"key": "a"}),
    ("get", "/sim/requests", None),
    ("post", "/sim/requests", {"person_id": "x", "text": "a"}),
]


def _call(client: TestClient, method: str, url: str, body: dict[str, Any] | None, **kw: Any) -> int:
    if method == "get":
        return client.get(url, **kw).status_code
    return client.post(url, json=body, **kw).status_code


@pytest.mark.usefixtures("branch")
def test_the_teach_routes_are_404_outside_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    client = TestClient(app)
    assert all(_call(client, *r) == 404 for r in ROUTES)


@pytest.mark.usefixtures("branch")
def test_the_teach_routes_are_404_off_loopback() -> None:
    lan = TestClient(app, client=("192.168.1.20", 50000))
    assert all(_call(lan, *r) == 404 for r in ROUTES)
    tunnel = TestClient(app)
    cf = {"headers": {"cf-ray": "8a1b2c3d4e5f-MNL"}}
    assert all(_call(tunnel, *r, **cf) == 404 for r in ROUTES)


def test_teach_from_a_phone_lists_retires_and_refuses_money(
    session: Session, ferinos: tuple[Any, dict[str, Person]]
) -> None:
    rosa = ferinos[1]["Rosa"]
    client = TestClient(app)
    options = client.get(f"/sim/phones/{rosa.id}/teach").json()
    sales = next(a for a in options if a["agent_id"] == "sales_supervisor")
    assert "sales_today" in {a["action"] for a in sales["actions"]}
    assert "void_receipt" not in {a["action"] for a in sales["actions"]}
    body = {"person_id": rosa.id, "text": "sales today?", "agent_id": "sales_supervisor"}
    res = client.post("/sim/teach", json={**body, "action": "void_receipt"})
    assert res.status_code == 422
    res = client.post("/sim/teach", json={**body, "action": "sales_today"})
    assert res.status_code == 200 and res.json() == {"key": "sales today", "version": 1}
    session.expire_all()
    ev = session.exec(select(Event).where(Event.action == phrases.TAUGHT)).one()
    assert (ev.actor_id, ev.on_behalf_of) == (rosa.id, "sim:tester")
    assert (ev.after or {})["roles"] == rosa.roles
    res = client.post("/sim/teach", json={**body, "text": "12", "action": "sales_today"})
    assert res.status_code == 422  # a bare number is never a phrase
    listed = client.get("/sim/phrases").json()
    assert 1 in listed["versions"].values()
    (row,) = listed["phrases"]
    assert (row["text"], row["action"], row["taught"]) == ("sales today?", "sales_today", True)
    res = client.post(
        "/sim/phrases/retire", json={"key": "sales today", "branch_id": row["branch_id"]}
    )
    assert res.json() == {"version": 2}
    assert client.get("/sim/phrases").json()["phrases"] == []


def test_a_request_from_a_phone_is_listed_with_its_count(
    ferinos: tuple[Any, dict[str, Person]],
) -> None:
    staff = ferinos[1]
    client = TestClient(app)
    for who in ("Ana", "Liza"):
        body = {"person_id": staff[who].id, "text": "dark mode", "failed_text": "night pls"}
        assert client.post("/sim/requests", json=body).status_code == 200
    (group,) = client.get("/sim/requests").json()
    assert (group["text"], group["count"], group["status"]) == ("dark mode", 2, "new")


def test_export_appends_short_rows_once_and_import_replays_them(
    session: Session, ferinos: tuple[Any, dict[str, Person]], tmp_path: Path
) -> None:
    rosa = ferinos[1]["Rosa"]
    cases = tmp_path / "cases"
    cases.mkdir()
    shutil.copy(FOLDER / "sales_supervisor.csv", cases / "sales_supervisor.csv")
    before = (cases / "sales_supervisor.csv").read_text(encoding="utf-8")
    phrases.teach(
        session, Actor.person(rosa), None, "total benta", "sales_supervisor", "sales_today",
        lang="fil", roles=["owner"],
    )  # fmt: skip
    assert phrases.export_rows(session, cases) == 1
    assert phrases.export_rows(session, cases) == 0  # already present
    text = (cases / "sales_supervisor.csv").read_text(encoding="utf-8")
    assert text.startswith(before)
    rows = list(csv.DictReader(text.splitlines()))
    assert tuple(rows[0]) == HEADER
    last = rows[-1]
    assert (last["intent"], last["message"], last["lang"], last["half"], last["role"]) == (
        "sales_today", "total benta", "fil", "short", "owner",
    )  # fmt: skip
    assert json.loads(last["extra"])["taught"] is True
    phrases.retire(session, Actor.person(rosa), None, "total benta")
    assert phrases.import_rows(session, cases, rosa.branch_id) == 1
    assert phrases.import_rows(session, cases, rosa.branch_id) == 0
    book = phrases.phrasebook(session, rosa.branch_id)[1]
    assert book == {"total benta": ("sales_supervisor", "sales_today")}
    last_taught = session.exec(select(Event).where(Event.action == phrases.TAUGHT)).all()[-1]
    assert last_taught.actor_type == "system"
    after = last_taught.after or {}
    assert after["branch_id"] == rosa.branch_id and after["roles"] == ["owner"]  # M3: no widening
    assert phrases.phrasebook(session, "another-branch")[1] == {}
