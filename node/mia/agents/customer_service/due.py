"""Customer service work on the tick: waiting orders nobody decided in time closed
(tools.close_undecided: the pickup passed or the approval's TTL did, the customer told), the
opening digest of the day's pickups to the branch's clerks and supervisors, and a reminder to
each customer an hour before their pickup.

What is due is pure code (rule 7). The digest is due in the first hour after an open day's
opening, only when the business date has confirmed or ready orders; it goes through notify
(not urgent, so its channel copies wait out quiet hours) and leaves a marker on the branch
with the date and the message ids, checked first, so it goes once per branch and date. A
reminder is due from an hour before a confirmed or ready order's pickup until the pickup,
outside quiet hours; it is queued (public.send_pending sends it, the tick awaits that after
run_due) only inside the customer's 24-hour window, else the order is marked skipped. Each
order's marker names its pickup time, so a moved pickup is reminded again. Each branch commits
alone (alerts._each_branch).
"""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.customer_service import MANIFEST, public, replies, tools
from mia.agents.customer_service.actions import STAFF_ORDER_STATUSES
from mia.agents.customer_service.models import Customer, Order
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import TextBlock
from mia.chat.channels import notify
from mia.core import events, orgconfig
from mia.core.db import utcnow
from mia.core.models import Actor, Branch, Event, Message
from mia.i18n import t
from mia.templates.retail import hours as retail_hours
from mia.templates.retail.models import RetailItem

DIGEST = f"{MANIFEST.id}.digest_sent"
REMINDER = f"{MANIFEST.id}.reminder_sent"
SKIPPED = public.SKIPPED  # customer_service.reminder_skipped
DIGEST_HOURS = dt.timedelta(hours=1)
REMIND_BEFORE = dt.timedelta(hours=1)
Hours = retail_hours.Hours

# ---- what is due (pure) ---------------------------------------------------------------------


def digest_due(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """Today's date in the first hour after an open day's opening, else None."""
    local = now.astimezone(ZoneInfo(branch.timezone))
    opens = retail_hours.at(branch, hours, local.date(), closing=False)
    on = retail_hours.open_days(hours)(local.date()) and opens <= local < opens + DIGEST_HOURS
    return local.date() if on else None


def reminder_due(order: Order, now: dt.datetime, quiet: bool) -> bool:
    """True from an hour before the pickup until the pickup, outside quiet hours."""
    return not quiet and order.pickup_at - REMIND_BEFORE <= now < order.pickup_at


# ---- data -------------------------------------------------------------------------------------


def _open_orders(session: Session, branch: Branch) -> list[tuple[Order, Customer]]:
    """The branch's confirmed and ready orders with their customers, by pickup time."""
    rows = session.exec(
        select(Order, Customer)
        .where(Order.customer_id == Customer.id)
        .where(Order.branch_id == branch.id)
        .where(col(Order.status).in_(STAFF_ORDER_STATUSES))
    ).all()
    return sorted(rows, key=lambda row: row[0].pickup_at)


def _lines(session: Session, branch: Branch, day: dt.date) -> list[str]:
    """The business date's open orders as order lines ("15:00 Mila R. (Classic x10)")."""
    tz = ZoneInfo(branch.timezone)
    names = {i.id: i.name for i in session.exec(select(RetailItem)).all()}
    return [
        replies.order_line(
            replies.hhmm(o.pickup_at, branch.timezone),
            replies.short_name(c.name),
            [(names.get(ln["item_id"], "?"), ln["quantity"]) for ln in o.lines],
        )
        for o, c in _open_orders(session, branch)
        # pickup_at is an ISO string with its own offset, so the day is compared here, not in SQL
        if o.pickup_at.astimezone(tz).date() == day
    ]


# ---- senders ------------------------------------------------------------------------------


def opening_digest(session: Session, branch: Branch, day: dt.date) -> list[Message]:
    """The day's orders to each clerk and supervisor of the branch (sensitive: customer
    names), not urgent; nothing without orders."""
    lines = _lines(session, branch, day)
    if not lines:
        return []
    people = {p.id: p for p in alerts._people(session, branch.id, "clerk")}
    people |= {p.id: p for p in alerts.supervisors(session, branch.id)}
    orders = replies.orders_line(lines)
    return [
        notify(
            session,
            p,
            [TextBlock(text=t("cs.digest", p.language, orders=orders))],
            Actor.system(branch.id),
            MANIFEST.id,
            sensitive=True,
        )
        for p in people.values()
    ]


def _reminded(session: Session, order: Order) -> bool:
    """True when the order has a reminder sent or skipped for its current pickup time."""
    rows = session.exec(
        select(Event)
        .where(col(Event.action).in_((REMINDER, SKIPPED)))
        .where(Event.entity_id == order.id)
    ).all()
    return any((r.after or {}).get("pickup_at") == order.pickup_at.isoformat() for r in rows)


def pickup_reminders(session: Session, branch: Branch, now: dt.datetime) -> int:
    """Queue cs.reminder for each open order due a reminder whose customer's window is open
    (marker REMINDER with the message id), else mark it SKIPPED; returns how many were
    queued. The marker is written with the queued row, in the branch's commit."""
    quiet = orgconfig.load().quiet_hours.contains(
        now.astimezone(ZoneInfo(branch.timezone)).time().replace(tzinfo=None)
    )
    count = 0
    for order, customer in _open_orders(session, branch):
        if not reminder_due(order, now, quiet) or _reminded(session, order):
            continue
        actor = public.customer_actor(customer)
        data: dict[str, object] = {"pickup_at": order.pickup_at.isoformat()}
        if not public.window_open(customer.last_inbound_at, now):
            events.emit(session, SKIPPED, ("order", order.id), None, data, actor)
            continue
        time = replies.hhmm(order.pickup_at, branch.timezone)
        text = t("cs.reminder", customer.language, time=time)
        row = public.queue(session, customer, [TextBlock(text=text)], actor)
        events.emit(
            session, REMINDER, ("order", order.id), None, data | {"message_id": row.id}, actor
        )
        count += 1
    return count


def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    count = tools.close_undecided(session, branch, now)
    count += pickup_reminders(session, branch, now)
    day = digest_due(branch, retail_hours.load(session, branch.id), now)
    if day is None or alerts._marked(session, DIGEST, branch.id, day):
        return count
    sent = opening_digest(session, branch, day)
    if sent:  # the marker records a send; a day without orders is checked again next tick
        data = {"date": day.isoformat(), "message_ids": [m.id for m in sent]}
        alerts._mark(session, branch.id, DIGEST, ("branch", branch.id), data)
        count += 1
    return count


def run_due(session: Session, now: dt.datetime | None = None) -> int:
    """Run the customer service's due work at `now` for every branch; returns how many waiting
    orders were closed, digests sent and reminders queued. Nothing runs when the organisation
    does not use the customer service."""
    if not public.runs():
        return 0
    return alerts._each_branch(session, now or utcnow(), _branch_due)
