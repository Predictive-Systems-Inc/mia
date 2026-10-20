"""Demo data for Ferino's Bibingka, a Philippine chain of kiosks.

Two branches (a mall kiosk and a street stall), eight items with short codes, opening hours,
an owner, two supervisors, three clerks, 14 days of sales counts and a month target per branch,
HR data, two customer service customers with their orders and a complaint, and the branch
manager's tips, quotes and pricing strategies. All rows are written through mia.core.store, so seeding appears in the events log.
"""

import datetime as dt
import random
from dataclasses import asdict
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.agents.branch_manager import tips as bm_tips
from mia.agents.branch_manager.models import Strategy, Tip
from mia.agents.customer_service.models import Complaint, Customer, Order
from mia.agents.hr_officer import calc, calendar
from mia.agents.hr_officer.models import Contract, Leave, Payslip
from mia.agents.inventory_manager.models import SupplierOrder
from mia.core import events, orgconfig, store
from mia.core.models import (
    Actor,
    Branch,
    Client,
    Job,
    Location,
    Organisation,
    Person,
    SalesCount,
    SalesTarget,
    StockEvent,
    Timesheet,
    Visit,
)
from mia.core.people import add_person
from mia.templates.retail.models import RetailBranchHours, RetailIngredient, RetailItem

