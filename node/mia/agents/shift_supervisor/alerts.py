"""Proactive alerts on the ticker (plan item 6): a missed check-in, tomorrow's unstaffed
visits, and the evening daily plan. All code (rule 7); messages go through notify, so the app
keeps a copy and channels get them under the quiet-hours rules. Each alert fires once: the
marker is an event, so a restart never repeats one. Each branch commits its own work and a
failing branch never silences the others.

Retail (D39, behind is_retail(); cleaning is unchanged): the same alerts in kiosk words
(word_key), the next week's roster on the configured weekday and time, the daily plan only when
a clerk's tomorrow changed since the roster or her last plan, shifts generated on a closed day
cancelled, and undecided swaps expired at the shift start with both clerks told. A no-show is
the missed check-in plus the cover flow. The end-of-shift work is not here: the counts
reminder and the missing list stay with the sales supervisor, the stock and closing summary
with the inventory manager, the cash with the bookkeeper (each skips a closed day).
"""

import datetime as dt
import logging
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.shift_supervisor import MANIFEST, cover, replies, timesheets
from mia.agents.shift_supervisor.rules import _visit_card, is_retail, word_key
from mia.agents.shift_supervisor.tools import LATE_HOLD_MAX, LATE_NOTICE, VisitInfo, visit_info
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import approvals, assignments, events, scheduling
from mia.core.models import Actor, Approval, Branch, Event, Person, Timesheet, Visit
from mia.core.orgconfig import load as load_org
from mia.i18n import t
from mia.templates.retail import hours as retail_hours

log = logging.getLogger(__name__)
MISSED = "visit.missed_check_in"
MISSED_OUT = "visit.missed_check_out"
LATE = LATE_NOTICE  # retail: a clerk's late notice for one shift (tools.record_absence)
NO_SHOW = "visit.late_no_show"  # retail: one clerk's missed check-in after her late notice
LATE_HOLD = dt.timedelta(minutes=60)  # a late notice with no time holds the alert this long
OVERTIME = "timesheet.overtime"
UNSTAFFED = "alert.unstaffed_visits"
PLAN = "notification.daily_plan"
ROSTER = "notification.weekly_roster"
SWAP_TYPES = (cover.SWAP_TYPE, cover.SWAP_OVERRIDE_TYPE)
BranchAlert = Callable[[Session, Branch, dt.datetime], int]


def _actor(branch_id: str) -> Actor:
    return Actor.system(branch_id)


def _marked(session: Session, action: str, entity_id: str, day: dt.date | None = None) -> bool:
    # ponytail: loads every marker of the entity; filter by timestamp when it ever hurts.
    rows = session.exec(
        select(Event).where(Event.action == action).where(Event.entity_id == entity_id)
    ).all()
    return any(day is None or (r.after or {}).get("date") == day.isoformat() for r in rows)


def _mark(
    session: Session, branch_id: str, action: str, entity: tuple[str, str], data: dict[str, Any]
) -> None:
    events.emit(session, action, entity, None, data, _actor(branch_id))


def _people(session: Session, branch_id: str, role: str) -> list[Person]:
    rows = session.exec(
        select(Person).where(Person.branch_id == branch_id).where(Person.status == "active")
    ).all()
    return [p for p in rows if role in p.roles]


def supervisors(session: Session, branch_id: str) -> list[Person]:
    """The branch's own supervisors, or its admins and owners when it has none, then the
    supervisors assigned to it today (D50: an assigned one never replaces the owners'
    fallback); each once."""
    branch = session.get(Branch, branch_id)
    found = _people(session, branch_id, "supervisor")
    if not found:
        found = _people(session, branch_id, "admin") + _people(session, branch_id, "owner")
    if branch is not None:
        found += assignments.assigned_to(session, branch_id, assignments.local_day(branch))
    seen: set[str] = set()
    out = []
    for p in found:
        if p.id not in seen:
            seen.add(p.id)
            out.append(p)
    return out


