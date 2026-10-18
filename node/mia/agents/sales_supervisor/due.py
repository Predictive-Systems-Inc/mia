"""Sales supervisor work on the tick: the closing reminder to clerks without counts, the missing
list to head staff, the owner's end-of-day report, the morning message and the why question.

What is due is pure code (rule 7): the five window functions take the branch, its hours rows
and `now`, and return a bool. The senders load rows and send through notify, so quiet hours
apply in deliver. Each send leaves a marker event on the branch with the business date (and
the message ids), checked first, so each fires at most once per branch and date. Each branch
commits alone and a failing branch never silences the others (alerts._each_branch).
"""

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.sales_supervisor import MANIFEST, actions, calc, replies, tools
from mia.agents.sales_supervisor.models import SalesTarget
from mia.agents.shift_supervisor import alerts
from mia.agents.shift_supervisor.classifier import EN_WEEKDAYS
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import orgconfig
from mia.core.models import Actor, Branch, Message, Person, Visit
from mia.core.money import format_int, format_money
from mia.i18n import t
from mia.templates.retail.models import RetailBranchHours

DEFAULT_OPENS = dt.time(9, 0)
HALF_HOUR = dt.timedelta(minutes=30)
HOUR = dt.timedelta(hours=1)
GOOD_DAY_PERCENT = 20  # without a target, a day this much above the 4-week average is good
REMINDER = "sales.reminder_sent"
MISSING = "sales.missing_sent"
REPORT = "sales.report_sent"
MORNING = "sales.morning_sent"
WHY = "sales.why_asked"
Hours = Sequence[RetailBranchHours]
Sender = Callable[[Session, Branch, Hours, dt.date], list[Message]]

# ---- what is due (pure) ---------------------------------------------------------------------


def _times(branch: Branch, hours: Hours, now: dt.datetime) -> tuple[dt.datetime, ...]:
    """(local now, opening, closing) on the branch's local date; 09:00 and 21:00 without a row.
    ponytail: a closing near midnight puts the after-close windows on the next date, where they
    never fire; handle it when a branch closes after 22:30."""
    local = now.astimezone(ZoneInfo(branch.timezone))
    row = next((h for h in hours if h.weekday == local.weekday()), None)
    opens = dt.time.fromisoformat(row.opens) if row else DEFAULT_OPENS
    closes = tools._closes(hours, local.weekday())
    day, tz = local.date(), local.tzinfo
    return local, dt.datetime.combine(day, opens, tz), dt.datetime.combine(day, closes, tz)


def closing_reminder(branch: Branch, hours: Hours, now: dt.datetime) -> bool:
    """True in the half hour before closing."""
    local, _, closes = _times(branch, hours, now)
    return closes - HALF_HOUR <= local < closes


def missing_list(branch: Branch, hours: Hours, now: dt.datetime) -> bool:
    """True from half an hour after closing to the end of the local day."""
    local, _, closes = _times(branch, hours, now)
    return closes + HALF_HOUR <= local


def owner_report(branch: Branch, hours: Hours, now: dt.datetime) -> bool:
    """True from an hour after closing to the end of the local day."""
    local, _, closes = _times(branch, hours, now)
    return closes + HOUR <= local


def why_question(branch: Branch, hours: Hours, now: dt.datetime) -> bool:
    """True when the report is due: the question is asked at the same time."""
    return owner_report(branch, hours, now)


def morning_message(branch: Branch, hours: Hours, now: dt.datetime) -> bool:
    """True in the first hour after opening (a node started later skips the day's message)."""
    local, opens, _ = _times(branch, hours, now)
    return opens <= local < opens + HOUR


def good_day(total: int, share: int | None, average: int | None) -> bool:
    """True when total beat the day's target share, or with no target is at least 20% above
    the 4-week same-weekday average. False without either."""
    if share is not None:
        return total > share
    if not average:
        return False
    return total * 100 >= average * (100 + GOOD_DAY_PERCENT)


# ---- data -------------------------------------------------------------------------------------


def _reporters(session: Session, branch_id: str, day: dt.date) -> set[str]:
    """The ids of the people with a live count for the branch and business date."""
    return {r.reported_by for r in tools._live_counts(session, [branch_id], day, day)}


