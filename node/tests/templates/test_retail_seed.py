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
    from mia.agents.inventory_manager.models import StockEvent, SupplierOrder
    from mia.agents.sales_supervisor.models import SalesCount, SalesTarget
    from mia.templates.retail import seed
    from mia.templates.retail.models import RetailBranchHours, RetailIngredient, RetailItem

    assert orgconfig.load().template == "retail"
    branch = seed.seed(session)
    assert branch.timezone == "Asia/Manila"
    assert len(session.exec(select(Branch)).all()) == 2
    assert len(session.exec(select(RetailItem)).all()) == 8
    assert len(session.exec(select(RetailBranchHours)).all()) == 14
    assert len(session.exec(select(SalesTarget)).all()) == 2
    assert len(session.exec(select(SalesCount)).all()) > 100
    assert len(session.exec(select(RetailIngredient)).all()) == 8
    for b in session.exec(select(Branch)).all():
        stock = select(StockEvent).where(StockEvent.branch_id == b.id)
        assert len(session.exec(stock).all()) >= 8
    orders = session.exec(select(SupplierOrder)).all()
    assert len(orders) == 1 and orders[0].status == "received"  # its receipt is seeded
    assert orders[0].lines[0]["received"] == orders[0].lines[0]["quantity"]
    roles = {p.name: p.roles for p in session.exec(select(Person)).all()}
    assert "clerk" in roles["Ana"] and "owner" in roles["Rosa"]


def test_no_item_and_ingredient_share_a_name_or_a_code() -> None:
    from mia.templates.retail.seed import INGREDIENTS, ITEMS

    def words(rows: list[tuple[str, list[str]]]) -> set[str]:
        return {w.casefold() for name, codes in rows for w in (name, *codes)}

    items = words([(name, codes) for name, codes, _ in ITEMS])
    ingredients = words([(name, codes) for name, codes, *_ in INGREDIENTS])
    assert not items & ingredients, items & ingredients
    codes = [c for _, cs, *_ in [*ITEMS, *INGREDIENTS] for c in cs]
    assert all(len(c.split()) == 1 for c in codes)  # menu_tokens does not split codes
    eggs = next(cs for name, cs, *_ in INGREDIENTS if name == "Eggs")
    assert "itlog" in eggs


def test_default_template_is_cleaning() -> None:
    assert orgconfig.OrgSettings().template == "cleaning"


def test_unknown_template_is_refused() -> None:
    with pytest.raises(ValueError):
        orgconfig.OrgSettings(template="bakery")  # type: ignore[arg-type]