def leads(session: Session, organisation_id: str) -> list[Person]:
    """Active owners and admins across the organisation's branches, each once, by id."""
    branch_ids = select(Branch.id).where(Branch.organisation_id == organisation_id)
    stmt = select(Person).where(col(Person.branch_id).in_(branch_ids))
    rows = session.exec(stmt.where(Person.status == "active").order_by(col(Person.id)))
    return [p for p in rows if {"owner", "admin"} & set(p.roles)]


def _send(session: Session, person: Person, blocks: list[Block], *, urgent: bool) -> None:
    notify(session, person, blocks, _actor(person.branch_id), MANIFEST.id, urgent=urgent)


def _each_branch(session: Session, now: dt.datetime, fn: BranchAlert) -> int:
    """Run one alert per branch; a failing branch (a bad time zone, say) is logged and does
    not silence the others. Each branch commits its own work (rule 11)."""
    count = 0
    for branch in session.exec(select(Branch)).all():
        try:
            count += fn(session, branch, now)
            session.commit()
        except Exception:
            session.rollback()
            log.exception("alert failed for branch %s", branch.id)
    return count


def _late_holds(session: Session, visit: Visit, grace: dt.timedelta) -> dict[str, dt.datetime]:
    """Each clerk's hold on this shift's missed check-in alert after their own late notice,
    by person id: the stated arrival plus the check-in window, else LATE_HOLD after the start,
    never past LATE_HOLD_MAX after the start. A clerk's newest notice (by event id) counts."""
    rows = session.exec(
        select(Event)
        .where(Event.action == LATE)
        .where(Event.entity_id == visit.id)
        .order_by(col(Event.id))
    ).all()
    newest = {(e.after or {}).get("person_id"): e for e in rows}  # later ids overwrite
    holds = {}
    for pid, e in newest.items():
        arrive = (e.after or {}).get("arrive_at")
        start = visit.planned_start
        until = dt.datetime.fromisoformat(arrive) + grace if arrive else start + LATE_HOLD
        if isinstance(pid, str):
            holds[pid] = min(until, start + LATE_HOLD_MAX)
    return holds


def _no_show_marked(session: Session, visit: Visit, person_id: str) -> bool:
    rows = session.exec(
        select(Event).where(Event.action == NO_SHOW).where(Event.entity_id == visit.id)
    ).all()
    return any((r.after or {}).get("person_id") == person_id for r in rows)


def _tell_missed(
    session: Session, branch: Branch, visit: Visit, people: list[str], *, late: bool
) -> None:
    """The missed check-in words to the clerks in `people` and the supervisors (the names
    listed): the plain alert, or after a late notice the "did not arrive" one."""
    info = visit_info(session, visit, branch.timezone)
    names = []
    for pid in people:
        person = session.get(Person, pid)
        if person is None:
            continue
        names.append(person.name)
        if person.status != "active":
            continue  # nothing to a person who left; the supervisors still hear
        key = "retail.alert.late_no_show" if late else word_key("alert.missed_check_in")
        text = t(key, person.language, location=info.location, time=info.start)
        _send(session, person, [TextBlock(text=text)], urgent=True)
    for sup in supervisors(session, branch.id):
        text = t(
            "retail.alert.late_no_show_supervisor"
            if late
            else word_key("alert.missed_check_in_supervisor"),
            sup.language,
            name=", ".join(names) or "?",
            location=info.location,
            time=info.start,
        )
        _send(session, sup, [TextBlock(text=text)], urgent=True)


