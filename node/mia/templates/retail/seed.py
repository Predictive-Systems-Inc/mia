"""Demo data for Ferino's Bibingka, a Philippine chain of kiosks.

Two branches (a mall kiosk and a street stall), eight items with short codes, opening hours, an
owner, two supervisors, three clerks, a commissary branch (no hours) with its head and driver, the
production planner's recipes and yesterday's production day (a confirmed plan, its batches, one
dispatch per kiosk, one matched and one short), 14 days of sales counts and a month target per
branch, HR data, a shift Job per clerk with availability, hour limits and shifts planned from today
(the stall closed on the next holiday), two customer service customers with their orders and a
complaint, and the branch manager's tips, quotes and pricing strategies. All rows are written
through mia.core.store, so seeding appears in the events log.
"""

import datetime as dt
import random
from dataclasses import asdict
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.bookkeeper import calc as bk_calc
from mia.agents.bookkeeper import tools as bk_tools
from mia.agents.bookkeeper.models import CashCount, Deposit, Expense, Payout, Settlement
from mia.agents.branch_manager import experiments
from mia.agents.branch_manager import tips as bm_tips
from mia.agents.branch_manager.models import Experiment, Strategy, Tip
from mia.agents.customer_service.models import Complaint, Customer
from mia.agents.hr_officer import calc, calendar
from mia.agents.production_planner import MANIFEST
from mia.agents.production_planner import tools as pp_tools
from mia.agents.production_planner.models import Recipe
from mia.agents.shift_supervisor import roster
from mia.core import events, orgconfig, scheduling, store
from mia.core.models import (
    Actor,
    Availability,
    Branch,
    Client,
    Contract,
    CustomerOrder,
    Incident,
    Job,
    Leave,
    Location,
    Organisation,
    Payslip,
    Person,
    SalesCount,
    SalesTarget,
    StockEvent,
    SupplierOrder,
    Timesheet,
    Visit,
    WorkLimit,
)
from mia.core.people import add_person
from mia.core.rbac import get_rbac
from mia.templates.retail import items as retail_items
from mia.templates.retail.models import (
    RetailBranchHours,
    RetailClosure,
    RetailIngredient,
    RetailItem,
)

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
# The kitchen that bakes for both kiosks: a third branch without hours rows (it sells nothing,
# retail_hours.is_shop), named in the production planner's settings (Q92).
COMMISSARY = "Commissary"
# name, role, branch index (2 is the commissary), language
PEOPLE = [
    ("Rosa", "owner", 0, "fil"),
    ("Marites", "supervisor", 0, "fil"),
    ("Jun", "supervisor", 1, "ceb"),
    ("Ana", "clerk", 0, "fil"),
    ("Liza", "clerk", 0, "fil"),
    ("Pao", "clerk", 1, "ceb"),
    ("Nonoy", "supervisor", 2, "fil"),
    ("Berto", "staff", 2, "fil"),
]
SKILLS = {"Berto": ["driver"]}  # the commissary's driver (Q94)
# The made-up recipes (the owner corrects them): pieces per batch, 45 oven minutes each, and
# one batch's lines in thousandths of each ingredient's unit. Classic's base, scaled to 36
# pieces for the 36-piece items, plus the item's own ingredient. Kape and Box of 4 have none.
OVEN_MINUTES = 45
BASE_RECIPE = {
    "Rice flour": 2000,
    "Eggs": 1000,
    "Coconut": 6000,
    "Sugar": 1000,
    "Banana leaves": 1000,
}
RECIPES: dict[str, tuple[int, dict[str, int]]] = {
    "Classic": (48, {}),
    "Special": (36, {}),
    "Ube": (36, {}),
    "Salted egg": (36, {"Salted duck eggs": 12000}),
    "Cheese overload": (36, {"Cheese": 500}),
    "Puto bumbong": (48, {}),
}
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
# each clerk's working days (scheduling.WEEKDAYS codes): every day but the contract's rest day
SHIFT_DAYS = {"Ana": "TU,WE,TH,FR,SA,SU", "Liza": "TU,WE,TH,FR,SA,SU", "Pao": "MO,WE,TH,FR,SA,SU"}
DAILY_LIMIT, WEEKLY_LIMIT = 600, 3240  # minutes (Q106 placeholders: six 9-hour shifts)
# The Mall kiosk's seeded experiments: item, strategy, days before today it started, status.
# experiments.propose reads the seeded data before the start: the running one the counts and the
# stock rows (Special sells out early most days at the kiosk), the done one, which ended last
# month before the counts, its own seed-only daily totals (done_units).
SEEDED_EXPERIMENTS: list[tuple[str, str, int, str]] = [
    ("Classic", "bm.strategy.charm", 49, "done"),
    ("Special", "bm.strategy.increase", 4, "running"),
]
KIOSK_SOLD_OUT = range(9, 15)  # days before today the kiosk's Special also sold out at 14:00
LATE_SHIFT = (
    "Liza",
    "13:00",
    "23:30",
)  # the clerk's most recent working day runs late (night minutes)


