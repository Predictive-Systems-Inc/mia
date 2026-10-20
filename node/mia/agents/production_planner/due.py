"""The production planner's work on the tick: the draft plan to the commissary's head, the
dispatch list at dispatch_at, the receipt match at each served kiosk and the closing yield.

What is due is pure code (rule 7): each window takes the branch, the settings or the kiosk's
hours, and `now`, and names the date the work is for. Markers: the plan row is the draft's (a
row exists, nothing is drafted); the dispatch rows are the dispatch's; a dispatch's status past
delivered is its match's; `{id}.yield_sent` per commissary and date is the closing yield's,
written with its send. Nothing is sent when there is nothing to say: no plan, no batch, a full
receipt. Only the dispatch list is urgent. Each branch commits alone (alerts._each_branch).
"""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.production_planner import MANIFEST, replies, tools, turn
from mia.agents.production_planner.models import Dispatch
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import orgconfig
from mia.core.db import utcnow
from mia.core.models import Actor, Branch, Message, Person
from mia.core.orgconfig import ProductionPlannerSettings
from mia.core.rbac import get_rbac
from mia.i18n import t
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailItem

HOUR = dt.timedelta(hours=1)
ONE_DAY = dt.timedelta(days=1)
YIELD_SENT = f"{MANIFEST.id}.yield_sent"
Hours = retail_hours.Hours

# ---- what is due (pure) ---------------------------------------------------------------------


def _local(branch: Branch, now: dt.datetime) -> dt.datetime:
    return now.astimezone(ZoneInfo(branch.timezone))


def draft_due(commissary: Branch, s: ProductionPlannerSettings, now: dt.datetime) -> dt.date | None:
    """The production date whose draft is due: from plan_at on day D the date D + 1, from 00:00
    to hours.start the date D (a node down at plan_at drafts that morning's), else None."""
    local = _local(commissary, now)
    if local.time() >= s.plan_at:
        return local.date() + ONE_DAY
    return local.date() if local.time() < s.hours.start else None


def dispatch_due(
    commissary: Branch, s: ProductionPlannerSettings, now: dt.datetime
) -> dt.date | None:
    """The local date from dispatch_at to the end of that day, else None."""
    local = _local(commissary, now)
    return local.date() if local.time() >= s.dispatch_at else None


