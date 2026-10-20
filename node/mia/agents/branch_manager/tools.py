"""The branch manager's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store and the retail template (mia.templates.retail.items). Every number is
code (experiments.py and calc.py): the baseline, the score, the engine's prices, the pairing, the
tip rotation; the model never computes one.

Scope: every tool works on the acting person's branch, except weekly_summary, which names
another branch (or "all") only with read_all on every resource it reads (admin, and the owner
through the hierarchy); an owner or admin who names none sees every branch. A clerk's coaching
is their own row only; another person's needs the plain read on branch_manager_coaching.
read_own on the sales tables gates by role only (the sales supervisor's _as_reporter); which
rows are read is decided by the queries.

Money goes through the approvals guard: propose_experiment and change_price have `approval:
always` and risk money (approvers owner and admin, app only, PIN step-up). Their prechecks
refuse before anything is asked (ExperimentRefused, PriceRefused; check_experiment runs
experiments.guard and completes the input: the strategy row's kind, the engine's price when
none was typed, the engine's rationale), so the approval's evidence carries the exact input the
approver sees. On approve, the handlers re-run the tool as the requester with the approval in
deps.approved and the evidence input: the experiment row approved with its two dated price rows
(or the new item an engine proposal describes), or the one price row; on reject, the events and
(for an experiment) a rejected row. The requester is told either way. experiment_tick is the
system's: it starts, ends and scores experiments and applies due prices.
"""

import datetime as dt
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding
from mia.agents.branch_manager import MANIFEST, calc, experiments
from mia.agents.branch_manager.experiments import Day
from mia.agents.branch_manager.models import Coaching, Experiment, Strategy, Tip
from mia.agents.sales_supervisor.tools import (
    COUNTS,
    ITEMS,
    NOTES,
    TARGETS,
    _as_reporter,
    _branches,
    _business_day,
    _catalog,
    _check,
    _currency,
    _hours,
    _is_lead,
    _live_counts,
    _share,
)
from mia.chat.blocks import TextBlock
from mia.chat.channels import notify
from mia.core import approvals, events, orgconfig, store
from mia.core.db import utcnow
from mia.core.models import (
    Actor,
    Approval,
    Branch,
    Person,
    SalesCount,
    SalesNote,
    StockEvent,
)
from mia.core.money import format_money
from mia.core.rbac import Resource
from mia.i18n import t
from mia.i18n.strings import STRINGS
from mia.templates.retail import hours as retail_hours
from mia.templates.retail import items
from mia.templates.retail.models import (
    RetailBranchHours,
    RetailIngredient,
    RetailItem,
    RetailItemPrice,
)

PROPOSE = f"{MANIFEST.id}.propose_experiment"
CHANGE_PRICE = f"{MANIFEST.id}.change_price"
EXPERIMENTS = Resource(kind="data", name=Experiment.__tablename__)
STRATEGIES = Resource(kind="data", name=Strategy.__tablename__)
TIPS = Resource(kind="data", name=Tip.__tablename__)
COACHING = Resource(kind="data", name=Coaching.__tablename__)
STOCK = Resource(kind="data", name=StockEvent.__tablename__)
PEOPLE = Resource(kind="data", name="core.person")
INGREDIENTS = Resource(kind="data", name=RetailIngredient.__tablename__)
OPEN = ("pending", "escalated")
COACHING_DAYS = 30  # this 30 days against the 30 before
THEME_DAYS = 90  # notes of the last 90 days
MEAN_DAYS = 28  # a day beat the item's mean of the 28 days before it
MAX_THEMES = 3
TIPS_GIVEN = 2
NUMBERS_DAYS = 28  # the window the strategy engine reads
PRICE_DAYS = 90  # experiments.guard's price history
END_DELAY = dt.timedelta(hours=1)  # an experiment ends an hour after its last closing
DEFAULT_LANGUAGE = "en"  # the tips of a language without rows


# ---- shared helpers -----------------------------------------------------------------------


def _owned(resource: Resource, person_id: str) -> Resource:
    """The resource owned by the person, so read_own and write_own apply to their own rows."""
    return resource.model_copy(update={"owner_id": person_id})


def _days(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=k) for k in range((end - start).days + 1)]


def daily(
    session: Session, branch_id: str, item_id: str, start: dt.date, end: dt.date
) -> dict[dt.date, Day]:
    """The item's live counts at the branch summed per business date from start to end
    (inclusive), as (units, amount); a date without counts is absent. Reads only, unchecked:
    callers check (or are the system tick)."""
    out: dict[dt.date, Day] = {}
    for row in _live_counts(session, [branch_id], start, end, item_id):
        units, amount = out.get(row.business_date, (0, 0))
        out[row.business_date] = (units + row.quantity, amount + row.amount)
    return out


def _daily_of(
    session: Session, branch_id: str, item_ids: Iterable[str], start: dt.date, end: dt.date
) -> dict[dt.date, Day]:
    """daily summed over several items (an experiment's item and the new item it made)."""
    out: dict[dt.date, Day] = {}
    for item_id in item_ids:
        for day, (units, amount) in daily(session, branch_id, item_id, start, end).items():
            had = out.get(day, (0, 0))
            out[day] = (had[0] + units, had[1] + amount)
    return out


def _sold_item(session: Session, branch_id: str, item_id: str) -> RetailItem:
    """The active item the branch sells. Raises LookupError("no_item") otherwise."""
    found = next((i for i in _catalog(session, branch_id) if i.id == item_id), None)
    if found is None:
        raise LookupError("no_item")
    return found


def _approved(deps: AgentDeps, tool_id: str) -> Approval | None:
    """The approved approval of tool_id among deps.approved, if any."""
    for approval_id in sorted(deps.approved):
        row = deps.session.get(Approval, approval_id)
        if row is not None and row.type == tool_id and row.status == "approved":
            return row
    return None


def _requester(session: Session, approval: Approval) -> tuple[Person, Branch]:
    person = session.get(Person, approval.requester_on_behalf_of or "")
    branch = session.get(Branch, person.branch_id) if person is not None else None
    if person is None or branch is None:
        raise LookupError("the requester")
    return person, branch


def _requester_deps(session: Session, approval: Approval) -> AgentDeps:
    """The requester's deps on their branch's business date now, with the approval approved."""
    person, branch = _requester(session, approval)
    today = retail_hours.business_date_at(branch, retail_hours.load(session, branch.id), utcnow())
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=today,
        lang=person.language or DEFAULT_LANGUAGE,
        manifest=MANIFEST,
        approved={approval.id},
    )


def _tell(session: Session, person: Person, key: str, **params: object) -> None:
    text = t(key, person.language or DEFAULT_LANGUAGE, **params)
    notify(session, person, [TextBlock(text=text)], Actor.system(person.branch_id), MANIFEST.id)


def _money(amount: int, currency: str, person: Person) -> str:
    return format_money(amount, currency, person.language or DEFAULT_LANGUAGE)


# ---- the strategy engine's numbers ----------------------------------------------------------


