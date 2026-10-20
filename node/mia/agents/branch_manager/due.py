"""The branch manager's work on the tick: the experiment tick (prices due, experiments started,
ended and scored), the morning message to each clerk on shift (yesterday's branch total, today's
target, one tip and one quote), cheers and one kind nudge after the closing, the experiment's
start and result to the leads and the requester, the weekly summary on Monday (the first open
day after a closed one) and the monthly numbers letter on the month's first open day.

What is due is pure code (rule 7): the window functions take the branch, its hours rows and
`now` and return the business date the work is due for, or None. After-close work keeps the
closing's business date after midnight (retail_hours.after_close). Every number is code: the
day share (the sales supervisor's _share: the owner's target wins, a day target beats a month
target), the personal best (calc.personal_best over the clerk's own amounts), the nudge
(calc.nudge_due), the tip rotation (calc.pick_tip). Tips and quotes come only from
branch_manager_tips rows; a person with every tip given within 30 days gets no tip line.

Markers: one Coaching row per person and day for the morning message, a cheer and a nudge
(and one per tip or quote given), written with the send; `{id}.weekly_sent` per branch and
Monday, `{id}.monthly_sent` per branch and month. Cheers and nudges are urgent (a branch may
close as quiet hours start); the morning message, the weekly and the monthly wait out quiet
hours in deliver. Nothing is sent with nothing to say. An experiment's result goes with Keep and
Revert buttons, stored as decisions (decision.clarify_asked) the turn validates, to whoever may
decide it; an unkept experiment reverts at the next opening (items.apply_due in the experiment
tick). Each branch commits alone (alerts._each_branch). The weekly and the monthly run the
tools as each recipient, so rbac decides what they read.
"""

import datetime as dt
from collections.abc import Sequence

from sqlmodel import Session, col, or_, select

from mia.agents.base import AgentDeps
from mia.agents.branch_manager import MANIFEST, calc, replies, tools
from mia.agents.branch_manager.models import Coaching, Experiment, Strategy, Tip
from mia.agents.sales_supervisor import due as sales_due
from mia.agents.sales_supervisor import tools as sales_tools
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import Block, QuickRepliesBlock, TextBlock
from mia.chat.channels import notify
from mia.core import events, orgconfig, store
from mia.core.db import utcnow
from mia.core.ids import new_id
from mia.core.models import Actor, Branch, Message, Person
from mia.core.money import format_money
from mia.core.rbac import PermissionDenied, Resource, get_rbac
from mia.i18n import t
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailItem

HOUR = dt.timedelta(hours=1)
WEEKLY = f"{MANIFEST.id}.weekly_sent"
MONTHLY = f"{MANIFEST.id}.monthly_sent"
NUDGE_LOOKBACK = 14  # days searched for the last open days with counts and a target
DECIDE = Resource(kind="tool", name=f"{MANIFEST.id}.decide_experiment")
Hours = retail_hours.Hours

# ---- what is due (pure) ---------------------------------------------------------------------