def _tender(n: int) -> str:
    """The seeded tender of the n-th count (deterministic): one in ten maya, every seventh grab,
    every fourth gcash, else cash."""
    if n % 10 == 0:
        return "maya"
    if n % 7 == 0:
        return "grab"
    return "gcash" if n % 4 == 0 else "cash"


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
    # ponytail: kept out of `branches`, which every kiosk helper below loops over
    commissary = Branch(organisation_id=org.id, name=COMMISSARY, timezone="Asia/Manila")
    store.insert(session, commissary, Actor.system(commissary.id))
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
        branch_id = [*branches, commissary][where].id
        staff[name] = add_person(
            session,
            Actor.system(branch_id),
            branch_id=branch_id,
            name=name,
            roles=[role],
            language=lang,
            skills=SKILLS.get(name),
        )
    clerks = {0: staff["Ana"], 1: staff["Pao"]}
    strategies = _seed_strategies(session, actor)
    planned: list[Planned] = []
    kiosk_daily: dict[str, dict[dt.date, experiments.Day]] = {}
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
        _seed_stock(session, branch, today, items, ingredients, clerks[index].id, index == 0)
        units: dict[dt.date, dict[str, int]] = {}
        for offset in range(1, 15):
            day = today - dt.timedelta(days=offset)
            boost = 1.3 if day.weekday() >= 5 else 1.0
            units[day] = {item.id: round(rng.randint(3, 12) * boost) for item in items}
        if index == 0:  # the price rows go in before the counts, so the counts are priced by them
            planned = _plan_experiments(session, branch, items, strategies, today, units)
        for day, sold in units.items():
            reported_at = dt.datetime.combine(day, dt.time(20, 0), ZoneInfo(branch.timezone))
            for item_index, item in enumerate(items):
                quantity = sold[item.id]
                amount = quantity * retail_items.price_on(session, item, branch.id, day)
                if index == 0:
                    kiosk_daily.setdefault(item.id, {})[day] = (quantity, amount)
                count = SalesCount(
                    branch_id=branch.id,
                    item_id=item.id,
                    quantity=quantity,
                    amount=amount,
                    currency=CURRENCY,
                    reported_at=reported_at,
                    reported_by=clerks[index].id,
                    business_date=day,
                    tender=_tender((today - day).days * len(items) + item_index),
                )
                store.insert(session, count, branch_actor)
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
    _seed_shift_supervisor(session, branches, staff, today)
    _seed_bookkeeper(session, branches, staff, today)
    _seed_branch_manager(session, items, actor)
    _seed_experiments(session, first, planned, kiosk_daily, staff)
    _seed_customers(session, first, items[1], staff["Marites"].id, today)
    _seed_recipes(session, commissary, items, ingredients, staff["Rosa"].id)
    _seed_production(session, commissary, branches, items, staff, today)
    return first