def _last_prices(session: Session, item: RetailItem, branch_id: str, today: dt.date) -> list[int]:
    """The item's prices at the branch in the PRICE_DAYS before today: the one in force at the
    window's start and every dated row since."""
    start = today - dt.timedelta(days=PRICE_DAYS)
    rows = session.exec(
        select(RetailItemPrice.price)
        .where(RetailItemPrice.branch_id == branch_id)
        .where(RetailItemPrice.item_id == item.id)
        .where(col(RetailItemPrice.effective_on) > start)
        .where(col(RetailItemPrice.effective_on) <= today)
    ).all()
    return [items.price_on(session, item, branch_id, start), *rows]


def _past_experiments(session: Session, branch_id: str) -> list[Experiment]:
    stmt = (
        select(Experiment)
        .where(Experiment.branch_id == branch_id)
        .where(Experiment.status != "rejected")
    )
    return list(session.exec(stmt))


def branch_numbers(session: Session, branch: Branch, today: dt.date) -> experiments.BranchNumbers:
    """What experiments.propose reads for the branch on today, over the NUMBERS_DAYS before it:
    live counts (units, open days, baskets of one reporter on one date), the stock rows
    (sold-out days, leftovers), the prices in force today and in the last PRICE_DAYS, last
    year's units by month and the days since each item's last experiment ended. Reads only,
    unchecked: callers check."""
    start, end = today - dt.timedelta(days=NUMBERS_DAYS), today - dt.timedelta(days=1)
    catalog = _catalog(session, branch.id)
    counts = _live_counts(session, [branch.id], start, end)
    units: Counter[str] = Counter()
    baskets: dict[tuple[str, dt.date], set[str]] = {}
    for c in counts:
        units[c.item_id] += c.quantity
        if c.quantity > 0:
            baskets.setdefault((c.reported_by, c.business_date), set()).add(c.item_id)
    stock = session.exec(
        select(StockEvent)
        .where(StockEvent.branch_id == branch.id)
        .where(col(StockEvent.business_date) >= start)
        .where(col(StockEvent.business_date) <= end)
    ).all()
    sold_out: dict[str, set[dt.date]] = {}
    leftovers: dict[str, dict[dt.date, int]] = {}
    for s in stock:
        if s.item_id is None:
            continue
        if s.kind == "sold_out":
            sold_out.setdefault(s.item_id, set()).add(s.business_date)
        if s.kind == "leftover":
            day = leftovers.setdefault(s.item_id, {})
            day[s.business_date] = day.get(s.business_date, 0) + (s.quantity or 0)
    year = today.year - 1
    last_year: dict[int, Counter[str]] = {}
    for c in _live_counts(session, [branch.id], dt.date(year, 1, 1), dt.date(year, 12, 31)):
        last_year.setdefault(c.business_date.month, Counter())[c.item_id] += c.quantity
    ended: dict[str, dt.date] = {}
    for e in _past_experiments(session, branch.id):
        if e.ends_on < today:
            ended[e.item_id] = max(ended.get(e.item_id, e.ends_on), e.ends_on)
    # ponytail: order_pieces stays empty (the volume strategy proposes nothing): customer orders
    # are the customer service's own table (rule 9); a shared order line needs a data standard
    # change.
    return experiments.BranchNumbers(
        open_days=len({c.business_date for c in counts}),
        units=dict(units),
        prices={i.id: items.price_on(session, i, branch.id, today) for i in catalog},
        sold_out_days={k: len(v) for k, v in sold_out.items()},
        leftovers=leftovers,
        baskets=[frozenset(b) for b in baskets.values()],
        last_year={m: dict(v) for m, v in last_year.items()},
        last_prices_90d={i.id: _last_prices(session, i, branch.id, today) for i in catalog},
        since_experiment={k: (today - d).days for k, d in ended.items()},
    )


def _engine_reads(deps: AgentDeps, tool_call_id: str) -> None:
    for resource in (EXPERIMENTS, STRATEGIES, ITEMS, STOCK):
        _check(deps, resource, "read", tool_call_id)
    _check(deps, _as_reporter(COUNTS, deps), "read", tool_call_id)


def proposals(deps: AgentDeps, starts_on: dt.date, tool_call_id: str) -> list[experiments.Proposal]:
    """The engine's proposals for the acting person's branch from starts_on (one per active
    strategy whose condition holds, catalogue order), after the read checks on everything
    branch_numbers reads. The turn offers them when a request names no strategy."""
    _engine_reads(deps, tool_call_id)
    strategies = deps.session.exec(select(Strategy).order_by(col(Strategy.created_at))).all()
    numbers = branch_numbers(deps.session, deps.branch, deps.today)
    catalog = _catalog(deps.session, deps.branch.id)
    return experiments.propose(numbers, catalog, strategies, starts_on)


# ---- coaching -----------------------------------------------------------------------------


class CoachingInput(BaseModel):
    item_id: str | None = None
    person_id: str | None = Field(None, description="Another person (supervisor, owner, admin)")


class ClerkRow(BaseModel):
    person_id: str
    name: str
    units: int
    amount: int
    before_units: int
    improved: bool


class CoachingOutput(BaseModel):
    start: dt.date
    end: dt.date
    rows: list[ClerkRow]
    pairing: tuple[str, str] | None


def _coached(deps: AgentDeps, person_id: str | None, tool_call_id: str) -> Person | None:
    """The one person the coaching is about, or None for every reporter of the branch. A clerk
    (no plain read on the coaching table) naming nobody gets their own row; naming someone else
    needs the plain read on coaching, counts and people. Raises LookupError for a person outside
    the branch, after the checks."""
    own = person_id in (None, deps.person.id)
    may_read = bool({"supervisor", "owner", "admin"} & set(deps.person.roles))
    if own and (person_id is not None or not may_read):
        for resource in (COACHING, PEOPLE):
            _check(deps, _owned(resource, deps.person.id), "read", tool_call_id)
        _check(deps, _as_reporter(COUNTS, deps), "read", tool_call_id)
        return deps.person
    for resource in (COACHING, PEOPLE, COUNTS):
        _check(deps, resource, "read", tool_call_id)
    if person_id is None:
        return None
    person = deps.session.get(Person, person_id)
    if person is None or person.branch_id != deps.branch.id:
        raise LookupError("no such person")
    return person


def coaching(deps: AgentDeps, args: CoachingInput, tool_call_id: str) -> CoachingOutput:
    """Per reporter of the branch (or the one person): units and amount of the item (or every
    item) in the COACHING_DAYS before the business date, the units of the COACHING_DAYS before
    that and whether they improved (calc.improved), most units first; and the pair of items
    most often in one of their baskets (calc.pairing)."""
    who = _coached(deps, args.person_id, tool_call_id)
    day = _business_day(deps, deps.branch, tool_call_id)
    end, start = day - dt.timedelta(days=1), day - dt.timedelta(days=COACHING_DAYS)
    before = start - dt.timedelta(days=COACHING_DAYS)
    rows = _live_counts(deps.session, [deps.branch.id], before, end)
    if who is not None:
        rows = [r for r in rows if r.reported_by == who.id]
    now: dict[str, list[int]] = {}
    earlier: Counter[str] = Counter()
    baskets: dict[tuple[str, dt.date], set[str]] = {}
    for r in rows:
        if r.business_date >= start and r.quantity > 0:
            baskets.setdefault((r.reported_by, r.business_date), set()).add(r.item_id)
        if args.item_id is not None and r.item_id != args.item_id:
            continue
        if r.business_date >= start:
            sums = now.setdefault(r.reported_by, [0, 0])
            sums[0] += r.quantity
            sums[1] += r.amount
        else:
            earlier[r.reported_by] += r.quantity
    ids = set(now) | set(earlier)
    names = {p.id: p.name for p in deps.session.exec(select(Person).where(col(Person.id).in_(ids)))}
    out = [
        ClerkRow(
            person_id=pid,
            name=names.get(pid, ""),
            units=now.get(pid, [0, 0])[0],
            amount=now.get(pid, [0, 0])[1],
            before_units=earlier[pid],
            improved=calc.improved(now.get(pid, [0, 0])[0], earlier[pid]),
        )
        for pid in ids
    ]
    out.sort(key=lambda r: (-r.units, r.person_id))
    pair = calc.pairing(frozenset(b) for b in baskets.values())
    return CoachingOutput(start=start, end=end, rows=out, pairing=pair)


