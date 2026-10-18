"""Demo data for Ferino's Bibingka, a Philippine chain of kiosks.

Two branches (a mall kiosk and a street stall), eight items with short codes, opening hours,
an owner, two supervisors, three clerks, 14 days of sales counts and a month target per branch.
All rows are written through mia.core.store, so seeding appears in the events log.
"""

import datetime as dt
import random
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.agents.sales_supervisor.models import SalesCount, SalesTarget
from mia.core import events, store
from mia.core.models import Actor, Branch, Organisation
from mia.core.people import add_person
from mia.templates.retail.models import RetailBranchHours, RetailItem

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
