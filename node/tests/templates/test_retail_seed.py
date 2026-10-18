from collections.abc import Iterator

import pytest
from sqlmodel import Session, select

from mia.core import orgconfig
from mia.core.models import Branch, Person
from mia.settings import get_settings


@pytest.fixture
def ferinos(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with monkeypatch.context() as m:
        m.setenv("MIA_ORG", "ferinos")
        get_settings.cache_clear()
        orgconfig.load.cache_clear()
        yield
    get_settings.cache_clear()
    orgconfig.load.cache_clear()


def test_org_template_selects_the_retail_seed(ferinos: None, session: Session) -> None:
    from mia.agents.sales_supervisor.models import SalesCount, SalesTarget
    from mia.templates.retail import seed
    from mia.templates.retail.models import RetailBranchHours, RetailItem

    assert orgconfig.load().template == "retail"
    branch = seed.seed(session)
    assert branch.timezone == "Asia/Manila"
    assert len(session.exec(select(Branch)).all()) == 2
    assert len(session.exec(select(RetailItem)).all()) == 8
    assert len(session.exec(select(RetailBranchHours)).all()) == 14
    assert len(session.exec(select(SalesTarget)).all()) == 2
    assert len(session.exec(select(SalesCount)).all()) > 100
    roles = {p.name: p.roles for p in session.exec(select(Person)).all()}
    assert "clerk" in roles["Ana"] and "owner" in roles["Rosa"]


def test_default_template_is_cleaning() -> None:
    assert orgconfig.OrgSettings().template == "cleaning"


def test_unknown_template_is_refused() -> None:
    with pytest.raises(ValueError):
        orgconfig.OrgSettings(template="bakery")  # type: ignore[arg-type]