def _missed_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    grace = dt.timedelta(minutes=load_org().alerts.check_in_grace_minutes)
    local_today = now.astimezone(ZoneInfo(branch.timezone)).date()
    rows = session.exec(  # by date in SQL (ISO strings with offsets do not compare), time in code
        select(Visit)
        .where(Visit.branch_id == branch.id)
        .where(Visit.status == "planned")
        .where(col(Visit.date) >= local_today - dt.timedelta(days=1))
        .where(col(Visit.date) <= local_today)
        .order_by(col(Visit.planned_start))
    ).all()
    count = 0
    for visit in rows:
        if not visit.assigned_person_ids or visit.planned_start > now - grace:
            continue
        if visit.planned_start < now - dt.timedelta(days=1):
            continue
        holds = _late_holds(session, visit, grace) if is_retail() else {}
        plain = [p for p in visit.assigned_person_ids if p not in holds]
        sent = False
        if plain and not _marked(session, MISSED, visit.id):
            start = visit_info(session, visit, branch.timezone).start
            _mark(session, branch.id, MISSED, ("visit", visit.id), {"planned_start": start})
            _tell_missed(session, branch, visit, plain, late=False)
            sent = True
        for pid, until in holds.items():  # held per clerk, until the arrival plus the window
            if pid not in visit.assigned_person_ids or now < until:
                continue
            if _no_show_marked(session, visit, pid):
                continue
            _mark(session, branch.id, NO_SHOW, ("visit", visit.id), {"person_id": pid})
            _tell_missed(session, branch, visit, [pid], late=True)
            sent = True
        count += sent
    return count


def missed_check_ins(session: Session, now: dt.datetime) -> int:
    """Planned visits that started more than the grace period ago without a check-in: ask
    the cleaner, tell the supervisors (one message per visit, the names listed). Once per
    visit, not per assignment. Returns how many visits were alerted."""
    return _each_branch(session, now, _missed_in)


def _missed_out_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    grace = dt.timedelta(minutes=load_org().alerts.check_out_grace_minutes)
    local_today = now.astimezone(ZoneInfo(branch.timezone)).date()
    rows = session.exec(
        select(Visit)
        .where(Visit.branch_id == branch.id)
        .where(Visit.status == "in_progress")
        .where(col(Visit.date) >= local_today - dt.timedelta(days=1))
        .where(col(Visit.date) <= local_today)
        .order_by(col(Visit.planned_start))
    ).all()
    count = 0
    for visit in rows:
        if visit.planned_end > now - grace or _marked(session, MISSED_OUT, visit.id):
            continue
        info = visit_info(session, visit, branch.timezone)
        _mark(session, branch.id, MISSED_OUT, ("visit", visit.id), {"planned_end": info.end})
        names = []
        for pid in visit.assigned_person_ids:
            person = session.get(Person, pid)
            if person is None:
                continue
            names.append(person.name)
            if person.status != "active":
                continue
            key = word_key("alert.missed_check_out")
            text = t(key, person.language, location=info.location, time=info.end)
            _send(session, person, [TextBlock(text=text)], urgent=True)
        for sup in supervisors(session, branch.id):
            text = t(
                word_key("alert.missed_check_out_supervisor"),
                sup.language,
                name=", ".join(names) or "?",
                location=info.location,
                time=info.end,
            )
            _send(session, sup, [TextBlock(text=text)], urgent=True)
        count += 1
    return count


def missed_check_outs(session: Session, now: dt.datetime) -> int:
    """Visits in progress past their planned end by more than the grace period: ask the
    cleaner, tell the supervisors; once per visit. Returns how many visits were alerted."""
    return _each_branch(session, now, _missed_out_in)


