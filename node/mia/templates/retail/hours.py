"""Opening hours of a retail branch as pure functions over its retail_branch_hours rows, and the
business date they give. Shared by the agents that work to a shop's hours; imports nothing from
mia.agents. Only load(), is_shop(), shops() and closed() read the database, unchecked: callers check
retail_branch_hours (or retail_closures) read first, or are the system tick.
"""

import datetime as dt
from collections.abc import Callable, Collection, Sequence
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.core.models import Branch
from mia.templates.retail.models import RetailBranchHours, RetailClosure

DEFAULT_OPENS = dt.time(9, 0)
DEFAULT_CLOSES = dt.time(21, 0)
NO_HOURS_WINDOW = dt.timedelta(hours=6)  # after-close work of a branch without hours
AFTER_CLOSING = dt.timedelta(hours=2)  # a report this soon after a late closing is that day's
Hours = Sequence[RetailBranchHours]


def load(session: Session, branch_id: str) -> list[RetailBranchHours]:
    """The branch's hours rows (no permission check; see the module docstring)."""
    stmt = select(RetailBranchHours).where(RetailBranchHours.branch_id == branch_id)
    return list(session.exec(stmt))


def is_shop(session: Session, branch_id: str) -> bool:
    """True when the branch sells (it has hours rows); a commissary has none, so the kiosk
    agents' due work skips it (no permission check; see the module docstring)."""
    stmt = select(RetailBranchHours.id).where(RetailBranchHours.branch_id == branch_id).limit(1)
    return session.exec(stmt).first() is not None


def shops(session: Session, organisation_id: str) -> list[Branch]:
    """The organisation's branches that sell (is_shop), by name: an owner's "every branch"
    never lists the commissary (no permission check; see the module docstring)."""
    selling = select(RetailBranchHours.branch_id)
    stmt = (
        select(Branch)
        .where(Branch.organisation_id == organisation_id)
        .where(col(Branch.id).in_(selling))
    )
    return list(session.exec(stmt.order_by(col(Branch.name))))


def closed(session: Session, branch_id: str) -> frozenset[dt.date]:
    """The branch's closed dates (no permission check; see the module docstring)."""
    stmt = select(RetailClosure).where(RetailClosure.branch_id == branch_id)
    return frozenset(row.date for row in session.exec(stmt))


def closes(hours: Hours, weekday: int) -> dt.time:
    """The closing time on the weekday, 21:00 when no hours are set for it."""
    row = next((h for h in hours if h.weekday == weekday), None)
    return dt.time.fromisoformat(row.closes) if row else DEFAULT_CLOSES


def opens(hours: Hours, weekday: int) -> dt.time:
    """The opening time on the weekday, 09:00 when no hours are set for it."""
    row = next((h for h in hours if h.weekday == weekday), None)
    return dt.time.fromisoformat(row.opens) if row else DEFAULT_OPENS


def open_days(hours: Hours, closed: Collection[dt.date] = frozenset()) -> Callable[[dt.date], bool]:
    """A weekday is open when the branch has hours for it (a branch without hours is always
    open), except on a `closed` date."""
    weekdays = {h.weekday for h in hours} or set(range(7))
    return lambda day: day.weekday() in weekdays and day not in closed


def at(branch: Branch, hours: Hours, day: dt.date, closing: bool) -> dt.datetime:
    """The opening (or closing) of `day` as an aware local time; 09:00 and 21:00 without a row."""
    when = (closes if closing else opens)(hours, day.weekday())
    return dt.datetime.combine(day, when, ZoneInfo(branch.timezone))


def window_end(branch: Branch, hours: Hours, day: dt.date) -> dt.datetime:
    """When the after-close work of `day` stops: the next open day's opening, or six hours
    after closing for a branch without hours."""
    if not hours:
        return at(branch, hours, day, closing=True) + NO_HOURS_WINDOW
    is_open = open_days(hours)
    nxt = next(d for k in range(1, 8) if is_open(d := day + dt.timedelta(days=k)))
    return at(branch, hours, nxt, closing=False)


def after_close(
    branch: Branch, hours: Hours, now: dt.datetime, delay: dt.timedelta
) -> dt.date | None:
    """The business date (today or yesterday, local) whose closing plus delay has passed and
    whose window has not ended; None when there is none. Crosses midnight."""
    local = now.astimezone(ZoneInfo(branch.timezone))
    is_open = open_days(hours)
    for day in (local.date(), local.date() - dt.timedelta(days=1)):
        start = at(branch, hours, day, closing=True) + delay
        if is_open(day) and start <= local < window_end(branch, hours, day):
            return day
    return None


def business_date(
    reported_at: dt.datetime, tz: str, opens: dt.time, closed_yesterday: dt.time
) -> dt.date:
    """The business date a report at `reported_at` belongs to: the day before the local date in
    `tz` when it is before today's opening `opens` and within two hours after the day before's
    closing `closed_yesterday` (a late closing, reported after midnight); else the local date.
    Never asks."""
    local = reported_at.astimezone(ZoneInfo(tz))
    day = local.date()
    yesterday = day - dt.timedelta(days=1)
    closed_at = dt.datetime.combine(yesterday, closed_yesterday, local.tzinfo)
    opened_at = dt.datetime.combine(day, opens, local.tzinfo)
    return yesterday if local < opened_at and local < closed_at + AFTER_CLOSING else day


def business_date_at(branch: Branch, hours: Hours, at_: dt.datetime) -> dt.date:
    """business_date at `at_` with the branch's hours (today's opening, yesterday's closing)."""
    weekday = at_.astimezone(ZoneInfo(branch.timezone)).weekday()
    return business_date(
        at_, branch.timezone, opens(hours, weekday), closes(hours, (weekday - 1) % 7)
    )