def _clerks(session: Session, branch_id: str, day: dt.date) -> list[Person]:
    """Active clerks on shift that day (assigned to a visit) when the branch has visits that
    day, else every active clerk of the branch."""
    clerks = alerts._people(session, branch_id, "clerk")
    stmt = select(Visit).where(Visit.branch_id == branch_id).where(Visit.date == day)
    visits = [v for v in session.exec(stmt) if v.status != "cancelled"]
    if not visits:
        return clerks
    on_shift = {pid for v in visits for pid in v.assigned_person_ids}
    return [p for p in clerks if p.id in on_shift]


def _leads(session: Session, organisation_id: str) -> list[Person]:
    """Active owners and admins across the organisation's branches, each once."""
    branch_ids = select(Branch.id).where(Branch.organisation_id == organisation_id)
    stmt = select(Person).where(col(Person.branch_id).in_(branch_ids))
    rows = session.exec(stmt.where(Person.status == "active").order_by(col(Person.id)))
    return [p for p in rows if tools.LEADS & set(p.roles)]


def _share(session: Session, branch_id: str, hours: Hours, day: dt.date) -> int | None:
    """tools.target_share without the rbac check (the tick is system work) and with the hours
    already loaded: a day target beats a month target, then an owner's or admin's, then the
    newest. ponytail: mirrors target_share's ranking; let target_share call this when tools.py
    is next touched."""
    stmt = select(SalesTarget).where(SalesTarget.branch_id == branch_id)
    rows = [r for r in session.exec(stmt.where(col(SalesTarget.starts_on) <= day)) if r.amount]
    setters = {p.id: p for p in session.exec(select(Person))}
    ranked = []
    for row in rows:
        assert row.amount is not None
        target = calc.Target(row.period, row.starts_on, row.amount)
        share = calc.day_share(target, day, tools._open_days(hours))
        if share is not None:
            lead = tools._is_lead(setters.get(row.set_by))
            ranked.append((row.period == "day", lead, row.created_at, row.id, share))
    return max(ranked)[-1] if ranked else None


def _total(session: Session, branch_id: str, day: dt.date) -> int:
    rows = tools._live_counts(session, [branch_id], day, day)
    return sum(a for _, a in calc.totals(tools._plain(rows)).values())