CURRENCY = "PHP"
ITEMS: list[tuple[str, list[str], int]] = [
    ("Special", ["sp", "special"], 4500),
    ("Classic", ["cl", "classic", "bibingka"], 4000),
    ("Ube", ["ube", "ub"], 4500),
    ("Salted egg", ["se", "salted"], 5000),
    ("Cheese overload", ["co", "overload"], 5500),
    ("Puto bumbong", ["pb"], 3500),
    ("Box of 4", ["b4", "box"], 16000),
    ("Kape", ["kape", "coffee"], 2500),
]
# Plausible unit costs (centavos) for two items only, made up for the demo until the owner gives
# hers (Q79); the other items have no cost.
COSTS = {"Classic": 2400, "Special": 2800}
BUNDLES = {"Box of 4": ["Classic"] * 4}  # a bundle's pieces by item name
# name, codes, unit, reorder point, supplier, pack price (centavos). No item and ingredient
# share a name or a code, and a code is one word (menu_tokens does not split codes).
INGREDIENTS: list[tuple[str, list[str], str, int, str | None, int | None]] = [
    ("Rice flour", ["rf", "flour"], "kg", 10, "Metro Supply", 6500),
    ("Eggs", ["egg", "eggs", "itlog"], "tray", 5, "Aling Nena", 25000),
    ("Coconut", ["coco", "niyog"], "pcs", 20, "Aling Nena", 3500),
    ("Sugar", ["sugar", "asukal"], "kg", 5, "Metro Supply", 7500),
    ("Cheese", ["cheese", "keso"], "kg", 2, "Metro Supply", 38000),
    ("Salted duck eggs", ["maalat", "pula"], "pcs", 30, "Metro Supply", 1500),
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
# name, employment type, daily rate (centavos), start date, position. The owner has no contract.
CONTRACTS: list[tuple[str, str, int, dt.date, str]] = [
    ("Marites", "regular", 80000, dt.date(2025, 2, 3), "Supervisor"),
    ("Jun", "regular", 80000, dt.date(2025, 3, 10), "Supervisor"),
    ("Ana", "regular", 61000, dt.date(2025, 4, 7), "Clerk"),
    ("Liza", "probationary", 61000, dt.date(2026, 3, 2), "Clerk"),
    ("Pao", "regular", 61000, dt.date(2025, 6, 2), "Clerk"),
]
REST_DAYS = (0, 1)  # Monday at the mall, Tuesday at the stall (by branch index)
# clerk, branch index, shift start, shift end (local); the last one runs to 23:30 (night minutes)
SHIFTS = {"Ana": (0, "09:00", "17:00"), "Liza": (0, "13:00", "21:00"), "Pao": (1, "06:00", "15:00")}
LATE_SHIFT = (
    "Liza",
    "13:00",
    "23:30",
)  # the clerk's most recent working day runs late (night minutes)


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

    items: list[RetailItem] = []
    for order, (name, codes, price) in enumerate(ITEMS):
        by_name = {i.name: i.id for i in items}
        item = RetailItem(
            name=name,
            short_codes=codes,
            price=price,
            currency=CURRENCY,
            sort_order=order,
            components=[by_name[piece] for piece in BUNDLES.get(name, [])],
            cost=COSTS.get(name),
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
    _seed_hr(session, branches, staff, today)
    _seed_branch_manager(session, items, actor)
    _seed_customers(session, first, items[1], staff["Marites"].id, today)
    return first


def _seed_branch_manager(session: Session, items: list[RetailItem], actor: Actor) -> None:
    """The branch manager's curated rows: tips and quotes in Filipino and English, and the
    pricing strategies, each with its source (mia/agents/branch_manager/tips.py)."""
    ids = {i.name: i.id for i in items}
    for name, fil, en, source in bm_tips.TIPS:
        for language, text in (("fil", fil), ("en", en)):
            tip = Tip(
                language=language,
                kind="tip",
                item_id=ids[name] if name else None,
                text=text,
                source=source,
            )
            store.insert(session, tip, actor)
    for fil, en, source in bm_tips.QUOTES:
        for language, text in (("fil", fil), ("en", en)):
            store.insert(
                session, Tip(language=language, kind="quote", text=text, source=source), actor
            )
    for name_key, kind, params, source in bm_tips.STRATEGIES:
        row = Strategy(name_key=name_key, kind=kind, params=params, source=source)
        store.insert(session, row, actor)


# name, language, channel address (made-up numbers)
CUSTOMERS = [("Mila Reyes", "fil", "+639170000101"), ("Mark Lim", "en", "+639170000102")]


def _seed_customers(
    session: Session, branch: Branch, classic: RetailItem, decider: str, today: dt.date
) -> None:
    """Two WhatsApp customers of the first branch: Mila (fil, last message three days ago, so
    her 24-hour window is closed) with a confirmed pickup of 10 Classic today at 15:00, and Mark
    (en, last message yesterday) with a picked-up order of 2 Classic yesterday and an open
    complaint about it. The seed does not go through approvals, so approval_id stays empty."""
    zone, actor = ZoneInfo(branch.timezone), Actor.system(branch.id)

    def at(days: int, hour: int) -> dt.datetime:
        return dt.datetime.combine(today + dt.timedelta(days=days), dt.time(hour), zone)

    def customer(index: int, last: int) -> Customer:
        name, lang, address = CUSTOMERS[index]
        row = Customer(
            branch_id=branch.id,
            channel="whatsapp",
            address=address,
            name=name,
            language=lang,
            first_seen_at=at(-10, 10),
            last_inbound_at=at(last, 10),
        )
        return store.insert(session, row, actor)

    def order(who: Customer, quantity: int, pickup: dt.datetime, status: str) -> Order:
        line = {"item_id": classic.id, "quantity": quantity, "unit_price": classic.price}
        row = Order(
            branch_id=branch.id,
            customer_id=who.id,
            lines=[line],
            total=quantity * classic.price,
            currency=CURRENCY,
            fulfilment="pickup",
            pickup_at=pickup,
            status=status,
            decided_by=decider,
        )
        return store.insert(session, row, actor)

    mila, mark = customer(0, -3), customer(1, -1)
    order(mila, 10, at(0, 15), "confirmed")
    picked = order(mark, 2, at(-1, 11), "picked_up")
    complaint = Complaint(
        branch_id=branch.id,
        customer_id=mark.id,
        text="The bibingka was already cold when I picked it up.",
        order_id=picked.id,
    )
    store.insert(session, complaint, actor)


def _cutoffs(today: dt.date, count: int) -> list[tuple[dt.date, dt.date]]:
    """The last `count` semi-monthly cutoffs (1st to 15th, 16th to month end) that ended
    before today, oldest first."""
    end = today.replace(day=15) if today.day > 15 else today.replace(day=1) - dt.timedelta(days=1)
    out = []
    for _ in range(count):
        start = end.replace(day=1) if end.day == 15 else end.replace(day=16)
        out.append((start, end))
        end = start - dt.timedelta(days=1)
    return out[::-1]


def _leave_plan(today: dt.date) -> list[tuple[str, str, dt.date, dt.date, int, str]]:
    """The two approved leave rows: name, kind, first day, last day, days, reason."""
    day = dt.timedelta
    return [
        ("Liza", "vacation", today - day(days=9), today - day(days=8), 2, "Family trip"),
        ("Pao", "sick", today - day(days=5), today - day(days=5), 1, "Fever"),
    ]


def _seed_hr(
    session: Session, branches: list[Branch], staff: dict[str, Person], today: dt.date
) -> None:
    """Seed-only HR data: contracts, a Counter shift per branch with completed visits and
    approved timesheets from the start of the last two closed cutoffs to yesterday (inserted
    directly with a note; the real flow is the shift supervisor's draft and approval), two
    approved leave rows and an issued payslip per clerk for each of those cutoffs, computed by
    calc.cutoff_pay and dated calendar.payday as the tick would issue them."""
    owner = staff["Rosa"].id
    where = {name: index for name, _, index, _ in PEOPLE}
    cutoffs = _cutoffs(today, 2)
    back = (today - cutoffs[0][0]).days
    contracts: dict[str, Contract] = {}
    for name, kind, rate, start, position in CONTRACTS:
        branch = branches[where[name]]
        contract = Contract(
            branch_id=branch.id,
            person_id=staff[name].id,
            employment_type=kind,
            daily_rate=rate,
            currency=CURRENCY,
            rest_day=REST_DAYS[where[name]],
            start_date=start,
            position=position,
            set_by=owner,
        )
        contracts[name] = store.insert(session, contract, Actor.system(branch.id))
    leave_plan = _leave_plan(today)
    for index, branch in enumerate(branches):
        actor = Actor.system(branch.id)
        client = store.insert(session, Client(branch_id=branch.id, name=BRANCHES[index][0]), actor)
        loc = Location(
            branch_id=branch.id, client_id=client.id, name=BRANCHES[index][0], address=""
        )
        loc = store.insert(session, loc, actor)
        job = Job(
            branch_id=branch.id,
            location_id=loc.id,
            name="Counter shift",
            recurrence="FREQ=DAILY",
            start_time=BRANCHES[index][1],
            duration_minutes=480,
        )
        job = store.insert(session, job, actor)
        for name, (where_index, begin, finish) in SHIFTS.items():
            if where_index != index:
                continue
            off = {
                start + dt.timedelta(days=n)
                for who, _, start, end, _, _ in leave_plan
                if who == name
                for n in range((end - start).days + 1)
            }
            _seed_shifts(
                session, branch, index, job, staff[name], owner, today, (begin, finish), off, back
            )
    for name, kind, start, end, days, reason in leave_plan:
        leave = Leave(
            branch_id=branches[where[name]].id,
            person_id=staff[name].id,
            kind=kind,
            start_date=start,
            end_date=end,
            days=days,
            status="approved",
            reason=reason,
        )
        store.insert(session, leave, Actor.system(leave.branch_id))
    holidays, lag = calc.holidays(), orgconfig.load().payroll.pay_lag_days
    for name in SHIFTS:
        branch = branches[where[name]]
        zone = ZoneInfo(branch.timezone)
        for start, end in cutoffs:
            pay = calc.cutoff_pay(session, contracts[name], start, end, zone, holidays)
            if pay is None:
                continue
            pay_date = calendar.payday(end, lag, holidays)
            slip = Payslip(
                branch_id=branch.id,
                person_id=staff[name].id,
                cutoff_start=start,
                cutoff_end=end,
                pay_date=pay_date,
                lines=[asdict(line) for line in pay.lines],
                gross=pay.gross,
                deductions=[{"kind": d.kind, "amount": d.amount} for d in pay.deductions],
                net=pay.net,
                currency=CURRENCY,
                issued_at=dt.datetime.combine(pay_date, dt.time(9, 0), zone),
            )
            store.insert(session, slip, Actor.system(branch.id))


def _seed_shifts(
    session: Session,
    branch: Branch,
    index: int,
    job: Job,
    clerk: Person,
    approver: str,
    today: dt.date,
    hours: tuple[str, str],
    off: set[dt.date],
    back: int,
) -> None:
    """One completed visit and one approved timesheet per working day of the last `back` days
    for a clerk, skipping the contract's rest day and the days in `off` (approved leave). The late
    clerk's most recent working day runs to the late end time."""
    begin, finish = hours
    zone = ZoneInfo(branch.timezone)
    rest = REST_DAYS[index]
    actor = Actor.system(branch.id)
    late_pending = clerk.name == LATE_SHIFT[0]
    for offset in range(1, back + 1):
        day = today - dt.timedelta(days=offset)
        if day.weekday() == rest or day in off:
            continue
        end_text = LATE_SHIFT[2] if late_pending else finish
        late_pending = False
        start = dt.datetime.combine(day, dt.time.fromisoformat(begin), zone)
        end = dt.datetime.combine(day, dt.time.fromisoformat(end_text), zone)
        visit = Visit(
            branch_id=branch.id,
            job_id=job.id,
            location_id=job.location_id,
            date=day,
            assigned_person_ids=[clerk.id],
            planned_start=start,
            planned_end=dt.datetime.combine(day, dt.time.fromisoformat(finish), zone),
            actual_start=start,
            actual_end=end,
            status="completed",
        )
        store.insert(session, visit, actor)
        sheet = Timesheet(
            branch_id=branch.id,
            visit_id=visit.id,
            person_id=clerk.id,
            date=day,
            start=start,
            end=end,
            minutes=int((end - start).total_seconds() // 60),
            status="approved",
            entered_by=clerk.id,
            note="seed-only: inserted approved, not through the draft flow",
            approved_by=approver,
            approved_at=end,
        )
        store.insert(session, sheet, actor)


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
    """Add one egg order from three days ago and its received stock event, so the order is
    received (no seeded order is open for a real delivery to close). The seed does not go
    through approvals, so approval_id stays empty."""
    day = today - dt.timedelta(days=3)
    price = eggs.pack_price or 0
    line = {"ingredient_id": eggs.id, "quantity": 10, "unit": "tray", "unit_price": price}
    order = SupplierOrder(
        branch_id=branch.id,
        supplier="Aling Nena",
        lines=[line | {"received": 10}],
        currency=CURRENCY,
        total=10 * price,
        status="received",
        approval_id=None,
        requested_by=by,
        business_date=day,
    )
    store.insert(session, order, Actor.system(branch.id))
    _stock(
        session, branch, "received", day, dt.time(10, 0), by,
        ingredient_id=eggs.id, quantity=10, unit="tray", order_id=order.id,
    )  # fmt: skip
