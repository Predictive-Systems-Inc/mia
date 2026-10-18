from collections.abc import Iterator
from zoneinfo import ZoneInfo

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


def test_seed_hr_data(ferinos: None, session: Session) -> None:
    import datetime as dt

    from mia.agents.hr_officer.models import Contract, Leave, Payslip
    from mia.core.models import Timesheet, Visit
    from mia.templates.retail import seed

    seed.seed(session)
    people = {p.id: p.name for p in session.exec(select(Person)).all()}
    assert len(session.exec(select(Contract)).all()) == 5
    leave = session.exec(select(Leave)).all()
    assert len(leave) == 2 and {x.status for x in leave} == {"approved"}
    slips = session.exec(select(Payslip)).all()
    for clerk in ("Ana", "Liza", "Pao"):
        assert [people[s.person_id] for s in slips].count(clerk) == 2
    today = dt.datetime.now(ZoneInfo("Asia/Manila")).date()
    sheets = session.exec(select(Timesheet)).all()
    assert {t.status for t in sheets} == {"approved"}
    for clerk in ("Ana", "Liza", "Pao"):
        days = {t.date for t in sheets if people[t.person_id] == clerk}
        assert len(days) >= 12 and min(days) <= today - dt.timedelta(days=13)
        assert max(days) >= today - dt.timedelta(days=2)
    late = [v for v in session.exec(select(Visit)).all() if v.actual_end.hour == 23]  # type: ignore[union-attr]
    assert len(late) == 1  # an evening shift to 23:30, so night minutes exist


def test_holidays_validate_and_a_bad_kind_is_refused() -> None:
    ok = orgconfig.OrgSettings(
        holidays=[{"date": "2026-12-25", "kind": "regular", "name": "Christmas"}]  # type: ignore[list-item]
    )
    assert ok.holidays[0].date.month == 12 and ok.payroll.pay_lag_days == 5
    with pytest.raises(ValueError):
        orgconfig.OrgSettings(
            holidays=[{"date": "2026-12-25", "kind": "bank", "name": "x"}]  # type: ignore[list-item]
        )


def test_ferinos_holidays_load_from_holidays_yaml(ferinos: None) -> None:
    holidays = orgconfig.load().holidays
    assert len(holidays) >= 18 and {h.kind for h in holidays} == {"regular", "special"}