# ---- how_to_sell --------------------------------------------------------------------------


class HowToSellInput(BaseModel):
    item_id: str


class TipOut(BaseModel):
    tip_id: str
    text: str
    source: str


class HowToSellOutput(BaseModel):
    themes: list[str]
    tips: list[TipOut]


def _themes(session: Session, branch_id: str, item_id: str, day: dt.date) -> list[str]:
    """The theme ids of the branch's notes of the THEME_DAYS before day, on the dates the item
    sold more units than its mean of the MEAN_DAYS before that date (dates with counts only),
    most frequent first (then by id), at most MAX_THEMES. Theme ids only, never note text."""
    start = day - dt.timedelta(days=THEME_DAYS)
    units = {
        d: u
        for d, (u, _) in daily(
            session, branch_id, item_id, start - dt.timedelta(days=MEAN_DAYS), day
        ).items()
    }
    notes = session.exec(
        select(SalesNote)
        .where(SalesNote.branch_id == branch_id)
        .where(col(SalesNote.business_date) >= start)
        .where(col(SalesNote.business_date) < day)
    ).all()
    found: Counter[str] = Counter()
    for note in notes:
        d = note.business_date
        window = [u for k, u in units.items() if d - dt.timedelta(days=MEAN_DAYS) <= k < d]
        if d in units and window and units[d] * len(window) > sum(window):
            found.update(note.themes)
    return [theme for theme, _ in sorted(found.items(), key=lambda kv: (-kv[1], kv[0]))][
        :MAX_THEMES
    ]


def how_to_sell(deps: AgentDeps, args: HowToSellInput, tool_call_id: str) -> HowToSellOutput:
    """The branch's own reasons first (_themes), then TIPS_GIVEN curated tips in the person's
    language (English rows when it has none) through calc.pick_tip: the item's first, never two
    within 30 days. One Coaching row of kind tip per tip given (event branch_manager.tip_given).
    Tip texts come only from branch_manager_tips rows. Raises LookupError("no_item")."""
    _check(deps, _as_reporter(NOTES, deps), "read", tool_call_id)
    _check(deps, _as_reporter(COUNTS, deps), "read", tool_call_id)
    _check(deps, TIPS, "read", tool_call_id)
    _check(deps, _owned(COACHING, deps.person.id), "read", tool_call_id)
    _check(deps, _owned(COACHING, deps.person.id), "write", tool_call_id)
    item = _sold_item(deps.session, deps.branch.id, args.item_id)
    day = _business_day(deps, deps.branch, tool_call_id)
    lang = deps.person.language or DEFAULT_LANGUAGE
    rows = _tips(deps.session, lang, "tip") or _tips(deps.session, DEFAULT_LANGUAGE, "tip")
    given: dict[str, dt.date] = {}
    for c in deps.session.exec(select(Coaching).where(Coaching.person_id == deps.person.id)):
        if c.tip_id is not None:
            given[c.tip_id] = max(given.get(c.tip_id, c.sent_on), c.sent_on)
    refs = [calc.TipRef(r.id, r.kind, r.item_id) for r in rows]
    by_id = {r.id: r for r in rows}
    picked: list[Tip] = []
    for _ in range(TIPS_GIVEN):
        tip_id = calc.pick_tip(refs, given, day, item.id)
        if tip_id is None:
            break
        given[tip_id] = day
        picked.append(by_id[tip_id])
        store.insert(
            deps.session,
            Coaching(
                branch_id=deps.branch.id,
                person_id=deps.person.id,
                kind="tip",
                sent_on=day,
                tip_id=tip_id,
            ),
            deps.actor,
            action=f"{MANIFEST.id}.tip_given",
            tool_call_id=tool_call_id,
        )
    return HowToSellOutput(
        themes=_themes(deps.session, deps.branch.id, item.id, day),
        tips=[TipOut(tip_id=r.id, text=r.text, source=r.source) for r in picked],
    )


def _tips(session: Session, lang: str, kind: str) -> list[Tip]:
    stmt = (
        select(Tip)
        .where(Tip.language == lang)
        .where(Tip.kind == kind)
        .where(col(Tip.active).is_(True))
    )
    return list(session.exec(stmt))


# ---- propose_experiment -------------------------------------------------------------------


class ProposeExperimentInput(BaseModel):
    item_id: str
    to_price: int | None = Field(
        None, gt=0, description="Minor units; none lets the strategy size it"
    )
    starts_on: dt.date
    kind: Literal["price", "promo", "bundle"] = "price"
    strategy_id: str | None = None
    # Code's only (check_experiment replaces whatever comes in with the engine's), hidden from
    # the model's schema; it rides in the approval's evidence to the handler.
    rationale: SkipJsonSchema[dict[str, Any]] = Field(default_factory=dict)


class ExperimentOut(BaseModel):
    experiment_id: str
    item_id: str
    new_item_id: str | None
    strategy_id: str
    strategy: str  # the strategy's name key (its i18n label)
    kind: str
    from_price: int
    to_price: int
    currency: str
    starts_on: dt.date
    ends_on: dt.date
    status: str
    approval_id: str | None