def morning_message(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """Today's date in the first hour after an open day's opening, else None."""
    return sales_due.morning_message(branch, hours, now)


def closing(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The business date from an hour after its closing to its window's end (past midnight)."""
    return retail_hours.after_close(branch, hours, now, HOUR)


def weekly(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The date of the week's first open day (Monday, or the first open day after a closed
    Monday) in its morning window, else None."""
    day = morning_message(branch, hours, now)
    if day is None:
        return None
    is_open = retail_hours.open_days(hours)
    earlier = (day - dt.timedelta(days=k) for k in range(1, day.weekday() + 1))
    return None if any(is_open(d) for d in earlier) else day


def monthly(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The date of the month's first open day in its morning window, else None."""
    day = morning_message(branch, hours, now)
    if day is None:
        return None
    is_open = retail_hours.open_days(hours)
    earlier = (day.replace(day=1) + dt.timedelta(days=k) for k in range(day.day - 1))
    return None if any(is_open(d) for d in earlier) else day


# ---- helpers ------------------------------------------------------------------------------


def _lang(person: Person) -> str:
    return person.language or tools.DEFAULT_LANGUAGE


def _send(
    session: Session, branch: Branch, person: Person, blocks: list[Block], urgent: bool = False
) -> Message:
    return notify(session, person, blocks, Actor.system(branch.id), MANIFEST.id, urgent=urgent)


def _coached(
    session: Session,
    branch: Branch,
    person: Person,
    kind: str,
    action: str,
    day: dt.date,
    message: Message,
    tip_id: str | None = None,
) -> None:
    """The Coaching row of a send (the per person and day marker), event `{id}.<action>`."""
    row = Coaching(
        branch_id=branch.id,
        person_id=person.id,
        kind=kind,
        sent_on=day,
        tip_id=tip_id,
        message_id=message.id,
    )
    store.insert(session, row, Actor.system(branch.id), action=f"{MANIFEST.id}.{action}")


def _rows(session: Session, person_id: str, kind: str | None = None) -> list[Coaching]:
    stmt = select(Coaching).where(Coaching.person_id == person_id)
    if kind is not None:
        stmt = stmt.where(Coaching.kind == kind)
    return list(session.exec(stmt))


def _had(session: Session, person_id: str, kind: str, day: dt.date) -> bool:
    return any(r.sent_on == day for r in _rows(session, person_id, kind))


def _deps(session: Session, person: Person, branch: Branch, day: dt.date) -> AgentDeps:
    """The recipient acting on the branch's business date, so the tools' rbac checks apply."""
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=day,
        lang=_lang(person),
        manifest=MANIFEST,
    )


def names(session: Session, organisation_id: str) -> dict[str, str]:
    """The organisation's branch, person and item ids to names, for the replies (ids are
    ULIDs, never shared); shared with turn. Reads only the organisation's rows (an item is
    the organisation's when it has no branch or one of its branches)."""
    branches = {
        b.id: b.name
        for b in session.exec(select(Branch).where(Branch.organisation_id == organisation_id))
    }
    here = col(Person.branch_id).in_(list(branches))
    out = {p.id: p.name for p in session.exec(select(Person).where(here))}
    mine = or_(col(RetailItem.branch_id).in_(list(branches)), col(RetailItem.branch_id).is_(None))
    out |= {i.id: i.name for i in session.exec(select(RetailItem).where(mine))}
    return out | branches


def _once_each(people: Sequence[Person]) -> list[Person]:
    return list({p.id: p for p in people}.values())


# ---- the morning message ------------------------------------------------------------------


def _pick(session: Session, person: Person, kind: str, day: dt.date) -> Tip | None:
    """A general tip or quote in the person's language (English rows when it has none), not
    given to them within calc.TIP_DAYS (calc.pick_tip); None when every one was."""
    rows = tools._tips(session, _lang(person), kind) or tools._tips(
        session, tools.DEFAULT_LANGUAGE, kind
    )
    given: dict[str, dt.date] = {}
    for c in _rows(session, person.id):
        if c.tip_id is not None:
            given[c.tip_id] = max(given.get(c.tip_id, c.sent_on), c.sent_on)
    picked = calc.pick_tip([calc.TipRef(r.id, r.kind, r.item_id) for r in rows], given, day)
    return next((r for r in rows if r.id == picked), None)


def morning_text(
    lang: str, yesterday: str | None, target: str | None, tip: Tip | None, quote: Tip | None
) -> str | None:
    """The morning words: yesterday's total and today's target (or what is missing), the tip
    and the quote with its source, each line only when it has a row; None with nothing to
    say."""
    if tip is None and quote is None and yesterday is None and target is None:
        return None
    values = {
        "yesterday": yesterday or t("bm.morning.no_counts", lang),
        "target": target or t("bm.morning.no_target", lang),
    }
    if tip is not None and quote is not None:
        return t("bm.morning", lang, tip=tip.text, quote=quote.text, source=quote.source, **values)
    if quote is not None:
        return t("bm.morning.no_tip", lang, quote=quote.text, source=quote.source, **values)
    if tip is not None:
        return t("bm.morning.no_quote", lang, tip=tip.text, **values)
    return t("bm.morning.result", lang, **values)


def _morning(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    """The morning message to each clerk on shift without one today, its Coaching rows (the
    morning marker, the tip and the quote given) written with the send."""
    yesterday = day - dt.timedelta(days=1)
    counted = retail_hours.open_days(hours)(yesterday) and sales_due._reporters(
        session, branch.id, yesterday
    )
    total = sales_due._total(session, branch.id, yesterday) if counted else None
    share = sales_tools._share(session, branch.id, hours, day)
    currency = sales_tools._currency(session, branch.id)
    sent = []
    for person in sales_due._clerks(session, branch.id, day):
        if _had(session, person.id, "morning", day):
            continue
        lang = _lang(person)
        tip, quote = _pick(session, person, "tip", day), _pick(session, person, "quote", day)
        text = morning_text(
            lang,
            None if total is None else format_money(total, currency, lang),
            None if share is None else format_money(share, currency, lang),
            tip,
            quote,
        )
        if text is None:
            continue
        message = _send(session, branch, person, [TextBlock(text=text)])
        _coached(session, branch, person, "morning", "morning_sent", day, message)
        for row in (tip, quote):
            if row is not None:
                _coached(session, branch, person, "tip", "tip_given", day, message, row.id)
        sent.append(message)
    return sent


# ---- cheers and nudges --------------------------------------------------------------------


def _amounts(session: Session, branch_id: str, person_id: str, day: dt.date) -> dict[dt.date, int]:
    """The person's own live amounts per business date in the calc.BEST_DAYS before day and
    on it."""
    rows = sales_tools._live_counts(
        session, [branch_id], day - dt.timedelta(days=calc.BEST_DAYS), day
    )
    out: dict[dt.date, int] = {}
    for r in rows:
        if r.reported_by == person_id:
            out[r.business_date] = out.get(r.business_date, 0) + r.amount
    return out


def _missed(session: Session, branch: Branch, hours: Hours, day: dt.date, after: int) -> list[bool]:
    """Oldest first, for the last `after` open days up to day with counts and a target (within
    NUDGE_LOOKBACK days): whether the branch total missed the day share."""
    is_open = retail_hours.open_days(hours)
    out: list[bool] = []
    for k in range(NUDGE_LOOKBACK):
        d = day - dt.timedelta(days=k)
        share = sales_tools._share(session, branch.id, hours, d)
        if not is_open(d) or share is None or not sales_due._reporters(session, branch.id, d):
            continue
        out.append(sales_due._total(session, branch.id, d) < share)
        if len(out) == after:
            break
    return out[::-1]


def _cheer_text(met: bool, best: int | None, currency: str, lang: str) -> str | None:
    if met:
        return t("bm.cheer.target", lang)
    if best is not None:
        return t("bm.cheer.best", lang, amount=format_money(best, currency, lang))
    return None


def _evening(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    """For each reporter of the day (owners and admins aside), once per day each: a cheer when
    the branch met its day share or the day is their personal best, and a kind nudge when the
    branch missed its last nudge_after_misses day shares (calc.nudge_due). Both urgent."""
    reporters = [
        session.get(Person, pid) for pid in sorted(sales_due._reporters(session, branch.id, day))
    ]
    people = [
        p
        for p in reporters
        if p is not None and p.status == "active" and not sales_tools._is_lead(p)
    ]
    if not people:
        return []
    share = sales_tools._share(session, branch.id, hours, day)
    met = share is not None and sales_due._total(session, branch.id, day) >= share
    currency = sales_tools._currency(session, branch.id)
    after = orgconfig.load().branch_manager.nudge_after_misses
    missed = _missed(session, branch, hours, day, after)
    sent = []
    for person in people:
        lang = _lang(person)
        amounts = _amounts(session, branch.id, person.id, day)
        best = amounts[day] if calc.personal_best(amounts, day) else None
        text = _cheer_text(met, best, currency, lang)
        if text is not None and not _had(session, person.id, "cheer", day):
            message = _send(session, branch, person, [TextBlock(text=text)], urgent=True)
            _coached(session, branch, person, "cheer", "cheered", day, message)
            sent.append(message)
        nudges = [r.sent_on for r in _rows(session, person.id, "nudge")]
        if calc.nudge_due(missed, max(nudges, default=None), day, after):
            message = _send(session, branch, person, [TextBlock(text=t("bm.nudge", lang))], True)
            _coached(session, branch, person, "nudge", "nudged", day, message)
            sent.append(message)
    return sent


# ---- experiments --------------------------------------------------------------------------


def _told(session: Session, row: Experiment) -> list[Person]:
    """The organisation's leads and the experiment's requester, each once."""
    branch = session.get(Branch, row.branch_id)
    leads = alerts.leads(session, branch.organisation_id) if branch is not None else []
    requester = session.get(Person, row.proposed_by)
    found = [*leads, *([requester] if requester is not None else [])]
    return _once_each([p for p in found if p.status == "active"])


def _ended(session: Session, branch: Branch, row: Experiment, person: Person) -> Message:
    """The result naming the strategy and the item; Keep and Revert buttons, stored as the
    decisions a tap runs (decision.clarify_asked), for a person who may decide it."""
    lang = _lang(person)
    strategy = session.get(Strategy, row.strategy_id)
    item = session.get(RetailItem, row.item_id)
    result = row.result or {}
    text = replies.score_text(
        result.get("units_pct"),
        result.get("amount_pct"),
        int(result.get("days") or 0),
        True,
        t(strategy.name_key, lang) if strategy is not None else "",
        item.name if item is not None else "",
        lang,
    )
    agent = Actor.person(person).as_agent(MANIFEST.roles.agent_role)
    if not get_rbac().check(agent, DECIDE, "execute"):
        return _send(session, branch, person, [TextBlock(text=text)])
    options = replies.keep_or_revert(row, lang)
    blocks: list[Block] = [
        TextBlock(text=text),
        TextBlock(text=t("bm.experiment.decide", lang)),
        QuickRepliesBlock(options=list(options)),
    ]
    message = _send(session, branch, person, blocks)
    after = {"options": options, "message_id": message.id}
    thread = ("thread", message.thread_id)
    events.emit(session, "decision.clarify_asked", thread, None, after, Actor.system(branch.id))
    return message


def _started(session: Session, branch: Branch, row: Experiment, person: Person) -> Message:
    lang = _lang(person)
    strategy = session.get(Strategy, row.strategy_id)
    item = session.get(RetailItem, row.item_id)
    text = t(
        "bm.experiment.started",
        lang,
        strategy=t(strategy.name_key, lang) if strategy is not None else "",
        item=item.name if item is not None else "",
        price=format_money(row.to_price, row.currency, lang),
        end=row.ends_on.isoformat(),
    )
    return _send(session, branch, person, [TextBlock(text=text)])


def _experiments(session: Session, branch: Branch, hours: Hours, now: dt.datetime) -> int:
    """The experiment tick, then each start and end told to the leads and the requester."""
    count = 0
    for kind, row in tools.experiment_tick(session, branch, hours, now):
        tell = _started if kind == "started" else _ended
        count += len([tell(session, branch, row, p) for p in _told(session, row)])
    return count


# ---- the weekly summary and the monthly letter --------------------------------------------


def _weekly(session: Session, branch: Branch, day: dt.date) -> list[Message]:
    """Last week's summary of the branch (tools.weekly_summary as each recipient) to its
    supervisors and the organisation's leads; a person the tool denies is skipped."""
    people = alerts.supervisors(session, branch.id) + alerts.leads(session, branch.organisation_id)
    names_ = names(session, branch.organisation_id)
    currency = sales_tools._currency(session, branch.id)
    last_monday = day - dt.timedelta(days=day.weekday() + 7)  # day may follow a closed Monday
    args = tools.WeeklyInput(branch_id=branch.id, week_start=last_monday)
    sent = []
    for person in _once_each(people):
        try:
            out = tools.weekly_summary(_deps(session, person, branch, day), args, new_id())
        except PermissionDenied:
            continue
        blocks = replies.weekly(out, names_, currency, _lang(person))
        sent.append(_send(session, branch, person, blocks))
    return sent


def _monthly(session: Session, branch: Branch, day: dt.date) -> list[Message]:
    """Last month's numbers letter of the branch (tools.monthly_letter as each lead)."""
    month = day.replace(day=1) - dt.timedelta(days=1)
    args = tools.MonthlyInput(month=month.replace(day=1))
    names_ = names(session, branch.organisation_id)
    sent = []
    for person in alerts.leads(session, branch.organisation_id):
        try:
            out = tools.monthly_letter(_deps(session, person, branch, day), args, new_id())
        except PermissionDenied:
            continue
        sent.append(_send(session, branch, person, replies.monthly(out, names_, _lang(person))))
    return sent


def _branch_marked(
    session: Session, branch: Branch, marker: str, on: dt.date, sent: list[Message]
) -> int:
    if sent:  # nothing sent leaves no marker: checked again on the next tick
        data = {"date": on.isoformat(), "message_ids": [m.id for m in sent]}
        alerts._mark(session, branch.id, marker, ("branch", branch.id), data)
    return len(sent)


# ---- the tick -------------------------------------------------------------------------------


def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    if not retail_hours.is_shop(session, branch.id):  # the commissary sells nothing
        return 0
    hours = retail_hours.load(session, branch.id)
    count = _experiments(session, branch, hours, now)  # prices due first, at the opening
    day = morning_message(branch, hours, now)
    if day is not None:
        count += len(_morning(session, branch, hours, day))
    day = closing(branch, hours, now)
    if day is not None:
        count += len(_evening(session, branch, hours, day))
    day = weekly(branch, hours, now)
    if day is not None and not alerts._marked(session, WEEKLY, branch.id, day):
        count += _branch_marked(session, branch, WEEKLY, day, _weekly(session, branch, day))
    day = monthly(branch, hours, now)
    if day is not None and not alerts._marked(session, MONTHLY, branch.id, day.replace(day=1)):
        sent = _monthly(session, branch, day)
        count += _branch_marked(session, branch, MONTHLY, day.replace(day=1), sent)
    return count


def run_due(session: Session, now: dt.datetime | None = None) -> int:
    """Run the branch manager's due work at `now` for every branch; returns how many
    notifications were sent. Nothing runs when the organisation does not use the branch
    manager."""
    if MANIFEST.id not in orgconfig.load().agents:
        return 0
    return alerts._each_branch(session, now or utcnow(), _branch_due)
