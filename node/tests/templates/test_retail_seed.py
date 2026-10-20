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
    from mia.core.models import SalesCount, SalesTarget, StockEvent, SupplierOrder
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

    from mia.core.models import Contract, Leave, Payslip, Timesheet, Visit
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
        assert len(days) >= 9 and min(days) <= today - dt.timedelta(days=10)
        assert max(days) >= today - dt.timedelta(days=2)
    # 21 Oct 2026: the seed also plans shifts from today (D39); a timesheet per completed visit
    visits = session.exec(select(Visit).where(Visit.status == "completed")).all()
    assert {t.visit_id for t in sheets} == {v.id for v in visits}  # a timesheet per visit
    assert len(sheets) == len(visits)


def test_ferinos_holidays_load_from_holidays_yaml(ferinos: None) -> None:
    holidays = orgconfig.load().holidays
    assert len(holidays) >= 18 and {h.kind for h in holidays} == {"regular", "special"}


@pytest.mark.parametrize("offset", range(7))
def test_late_shift_exists_on_any_weekday_and_skips_rest_and_leave_days(
    ferinos: None, session: Session, offset: int
) -> None:
    import datetime as dt

    from mia.core.models import Contract, Leave, Timesheet, Visit
    from mia.templates.retail import seed

    today = dt.date(2026, 10, 19) + dt.timedelta(days=offset)  # each weekday once
    seed.seed(session, today)
    contracts = {c.person_id: c for c in session.exec(select(Contract)).all()}
    off = {
        (x.person_id, x.start_date + dt.timedelta(days=n))
        for x in session.exec(select(Leave)).all()
        for n in range((x.end_date - x.start_date).days + 1)
    }
    sheets = session.exec(select(Timesheet)).all()
    for t in sheets:
        assert t.date.weekday() != contracts[t.person_id].rest_day
        assert (t.person_id, t.date) not in off
    assert off  # the leave rows exist
    late = [
        t
        for t in sheets
        if (t.end - t.start).total_seconds() / 60 > 600  # 13:00 to 23:30
    ]
    assert len(late) == 1 and late[0].minutes == 630
    night = (late[0].end - late[0].end.replace(hour=22, minute=0)).total_seconds() / 60
    assert night == 90  # the 22:00 to 06:00 window
    visits = session.exec(select(Visit).where(Visit.status == "completed")).all()
    assert len(visits) == len(sheets)  # 21 Oct 2026: the planned shifts from today are not


def test_hr_events_hide_rates_amounts_and_leave_reasons(ferinos: None, session: Session) -> None:
    from mia.core.models import Event
    from mia.templates.retail import seed

    seed.seed(session)
    hidden = {
        "contracts": {"daily_rate"},
        "payslips": {"lines", "gross", "deductions", "net"},
        "leave": {"kind", "reason"},
    }
    events = session.exec(select(Event)).all()
    for table, fields in hidden.items():
        rows = [e for e in events if e.action == f"{table}.created"]
        assert rows
        for e in rows:
            assert e.after is not None
            assert all(e.after[f] == "<redacted>" for f in fields)


def test_the_box_holds_four_classics_and_two_items_have_a_cost(
    ferinos: None, session: Session
) -> None:
    from mia.templates.retail import seed
    from mia.templates.retail.models import RetailItem

    seed.seed(session)
    rows = {i.name: i for i in session.exec(select(RetailItem)).all()}
    assert rows["Box of 4"].components == [rows["Classic"].id] * 4
    assert {n for n, i in rows.items() if i.components} == {"Box of 4"}
    costs = {n: i.cost for n, i in rows.items() if i.cost is not None}
    assert costs.keys() == {"Classic", "Special"}
    assert all(0 < cost < rows[n].price for n, cost in costs.items())