class ExperimentRefused(LookupError):
    """An experiment refused before any approval is asked; reason names why (no_strategy,
    no_item, starts_too_soon, open_experiment, price_scheduled, no_proposal, or a guard rail of
    experiments.guard) for the reply to word."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _experiment_out(session: Session, row: Experiment) -> ExperimentOut:
    strategy = session.get(Strategy, row.strategy_id)
    new = row.rationale.get("new_item") or {}
    return ExperimentOut(
        experiment_id=row.id,
        item_id=row.item_id,
        new_item_id=new.get("item_id"),
        strategy_id=row.strategy_id,
        strategy=strategy.name_key if strategy is not None else "",
        kind=row.kind,
        from_price=row.from_price,
        to_price=row.to_price,
        currency=row.currency,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        status=row.status,
        approval_id=row.approval_id,
    )


def _open_experiment(session: Session, branch_id: str) -> bool:
    """A pending propose_experiment approval or an approved or running experiment row."""
    pending = session.exec(
        select(Approval)
        .where(Approval.branch_id == branch_id)
        .where(Approval.type == PROPOSE)
        .where(col(Approval.status).in_(OPEN))
    ).first()
    row = session.exec(
        select(Experiment)
        .where(Experiment.branch_id == branch_id)
        .where(col(Experiment.status).in_(["approved", "running"]))
    ).first()
    return pending is not None or row is not None


def _proposal_for(
    numbers: experiments.BranchNumbers,
    catalog: Sequence[RetailItem],
    item: RetailItem,
    strategy: Strategy,
    starts_on: dt.date,
) -> experiments.Proposal | None:
    """The engine's proposal of the strategy for the item: with the item alone first (the rule
    otherwise takes the best seller), then with the whole catalogue (a bundle or a box needs the
    other items)."""
    for pool in ([item], catalog):
        for p in experiments.propose(numbers, pool, [strategy], starts_on):
            if p.item_id == item.id:
                return p
    return None


def check_experiment(deps: AgentDeps, args: ProposeExperimentInput, tool_call_id: str) -> None:
    """The guard's precheck for propose_experiment (after the permission check, before the
    approval). Refuses (ExperimentRefused) a request naming no active strategy, an item the
    branch does not sell, a strategy with no proposal for the item (no_proposal without a
    typed price, no_strategy with one: every proposal names its rationale), and whatever
    _verify_experiment refuses. Completes the input in place, so the approval carries it: kind
    from the strategy row, to_price from the engine when none was typed, and the rationale
    always from the engine's proposal (with new_item: its components and from_price), never
    from the input."""
    _engine_reads(deps, tool_call_id)
    strategy = deps.session.get(Strategy, args.strategy_id or "")
    if strategy is None or not strategy.active:
        raise ExperimentRefused("no_strategy")
    try:
        item = _sold_item(deps.session, deps.branch.id, args.item_id)
    except LookupError:
        raise ExperimentRefused("no_item") from None
    numbers = branch_numbers(deps.session, deps.branch, deps.today)
    catalog = _catalog(deps.session, deps.branch.id)
    proposal = _proposal_for(numbers, catalog, item, strategy, args.starts_on)
    if proposal is None:  # a typed price under a strategy whose condition does not hold
        raise ExperimentRefused("no_proposal" if args.to_price is None else "no_strategy")
    if args.to_price is None:
        args.to_price = proposal.to_price
    args.rationale = dict(proposal.rationale) if proposal is not None else {}
    if proposal is not None and proposal.new_item is not None:
        args.rationale["new_item"] = {
            "components": proposal.new_item,
            "from_price": proposal.from_price,
        }
    args.kind = strategy.kind  # type: ignore[assignment]  # a seeded kind: price, promo, bundle
    _verify_experiment(deps, args, tool_call_id)


def _verify_experiment(deps: AgentDeps, args: ProposeExperimentInput, tool_call_id: str) -> None:
    """The checks that must still hold when the request is approved: a start after the
    business date, no other open experiment at the branch, no price of the item at the branch
    dated after the business date (the experiment's revert row would undo it, or it would
    contaminate the test), and the guard rails (experiments.guard: the price in force on the
    start, the cost, the last PRICE_DAYS of prices, the days since the item's last experiment;
    a new item against what it stands for and the summed cost of its parts). Raises
    ExperimentRefused."""
    today = _business_day(deps, deps.branch, tool_call_id)
    if args.starts_on <= today:
        raise ExperimentRefused("starts_too_soon")
    if _open_experiment(deps.session, deps.branch.id):
        raise ExperimentRefused("open_experiment")
    item = _sold_item(deps.session, deps.branch.id, args.item_id)
    scheduled = deps.session.exec(
        select(RetailItemPrice)
        .where(RetailItemPrice.branch_id == deps.branch.id)
        .where(RetailItemPrice.item_id == item.id)
        .where(col(RetailItemPrice.effective_on) > today)
    ).first()
    if scheduled is not None:
        raise ExperimentRefused("price_scheduled")
    if args.to_price is None:
        raise ExperimentRefused("no_proposal")
    new_item = args.rationale.get("new_item")
    if new_item is not None:
        parts = list(new_item["components"])
        cost = items.variant_cost(deps.session, item, parts)
        against = _reference(deps.session, item, deps.branch.id, parts, args.starts_on)
        refused = experiments.guard(against, cost, args.to_price, (), None)
    else:
        past = _past_experiments(deps.session, deps.branch.id)
        last = max((e.ends_on for e in past if e.item_id == item.id), default=None)
        refused = experiments.guard(
            items.price_on(deps.session, item, deps.branch.id, args.starts_on),
            item.cost,
            args.to_price,
            _last_prices(deps.session, item, deps.branch.id, deps.today),
            (args.starts_on - last).days if last is not None else None,
        )
    if refused is not None:
        raise ExperimentRefused(refused)


def _reference(
    session: Session, base: RetailItem, branch_id: str, parts: list[str], day: dt.date
) -> int:
    """What a new item stands against, read now (never the request's copy): the base item's
    price in force on day for a premium variant (no parts), else its parts bought singly.
    ponytail: a decoy box is held against its pieces, not the engine's two smaller boxes; the
    seed's boxes cost their pieces, a discounted box needs the engine's reference here."""
    if not parts:
        return items.price_on(session, base, branch_id, day)
    found = {i.id: i for i in session.exec(select(RetailItem).where(col(RetailItem.id).in_(parts)))}
    return sum(items.price_on(session, found[c], branch_id, day) for c in parts)


def _variant_name(session: Session, base: RetailItem, components: list[str]) -> str:
    """A new item's name from its parts: "<base> Premium" (no parts), "<a> + <b>" (a bundle of
    different items), "<item> x<n>" (n pieces of one item). Data, not i18n; the owner renames."""
    if not components:
        return f"{base.name} Premium"
    names = {i.id: i.name for i in session.exec(select(RetailItem))}
    if len(set(components)) > 1:
        return " + ".join(names[c] for c in dict.fromkeys(components))
    return f"{names[components[0]]} x{len(components)}"


def propose_experiment(
    deps: AgentDeps, args: ProposeExperimentInput, tool_call_id: str
) -> ExperimentOut:
    """Write the experiment of an approved request (status approved, event
    branch_manager.experiment_proposed) for experiment_days from starts_on: two dated prices at
    the branch (to_price from starts_on, the price in force then from the day after the end),
    or, for an engine proposal with new_item, the new item (items.create_variant, inactive
    until the start; its id in the rationale) and no price row. Runs only with an approved
    approval in deps.approved (the guard asks for one first) and writes at most one row per
    approval. Raises LookupError without an approval, a price or the item."""
    _check(deps, EXPERIMENTS, "write", tool_call_id)
    _check(deps, ITEMS, "write", tool_call_id)
    approval = _approved(deps, PROPOSE)
    if approval is None or args.to_price is None or args.strategy_id is None:
        raise LookupError("an experiment needs an approved request with a price")
    stmt = select(Experiment).where(Experiment.approval_id == approval.id)
    if (done := deps.session.exec(stmt).first()) is not None:
        return _experiment_out(deps.session, done)
    item = _sold_item(deps.session, deps.branch.id, args.item_id)
    days = orgconfig.load().branch_manager.experiment_days
    ends_on = args.starts_on + dt.timedelta(days=days - 1)
    rationale = dict(args.rationale)
    new = rationale.get("new_item")
    if new is not None:
        components = list(new["components"])
        name = _variant_name(deps.session, item, components)
        variant = items.create_variant(
            deps.session, item, name, args.to_price, components, deps.actor, tool_call_id
        )
        rationale["new_item"] = {**new, "item_id": variant.id}
        from_price = _reference(deps.session, item, deps.branch.id, components, args.starts_on)
    else:
        from_price = items.price_on(deps.session, item, deps.branch.id, args.starts_on)
        for price, on in (
            (args.to_price, args.starts_on),
            (from_price, ends_on + dt.timedelta(days=1)),
        ):
            items.schedule_price(
                deps.session,
                item,
                deps.branch.id,
                price,
                on,
                deps.actor,
                approval_id=approval.id,
                tool_call_id=tool_call_id,
            )
    row = store.insert(
        deps.session,
        Experiment(
            branch_id=deps.branch.id,
            kind=args.kind,
            strategy_id=args.strategy_id,
            item_id=item.id,
            from_price=from_price,
            to_price=args.to_price,
            currency=item.currency,
            starts_on=args.starts_on,
            ends_on=ends_on,
            rationale=rationale,
            status="approved",
            approval_id=approval.id,
            proposed_by=deps.person.id,
            decided_by=approval.decided_by,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.experiment_proposed",
        tool_call_id=tool_call_id,
        approval_id=approval.id,
    )
    return _experiment_out(deps.session, row)


def _refused_key(prefix: str, reason: str | None) -> str:
    """<prefix>.<reason> when that key exists, else <prefix>.other (a plain LookupError's
    words, "the requester", never reach a person as a raw key)."""
    key = f"{prefix}.{reason}"
    return key if key in STRINGS["en"] else f"{prefix}.other"


def _requested(approval: Approval, model: type[BaseModel]) -> Any:
    raw = approval.evidence.get("input")
    if raw is None:
        raise LookupError("the approval carries no input")
    return model.model_validate(raw)


def apply_experiment_approval(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: check again as the requester that the start is still ahead, no other
    experiment opened and the guard rails still pass (the price in force may have moved since
    the request), then re-run propose_experiment as the requester (their permissions, the
    approval in deps.approved, the evidence input) and tell the requester. Raises LookupError
    (ExperimentRefused with the reason: nothing is written, the decide route answers 409) or
    when the requester or the input cannot be found."""
    deps = _requester_deps(session, approval)
    args: ProposeExperimentInput = _requested(approval, ProposeExperimentInput)
    tool_call_id = str(approval.evidence.get("tool_call_id"))
    _verify_experiment(deps, args, tool_call_id)
    out = propose_experiment(deps, args, tool_call_id)
    item = session.get(RetailItem, out.new_item_id or out.item_id)
    _tell(
        session,
        deps.person,
        "bm.experiment_approved",
        item=item.name if item is not None else "",
        price=_money(out.to_price, out.currency, deps.person),
        start=out.starts_on.isoformat(),
        end=out.ends_on.isoformat(),
        strategy=t(out.strategy, deps.lang),
    )