def _overtime_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    limit = load_org().alerts.overtime_minutes
    since = (now - timesheets.LOOKBACK).date()
    rows = session.exec(
        select(Timesheet)
        .where(Timesheet.branch_id == branch.id)
        .where(Timesheet.source == "check_out")
        .where(col(Timesheet.date) >= since)
        .order_by(col(Timesheet.id))
    ).all()
    count = 0
    for ts in rows:
        visit = session.get(Visit, ts.visit_id)
        if visit is None:
            continue
        planned = int((visit.planned_end - visit.planned_start).total_seconds() // 60)
        over = ts.minutes - planned
        if over <= limit or _marked(session, OVERTIME, ts.id):
            continue
        _mark(session, branch.id, OVERTIME, ("timesheet", ts.id), {"over_minutes": over})
        person = session.get(Person, ts.person_id)
        info = visit_info(session, visit, branch.timezone)
        for sup in supervisors(session, branch.id):
            text = t(
                "alert.overtime_supervisor",
                sup.language,
                name=person.name if person else "?",
                minutes=str(over),
                location=info.location,
                date=ts.date.isoformat(),
            )
            _send(session, sup, [TextBlock(text=text)], urgent=False)
        count += 1
    return count


def overtime(session: Session, now: dt.datetime) -> int:
    """Timesheets from a check-out that run more than the overtime limit past the plan: tell
    the supervisors once per timesheet. Returns how many."""
    return _each_branch(session, now, _overtime_in)


def _unstaffed_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    local = now.astimezone(ZoneInfo(branch.timezone))
    if local.time() < load_org().alerts.unstaffed_check_time:
        return 0
    if _marked(session, UNSTAFFED, branch.id, local.date()):
        return 0
    tomorrow = local.date() + dt.timedelta(days=1)
    rows = session.exec(
        select(Visit)
        .where(Visit.branch_id == branch.id)
        .where(Visit.date == tomorrow)
        .where(Visit.status == "unfilled")
        .order_by(col(Visit.planned_start))
    ).all()
    if not rows:
        return 0
    data = {"date": local.date().isoformat(), "visits": len(rows)}
    _mark(session, branch.id, UNSTAFFED, ("branch", branch.id), data)
    infos = [visit_info(session, v, branch.timezone).model_dump(mode="json") for v in rows]
    for sup in supervisors(session, branch.id):
        lang = sup.language
        blocks: list[Block] = [
            TextBlock(text=t(word_key("alert.unstaffed_intro"), lang, count=len(rows))),
            _visit_card(infos, t("alert.unstaffed_title", lang), lang),
        ]
        _send(session, sup, blocks, urgent=False)
    return 1


def unstaffed_visits(session: Session, now: dt.datetime) -> int:
    """From the check time on, once a day: tomorrow's unfilled visits as a card to the
    supervisors. Returns how many branches got the card."""
    return _each_branch(session, now, _unstaffed_in)


def _plan_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    local = now.astimezone(ZoneInfo(branch.timezone))
    if local.time() < load_org().alerts.daily_plan_time:
        return 0
    tomorrow = local.date() + dt.timedelta(days=1)
    rows = session.exec(
        select(Visit)
        .where(Visit.branch_id == branch.id)
        .where(Visit.date == tomorrow)
        .where(Visit.status != "cancelled")
        .order_by(col(Visit.planned_start))
    ).all()
    assigned: dict[str, list[Visit]] = {}
    for v in rows:
        for pid in v.assigned_person_ids:
            assigned.setdefault(pid, []).append(v)
    if is_retail():
        return _retail_plan(session, branch, local.date(), assigned)
    count = 0
    for pid, mine in assigned.items():  # anyone assigned, whatever their role
        person = session.get(Person, pid)
        if person is None or person.status != "active":
            continue
        if _marked(session, PLAN, person.id, local.date()):
            continue
        data = {"date": local.date().isoformat(), "visits": len(mine)}
        _mark(session, branch.id, PLAN, ("person", person.id), data)
        infos = [visit_info(session, v, branch.timezone).model_dump(mode="json") for v in mine]
        lang = person.language
        blocks: list[Block] = [
            TextBlock(text=t("plan.intro", lang, count=len(mine))),
            _visit_card(infos, t("plan.title", lang), lang),
        ]
        _send(session, person, blocks, urgent=False)
        count += 1
    return count


Shift = list[str]  # visit id, local date, planned start and end (UTC ISO): what a clerk was told


def _shift(v: Visit) -> Shift:
    start, end = (x.astimezone(dt.UTC).isoformat() for x in (v.planned_start, v.planned_end))
    return [v.id, v.date.isoformat(), start, end]


def _told(marks: list[Event], person_id: str, day: dt.date) -> list[Shift] | None:
    """The person's shifts on `day` as last sent (`marks`: the branch's plan and roster markers,
    oldest first): her newest retail plan for the day, else the weekly roster holding the day;
    None when neither went out (nothing to compare)."""
    for e in reversed(marks):
        after = e.after or {}
        if e.action == PLAN and e.entity_id == person_id and after.get("for") == day.isoformat():
            return list(after.get("shifts", []))
    monday = day - dt.timedelta(days=day.weekday())
    for e in marks:
        after = e.after or {}
        if e.action == ROSTER and after.get("date") == monday.isoformat():
            return [
                s for s in after.get("people", {}).get(person_id, []) if s[1] == day.isoformat()
            ]
    return None


def _retail_plan(
    session: Session, branch: Branch, today: dt.date, assigned: dict[str, list[Visit]]
) -> int:
    """Each person whose tomorrow at the branch differs from what the roster or her last plan
    told her gets her new day (or shift.plan.off for a day emptied), not urgent, the marker with
    the send. Nothing went out yet for the day: nothing to correct, so nothing is sent. A closed
    day sends nothing either: close_day already told the clerks (shift.closed.told)."""
    tomorrow = today + dt.timedelta(days=1)
    if tomorrow in retail_hours.closed(session, branch.id):
        return 0
    # ponytail: loads the branch's plan and roster markers each tick; filter by date if it hurts.
    marks = list(
        session.exec(
            select(Event)
            .where(Event.branch_id == branch.id)
            .where(col(Event.action).in_((PLAN, ROSTER)))
            .order_by(col(Event.id))
        ).all()
    )
    people = set(assigned)
    for e in marks:
        people |= set((e.after or {}).get("people", {})) if e.action == ROSTER else set()
        if e.action == PLAN and (e.after or {}).get("for") == tomorrow.isoformat():
            people.add(e.entity_id)
    count = 0
    for pid in sorted(people):
        person = session.get(Person, pid)
        if person is None or person.status != "active":
            continue
        mine = assigned.get(pid, [])
        shifts = [_shift(v) for v in mine]
        told = _told(marks, pid, tomorrow)
        if told is None or sorted(told) == sorted(shifts):
            continue
        data = {"date": today.isoformat(), "for": tomorrow.isoformat(), "shifts": shifts}
        _mark(session, branch.id, PLAN, ("person", pid), data)
        lang = person.language
        blocks: list[Block] = [TextBlock(text=t("shift.plan.off", lang))]
        if mine:
            infos = [visit_info(session, v, branch.timezone).model_dump(mode="json") for v in mine]
            blocks = [
                TextBlock(text=t(word_key("plan.intro"), lang, count=len(mine))),
                _visit_card(infos, t("plan.title", lang), lang),
            ]
        _send(session, person, blocks, urgent=False)
        count += 1
    return count


def daily_plan(session: Session, now: dt.datetime) -> int:
    """From the plan time on. Cleaning: once a day, everyone assigned tomorrow gets a card of
    their visits (people without visits get nothing). Retail: only a clerk whose tomorrow changed
    since the roster or her last plan, her new day or shift.plan.off for a day emptied, never for
    a closed day. Returns how many plans went out."""
    return _each_branch(session, now, _plan_in)


def _roster_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    settings = load_org().shift_supervisor
    local = now.astimezone(ZoneInfo(branch.timezone))
    if local.weekday() != settings.weekly_roster_weekday:
        return 0
    if local.time() < settings.weekly_roster_time:
        return 0
    monday = local.date() + dt.timedelta(days=7 - local.weekday())
    if _marked(session, ROSTER, branch.id, monday):
        return 0
    rows = [v for v in scheduling.week(session, branch.id, monday) if v.status != "cancelled"]
    if not rows:
        return 0
    mine: dict[str, list[Visit]] = {}
    for v in rows:
        for pid in v.assigned_person_ids:
            mine.setdefault(pid, []).append(v)
    people = {pid: [_shift(v) for v in vs] for pid, vs in mine.items()}
    data = {"date": monday.isoformat(), "people": people}
    _mark(session, branch.id, ROSTER, ("branch", branch.id), data)
    infos = {v.id: visit_info(session, v, branch.timezone) for v in rows}
    count = 0
    for pid, visits in mine.items():
        person = session.get(Person, pid)
        if person is None or person.status != "active":
            continue
        intro = TextBlock(text=t("shift.roster.week_intro", person.language, count=len(visits)))
        card = _week_card(session, monday, {pid: [infos[v.id] for v in visits]}, person.language)
        _send(session, person, [intro, *card], urgent=False)
        count += 1
    everyone = {pid: [infos[v.id] for v in vs] for pid, vs in mine.items()}
    for sup in supervisors(session, branch.id):
        lang = sup.language
        intro = TextBlock(
            text=t("shift.roster.branch_intro", lang, branch=branch.name, count=len(rows))
        )
        _send(session, sup, [intro, *_week_card(session, monday, everyone, lang)], urgent=False)
        count += 1
    return count


def _week_card(
    session: Session, monday: dt.date, shifts: dict[str, list[VisitInfo]], lang: str
) -> list[Block]:
    """The roster tool's week card (replies.retail_reply), a field per first name."""
    people: dict[str, list[dict[str, Any]]] = {}
    for pid, infos in shifts.items():
        person = session.get(Person, pid)
        name = person.name.split()[0] if person else "?"
        people.setdefault(name, []).extend(i.model_dump(mode="json") for i in infos)
    return replies.retail_reply("roster", {"start": monday.isoformat(), "people": people}, lang)


def weekly_roster(session: Session, now: dt.datetime) -> int:
    """Retail only: from weekly_roster_time on weekly_roster_weekday (local), once per branch
    and week, each clerk her own Monday to Sunday card of the week that follows and head staff
    the branch's; not urgent. The marker, written with the sends, keeps each person's shift
    ids and times, which the daily plan compares against. Returns how many went out."""
    if not is_retail():
        return 0
    return _each_branch(session, now, _roster_in)


def _closures_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    today = now.astimezone(ZoneInfo(branch.timezone)).date()
    days = sorted(d for d in retail_hours.closed(session, branch.id) if d >= today)
    actor = _actor(branch.id)
    return sum(len(scheduling.cancel_day(session, actor, branch.id, d)) for d in days)


def enforce_closures(session: Session, now: dt.datetime) -> int:
    """Retail only: open shifts on a closed date from today on (generated after the closing was
    set) cancelled; nobody is told, they were never announced. Returns how many."""
    if not is_retail():
        return 0
    return _each_branch(session, now, _closures_in)


def _swaps_in(session: Session, branch: Branch, now: dt.datetime) -> int:
    count = 0
    for approval in approvals.pending(session, branch.id):
        if approval.type not in SWAP_TYPES or approval.expires_at is None:
            continue
        if approval.expires_at > now:
            continue
        approvals.expire(session, approval, _actor(branch.id), "the shift started undecided")
        _tell_expired(session, approval)
        count += 1
    return count


def _tell_expired(session: Session, approval: Approval) -> None:
    ev = approval.evidence
    a, b = session.get(Person, str(ev["asker_id"])), session.get(Person, str(ev["other_id"]))
    for who, other in ((a, b), (b, a)):
        if who is None or other is None or who.status != "active":
            continue
        text = t("shift.swap.expired", who.language, name=other.name.split()[0])
        _send(session, who, [TextBlock(text=text)], urgent=False)


def close_undecided_swaps(session: Session, now: dt.datetime) -> int:
    """Retail only: an open swap approval past its TTL (the earlier shift's planned start)
    expired through approvals.expire, both clerks told; the shifts stay as they were.
    Returns how many."""
    if not is_retail():
        return 0
    return _each_branch(session, now, _swaps_in)


def run_due(session: Session, now: dt.datetime) -> int:
    """Every alert, after the timesheet drafts are built; returns how many went out. In retail,
    closed days and undecided swaps are settled first, the weekly roster before the daily plan
    it is compared with."""
    timesheets.build_due(session, now)
    return (
        enforce_closures(session, now)
        + close_undecided_swaps(session, now)
        + missed_check_ins(session, now)
        + missed_check_outs(session, now)
        + overtime(session, now)
        + unstaffed_visits(session, now)
        + weekly_roster(session, now)
        + daily_plan(session, now)
    )
