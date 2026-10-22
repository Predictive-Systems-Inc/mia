"""Sales supervisor work on the tick: the closing reminder to clerks without counts, the missing
list to head staff, the owner's end-of-day report, the morning message and the why question.

What is due is pure code (rule 7): the five window functions take the branch, its hours rows
and `now`, and return the business date the work is due for, or None (on the retail template's
hours helpers). After-close work belongs
to the closing's date, also after midnight, until the next opening. The senders load rows and
send through notify. The reminder and the morning message wait for quiet hours in deliver; the
end-of-shift messages (the missing list, the owner's report, the why question) are urgent and
go out at once, since a branch may close as quiet hours start. Each send leaves a marker event
on the branch with the business date (and the message ids), checked first, so each fires at
most once per branch and date. Each branch commits alone and a failing branch never silences
the others (alerts._each_branch).
"""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.agents.branch_manager import MANIFEST as BRANCH_MANAGER
from mia.agents.sales_supervisor import MANIFEST, actions, calc, replies, tools
from mia.agents.shift_supervisor import alerts
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import orgconfig, sales
from mia.core.models import Actor, Branch, Message, Person, Visit
from mia.core.money import format_int, format_money
from mia.i18n import t
from mia.templates.retail import hours as retail_hours

HALF_HOUR = dt.timedelta(minutes=30)
HOUR = dt.timedelta(hours=1)
GOOD_DAY_PERCENT = 20  # without a target, a day this much above the 4-week average is good
REMINDER = "sales.reminder_sent"
MISSING = "sales.missing_sent"
REPORT = "sales.report_sent"
MORNING = "sales.morning_sent"
WHY = tools.WHY_ASKED
Hours = retail_hours.Hours
Sender = Callable[[Session, Branch, Hours, dt.date], list[Message]]

# ---- what is due (pure) ---------------------------------------------------------------------