def apply_experiment_rejection(session: Session, approval: Approval, decider: Actor) -> None:
    """Reject handler: an experiment row with status rejected (event
    branch_manager.experiment_rejected; no price row, no new item) and the requester told. An
    approval closed as expired after the approve handler refused it (approvals.close_refused)
    writes no row: the requester is told the reason (bm.experiment_refused.<reason>, else
    .other). Raises LookupError when the requester or the input cannot be found."""
    deps = _requester_deps(session, approval)
    args: ProposeExperimentInput = _requested(approval, ProposeExperimentInput)
    if approval.status == "expired":
        _tell(session, deps.person, _refused_key("bm.experiment_refused", approval.reason))
        return
    _check(deps, EXPERIMENTS, "write", str(approval.evidence.get("tool_call_id")))
    item = session.get(RetailItem, args.item_id)
    if item is None or args.to_price is None or args.strategy_id is None:
        raise LookupError("the rejected experiment")
    days = orgconfig.load().branch_manager.experiment_days
    new = args.rationale.get("new_item")
    from_price = (
        int(new["from_price"])
        if new is not None
        else items.price_on(session, item, deps.branch.id, args.starts_on)
    )
    store.insert(
        session,
        Experiment(
            branch_id=deps.branch.id,
            kind=args.kind,
            strategy_id=args.strategy_id,
            item_id=item.id,
            from_price=from_price,
            to_price=args.to_price,
            currency=item.currency,
            starts_on=args.starts_on,
            ends_on=args.starts_on + dt.timedelta(days=days - 1),
            rationale=args.rationale,
            status="rejected",
            approval_id=approval.id,
            proposed_by=deps.person.id,
            decided_by=approval.decided_by,
        ),
        deps.actor,
        action=f"{MANIFEST.id}.experiment_rejected",
        approval_id=approval.id,
    )
    _tell(
        session,
        deps.person,
        "bm.experiment_rejected",
        item=item.name,
        price=_money(args.to_price, item.currency, deps.person),
    )


approvals.register_handler(PROPOSE, apply_experiment_approval)
approvals.register_reject_handler(PROPOSE, apply_experiment_rejection, on_refused=True)


# ---- score_experiment ---------------------------------------------------------------------


class ScoreInput(BaseModel):
    experiment_id: str | None = Field(None, description="None: the branch's open or last one")


class ScoreOutput(BaseModel):
    experiment_id: str
    item_id: str
    days: int
    units_pct: int | None
    amount_pct: int | None
    enough: bool
    status: str


def _result(session: Session, row: Experiment, upto: dt.date) -> dict[str, Any] | None:
    """The experiment's stored result, else its days from starts_on to upto (at most ends_on)
    scored against its baseline (experiments.score as a dict), the new item's counts added to
    the item's; None without a baseline (not enough data)."""
    if row.result is not None:
        return row.result
    if row.baseline is None:
        return None
    # ponytail: a new item is scored as the line (base item plus new item) against the base
    # item's baseline; per-item scores need a baseline the new item cannot have.
    new = (row.rationale.get("new_item") or {}).get("item_id")
    ids = [row.item_id, *([new] if new else [])]
    during = _daily_of(session, row.branch_id, ids, row.starts_on, min(row.ends_on, upto))
    return asdict(experiments.score(experiments.Baseline(**row.baseline), during))


def _score(session: Session, row: Experiment, upto: dt.date) -> ScoreOutput:
    """_result as the tool's output; enough is False without a baseline."""
    result = _result(session, row, upto) or {}
    return ScoreOutput(
        experiment_id=row.id,
        item_id=row.item_id,
        days=int(result.get("days") or 0),
        units_pct=result.get("units_pct"),
        amount_pct=result.get("amount_pct"),
        enough=row.baseline is not None,
        status=row.status,
    )


def score_experiment(deps: AgentDeps, args: ScoreInput, tool_call_id: str) -> ScoreOutput:
    """The named experiment of the branch, else its running one, else its latest started one
    (approved, rejected and later ones aside), scored up to yesterday. Raises
    LookupError("no_experiment")."""
    _check(deps, EXPERIMENTS, "read", tool_call_id)
    _check(deps, _as_reporter(COUNTS, deps), "read", tool_call_id)
    day = _business_day(deps, deps.branch, tool_call_id)
    stmt = select(Experiment).where(Experiment.branch_id == deps.branch.id)
    if args.experiment_id is not None:
        stmt = stmt.where(Experiment.id == args.experiment_id)
    else:
        stmt = stmt.where(col(Experiment.status).in_(["running", "done", "kept"]))
    rows = deps.session.exec(stmt).all()
    if not rows:
        raise LookupError("no_experiment")
    row = max(rows, key=lambda r: (r.status == "running", r.starts_on, r.id))
    return _score(deps.session, row, day - dt.timedelta(days=1))


