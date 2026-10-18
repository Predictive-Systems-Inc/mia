"""Demo data for Ferino's Bibingka, a Philippine chain of kiosks.

Two branches (a mall kiosk and a street stall), eight items with short codes, opening hours,
an owner, two supervisors, three clerks, 14 days of sales counts and a month target per branch.
All rows are written through mia.core.store, so seeding appears in the events log.
"""

import datetime as dt
import random
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.agents.inventory_manager.models import StockEvent, SupplierOrder
from mia.agents.sales_supervisor.models import SalesCount, SalesTarget
from mia.core import events, store
from mia.core.models import Actor, Branch, Organisation
from mia.core.people import add_person
from mia.templates.retail.models import RetailBranchHours, RetailIngredient, RetailItem

CURRENCY = "PHP"
ITEMS: list[tuple[str, list[str], int]] = [
    ("Special", ["sp", "special"], 4500),
    ("Classic", ["cl", "classic"], 4000),
    ("Ube", ["ube", "ub"], 4500),
    ("Salted egg", ["se", "salted"], 5000),
    ("Cheese overload", ["co", "overload"], 5500),
    ("Puto bumbong", ["pb"], 3500),
    ("Box of 4", ["b4", "box"], 16000),
    ("Kape", ["kape", "coffee"], 2500),
]
# name, codes, unit, reorder point, supplier, pack price (centavos)
INGREDIENTS: list[tuple[str, list[str], str, int, str | None, int | None]] = [
    ("Rice flour", ["rf", "flour"], "kg", 10, "Metro Supply", 6500),
    ("Eggs", ["egg", "eggs"], "tray", 5, "Aling Nena", 25000),
    ("Coconut", ["coco", "niyog"], "pcs", 20, "Aling Nena", 3500),
    ("Sugar", ["sugar", "asukal"], "kg", 5, "Metro Supply", 7500),
    ("Cheese", ["cheese", "keso"], "kg", 2, "Metro Supply", 38000),
    ("Salted egg", ["itlog", "se"], "pcs", 30, "Metro Supply", 1500),
    ("Banana leaves", ["bl", "dahon"], "pack", 3, "Metro Supply", 5000),
    ("LPG", ["lpg", "gas"], "tank", 1, "Metro Supply", 95000),
]
# branch name, opens, closes, month target (centavos)
BRANCHES = [("Mall kiosk", "09:00", "21:00", 480000), ("Street stall", "06:00", "19:00", 300000)]
# name, role, branch index, language
PEOPLE = [
    ("Rosa", "owner", 0, "fil"),
    ("Marites", "supervisor", 0, "fil"),
    ("Jun", "supervisor", 1, "ceb"),
    ("Ana", "clerk", 0, "fil"),
    ("Liza", "clerk", 0, "fil"),
    ("Pao", "clerk", 1, "ceb"),
]


def is_seeded(session: Session) -> bool:
    """True when the database already holds an organisation."""
    return session.exec(select(Organisation).limit(1)).first() is not None


def seed(session: Session, today: dt.date | None = None) -> Branch:
    """Load the demo data and return the first branch. Refuses to run on a used database."""
    if is_seeded(session):
        raise RuntimeError("database already has data; seed runs only on an empty database")
    org = Organisation(name="Ferino's Bibingka (demo)", country="PH", default_language="fil")
    branches = [
        Branch(organisation_id=org.id, name=name, timezone="Asia/Manila") for name, *_ in BRANCHES
    ]
    first = branches[0]
    actor = Actor.system(first.id)
    store.insert(session, org, actor)
    for branch in branches:
        store.insert(session, branch, Actor.system(branch.id))
    today = today or dt.datetime.now(ZoneInfo(first.timezone)).date()

    items = []
    for order, (name, codes, price) in enumerate(ITEMS):
        item = RetailItem(
            name=name, short_codes=codes, price=price, currency=CURRENCY, sort_order=order
        )
        store.insert(session, item, actor)
        events.emit(
            session, "retail.item_priced", item, None, {"price": price, "currency": CURRENCY}, actor
        )
        items.append(item)

    ingredients = {}
    for name, codes, unit, reorder, supplier, pack_price in INGREDIENTS:
        ingredient = RetailIngredient(
            name=name,
            short_codes=codes,
            unit=unit,
            reorder_point=reorder,
            supplier=supplier,
            pack_price=pack_price,
            currency=CURRENCY,
        )
        store.insert(session, ingredient, actor)
        ingredients[name] = ingredient

    staff = {}
    for name, role, where, lang in PEOPLE:
        branch_id = branches[where].id
        staff[name] = add_person(
            session,
            Actor.system(branch_id),
            branch_id=branch_id,
            name=name,
            roles=[role],
            language=lang,
        )
    clerks = {0: staff["Ana"], 1: staff["Pao"]}
    rng = random.Random(7)
    for index, (branch, (_, opens, closes, target)) in enumerate(
        zip(branches, BRANCHES, strict=True)
    ):
        branch_actor = Actor.system(branch.id)
        for weekday in range(7):
            hours = RetailBranchHours(
                branch_id=branch.id, weekday=weekday, opens=opens, closes=closes
            )
            store.insert(session, hours, branch_actor)
        for offset in range(1, 15):
            day = today - dt.timedelta(days=offset)
            boost = 1.3 if day.weekday() >= 5 else 1.0
            reported_at = dt.datetime.combine(day, dt.time(20, 0), ZoneInfo(branch.timezone))
            for item in items:
                quantity = round(rng.randint(3, 12) * boost)
                count = SalesCount(
                    branch_id=branch.id,
                    item_id=item.id,
                    quantity=quantity,
                    amount=quantity * item.price,
                    currency=CURRENCY,
                    reported_at=reported_at,
                    reported_by=clerks[index].id,
                    business_date=day,
                )
                store.insert(session, count, branch_actor)
        _seed_stock(session, branch, today, items, ingredients, clerks[index].id)
        if index == 0:
            _seed_order(session, branch, today, ingredients["Eggs"], staff["Marites"].id)
        target_row = SalesTarget(
            branch_id=branch.id,
            period="month",
            starts_on=today.replace(day=1),
            amount=target,
            currency=CURRENCY,
            set_by=staff["Rosa"].id,
        )
        store.insert(session, target_row, branch_actor)
    return first


