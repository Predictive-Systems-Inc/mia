import asyncio

import pytest
from sqlmodel import Session

from mia.agents.base import Turn
from mia.agents.registry import AGENTS
from mia.chat import service
from mia.chat.access import agents_for
from mia.core import orgconfig
from mia.core.models import Person
from mia.i18n import t

ROSTER = [
    "sales_supervisor",
    "shift_supervisor",
    "inventory_manager",
    "bookkeeper",
    "hr_officer",
    "branch_manager",
]
SALES_SHIFT_STOCK = ["sales_supervisor", "shift_supervisor", "inventory_manager"]


def _run_org(monkeypatch: pytest.MonkeyPatch, agents: list[str]) -> None:
    monkeypatch.setattr(orgconfig, "load", lambda org=None: orgconfig.OrgSettings(agents=agents))


@pytest.fixture
def all_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_org(monkeypatch, ROSTER)


def _ids(session: Session, person: Person) -> list[str]:
    return [a.id for a in agents_for(session, person)]


def test_the_roster_is_registered() -> None:
    assert set(ROSTER) <= set(AGENTS)


def test_by_default_everyone_has_only_the_shift_supervisor(
    session: Session, people: dict[str, Person]
) -> None:
    assert _ids(session, people["Helena"]) == ["shift_supervisor"]
    assert _ids(session, people["Juha"]) == ["shift_supervisor"]


def test_access_per_role(session: Session, people: dict[str, Person], all_enabled: None) -> None:
    assert _ids(session, people["Helena"]) == ROSTER  # owner: all six
    assert _ids(session, people["Sanna"]) == SALES_SHIFT_STOCK
    assert _ids(session, people["Juha"]) == ["shift_supervisor"]  # staff


def test_a_clerk_gets_sales_shift_and_inventory(
    session: Session, people: dict[str, Person], all_enabled: None
) -> None:
    juha = people["Juha"]
    clerk = Person(name=juha.name, branch_id=juha.branch_id, roles=["clerk"])
    assert _ids(session, clerk) == SALES_SHIFT_STOCK


def test_an_agent_the_org_does_not_run_is_never_offered(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_org(monkeypatch, ["bookkeeper", "nonexistent"])
    assert _ids(session, people["Juha"]) == []  # staff may not use the bookkeeper
    assert _ids(session, people["Helena"]) == ["bookkeeper"]  # unknown ids are skipped


def test_a_stub_answers_that_it_is_not_available(
    session: Session, people: dict[str, Person]
) -> None:
    from mia.agents.stubs import STUBS

    assert {s.id for s in STUBS} == set(ROSTER) - {"shift_supervisor"}
    assert all(s.router_description and s.run_due is None for s in STUBS)

    person = people["Juha"]
    thread, past, deps, ctx = service._prepare(session, person, "how many did we sell?", None)
    stub = next(s for s in STUBS if s.id == "bookkeeper")
    deps.manifest = stub.manifest
    reply = asyncio.run(stub.handle_turn(Turn(session, deps, thread, "hi", past, ctx)))
    assert t("reply.unavailable", person.language) in reply.text()