def _history(session: Session, branch_id: str, day: dt.date) -> tuple[int | None, int | None]:
    """(the same weekday last week's total, the mean of the last four same-weekday totals);
    weeks without counts are left out, None when there are none."""
    rows = tools._live_counts(session, [branch_id], day - dt.timedelta(days=28), day)
    by_day: dict[dt.date, int] = {}
    for row in rows:
        by_day[row.business_date] = by_day.get(row.business_date, 0) + row.amount
    weeks = [by_day[d] for k in range(1, 5) if (d := day - dt.timedelta(weeks=k)) in by_day]
    average = (sum(weeks) + len(weeks) // 2) // len(weeks) if weeks else None
    return by_day.get(day - dt.timedelta(weeks=1)), average


# ---- senders ------------------------------------------------------------------------------


def _send(session: Session, branch: Branch, person: Person, blocks: list[Block]) -> Message:
    actor = Actor.system(branch.id)
    return notify(session, person, blocks, actor, MANIFEST.id, urgent=False)


def _text(session: Session, branch: Branch, person: Person, text: str) -> Message:
    return _send(session, branch, person, [TextBlock(text=text)])


def _remind(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    reported = _reporters(session, branch.id, day)
    return [
        _text(session, branch, p, t("sales.reminder", p.language))
        for p in _clerks(session, branch.id, day)
        if p.id not in reported
    ]


def _missing(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    reported = _reporters(session, branch.id, day)
    names = [p.name for p in _clerks(session, branch.id, day) if p.id not in reported]
    if not names:
        return []
    return [
        _text(session, branch, sup, t("sales.missing", sup.language, names=", ".join(names)))
        for sup in alerts.supervisors(session, branch.id)
    ]


def _signed(percent: int, lang: str) -> str:
    return ("+" if percent > 0 else "") + format_int(percent, lang)


def _weekday(day: dt.date, lang: str) -> str:
    name = actions.DAY_NAMES.get(lang, EN_WEEKDAYS)[day.weekday()]
    return name if lang == "fi" else name.capitalize()


@dataclass(frozen=True)
class _Day:
    """One branch's business date as the report words it."""

    branch: str
    day: dt.date
    items: list[tuple[str, int, int]]  # (item name, quantity, amount) in menu order
    total: int
    currency: str
    share: int | None
    last_week: int | None
    average: int | None


def _report_blocks(d: _Day, lang: str) -> list[Block]:
    """The report in lang: items, total and target, then the comparison when both exist."""
    if not d.items:
        return [TextBlock(text=t("sales.today.empty", lang, branch=d.branch))]
    lines = ", ".join(
        t(
            "sales.report.line",
            lang,
            quantity=format_int(q, lang),
            item=name,
            amount=format_money(a, d.currency, lang),
        )
        for name, q, a in d.items
    )
    total = format_money(d.total, d.currency, lang)
    target = replies._target(d.total, d.share, d.currency, lang)
    text = t("sales.report", lang, branch=d.branch, lines=lines, total=total, target=target)
    blocks: list[Block] = [TextBlock(text=text)]
    week, avg = calc.compare(d.total, d.last_week), calc.compare(d.total, d.average)
    if week is not None and avg is not None:
        compare = {"percent": _signed(week, lang), "avg_percent": _signed(avg, lang)}
        weekday = _weekday(d.day, lang)
        blocks.append(TextBlock(text=t("sales.report.compare", lang, weekday=weekday, **compare)))
    return blocks


def _report(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    sums = calc.totals(tools._plain(tools._live_counts(session, [branch.id], day, day)))
    names = tools._names(session)
    ordered = sorted(sums.items(), key=lambda kv: names[kv[0]].sort_order)
    last_week, average = _history(session, branch.id, day)
    report = _Day(
        branch=branch.name,
        day=day,
        items=[(names[i].name, q, a) for i, (q, a) in ordered],
        total=sum(a for _, a in sums.values()),
        currency=tools._currency(session, branch.id),
        share=_share(session, branch.id, hours, day),
        last_week=last_week,
        average=average,
    )
    return [
        _send(session, branch, p, _report_blocks(report, p.language))
        for p in _leads(session, branch.organisation_id)
    ]


def _morning(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    yesterday = day - dt.timedelta(days=1)
    total = _total(session, branch.id, yesterday)
    currency = tools._currency(session, branch.id)
    past, share = (
        _share(session, branch.id, hours, yesterday),
        _share(session, branch.id, hours, day),
    )
    people = {p.id: p for p in alerts._people(session, branch.id, "clerk")}
    people |= {p.id: p for p in alerts.supervisors(session, branch.id)}
    sent = []
    for person in people.values():
        lang = person.language
        done = format_money(total, currency, lang) + replies._target(total, past, currency, lang)
        if share is None:
            text = t("sales.morning.no_target", lang, yesterday=done)
        else:
            text = t(
                "sales.morning", lang, yesterday=done, target=format_money(share, currency, lang)
            )
        sent.append(_text(session, branch, person, text))
    return sent


def _why(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    total = _total(session, branch.id, day)
    _, average = _history(session, branch.id, day)
    if not good_day(total, _share(session, branch.id, hours, day), average):
        return []
    reporters = [session.get(Person, pid) for pid in sorted(_reporters(session, branch.id, day))]
    return [
        _text(session, branch, p, t("sales.why", p.language))
        for p in reporters
        if p is not None and p.status == "active"
    ]


DUE: list[tuple[Callable[[Branch, Hours, dt.datetime], bool], str, Sender]] = [
    (morning_message, MORNING, _morning),
    (closing_reminder, REMINDER, _remind),
    (missing_list, MISSING, _missing),
    (owner_report, REPORT, _report),
    (why_question, WHY, _why),
]


def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    stmt = select(RetailBranchHours).where(RetailBranchHours.branch_id == branch.id)
    hours = list(session.exec(stmt))
    day = now.astimezone(ZoneInfo(branch.timezone)).date()
    if not tools._open_days(hours)(day):
        return 0
    count = 0
    for is_due, marker, send in DUE:
        if not is_due(branch, hours, now) or alerts._marked(session, marker, branch.id, day):
            continue
        sent = send(session, branch, hours, day)
        if sent:  # the marker records a send; nothing sent is checked again on the next tick
            data = {"date": day.isoformat(), "message_ids": [m.id for m in sent]}
            alerts._mark(session, branch.id, marker, ("branch", branch.id), data)
        count += len(sent)
    return count


def run_due(session: Session, now: dt.datetime) -> int:
    """Send the sales work due at `now` for every branch; returns how many notifications were
    sent. Each kind is sent at most once per branch and business date. Nothing runs when the
    organisation does not use the sales supervisor (a cleaning node has no sales)."""
    if MANIFEST.id not in orgconfig.load().agents:
        return 0
    return alerts._each_branch(session, now, _branch_due)