# ---- decide_experiment --------------------------------------------------------------------


class DecideInput(BaseModel):
    experiment_id: str
    keep: bool


def _variant(session: Session, row: Experiment) -> RetailItem | None:
    new = (row.rationale.get("new_item") or {}).get("item_id")
    return session.get(RetailItem, new) if new else None


def _reverted(session: Session, row: Experiment) -> bool:
    """The experiment's end took effect: its revert price row (from_price on ends_on + 1) was
    applied, or its new item was taken off the menu after the end."""
    variant = _variant(session, row)
    if variant is not None:
        return row.status == "done" and not variant.active
    applied = session.exec(
        select(RetailItemPrice)
        .where(RetailItemPrice.branch_id == row.branch_id)
        .where(RetailItemPrice.item_id == row.item_id)
        .where(RetailItemPrice.effective_on == row.ends_on + dt.timedelta(days=1))
        .where(col(RetailItemPrice.applied_at).is_not(None))
    ).first()
    return applied is not None


def decide_experiment(deps: AgentDeps, args: DecideInput, tool_call_id: str) -> ExperimentOut:
    """The owner's decision on a running or done experiment before its end takes effect: keep
    (status kept, event branch_manager.experiment_kept, a to_price row from ends_on + 1 so the
    tested price stays; a new item stays on the menu) or not (decided_by only, event
    branch_manager.experiment_not_kept; the revert happens as scheduled). No approval: it stays
    inside the approved experiment. Raises LookupError("no_experiment") or ("too_late")."""
    _check(deps, EXPERIMENTS, "write", tool_call_id)
    _check(deps, ITEMS, "write", tool_call_id)
    row = deps.session.get(Experiment, args.experiment_id)
    if row is None or row.branch_id != deps.branch.id or row.status not in ("running", "done"):
        raise LookupError("no_experiment")
    if _reverted(deps.session, row):
        raise LookupError("too_late")
    if not args.keep:
        row = store.update(
            deps.session,
            row,
            {"decided_by": deps.person.id},
            deps.actor,
            action=f"{MANIFEST.id}.experiment_not_kept",
            tool_call_id=tool_call_id,
        )
        return _experiment_out(deps.session, row)
    variant = _variant(deps.session, row)
    if variant is None:
        item = deps.session.get(RetailItem, row.item_id)
        if item is None:
            raise LookupError("no_item")
        items.schedule_price(
            deps.session,
            item,
            row.branch_id,
            row.to_price,
            row.ends_on + dt.timedelta(days=1),
            deps.actor,
            approval_id=row.approval_id,
            tool_call_id=tool_call_id,
        )
    elif not variant.active:
        store.update(deps.session, variant, {"active": True}, deps.actor, tool_call_id=tool_call_id)
    row = store.update(
        deps.session,
        row,
        {"status": "kept", "decided_by": deps.person.id},
        deps.actor,
        action=f"{MANIFEST.id}.experiment_kept",
        tool_call_id=tool_call_id,
    )
    return _experiment_out(deps.session, row)


# ---- change_price -------------------------------------------------------------------------


class ChangePriceInput(BaseModel):
    item_id: str
    price: int = Field(gt=0, description="Minor units")
    effective_on: dt.date


class PriceOut(BaseModel):
    price_id: str
    item_id: str
    price: int
    currency: str
    effective_on: dt.date
    approval_id: str | None


class PriceRefused(LookupError):
    """A price change refused before any approval is asked (no_item, in_the_past, unchanged)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check_price(deps: AgentDeps, args: ChangePriceInput, tool_call_id: str) -> None:
    """The guard's precheck for change_price: the branch sells the item, effective_on is not
    before the business date and the price differs from the one in force that day. Raises
    PriceRefused."""
    _check(deps, ITEMS, "read", tool_call_id)
    try:
        item = _sold_item(deps.session, deps.branch.id, args.item_id)
    except LookupError:
        raise PriceRefused("no_item") from None
    if args.effective_on < _business_day(deps, deps.branch, tool_call_id):
        raise PriceRefused("in_the_past")
    if args.price == items.price_on(deps.session, item, deps.branch.id, args.effective_on):
        raise PriceRefused("unchanged")
    _check(deps, EXPERIMENTS, "read", tool_call_id)
    if _item_in_experiment(deps.session, deps.branch.id, item.id):
        raise PriceRefused("open_experiment")


def _item_in_experiment(session: Session, branch_id: str, item_id: str) -> bool:
    """The item has a pending or escalated propose_experiment request, or an approved or
    running experiment, or a done one whose revert has not taken effect, at the branch (its
    revert row would undo a price set meanwhile)."""
    asked = session.exec(
        select(Approval)
        .where(Approval.branch_id == branch_id)
        .where(Approval.type == PROPOSE)
        .where(col(Approval.status).in_(OPEN))
    ).all()
    if any((a.evidence.get("input") or {}).get("item_id") == item_id for a in asked):
        return True
    rows = session.exec(
        select(Experiment)
        .where(Experiment.branch_id == branch_id)
        .where(Experiment.item_id == item_id)
        .where(col(Experiment.status).in_(["approved", "running", "done"]))
    ).all()
    return any(r.status != "done" or not _reverted(session, r) for r in rows)


def change_price(deps: AgentDeps, args: ChangePriceInput, tool_call_id: str) -> PriceOut:
    """Write the price of an approved request: one dated row at the branch from effective_on
    (items.schedule_price, then event branch_manager.price_changed); the counts use it from
    that business date. Runs only with an approved approval in deps.approved and writes at most
    one row per approval. Raises LookupError without an approval or the item."""
    _check(deps, ITEMS, "write", tool_call_id)
    approval = _approved(deps, CHANGE_PRICE)
    if approval is None:
        raise LookupError("a price change needs an approved request")
    stmt = select(RetailItemPrice).where(RetailItemPrice.approval_id == approval.id)
    row = deps.session.exec(stmt).first()
    if row is None:
        item = _sold_item(deps.session, deps.branch.id, args.item_id)
        row = items.schedule_price(
            deps.session,
            item,
            deps.branch.id,
            args.price,
            args.effective_on,
            deps.actor,
            approval_id=approval.id,
            tool_call_id=tool_call_id,
        )
        after = {"item_id": item.id, "price": row.price, "effective_on": str(row.effective_on)}
        events.emit(
            deps.session,
            f"{MANIFEST.id}.price_changed",
            row,
            None,
            after,
            deps.actor,
            tool_call_id=tool_call_id,
            approval_id=approval.id,
        )
    return PriceOut(
        price_id=row.id,
        item_id=row.item_id,
        price=row.price,
        currency=row.currency,
        effective_on=row.effective_on,
        approval_id=row.approval_id,
    )


def apply_price_approval(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: run check_price again as the requester (the date may have passed, the
    price in force moved or an experiment opened on the item since the request; PriceRefused,
    a LookupError: nothing is written, the decide route answers 409), then re-run change_price
    as the requester with the approval in deps.approved and the evidence input, and tell the
    requester."""
    deps = _requester_deps(session, approval)
    args: ChangePriceInput = _requested(approval, ChangePriceInput)
    tool_call_id = str(approval.evidence.get("tool_call_id"))
    check_price(deps, args, tool_call_id)
    out = change_price(deps, args, tool_call_id)
    item = session.get(RetailItem, out.item_id)
    _tell(
        session,
        deps.person,
        "bm.price_approved",
        item=item.name if item is not None else "",
        price=_money(out.price, out.currency, deps.person),
        date=out.effective_on.isoformat(),
    )