def match_due(kiosk: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The kiosk's date on an open day from its opening plus an hour to its closing, else None."""
    local = _local(kiosk, now)
    day = local.date()
    opens = retail_hours.at(kiosk, hours, day, closing=False)
    closes = retail_hours.at(kiosk, hours, day, closing=True)
    on = retail_hours.open_days(hours)(day) and opens + HOUR <= local < closes
    return day if on else None


def yield_due(commissary: Branch, s: ProductionPlannerSettings, now: dt.datetime) -> dt.date | None:
    """The production date from an hour after the end of production to plan_at, else None."""
    local = _local(commissary, now)
    end = (dt.datetime.combine(local.date(), s.hours.end) + HOUR).time()
    return local.date() if end <= local.time() < s.plan_at else None


def arrived(commissary: Branch, s: ProductionPlannerSettings, row: Dispatch) -> dt.datetime:
    """When the dispatch reached the kiosk: its delivered_at, else dispatch_at of its date at
    the commissary. A match waits an hour past it too, so a kiosk that opens early is not
    told of a gap before its delivery."""
    if row.delivered_at is not None:
        return row.delivered_at
    return dt.datetime.combine(row.business_date, s.dispatch_at, ZoneInfo(commissary.timezone))


# ---- helpers ------------------------------------------------------------------------------


def _lang(person: Person) -> str:
    return person.language or "en"


def names(session: Session, organisation_id: str) -> dict[str, str]:
    """Item and branch names by id (the replies' names)."""
    items = {i.id: i.name for i in session.exec(select(RetailItem))}
    stmt = select(Branch).where(Branch.organisation_id == organisation_id)
    return items | {b.id: b.name for b in session.exec(stmt)}


def _send(session: Session, branch: Branch, person: Person, blocks: list[Block]) -> Message:
    return notify(session, person, blocks, Actor.system(branch.id), MANIFEST.id)


def _commissary(session: Session, s: ProductionPlannerSettings) -> Branch | None:
    if not s.commissary:
        return None
    return session.exec(select(Branch).where(Branch.name == s.commissary)).first()


# ---- senders ------------------------------------------------------------------------------


def _draft(session: Session, commissary: Branch, day: dt.date) -> int:
    """The draft plan of day (tools.draft_plan) to the commissary's supervisors as the plan
    card with its Confirm button, not urgent. Nothing when the plan row exists."""
    if tools.plan_for(session, commissary.id, day) is not None:
        return 0
    out = tools.plan_out(session, tools.draft_plan(session, commissary, day))
    by_id, actor = names(session, commissary.organisation_id), Actor.system(commissary.id)
    people = alerts.supervisors(session, commissary.id)
    for person in people:
        blocks, options = replies.plan_card(out, by_id, _lang(person))
        turn.remember(session, _send(session, commissary, person, blocks), options, actor)
    return len(people)


def _dispatch(session: Session, commissary: Branch, day: dt.date) -> int:
    """The plan of day packed by the agent alone (tools.pack: the planned yield for batches not
    recorded) and each kiosk's list sent (tools.send_dispatch). Nothing without a plan or when
    it is packed."""
    plan = tools.plan_for(session, commissary.id, day)
    if plan is None:
        return 0
    if session.exec(select(Dispatch.id).where(Dispatch.plan_id == plan.id)).first() is not None:
        return 0
    agent = tools.agent_actor(commissary.id)
    get_rbac().require(agent, tools.DISPATCHES, "write_all", session=session)
    return len(tools.send_dispatch(session, commissary, tools.pack(session, plan, agent)))


def _short_text(session: Session, kiosk: Branch, row: Dispatch, lang: str) -> str:
    items = {i.id: i.name for i in session.exec(select(RetailItem))}
    got = {x["item_id"]: x["quantity"] for x in row.received or []}
    lines = [
        t(
            "pp.short.line",
            lang,
            kiosk=kiosk.name,
            item=items.get(x["item_id"], ""),
            sent=x["quantity"],
            received=got.get(x["item_id"], 0),
        )
        for x in row.lines
        if got.get(x["item_id"], 0) != x["quantity"]
    ]
    return "\n".join([t("pp.short.head", lang, date=row.business_date.isoformat()), *lines])


def _match(
    session: Session, commissary: Branch, kiosk: Branch, day: dt.date, now: dt.datetime
) -> int:
    """The kiosk's packed or delivered dispatches of day matched with its receipts (tools.match
    by the agent alone) once an hour has passed since they arrived; a short one (no receipt at all included) goes to the
    commissary's supervisors and the leads, not urgent. A full receipt is quiet."""
    stmt = (
        select(Dispatch)
        .where(Dispatch.branch_id == kiosk.id)
        .where(Dispatch.business_date == day)
        .where(col(Dispatch.status).in_(("packed", "delivered")))
    )
    rows = list(session.exec(stmt))
    if not rows:
        return 0
    agent = tools.agent_actor(kiosk.id)
    get_rbac().require(agent, tools.DISPATCHES, "write_all", session=session)
    people = alerts.supervisors(session, commissary.id) + alerts.leads(
        session, commissary.organisation_id
    )
    to = list({p.id: p for p in people}.values())
    settings = orgconfig.load().production_planner
    count = 0
    for row in rows:
        if now < arrived(commissary, settings, row) + HOUR:
            continue
        if tools.match(session, row, now, agent) != "short":
            continue
        for person in to:
            text = _short_text(session, kiosk, row, _lang(person))
            _send(session, commissary, person, [TextBlock(text=text)])
            count += 1
    return count


def _yield(session: Session, commissary: Branch, day: dt.date) -> int:
    """The day's yield (tools.day_yield) to the commissary's supervisors once, its marker
    written with the send. Nothing without a batch."""
    if alerts._marked(session, YIELD_SENT, commissary.id, day):
        return 0
    out = tools.day_yield(session, commissary, day)
    if not out.items:
        return 0
    by_id = names(session, commissary.organisation_id)
    sent = [
        _send(session, commissary, p, [TextBlock(text=replies.yield_text(out, by_id, _lang(p)))])
        for p in alerts.supervisors(session, commissary.id)
    ]
    if sent:
        data = {"date": day.isoformat(), "message_ids": [m.id for m in sent]}
        alerts._mark(session, commissary.id, YIELD_SENT, ("branch", commissary.id), data)
    return len(sent)


# ---- the tick -------------------------------------------------------------------------------


def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    s = orgconfig.load().production_planner
    commissary = _commissary(session, s)
    if commissary is None or commissary.organisation_id != branch.organisation_id:
        return 0
    if branch.id == commissary.id:
        count = 0
        if (day := draft_due(branch, s, now)) is not None:
            count += _draft(session, branch, day)
        if (day := dispatch_due(branch, s, now)) is not None:
            count += _dispatch(session, branch, day)
        if (day := yield_due(branch, s, now)) is not None:
            count += _yield(session, branch, day)
        return count
    if branch.id not in {k.id for k in tools.served(session, commissary)}:
        return 0
    day = match_due(branch, retail_hours.load(session, branch.id), now)
    return 0 if day is None else _match(session, commissary, branch, day, now)


def run_due(session: Session, now: dt.datetime | None = None) -> int:
    """Run the planner's due work at `now` for every branch; returns how many notifications were
    sent. Nothing runs when the organisation does not use the production planner."""
    if MANIFEST.id not in orgconfig.load().agents:
        return 0
    return alerts._each_branch(session, now or utcnow(), _branch_due)