def closing_reminder(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """Today's date in the half hour before an open day's closing, else None."""
    local = now.astimezone(ZoneInfo(branch.timezone))
    closes = retail_hours.at(branch, hours, local.date(), closing=True)
    on = retail_hours.open_days(hours)(local.date()) and closes - HALF_HOUR <= local < closes
    return local.date() if on else None


def missing_list(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The business date from half an hour after its closing to its window's end."""
    return retail_hours.after_close(branch, hours, now, HALF_HOUR)


def owner_report(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """The business date from an hour after its closing to its window's end."""
    return retail_hours.after_close(branch, hours, now, HOUR)


def why_question(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """As owner_report: the question is asked at the same time."""
    return owner_report(branch, hours, now)


def morning_message(branch: Branch, hours: Hours, now: dt.datetime) -> dt.date | None:
    """Today's date in the first hour after an open day's opening (a node started later skips
    the day's message), else None."""
    local = now.astimezone(ZoneInfo(branch.timezone))
    opens = retail_hours.at(branch, hours, local.date(), closing=False)
    on = retail_hours.open_days(hours)(local.date()) and opens <= local < opens + HOUR
    return local.date() if on else None


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
    """The ids of the people with a sale for the branch and business date from its one source
    (sales.day_sales: a live count's reporter, or a paid receipt's clerk)."""
    return set(sales.day_sales(session, branch_id, day).by_clerk)


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


def _day_total(session: Session, branch_id: str, day: dt.date) -> int | None:
    """The day's sales amount from its one source (sales.day_sales), None with no sales rows."""
    items = sales.day_sales(session, branch_id, day).by_item
    return sum(a for _, a in items.values()) if items else None


def _total(session: Session, branch_id: str, day: dt.date) -> int:
    return _day_total(session, branch_id, day) or 0


def _history(session: Session, branch_id: str, day: dt.date) -> tuple[int | None, int | None]:
    """(the same weekday last week's total, the mean of the last four same-weekday totals);
    weeks without sales are left out, None when there are none."""
    # ponytail: one day_sales query pair per same weekday (four days); a range query when it shows
    totals = [_day_total(session, branch_id, day - dt.timedelta(weeks=k)) for k in range(1, 5)]
    weeks = [x for x in totals if x is not None]
    average = (sum(weeks) + len(weeks) // 2) // len(weeks) if weeks else None
    return totals[0], average


# ---- senders ------------------------------------------------------------------------------


def _send(
    session: Session, branch: Branch, person: Person, blocks: list[Block], urgent: bool = False
) -> Message:
    actor = Actor.system(branch.id)
    return notify(session, person, blocks, actor, MANIFEST.id, urgent=urgent)


def _text(
    session: Session, branch: Branch, person: Person, text: str, urgent: bool = False
) -> Message:
    return _send(session, branch, person, [TextBlock(text=text)], urgent)


def _remind(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    if sales.source_of(branch, day) == "receipts":
        return []  # clerks ring up receipts: there is no count to remind of
    reported = _reporters(session, branch.id, day)
    return [
        _text(session, branch, p, t("sales.reminder", p.language))
        for p in _clerks(session, branch.id, day)
        if p.id not in reported
    ]


def _missing(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    if sales.source_of(branch, day) == "receipts":
        return []
    reported = _reporters(session, branch.id, day)
    names = [p.name for p in _clerks(session, branch.id, day) if p.id not in reported]
    if not names:
        return []
    return [
        _text(session, branch, sup, t("sales.missing", sup.language, names=", ".join(names)), True)
        for sup in alerts.supervisors(session, branch.id)
    ]


def _signed(percent: int, lang: str) -> str:
    return ("+" if percent > 0 else "") + format_int(percent, lang)


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
        weekday = actions.day_when(d.day.weekday(), lang)
        blocks.append(TextBlock(text=t("sales.report.compare", lang, weekday=weekday, **compare)))
    return blocks


def _report(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    sums = sales.day_sales(session, branch.id, day).by_item
    names = tools._names(session)
    ordered = sorted(sums.items(), key=lambda kv: names[kv[0]].sort_order)
    last_week, average = _history(session, branch.id, day)
    report = _Day(
        branch=branch.name,
        day=day,
        items=[(names[i].name, q, a) for i, (q, a) in ordered],
        total=sum(a for _, a in sums.values()),
        currency=tools._currency(session, branch.id),
        share=tools._share(session, branch.id, hours, day),
        last_week=last_week,
        average=average,
    )
    return [
        _send(session, branch, p, _report_blocks(report, p.language), urgent=True)
        for p in alerts.leads(session, branch.organisation_id)
    ]


def _morning_text(lang: str, yesterday: str | None, target: str | None) -> str | None:
    """The morning words: yesterday and today's target, either one alone, or None."""
    if yesterday is None:
        return t("sales.morning.first", lang, target=target) if target else None
    if target is None:
        return t("sales.morning.no_target", lang, yesterday=yesterday)
    return t("sales.morning", lang, yesterday=yesterday, target=target)


def _branch_manager_runs() -> bool:
    """True when the organisation runs the branch manager, whose morning message (with a tip
    and a quote) then goes to the clerks instead of this one."""
    return BRANCH_MANAGER.id in orgconfig.load().agents


def _morning(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    """Yesterday against its target and today's target to the supervisors, and to the clerks
    unless the branch manager runs."""
    yesterday = day - dt.timedelta(days=1)
    is_open = retail_hours.open_days(hours, retail_hours.closed(session, branch.id))
    counted = is_open(yesterday) and _reporters(session, branch.id, yesterday)
    total = _total(session, branch.id, yesterday)
    currency = tools._currency(session, branch.id)
    past = tools._share(session, branch.id, hours, yesterday)
    share = tools._share(session, branch.id, hours, day)
    people = (
        {}
        if _branch_manager_runs()
        else {p.id: p for p in alerts._people(session, branch.id, "clerk")}
    )
    people |= {p.id: p for p in alerts.supervisors(session, branch.id)}
    sent = []
    for person in people.values():
        lang = person.language
        done = format_money(total, currency, lang) + replies._target(total, past, currency, lang)
        target = None if share is None else format_money(share, currency, lang)
        text = _morning_text(lang, done if counted else None, target)
        if text is not None:
            sent.append(_text(session, branch, person, text))
    return sent


def _why(session: Session, branch: Branch, hours: Hours, day: dt.date) -> list[Message]:
    total = _total(session, branch.id, day)
    _, average = _history(session, branch.id, day)
    share = tools._share(session, branch.id, hours, day)
    if not good_day(total, share, average):
        return []
    reporters = [session.get(Person, pid) for pid in sorted(_reporters(session, branch.id, day))]
    return [
        _text(session, branch, p, _why_text(p.language, day, share), urgent=True)
        for p in reporters
        if p and p.status == "active" and not tools.LEADS & set(p.roles)  # owners read notes
    ]


def _why_text(lang: str, day: dt.date, share: int | None) -> str:
    """sales.why after beating a target; sales.why.average after beating the usual weekday."""
    if share is not None:
        return t("sales.why", lang)
    return t("sales.why.average", lang, weekday=actions.day_when(day.weekday(), lang))


DUE: list[tuple[Callable[[Branch, Hours, dt.datetime], dt.date | None], str, Sender]] = [
    (morning_message, MORNING, _morning),
    (closing_reminder, REMINDER, _remind),
    (missing_list, MISSING, _missing),
    (owner_report, REPORT, _report),
    (why_question, WHY, _why),
]


def _branch_due(session: Session, branch: Branch, now: dt.datetime) -> int:
    if not retail_hours.is_shop(session, branch.id):  # the commissary sells nothing
        return 0
    hours, closed = retail_hours.load(session, branch.id), retail_hours.closed(session, branch.id)
    count = 0
    for is_due, marker, send in DUE:
        day = is_due(branch, hours, now)
        if day is None or day in closed or alerts._marked(session, marker, branch.id, day):
            continue
        sent = send(session, branch, hours, day)
        if sent:  # the marker records a send; nothing sent is checked again on the next tick
            data = {"date": day.isoformat(), "message_ids": [m.id for m in sent]}
            alerts._mark(session, branch.id, marker, ("branch", branch.id), data)
        count += len(sent)
    return count


def run_due(session: Session, now: dt.datetime) -> int:
    """Send the sales work due at `now` for every branch; returns how many notifications were
    sent. Each kind is sent at most once per branch and business date, never for a closed day
    (retail_closures). Nothing runs when the organisation does not use the sales supervisor (a
    cleaning node has no sales)."""
    if MANIFEST.id not in orgconfig.load().agents:
        return 0
    return alerts._each_branch(session, now, _branch_due)