def _stock(
    session: Session,
    branch: Branch,
    kind: str,
    day: dt.date,
    at: dt.time,
    by: str,
    **fields: object,
) -> StockEvent:
    """Insert one stock event for a local day and time, logged as stock.<kind>."""
    row = StockEvent(
        branch_id=branch.id,
        kind=kind,
        at=dt.datetime.combine(day, at, ZoneInfo(branch.timezone)),
        reported_by=by,
        business_date=day,
        **fields,  # type: ignore[arg-type]
    )
    return store.insert(session, row, Actor.system(branch.id), action=f"stock.{kind}")


def _seed_stock(
    session: Session,
    branch: Branch,
    today: dt.date,
    items: list[RetailItem],
    ingredients: dict[str, RetailIngredient],
    by: str,
) -> None:
    """Add a fortnight's stock events: Special sold out on two Saturdays, Classic leftovers on
    two weekdays, one waste row, counts of LPG (under its reorder point) and eggs, and a low
    banana leaves."""
    days = [today - dt.timedelta(days=n) for n in range(1, 15)]
    saturdays = [d for d in days if d.weekday() == 5][:2]
    weekdays = [d for d in days if d.weekday() < 5][:2]
    special, classic, ube = items[0], items[1], items[2]
    for day in saturdays:
        _stock(session, branch, "sold_out", day, dt.time(14, 0), by, item_id=special.id)
    for day in weekdays:
        _stock(
            session, branch, "leftover", day, dt.time(20, 0), by,
            item_id=classic.id, quantity=3, unit="tray",
        )  # fmt: skip
    _stock(
        session, branch, "waste", days[2], dt.time(20, 0), by,
        item_id=ube.id, quantity=8, reason="too_dry",
    )  # fmt: skip
    lpg = ingredients["LPG"]
    _stock(
        session, branch, "count", today, dt.time(9, 0), by,
        ingredient_id=lpg.id, quantity=0, unit=lpg.unit,
    )  # fmt: skip
    eggs = ingredients["Eggs"]
    _stock(
        session, branch, "count", today, dt.time(9, 5), by,
        ingredient_id=eggs.id, quantity=6, unit=eggs.unit,
    )  # fmt: skip
    _stock(
        session,
        branch,
        "low",
        days[0],
        dt.time(18, 0),
        by,
        ingredient_id=ingredients["Banana leaves"].id,
    )


def _seed_order(
    session: Session,
    branch: Branch,
    today: dt.date,
    eggs: RetailIngredient,
    by: str,
) -> None:
    """Add one approved egg order from three days ago and its received stock event. The seed
    does not go through approvals, so approval_id stays empty."""
    day = today - dt.timedelta(days=3)
    price = eggs.pack_price or 0
    order = SupplierOrder(
        branch_id=branch.id,
        supplier="Aling Nena",
        lines=[{"ingredient_id": eggs.id, "quantity": 10, "unit": "tray", "unit_price": price}],
        currency=CURRENCY,
        total=10 * price,
        status="approved",
        approval_id=None,
        requested_by=by,
        business_date=day,
    )
    store.insert(session, order, Actor.system(branch.id))
    _stock(
        session, branch, "received", day, dt.time(10, 0), by,
        ingredient_id=eggs.id, quantity=10, unit="tray", order_id=order.id,
    )  # fmt: skip
