"""Inventory manager work on the tick: the closing stock summary to head staff and owners, and
the bake plan to the branch's clerks and supervisors before opening.

What is due is pure code (rule 7), on the retail template's hours helpers: the summary belongs
to the closing's business date from closes plus 45 minutes to the next opening (also after
midnight); the plan is due in the hour before an open day's opening. The summary is urgent (the
end of the shift, it goes out in quiet hours); the plan waits for quiet hours in deliver. Each
send leaves a marker event on the branch with the business date and the message ids, checked
first, so each fires at most once per branch and date; a quiet night (nothing to say) sends
no summary and leaves no marker. Each branch commits alone (alerts._each_branch). Events
reported after the summary went out but on its business date reach no summary (carried over
in the spec).
"""

import datetime as dt
from collections.abc import Callable
from zoneinfo import ZoneInfo

from sqlmodel import Session

from mia.agents.inventory_manager import MANIFEST, replies, tools
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import orgconfig
from mia.core.models import Actor, Branch, Message, Person
from mia.i18n import t
from mia.templates.retail import hours as retail_hours

SUMMARY_DELAY = dt.timedelta(minutes=45)
PLAN_LEAD = dt.timedelta(hours=1)
SUMMARY = "inventory.summary_sent"
PLAN = "inventory.plan_sent"
SUMMED = ("sold_out", "leftover", "waste")  # the day's events the summary words
Hours = retail_hours.Hours
Sender = Callable[[Session, Branch, Hours, dt.date], list[Message]]

# ---- what is due (pure) ---------------------------------------------------------------------


def closing_summary(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The business date from 45 minutes after its closing to the next opening, else None."""
    return retail_hours.after_close(branch, hours, now, SUMMARY_DELAY)


def plan_message(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """Today's date in the hour before an open day's opening (a node started later skips the
    day's message), else None."""
    local = now.astimezone(ZoneInfo(branch.timezone))
    opens = retail_hours.at(branch, hours, local.date(), closing=False)
    on = retail_hours.open_days(hours)(local.date()) and opens - PLAN_LEAD <= local < opens
    return local.date() if on else None


# ---- data -------------------------------------------------------------------------------------


def _low(session: Session, branch_id: str, day: dt.date) -> list[str]:
    """The names of the branch's ingredients low on `day` (tools.low_ids)."""
    ingredients = tools._ingredients(session, branch_id)
    return [ingredients[i].name for i in tools.low_ids(session, branch_id, day)[0]]


def _day_events(session: Session, branch_id: str, day: dt.date) -> list[tools.EventOut]:
    """The branch's sell-outs, leftovers and waste of the business date, oldest first, each
    named by its item or ingredient."""
    names = {k: v.name for k, v in tools._items(session, branch_id).items()}
    names |= {k: v.name for k, v in tools._ingredients(session, branch_id).items()}
    rows = [r for r in tools._stock_rows(session, branch_id, SUMMED) if r.business_date == day]
    return [tools._event_out(r, names.get(r.item_id or r.ingredient_id or "", "")) for r in rows]


def _leads(session: Session, branch: Branch) -> list[Person]:
    """The branch's supervisors, then the organisation's owners and admins, each once."""
    people = alerts.supervisors(session, branch.id) + alerts.leads(session, branch.organisation_id)
    return list({p.id: p for p in people}.values())


# ---- senders ------------------------------------------------------------------------------


def _send(
    session: Session, branch: Branch, person: Person, blocks: list[Block], urgent: bool
) -> Message:
    return notify(session, person, blocks, Actor.system(branch.id), MANIFEST.id, urgent=urgent)


def _summary_blocks(
    branch: Branch, events: list[tools.EventOut], low: list[str], lang: str
) -> list[Block]:
    """The summary in lang: a heading, one line per event, the low ingredients."""
    lines = [replies.event_line(e, lang, branch.timezone) for e in events]
    if low:
        lines.append(t("stock.summary.line", lang, ingredients=", ".join(low)))
    heading = t("stock.summary", lang, branch=branch.name)
    return [TextBlock(text=text) for text in (heading, *lines)]


def _summary(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    events = _day_events(session, branch.id, day)
    low = _low(session, branch.id, day)
    if not events and not low:
        return []  # a quiet night sends nothing (and leaves no marker)
    return [
        _send(session, branch, p, _summary_blocks(branch, events, low, p.language), urgent=True)
        for p in _leads(session, branch)
    ]


def _plan_sends(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    closes = retail_hours.closes(hours, day.weekday())
    lines = tools.plan_lines(session, branch.id, day - dt.timedelta(days=1), closes)
    if all(line.plan == "same" for line in lines):
        return []  # nothing to change: no message
    out = tools.PlanOutput(lines=lines).model_dump(mode="json")
    people = {p.id: p for p in alerts._people(session, branch.id, "clerk")}
    people |= {p.id: p for p in alerts.supervisors(session, branch.id)}
    return [
        _send(
            session,
            branch,
            p,
            replies.tool_reply("plan_tomorrow", out, {}, p.language, branch.timezone),
            urgent=False,
        )
        for p in people.values()
    ]


DUE: list[tuple[Callable[[Branch, Hours, dt.datetime], dt.date | None], str, Sender]] = [
    (plan_message, PLAN, _plan_sends),
    (closing_summary, SUMMARY, _summary),
]


def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    hours = retail_hours.load(session, branch.id)
    count = 0
    for is_due, marker, send in DUE:
        day = is_due(branch, hours, now)
        if day is None or alerts._marked(session, marker, branch.id, day):
            continue
        sent = send(session, branch, hours, day)
        if sent:  # the marker records a send; nothing sent is checked again on the next tick
            data = {"date": day.isoformat(), "message_ids": [m.id for m in sent]}
            alerts._mark(session, branch.id, marker, ("branch", branch.id), data)
        count += len(sent)
    return count


def run_due(session: Session, now: dt.datetime) -> int:
    """Send the inventory work due at `now` for every branch; returns how many notifications
    were sent. Each kind is sent at most once per branch and business date. Nothing runs when
    the organisation does not use the inventory manager."""
    if MANIFEST.id not in orgconfig.load().agents:
        return 0
    return alerts._each_branch(session, now, _branch_due)