def _seed_production(
    session: Session,
    commissary: Branch,
    kiosks: list[Branch],
    items: list[RetailItem],
    staff: dict[str, Person],
    today: dt.date,
) -> None:
    """Yesterday's production day through the planner's own helpers: the draft (one same
    weekday in the counts, so every forecast is None), Nonoy's batches (Classic 3, every other
    recipe item 1) and his confirmation, every batch at full yield but Classic batch 3 (good 40,
    waste 8, burnt), two to an oven round from the start of production, the dispatches packed,
    the Mall kiosk's receipt equal to its lines and the Street stall's one Classic short by 4,
    each matched an hour after the receipt. Nothing when the planner is off for the org."""
    s = orgconfig.load().production_planner
    if s.commissary != commissary.name:
        return
    roles = MANIFEST.roles  # the CLI seed runs without the app's registry.load_roles
    get_rbac().load_agent_role(roles.agent_role, roles.grants, roles.denies)
    day = today - dt.timedelta(days=1)
    zone = ZoneInfo(commissary.timezone)
    head = staff["Nonoy"]
    by_head = Actor.person(head).as_agent(roles.agent_role)
    plan = pp_tools.draft_plan(session, commissary, day)
    classic = items[1].id
    for line in list(plan.lines):
        batches = 3 if line["item_id"] == classic else 1
        plan = pp_tools.set_batches(session, plan, line["item_id"], batches, by_head)
    plan = pp_tools.confirm(session, plan, head, by_head)
    start = dt.datetime.combine(day, s.hours.start, zone)
    n = 0
    for line in plan.lines:
        per = line["pieces"] // line["batches"]
        for batch_no in range(1, line["batches"] + 1):
            short = line["item_id"] == classic and batch_no == 3
            args = pp_tools.BatchInput(
                item_id=line["item_id"],
                batch_no=batch_no,
                good=40 if short else per,
                waste=per - 40 if short else 0,
                reason="burnt" if short else None,
            )
            at = start + dt.timedelta(minutes=OVEN_MINUTES * (n // s.ovens + 1))
            pp_tools.save_batch(session, plan, args, head, by_head, at=at)
            n += 1
    agent = pp_tools.agent_actor(commissary.id)
    receivers = {kiosks[0].id: staff["Marites"].id, kiosks[1].id: staff["Jun"].id}
    received_at = dt.datetime.combine(day, dt.time(9, 0), zone)
    for dispatch in pp_tools.pack(session, plan, agent):
        for x in dispatch.lines:
            gap = 4 if dispatch.branch_id == kiosks[1].id and x["item_id"] == classic else 0
            row = StockEvent(
                branch_id=dispatch.branch_id,
                kind="received",
                item_id=x["item_id"],
                quantity=x["quantity"] - gap,
                unit="pcs",
                at=received_at,
                reported_by=receivers[dispatch.branch_id],
                business_date=day,
            )
            store.insert(session, row, Actor.system(dispatch.branch_id))
        now = received_at + dt.timedelta(hours=1)
        pp_tools.match(session, dispatch, now, pp_tools.agent_actor(dispatch.branch_id))


def _seed_recipes(
    session: Session,
    commissary: Branch,
    items: list[RetailItem],
    ingredients: dict[str, RetailIngredient],
    owner: str,
) -> None:
    """The production planner's recipes at the commissary (RECIPES): the base lines scaled to
    the batch yield (exact: 48 and 36 pieces), plus the item's own ingredient, set by the owner."""
    by_name = {item.name: item for item in items}
    for name, (batch_yield, extra) in RECIPES.items():
        lines = {k: v * batch_yield // 48 for k, v in BASE_RECIPE.items()} | extra
        recipe = Recipe(
            branch_id=commissary.id,
            item_id=by_name[name].id,
            batch_yield=batch_yield,
            oven_minutes=OVEN_MINUTES,
            lines=[
                {"ingredient_id": ingredients[k].id, "quantity_milli": v} for k, v in lines.items()
            ],
            set_by=owner,
        )
        store.insert(session, recipe, Actor.system(commissary.id))


def _seed_branch_manager(session: Session, items: list[RetailItem], actor: Actor) -> None:
    """The branch manager's curated rows: tips and quotes in Filipino and English, each with its
    source (mia/agents/branch_manager/tips.py)."""
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


def _seed_strategies(session: Session, actor: Actor) -> list[Strategy]:
    """The pricing strategies with their sources (mia/agents/branch_manager/tips.py)."""
    return [
        store.insert(
            session,
            Strategy(name_key=k, kind=kind, params=params, source=src, description=text),
            actor,
        )
        for k, kind, params, src, text in bm_tips.STRATEGIES
    ]


Planned = tuple[RetailItem, experiments.Proposal, dt.date, dt.date, str]


def done_units(starts_on: dt.date, days: int) -> tuple[dict[dt.date, int], dict[dt.date, int]]:
    """The done experiment's seed-only daily units (no counts exist that far back): the 28 days
    before starts_on and its `days` days, from random.Random(11) so the counts' sequence is
    unchanged. Pure; the seed test recomputes the row from it."""
    rng = random.Random(11)
    before = {starts_on - dt.timedelta(days=k): rng.randint(8, 13) for k in range(1, 29)}
    during = {starts_on + dt.timedelta(days=k): rng.randint(9, 15) for k in range(days)}
    return before, during


def kiosk_numbers(
    session: Session, kiosk: Branch, units: dict[dt.date, dict[str, int]], starts_on: dt.date
) -> experiments.BranchNumbers:
    """The BranchNumbers experiments.propose reads on starts_on from the seeded data: the days
    with units before it (open days), their units by item, and the kiosk's sold-out stock rows
    on those days (distinct dates by item)."""
    days = {d: v for d, v in units.items() if d < starts_on}
    rows = session.exec(
        select(StockEvent)
        .where(StockEvent.branch_id == kiosk.id)
        .where(StockEvent.kind == "sold_out")
        .where(col(StockEvent.business_date).in_(days))
    ).all()
    sold_out: dict[str, set[dt.date]] = {}
    for row in rows:
        if row.item_id is not None:
            sold_out.setdefault(row.item_id, set()).add(row.business_date)
    totals: dict[str, int] = {}
    for sold in days.values():
        for item_id, q in sold.items():
            totals[item_id] = totals.get(item_id, 0) + q
    return experiments.BranchNumbers(
        open_days=len(days),
        units=totals,
        sold_out_days={k: len(v) for k, v in sold_out.items()},
    )


def _plan_experiments(
    session: Session,
    kiosk: Branch,
    items: list[RetailItem],
    strategies: list[Strategy],
    today: dt.date,
    units: dict[dt.date, dict[str, int]],
) -> list[Planned]:
    """Each seeded experiment as experiments.propose makes it on its start date from the
    seeded data (kiosk_numbers over the counts' units and the stock rows; the done one over
    done_units), with its two price rows at the kiosk (to_price from the start, from_price
    after the end)."""
    ids = {i.name: i.id for i in items}
    days = orgconfig.load().branch_manager.experiment_days
    actor, out = Actor.system(kiosk.id), []
    for name, key, back, status in SEEDED_EXPERIMENTS:
        starts_on = today - dt.timedelta(days=back)
        if status == "done":
            before, _ = done_units(starts_on, days)
            units_on = {d: {ids[name]: q} for d, q in before.items()}
        else:
            units_on = units
        numbers = kiosk_numbers(session, kiosk, units_on, starts_on)
        strategy = next(s for s in strategies if s.name_key == key)
        proposal = next(
            p
            for p in experiments.propose(numbers, items, [strategy], starts_on)
            if p.item_id == ids[name] and p.new_item is None
        )
        item = next(i for i in items if i.id == proposal.item_id)
        ends_on = starts_on + dt.timedelta(days=days - 1)
        retail_items.schedule_price(session, item, kiosk.id, proposal.to_price, starts_on, actor)
        retail_items.schedule_price(
            session, item, kiosk.id, proposal.from_price, ends_on + dt.timedelta(days=1), actor
        )
        out.append((item, proposal, starts_on, ends_on, status))
    retail_items.apply_due(session, kiosk, today, actor)
    return out


def _seed_experiments(
    session: Session,
    kiosk: Branch,
    planned: list[Planned],
    kiosk_daily: dict[str, dict[dt.date, experiments.Day]],
    staff: dict[str, Person],
) -> None:
    """The kiosk's experiment rows (proposed by Marites, approved by Rosa; the seed does not go
    through approvals, so approval_id stays empty): baseline and result from experiments.baseline
    and experiments.score. A running one reads the seeded counts; a done one done_units, priced
    at from_price before and to_price during."""
    for item, p, starts_on, ends_on, status in planned:
        days = (ends_on - starts_on).days + 1
        daily = kiosk_daily.get(item.id, {})
        if status == "done":
            before, during = done_units(starts_on, days)
            daily = {d: (q, q * p.from_price) for d, q in before.items()}
            daily |= {d: (q, q * p.to_price) for d, q in during.items()}
        base = experiments.baseline(daily, starts_on, days)
        assert base is not None, "a seeded experiment needs its baseline"
        during_daily = {d: v for d, v in daily.items() if starts_on <= d <= ends_on}
        result = asdict(experiments.score(base, during_daily)) if status == "done" else None
        row = Experiment(
            branch_id=kiosk.id,
            kind=p.kind,
            strategy_id=p.strategy_id,
            item_id=item.id,
            from_price=p.from_price,
            to_price=p.to_price,
            currency=item.currency,
            starts_on=starts_on,
            ends_on=ends_on,
            baseline=asdict(base),
            result=result,
            rationale=p.rationale,
            status=status,
            proposed_by=staff["Marites"].id,
            decided_by=staff["Rosa"].id,
        )
        store.insert(session, row, Actor.system(kiosk.id))


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

    def order(who: Customer, quantity: int, pickup: dt.datetime, status: str) -> CustomerOrder:
        line = {"item_id": classic.id, "quantity": quantity, "unit_price": classic.price}
        row = CustomerOrder(
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
    """Seed-only HR data: contracts, a shift Job per clerk (_shift_job) with completed visits and
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
        for name, (where_index, begin, finish) in SHIFTS.items():
            if where_index != index:
                continue
            job = _shift_job(session, branch, loc, name, today - dt.timedelta(days=back))
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


def _shift_job(session: Session, branch: Branch, loc: Location, name: str, since: dt.date) -> Job:
    """The clerk's weekly shift Job on SHIFT_DAYS at SHIFTS' times, named by roster.job_name
    from the branch's hours ("Opening Ana"); created on `since` (local), so generation never
    depends on the wall clock."""
    where, begin, finish = SHIFTS[name]
    zone = ZoneInfo(branch.timezone)
    start, end = (dt.datetime.combine(since, dt.time.fromisoformat(t)) for t in (begin, finish))
    _, opens, closes, _ = BRANCHES[where]
    times = (dt.time.fromisoformat(t) for t in (begin, finish, opens, closes))
    shift_start, shift_end, branch_opens, branch_closes = times
    days = SHIFT_DAYS[name].split(",")
    job = Job(
        branch_id=branch.id,
        location_id=loc.id,
        name=roster.job_name(shift_start, shift_end, days, branch_opens, branch_closes, name),
        recurrence=f"FREQ=WEEKLY;BYDAY={SHIFT_DAYS[name]}",
        start_time=begin,
        duration_minutes=int((end - start).total_seconds() // 60),
        created_at=dt.datetime.combine(since, dt.time(0, 0), zone),
    )
    return store.insert(session, job, Actor.system(branch.id))


def _seed_shift_supervisor(
    session: Session, branches: list[Branch], staff: dict[str, Person], today: dt.date
) -> None:
    """The shift supervisor's retail rows: each clerk's Availability on SHIFT_DAYS within the
    branch hours and a WorkLimit, planned visits generated from today, a closure at the Street
    stall on the first holiday after today (its open visits cancelled) and one open equipment
    incident on Pao's next visit."""
    where = {name: index for name, _, index, _ in PEOPLE}
    for name in SHIFTS:
        branch = branches[where[name]]
        actor, person = Actor.system(branch.id), staff[name]
        _, opens, closes, _ = BRANCHES[where[name]]
        for code in SHIFT_DAYS[name].split(","):
            window = Availability(
                branch_id=branch.id,
                person_id=person.id,
                weekday=scheduling.WEEKDAYS.index(code),
                start=opens,
                end=closes,
            )
            store.insert(session, window, actor)
        limit = WorkLimit(
            branch_id=branch.id,
            person_id=person.id,
            max_daily_minutes=DAILY_LIMIT,
            max_weekly_minutes=WEEKLY_LIMIT,
        )
        store.insert(session, limit, actor)
    for branch in branches:
        scheduling.generate(session, Actor.system(branch.id), branch, today=today)
    stall, pao = branches[where["Pao"]], staff["Pao"]
    ahead = sorted((h for h in orgconfig.load().holidays if h.date > today), key=lambda h: h.date)
    if ahead:
        closure = RetailClosure(
            branch_id=stall.id, date=ahead[0].date, reason=ahead[0].name, set_by=staff["Rosa"].id
        )
        store.insert(session, closure, Actor.system(stall.id), action="retail.closure_set")
        scheduling.cancel_day(session, Actor.system(stall.id), stall.id, ahead[0].date)
    upcoming = session.exec(
        select(Visit)
        .where(Visit.branch_id == stall.id)
        .where(col(Visit.date) >= today)
        .where(Visit.status == "planned")
        .order_by(col(Visit.planned_start))
    ).all()
    visit = next(v for v in upcoming if pao.id in v.assigned_person_ids)
    incident = Incident(
        branch_id=stall.id,
        visit_id=visit.id,
        person_id=pao.id,
        kind="equipment",
        text="seed-only: the freezer door does not close",
    )
    store.insert(session, incident, Actor.system(stall.id), action="site_problem.reported")


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
    kiosk: bool = False,
) -> None:
    """Add a fortnight's stock events: Special sold out on two Saturdays (at the kiosk also on
    the KIOSK_SOLD_OUT days, its price increase experiment's reason), Classic leftovers on two
    weekdays, one waste row, counts of LPG (under its reorder point) and eggs, and a low banana
    leaves."""
    days = [today - dt.timedelta(days=n) for n in range(1, 15)]
    saturdays = [d for d in days if d.weekday() == 5][:2]
    weekdays = [d for d in days if d.weekday() < 5][:2]
    special, classic, ube = items[0], items[1], items[2]
    early = set(saturdays) | {today - dt.timedelta(days=n) for n in KIOSK_SOLD_OUT if kiosk}
    for day in sorted(early):
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


# category, days before today, amount, VAT amount, receipt number, source (the Mall kiosk's
# expenses, each under the expense limit; the petty spends add up to 1,200 pesos)
EXPENSES: list[tuple[str, int, int, int | None, str | None, str]] = [
    ("utilities", 12, 224_000, 24_000, "MER-55120", "cash"),
    ("rent", 10, 450_000, None, None, "bank"),
    ("supplies", 8, 112_000, 12_000, "OR-00342", "cash"),
    ("transport", 6, 70_000, None, None, "petty"),
    ("repairs", 5, 85_000, None, "OR-1187", "cash"),
    ("other", 2, 50_000, None, None, "petty"),
]
PETTY_REFILL = (13, 200_000)  # days before today, amount
SHORT_DAY = 6  # days before today the closing count is 150 pesos short


def _seed_bookkeeper(
    session: Session, branches: list[Branch], staff: dict[str, Person], today: dt.date
) -> None:
    """Seed the books from the bookkeeper's own functions: a closing cash count for each seeded
    day per branch (expected from bk_tools.tender_sales, counted off by 0 to 80 pesos, one day
    150 pesos short), a GCash settlement for each of the last three days and a Grab payout for
    last week (bk_calc.match with the settings' fee and commission), the Mall kiosk's expenses
    and petty cash, and a bank deposit every Monday of the undeposited cash before it."""
    settings = orgconfig.load().bookkeeper
    supervisors = [staff["Marites"].id, staff["Jun"].id]
    last_monday = today - dt.timedelta(days=today.weekday() + 7)
    for index, branch in enumerate(branches):
        actor, by, bid = Actor.system(branch.id), supervisors[index], branch.id
        days = [today - dt.timedelta(days=offset) for offset in range(14, 0, -1)]
        for day in days:
            offset = (today - day).days
            expected = bk_tools.tender_sales(session, bid, "cash", day, day)
            off = -15_000 if offset == SHORT_DAY else (offset * 37 + index * 11) % 81 * 100
            counted = expected + (off if offset % 2 or offset == SHORT_DAY else -off)
            gap = bk_calc.match(counted, expected, 0, settings.threshold).gap
            row = CashCount(
                branch_id=bid, business_date=day, counted=counted, expected=expected,
                difference=gap, currency=CURRENCY, counted_by=by,
            )  # fmt: skip
            store.insert(session, row, actor)
        for day in days[-3:]:
            sales = bk_tools.tender_sales(session, bid, "gcash", day, day)
            fee = settings.fees["gcash"]
            amount = sales - bk_calc.percent_of(sales, fee)  # settled in full
            m = bk_calc.match(amount, sales, fee, settings.threshold)
            settlement = Settlement(
                branch_id=bid, provider="gcash", period_start=day, period_end=day,
                amount=amount, expected=m.expected, fee=m.cut, currency=CURRENCY, matched_by=by,
            )  # fmt: skip
            store.insert(session, settlement, actor)
        week_end = last_monday + dt.timedelta(days=6)
        sales = bk_tools.tender_sales(session, bid, "grab", last_monday, week_end)
        commission = settings.commissions["grab"]
        amount = sales - bk_calc.percent_of(sales, commission) - 2_000  # 20 pesos short
        m = bk_calc.match(amount, sales, commission, settings.threshold)
        payout = Payout(
            branch_id=bid, provider="grab", period_start=last_monday, period_end=week_end,
            amount=amount, expected=m.expected, commission=m.cut, currency=CURRENCY,
            recorded_by=by,
        )  # fmt: skip
        store.insert(session, payout, actor)
        if index == 0:
            back, refill = PETTY_REFILL
            petty = Deposit(
                branch_id=bid, business_date=today - dt.timedelta(days=back),
                bank=bk_tools.PETTY, amount=refill, currency=CURRENCY, recorded_by=by,
            )  # fmt: skip
            store.insert(session, petty, actor)
            for category, back, amount, vat, receipt, source in EXPENSES:
                expense = Expense(
                    branch_id=bid, business_date=today - dt.timedelta(days=back),
                    category=category, amount=amount, currency=CURRENCY, vat_amount=vat,
                    receipt_no=receipt, source=source, recorded_by=by,
                )  # fmt: skip
                store.insert(session, expense, actor)
        for day in days:
            if day.weekday() != 0:
                continue
            _, undeposited = bk_tools.balance_days(session, bid, day - dt.timedelta(days=1))
            amount = undeposited[max(undeposited)] if undeposited else 0
            if amount > 0:
                deposit = Deposit(
                    branch_id=bid, business_date=day, bank="bdo", amount=amount,
                    currency=CURRENCY, reference=f"DS-{day:%m%d}-{index + 1}", recorded_by=by,
                )  # fmt: skip
                store.insert(session, deposit, actor)


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
