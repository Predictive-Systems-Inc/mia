"""Fixtures: a temp SQLite file per test, a seeded demo branch, actors and agents.

No network and no API keys: MIA_MODEL=test everywhere, and egress tests use mock transports.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from mia.agents.dispatcher import agent as dispatcher_agent
from mia.core import db
from mia.core.models import Actor, Branch, Person
from mia.schema import create_all
from mia.settings import get_settings
from mia.templates.cleaning.seed import seed


def pytest_configure(config: pytest.Config) -> None:
    """The 80% floor applies to mia/core in the unit run; evals measure behaviour, not coverage."""
    markexpr = getattr(config.option, "markexpr", "") or ""
    cov = config.pluginmanager.get_plugin("_cov")
    if cov is not None and "evals" in markexpr and "not evals" not in markexpr:
        cov.options.cov_fail_under = None


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every test gets its own database file and the test model."""
    monkeypatch.setenv("MIA_DB_PATH", str(tmp_path / "mia.db"))
    monkeypatch.setenv("MIA_MODEL", "test")
    monkeypatch.setenv("MIA_EGRESS_LEVEL", "pseudonymised")
    monkeypatch.setenv("MIA_GATEWAY_KEY", "test-key")
    monkeypatch.setenv("MIA_GATEWAY_URL", "http://gateway.test/v1")
    get_settings.cache_clear()
    dispatcher_agent.get_agent.cache_clear()
    db.reset_engines()
    yield
    db.reset_engines()
    get_settings.cache_clear()
    dispatcher_agent.get_agent.cache_clear()


@pytest.fixture
def engine() -> Engine:
    eng = db.get_engine()
    create_all(eng)
    return eng


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def branch(session: Session) -> Branch:
    b = seed(session)
    session.commit()
    return b


@pytest.fixture
def people(session: Session, branch: Branch) -> dict[str, Person]:
    """Seeded people by first name: Helena (owner), Sanna (supervisor), Juha, Mikael, ..."""
    rows = session.exec(select(Person).where(Person.branch_id == branch.id)).all()
    return {p.name.split()[0]: p for p in rows}


@pytest.fixture
def actor(people: dict[str, Person]) -> Actor:
    """A cleaner acting for themselves."""
    return Actor.person(people["Juha"])


@pytest.fixture
def test_model_agent():  # type: ignore[no-untyped-def]
    """The dispatcher wired to Pydantic AI's TestModel (no tool calls, schema-valid output)."""
    from pydantic_ai.models.test import TestModel

    from mia.agents.base import build_agent
    from mia.agents.dispatcher.agent import AGENT_DIR, MANIFEST
    from mia.agents.dispatcher.tools import BINDINGS
    from mia.chat.blocks import AgentReply

    return build_agent(
        MANIFEST,
        AGENT_DIR,
        BINDINGS,
        AgentReply,
        TestModel(call_tools=[], custom_output_args={"blocks": [{"type": "text", "text": "hei"}]}),
        "demo",
    )