def apply_price_rejection(session: Session, approval: Approval, decider: Actor) -> None:
    """Reject handler: event branch_manager.price_rejected with the item, price and date (no
    row) and the requester told. An approval closed as expired after the approve handler
    refused it (approvals.close_refused): the requester is told the reason
    (bm.price_refused.<reason>, else .other), no event."""
    person, _ = _requester(session, approval)
    args: ChangePriceInput = _requested(approval, ChangePriceInput)
    if approval.status == "expired":
        _tell(session, person, _refused_key("bm.price_refused", approval.reason))
        return
    after = {"item_id": args.item_id, "price": args.price, "effective_on": str(args.effective_on)}
    events.emit(
        session,
        f"{MANIFEST.id}.price_rejected",
        approval,
        None,
        after,
        decider,
        approval_id=approval.id,
    )
    item = session.get(RetailItem, args.item_id)
    _tell(
        session,
        person,
        "bm.price_rejected",
        item=item.name if item is not None else "",
        price=_money(args.price, item.currency if item is not None else "", person),
        date=args.effective_on.isoformat(),
    )


approvals.register_handler(CHANGE_PRICE, apply_price_approval)
approvals.register_reject_handler(CHANGE_PRICE, apply_price_rejection, on_refused=True)


# ---- set_short_code -----------------------------------------------------------------------


class SetShortCodeInput(BaseModel):
    item_id: str
    codes: list[str] = Field(min_length=1)


class ItemOut(BaseModel):
    item_id: str
    name: str
    codes: list[str]


def _taken(session: Session, item_id: str) -> set[str]:
    """Every short code (lower case) of the other items and of the ingredients."""
    rows: list[list[str]] = [
        i.short_codes for i in session.exec(select(RetailItem)) if i.id != item_id
    ]
    rows += [i.short_codes for i in session.exec(select(RetailIngredient))]
    return {c.lower() for codes in rows for c in codes}


def check_short_code(deps: AgentDeps, args: SetShortCodeInput, tool_call_id: str) -> None:
    """The precheck of set_short_code: the branch sells the item and no other item or
    ingredient holds one of the codes (any case). Raises LookupError."""
    _check(deps, ITEMS, "read", tool_call_id)
    _check(deps, INGREDIENTS, "read", tool_call_id)
    _sold_item(deps.session, deps.branch.id, args.item_id)
    if {c.lower() for c in args.codes} & _taken(deps.session, args.item_id):
        raise LookupError("code_taken")


def set_short_code(deps: AgentDeps, args: SetShortCodeInput, tool_call_id: str) -> ItemOut:
    """Add the codes (lower case) to the item's short codes (items.set_short_codes, then event
    branch_manager.short_code_set); no money, no approval. Raises LookupError for an item the
    branch does not sell or a code another item or ingredient holds."""
    check_short_code(deps, args, tool_call_id)
    _check(deps, ITEMS, "write", tool_call_id)
    item = _sold_item(deps.session, deps.branch.id, args.item_id)
    codes = list(dict.fromkeys([*item.short_codes, *(c.lower() for c in args.codes)]))
    item = items.set_short_codes(deps.session, item, codes, deps.actor, tool_call_id)
    events.emit(
        deps.session,
        f"{MANIFEST.id}.short_code_set",
        item,
        None,
        {"codes": codes},
        deps.actor,
        tool_call_id=tool_call_id,
    )
    return ItemOut(item_id=item.id, name=item.name, codes=item.short_codes)


# ---- weekly_summary -----------------------------------------------------------------------


class WeeklyInput(BaseModel):
    branch_id: str | None = Field(
        None, description='Another branch, or "all" (only an owner or admin)'
    )
    week_start: dt.date | None = Field(None, description="None: last week, Monday to Sunday")


class BranchWeek(BaseModel):
    branch_id: str
    amount: int
    target: int | None
    best_item: str | None
    worst_item: str | None
    waste: dict[str, int]
    experiment: ScoreOutput | None


class WeeklyOutput(BaseModel):
    start: dt.date
    end: dt.date
    branches: list[BranchWeek]


def _target(
    session: Session, branch_id: str, hours: Sequence[RetailBranchHours], days: list[dt.date]
) -> int | None:
    """The sum of the day targets (sales supervisor _share) over the days; None without any."""
    shares = [s for d in days if (s := _share(session, branch_id, hours, d)) is not None]
    return sum(shares) if shares else None


def _branch_week(
    deps: AgentDeps, branch: Branch, start: dt.date, end: dt.date, tool_call_id: str
) -> BranchWeek:
    session = deps.session
    counts = _live_counts(session, [branch.id], start, end)
    amounts: Counter[str] = Counter()
    for c in counts:
        amounts[c.item_id] += c.amount
    order = {i.id: i.sort_order for i in session.exec(select(RetailItem))}
    ranked = sorted(amounts, key=lambda i: (-amounts[i], order.get(i, 0)))
    waste: Counter[str] = Counter()
    for s in session.exec(
        select(StockEvent)
        .where(StockEvent.branch_id == branch.id)
        .where(StockEvent.kind == "waste")
        .where(col(StockEvent.business_date) >= start)
        .where(col(StockEvent.business_date) <= end)
    ):
        if s.item_id is not None:
            waste[s.item_id] += s.quantity or 0
    running = session.exec(
        select(Experiment)
        .where(Experiment.branch_id == branch.id)
        .where(Experiment.status == "running")
    ).first()
    return BranchWeek(
        branch_id=branch.id,
        amount=sum(amounts.values()),
        target=_target(
            session, branch.id, _hours(deps, branch.id, tool_call_id), _days(start, end)
        ),
        best_item=ranked[0] if ranked else None,
        worst_item=ranked[-1] if ranked else None,
        waste=dict(waste),
        experiment=_score(session, running, end) if running is not None else None,
    )


def weekly_summary(deps: AgentDeps, args: WeeklyInput, tool_call_id: str) -> WeeklyOutput:
    """Per branch for the week (Monday to Sunday; default the last full week before the
    business date): the live amount, the summed day targets, the best and worst item by amount
    (menu order on a tie), waste pieces by item from stock_events and the running experiment's
    score up to the week's end. The person's branch, or another branch or "all" (the default
    for an owner or admin) after read_all on counts, targets, stock and experiments."""
    branch_id = args.branch_id
    if branch_id is None and _is_lead(deps.person):
        branch_id = "all"
    branches = _branches(deps, branch_id, COUNTS, "read", tool_call_id)
    if branches != [deps.branch]:
        for resource in (TARGETS, STOCK, EXPERIMENTS):
            _check(deps, resource, "read_all", tool_call_id)
    for resource in (COUNTS, TARGETS, STOCK, EXPERIMENTS):
        _check(deps, resource, "read", tool_call_id)  # the plain read: every reporter's rows
    day = _business_day(deps, deps.branch, tool_call_id)
    start = args.week_start or day - dt.timedelta(days=day.weekday() + 7)
    end = start + dt.timedelta(days=6)
    weeks = [_branch_week(deps, b, start, end, tool_call_id) for b in branches]
    return WeeklyOutput(start=start, end=end, branches=weeks)


