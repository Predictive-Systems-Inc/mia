"""Fixtures: a temp SQLite file per test, a seeded demo branch, actors and agents.

No network and no API keys: MIA_MODEL=test everywhere, and egress tests use mock transports.
"""

import datetime as dt
import importlib
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import models

from mia import i18n
from mia.agents.shift_supervisor import agent as shift_supervisor_agent
from mia.channels import registry
from mia.core import db, keys, orgconfig, scheduling
from mia.core.models import Actor, Branch, Person
from mia.schema import create_all
from mia.settings import get_settings
from mia.templates.cleaning.seed import seed

# Any model other than TestModel or FunctionModel fails unless a test opts in with
# models.override_allow_model_requests(True) (egress tests with a mock transport, real evals).
models.ALLOW_MODEL_REQUESTS = False


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
    if not os.environ.get("MIA_EVAL_MODEL"):  # real evals keep the real gateway from the env
        monkeypatch.setenv("MIA_GATEWAY_KEY", "test-key")
        monkeypatch.setenv("MIA_GATEWAY_URL", "http://gateway.test/v1")
    monkeypatch.setenv("MIA_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("MIA_LEARNING_DIR", str(tmp_path / "learning"))
    monkeypatch.setenv("MIA_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("MIA_TICK_SECONDS", "0")
    monkeypatch.setenv("MIA_GEOCODER", "static")
    monkeypatch.setenv("MIA_NODE_SECRET", "test-node-secret")
    monkeypatch.setenv("MIA_WA_NUMBER", "358401110000")
    monkeypatch.setenv("MIA_PUBLIC_URL", "http://localhost:8000")  # not the developer's .env
    key_file = tmp_path / "master.key"
    keys.generate(key_file)
    monkeypatch.setenv("MIA_MASTER_KEY_FILE", str(key_file))
    monkeypatch.setenv("MIA_AUTH_MODE", "dev")
    monkeypatch.setattr(i18n, "_pick", lambda variants: variants[0])  # stable pinned texts
    monkeypatch.setattr(keys, "SCRYPT_N", 2**8)  # the real 2**17 makes every login slow
    keys.reset_cache()
    scheduling.reset_generation()
    get_settings.cache_clear()
    shift_supervisor_agent.get_agent.cache_clear()
    db.reset_engines()
    saved_adapters = dict(registry._adapters)
    yield
    registry._adapters.clear()
    registry._adapters.update(saved_adapters)
    db.reset_engines()
    keys.reset_cache()
    get_settings.cache_clear()
    shift_supervisor_agent.get_agent.cache_clear()


@pytest.fixture(autouse=True)
def _loopback_test_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """TestClient requests come from 127.0.0.1 (the dev header needs a loopback peer), unless a
    test passes its own `client=` address."""
    from starlette import testclient

    original = testclient.TestClient.__init__

    def init(self, app, *args, client=("127.0.0.1", 50000), **kwargs):  # type: ignore[no-untyped-def]
        original(self, app, *args, client=client, **kwargs)

    monkeypatch.setattr(testclient.TestClient, "__init__", init)


@pytest.fixture(autouse=True)
def shift_supervisor_role() -> None:
    """The shift supervisor's manifest grants are in RBAC for every test, so tool tests do not
    depend on which test built an agent first."""
    from mia.agents.shift_supervisor.agent import create_agent

    create_agent("test")


@pytest.fixture(autouse=True)
def sales_supervisor_role() -> None:
    """The sales supervisor's manifest grants are in RBAC for every test (it has no LLM agent
    whose build would load them)."""
    from mia.agents.sales_supervisor import MANIFEST
    from mia.core.rbac import get_rbac

    roles = MANIFEST.roles
    get_rbac().load_agent_role(roles.agent_role, roles.grants, roles.denies)


@pytest.fixture(autouse=True)
def inventory_manager_role() -> None:
    """The inventory manager's manifest grants are in RBAC for every test (no LLM agent)."""
    from mia.agents.inventory_manager import MANIFEST
    from mia.core.rbac import get_rbac

    roles = MANIFEST.roles
    get_rbac().load_agent_role(roles.agent_role, roles.grants, roles.denies)


@pytest.fixture(autouse=True)
def hr_officer_role() -> None:
    """The hr officer's manifest grants are in RBAC for every test (no LLM agent)."""
    from mia.agents.hr_officer import MANIFEST
    from mia.core.rbac import get_rbac

    roles = MANIFEST.roles
    get_rbac().load_agent_role(roles.agent_role, roles.grants, roles.denies)


@pytest.fixture(autouse=True)
def customer_service_role() -> None:
    """The customer service's manifest grants are in RBAC for every test (no LLM agent)."""
    from mia.agents.customer_service import MANIFEST
    from mia.core.rbac import get_rbac

    roles = MANIFEST.roles
    get_rbac().load_agent_role(roles.agent_role, roles.grants, roles.denies)


@pytest.fixture(autouse=True)
def branch_manager_role() -> None:
    """The branch manager's manifest grants are in RBAC for every test (no LLM agent)."""
    from mia.agents.branch_manager import MANIFEST
    from mia.core.rbac import get_rbac

    roles = MANIFEST.roles
    get_rbac().load_agent_role(roles.agent_role, roles.grants, roles.denies)


@pytest.fixture(autouse=True)
def bookkeeper_role() -> None:
    """The bookkeeper's manifest grants are in RBAC for every test (no LLM agent)."""
    from mia.agents.bookkeeper import MANIFEST
    from mia.core.rbac import get_rbac

    roles = MANIFEST.roles
    get_rbac().load_agent_role(roles.agent_role, roles.grants, roles.denies)


@pytest.fixture
def fresh_rbac() -> Iterator[None]:
    """A new enforcer from the policy files only, as on a node that built no agent: the autouse
    role loaders above have loaded the old one."""
    from mia.core.rbac import get_rbac

    get_rbac.cache_clear()
    yield
    get_rbac.cache_clear()


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
def login(session: Session):  # type: ignore[no-untyped-def]
    """Sign a person in on a TestClient through the service (bearer token on every request)."""
    from mia.core import auth as auth_service
    from mia.core.db import utcnow

    def _login(
        client, person, *, aal="aal2", method="password_totp", stepped_up=False, device=None
    ):  # type: ignore[no-untyped-def]
        now = utcnow()
        tokens = auth_service.issue_session(
            session, person, method=method, aal=aal, ip="127.0.0.1", now=now, device=device
        )
        if stepped_up:
            auth_service.step_up(session, tokens.row, now)
        session.commit()
        client.headers["Authorization"] = f"Bearer {tokens.access}"
        return tokens

    return _login


@pytest.fixture
def test_model_agent():  # type: ignore[no-untyped-def]
    """The shift supervisor wired to Pydantic AI's TestModel (no tool calls, schema-valid output)."""
    from pydantic_ai.models.test import TestModel

    from mia.agents.base import build_agent
    from mia.agents.shift_supervisor.agent import AGENT_DIR, MANIFEST
    from mia.agents.shift_supervisor.tools import BINDINGS
    from mia.chat.blocks import AgentReply

    return build_agent(
        MANIFEST,
        AGENT_DIR,
        BINDINGS,
        AgentReply,
        TestModel(call_tools=[], custom_output_args={"blocks": [{"type": "text", "text": "hei"}]}),
        "demo",
    )


CLOCK_USERS = (
    "mia.core.db",
    "mia.core.approvals",
    "mia.agents.shift_supervisor.tools",
    "mia.agents.sales_supervisor.tools",
    "mia.agents.inventory_manager.tools",
    "mia.agents.hr_officer.tools",
    "mia.agents.shift_supervisor.cover",
    "mia.chat.service",
    "mia.api.main",
    "mia.channels.outbox",
    "mia.channels.service",
    "mia.channels.linking",
    "mia.channels.inbound",
    "mia.channels.simulator",
    "mia.agents.customer_service.public",
    "mia.agents.customer_service.due",
    "mia.templates.retail.items",
    "mia.agents.branch_manager.tools",
    "mia.agents.branch_manager.due",
    "mia.agents.bookkeeper.tools",
    "mia.agents.bookkeeper.due",
)
for _name in CLOCK_USERS:
    # Import every clock user up front: one first imported while mia.core.db.utcnow is patched
    # binds the fake, and monkeypatch then "restores" that fake, leaking it to later tests.
    importlib.import_module(_name)


@pytest.fixture
def daytime(monkeypatch: pytest.MonkeyPatch) -> Callable[[], datetime]:
    """Run the clock from noon in Helsinki today, so quiet hours (21:00 to 06:00) never hold a
    message and a test does not depend on when it runs. Same date, so seeded visits line up."""
    start = datetime.now(UTC)
    noon = (
        datetime.now(ZoneInfo("Europe/Helsinki"))
        .replace(hour=12, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )

    def now() -> datetime:
        return noon + (datetime.now(UTC) - start)

    for name in CLOCK_USERS:
        monkeypatch.setattr(importlib.import_module(name), "utcnow", now)
    return now


@pytest.fixture
def ferinos(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> Iterator[tuple[Branch, dict[str, Person]]]:
    """The retail demo org (MIA_ORG=ferinos) seeded: the Mall kiosk and people by first name
    (Rosa owner, Marites and Jun supervisors, Ana, Liza and Pao clerks)."""
    from mia.core import orgconfig
    from mia.templates.retail import seed as retail_seed

    load = orgconfig.load  # a test may patch orgconfig.load: clear the real cache after it
    with monkeypatch.context() as m:
        m.setenv("MIA_ORG", "ferinos")
        get_settings.cache_clear()
        load.cache_clear()
        kiosk = retail_seed.seed(session)
        session.commit()
        staff = {p.name.split()[0]: p for p in session.exec(select(Person)).all()}
        yield kiosk, staff
    get_settings.cache_clear()
    load.cache_clear()


MANILA = ZoneInfo("Asia/Manila")


@pytest.fixture
def manila_at(monkeypatch: pytest.MonkeyPatch) -> Callable[[int, int], datetime]:
    """Pin the clock on CLOCK_USERS to hour:minute today in Manila (the clock keeps running from
    there). Returns the pinned local time."""
    start = datetime.now(UTC)

    def pin(hour: int, minute: int = 0) -> datetime:
        at = datetime.now(MANILA).replace(hour=hour, minute=minute, second=0, microsecond=0)

        def now() -> datetime:
            return at.astimezone(UTC) + (datetime.now(UTC) - start)

        for name in CLOCK_USERS:
            monkeypatch.setattr(importlib.import_module(name), "utcnow", now)
        return at

    return pin


@pytest.fixture
def manila_evening(manila_at: Callable[[int, int], datetime]) -> datetime:
    """The clock at 21:30 in Manila today: within two hours after the Mall kiosk closes."""
    return manila_at(21, 30)


MNL = ZoneInfo("Asia/Manila")
TODAY = dt.date(2026, 10, 20)  # a Tuesday


@dataclass
class Shop:
    kiosk: Branch
    people: dict[str, Person]
    pin: Callable[..., dt.datetime]


def _ferinos_on(
    monkeypatch: pytest.MonkeyPatch, session: Session, today: dt.date
) -> Iterator[Shop]:
    """The Ferino's seed on today (MIA_ORG=ferinos, both caches cleared) with the clock at 10:00
    Manila; pin(hour, minute, days) moves the clock on every CLOCK_USERS module (it keeps
    running from there)."""
    from mia.templates.retail import seed as retail_seed

    start = dt.datetime.now(dt.UTC)  # only the elapsed time is read, never the date

    def pin(hour: int, minute: int = 0, days: int = 0) -> dt.datetime:
        local = dt.datetime.combine(today + dt.timedelta(days=days), dt.time(hour, minute), MNL)

        def now() -> dt.datetime:
            return local.astimezone(dt.UTC) + (dt.datetime.now(dt.UTC) - start)

        for name in CLOCK_USERS:
            monkeypatch.setattr(importlib.import_module(name), "utcnow", now)
        return local

    pin(10)
    load = orgconfig.load  # a test may patch orgconfig.load: clear the real cache after it
    with monkeypatch.context() as m:
        m.setenv("MIA_ORG", "ferinos")
        get_settings.cache_clear()
        load.cache_clear()
        kiosk = retail_seed.seed(session, today=today)
        session.commit()
        people = {p.name.split()[0]: p for p in session.exec(select(Person)).all()}
        yield Shop(kiosk, people, pin)
    get_settings.cache_clear()
    load.cache_clear()


@pytest.fixture
def cs(monkeypatch: pytest.MonkeyPatch, session: Session) -> Iterator[Shop]:
    """The customer service's shop: _ferinos_on TODAY (a Tuesday)."""
    yield from _ferinos_on(monkeypatch, session, TODAY)


BM_TODAY = dt.date(2026, 10, 26)  # a Monday; the seed's counts are 12 to 25 October


@pytest.fixture
def bm_shop(monkeypatch: pytest.MonkeyPatch, session: Session) -> Iterator[Shop]:
    """The branch manager's shop: _ferinos_on BM_TODAY, the seed's languages kept."""
    yield from _ferinos_on(monkeypatch, session, BM_TODAY)


@pytest.fixture
def bm(bm_shop: Shop) -> tuple[Branch, dict[str, Person]]:
    """bm_shop as (the Mall kiosk, people by first name); bm_shop.pin moves the clock."""
    return bm_shop.kiosk, bm_shop.people


def _en(shop: Shop, session: Session) -> tuple[Branch, dict[str, Person]]:
    """Every seeded person of the shop set to English (people.set_language), for English
    literals; returns (the Mall kiosk, people by first name)."""
    from mia.core import people

    for person in session.exec(select(Person)).all():
        people.set_language(session, Actor.system(shop.kiosk.id), person, "en")
    session.commit()
    return shop.kiosk, {p.name.split()[0]: p for p in session.exec(select(Person)).all()}


Pin = Callable[[dt.datetime], dt.datetime]


def _set_at(shop: Shop, today: dt.date) -> Pin:
    """Move the shop clock to an aware moment (shop.pin at its Manila hour, minute and days
    from today; the clock keeps running from there). Returns the local moment."""

    def set_at(at: dt.datetime) -> dt.datetime:
        local = at.astimezone(MNL)
        return shop.pin(local.hour, local.minute, (local.date() - today).days)

    return set_at


@pytest.fixture
def bm_en(bm_shop: Shop, session: Session) -> tuple[Branch, dict[str, Person]]:
    """bm with every seeded person set to English (_en), for English literals."""
    return _en(bm_shop, session)


@pytest.fixture
def pin(bm_shop: Shop) -> Pin:
    """Move the bm_shop clock to an aware moment (_set_at from BM_TODAY)."""
    return _set_at(bm_shop, BM_TODAY)


BK_TODAY = dt.date(2026, 11, 3)  # a Tuesday; the seed's counts are 20 October to 2 November


@pytest.fixture
def bk_shop(monkeypatch: pytest.MonkeyPatch, session: Session) -> Iterator[Shop]:
    """The bookkeeper's shop: _ferinos_on BK_TODAY, the seed's languages kept (both seeded
    payslip cutoffs are October's)."""
    yield from _ferinos_on(monkeypatch, session, BK_TODAY)


@pytest.fixture
def bk(bk_shop: Shop) -> tuple[Branch, dict[str, Person]]:
    """bk_shop as (the Mall kiosk, people by first name); bk_shop.pin moves the clock."""
    return bk_shop.kiosk, bk_shop.people


@pytest.fixture
def bk_en(bk_shop: Shop, session: Session) -> tuple[Branch, dict[str, Person]]:
    """bk with every seeded person set to English (_en), for English literals."""
    return _en(bk_shop, session)


@pytest.fixture
def bk_pin(bk_shop: Shop) -> Pin:
    """Move the bk_shop clock to an aware moment (_set_at from BK_TODAY)."""
    return _set_at(bk_shop, BK_TODAY)