# ---- monthly_letter -----------------------------------------------------------------------


class MonthlyInput(BaseModel):
    month: dt.date | None = Field(None, description="Any day of the month; None: last month")


class MonthlyOutput(BaseModel):
    start: dt.date
    end: dt.date
    amount: int
    target: int | None
    currency: str
    best_days: list[tuple[dt.date, int]]
    clerks: dict[str, int]
    decided: list[ExperimentOut]


BEST_DAYS_SHOWN = 3


def monthly_letter(deps: AgentDeps, args: MonthlyInput, tool_call_id: str) -> MonthlyOutput:
    """The branch's month in numbers (a template fills the letter, no prose): the live amount,
    the summed day targets, the BEST_DAYS_SHOWN best days by amount (earlier on a tie), the
    amount per reporter and the experiments that ended in the month (done, kept or rejected).
    Default month: the one before the business date's."""
    for resource in (COUNTS, TARGETS, EXPERIMENTS, PEOPLE):
        _check(deps, resource, "read", tool_call_id)  # the plain read: every reporter's rows
    day = _business_day(deps, deps.branch, tool_call_id)
    month = args.month or (day.replace(day=1) - dt.timedelta(days=1))
    start = month.replace(day=1)
    end = (start + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    counts: list[SalesCount] = _live_counts(deps.session, [deps.branch.id], start, end)
    by_day: Counter[dt.date] = Counter()
    clerks: Counter[str] = Counter()
    for c in counts:
        by_day[c.business_date] += c.amount
        clerks[c.reported_by] += c.amount
    best = sorted(by_day.items(), key=lambda kv: (-kv[1], kv[0]))[:BEST_DAYS_SHOWN]
    decided = deps.session.exec(
        select(Experiment)
        .where(Experiment.branch_id == deps.branch.id)
        .where(col(Experiment.status).in_(["done", "kept", "rejected"]))
        .where(col(Experiment.ends_on) >= start)
        .where(col(Experiment.ends_on) <= end)
        .order_by(col(Experiment.ends_on))
    ).all()
    hours = _hours(deps, deps.branch.id, tool_call_id)
    return MonthlyOutput(
        start=start,
        end=end,
        amount=sum(by_day.values()),
        target=_target(deps.session, deps.branch.id, hours, _days(start, end)),
        currency=_currency(deps.session, deps.branch.id),
        best_days=best,
        clerks=dict(clerks),
        decided=[_experiment_out(deps.session, e) for e in decided],
    )


# ---- the experiment tick (system) ---------------------------------------------------------


def _set_variant(session: Session, row: Experiment, active: bool, actor: Actor) -> None:
    variant = _variant(session, row)
    if variant is not None and variant.active != active:
        store.update(session, variant, {"active": active}, actor)


def experiment_tick(
    session: Session, branch: Branch, hours: Sequence[RetailBranchHours], now: dt.datetime
) -> list[tuple[str, Experiment]]:
    """The system's experiment work at the branch at `now` (unchecked: no person acts). From
    the opening of a business date: the due prices applied (items.apply_due), approved
    experiments whose start has come set running with their baseline (experiments.baseline over
    the BASELINE_DAYS before; event branch_manager.experiment_started; a new item goes on the
    menu), and a done, unkept experiment's new item taken off the menu after its end. An hour
    after the closing of ends_on: running set done with the result (experiments.score; events
    .experiment_ended and .experiment_scored). Returns ("started" or "ended", row) per change;
    a second call at the same moment returns nothing."""
    actor = Actor.system(branch.id)
    day = retail_hours.business_date_at(branch, hours, now)
    opened = now >= retail_hours.at(branch, hours, day, closing=False)
    rows = session.exec(select(Experiment).where(Experiment.branch_id == branch.id)).all()
    out: list[tuple[str, Experiment]] = []
    if opened:
        items.apply_due(session, branch, day, actor)
    for row in rows:
        days = (row.ends_on - row.starts_on).days + 1
        if row.status == "approved" and (row.starts_on < day or (row.starts_on == day and opened)):
            before = row.starts_on - dt.timedelta(days=experiments.BASELINE_DAYS)
            history = daily(session, branch.id, row.item_id, before, row.starts_on)
            base = experiments.baseline(history, row.starts_on, days)
            _set_variant(session, row, True, actor)
            changes = {"status": "running", "baseline": asdict(base) if base else None}
            row = store.update(
                session, row, changes, actor, action=f"{MANIFEST.id}.experiment_started"
            )
            out.append(("started", row))
        closed = retail_hours.at(branch, hours, row.ends_on, closing=True) + END_DELAY
        if row.status == "running" and now >= closed:
            changes = {"status": "done", "result": _result(session, row, row.ends_on)}
            row = store.update(
                session, row, changes, actor, action=f"{MANIFEST.id}.experiment_ended"
            )
            events.emit(
                session,
                f"{MANIFEST.id}.experiment_scored",
                row,
                None,
                {"result": row.result},
                actor,
            )
            out.append(("ended", row))
        if row.status == "done" and opened and row.ends_on < day:
            _set_variant(session, row, False, actor)
    return out


# ---- bindings -----------------------------------------------------------------------------


BINDINGS = [
    ToolBinding(
        f"{MANIFEST.id}.coaching",
        coaching,
        CoachingInput,
        "Per-clerk sales of the last 30 days against the 30 before, and the best item pair.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.how_to_sell",
        how_to_sell,
        HowToSellInput,
        "The branch's own reasons an item sold well, then two curated selling tips.",
    ),
    ToolBinding(
        PROPOSE,
        propose_experiment,
        ProposeExperimentInput,
        "Propose a 14-day price, promo or bundle test from a pricing strategy; the owner decides.",
        precheck=check_experiment,
    ),
    ToolBinding(
        f"{MANIFEST.id}.score_experiment",
        score_experiment,
        ScoreInput,
        "How the running or last experiment does against its baseline.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.decide_experiment",
        decide_experiment,
        DecideInput,
        "Keep an experiment's tested price, or let it go back to the old price.",
    ),
    ToolBinding(
        CHANGE_PRICE,
        change_price,
        ChangePriceInput,
        "Change an item's price from a date; the owner decides.",
        precheck=check_price,
    ),
    ToolBinding(
        f"{MANIFEST.id}.set_short_code",
        set_short_code,
        SetShortCodeInput,
        "Add a short code staff can type for an item.",
        precheck=check_short_code,
    ),
    ToolBinding(
        f"{MANIFEST.id}.weekly_summary",
        weekly_summary,
        WeeklyInput,
        "Last week's sales against target, best and worst items, waste and the experiment.",
    ),
    ToolBinding(
        f"{MANIFEST.id}.monthly_letter",
        monthly_letter,
        MonthlyInput,
        "Last month in numbers: sales against target, best days, per clerk, experiments.",
    ),
]
