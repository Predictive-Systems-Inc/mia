"""Proactive alerts on the ticker (plan item 6): a missed check-in, tomorrow's unstaffed
visits, and the evening daily plan. All code (rule 7); messages go through notify, so the app
keeps a copy and channels get them under the quiet-hours rules. Each alert fires once: the
marker is an event, so a restart never repeats one. Each branch commits its own work and a
failing branch never silences the others.
"""

import datetime as dt
import logging
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.shift_supervisor import MANIFEST, timesheets
from mia.agents.shift_supervisor.rules import _visit_card
from mia.agents.shift_supervisor.tools import visit_info
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import events
from mia.core.models import Actor, Branch, Event, Person, Timesheet, Visit
from mia.core.orgconfig import load as load_org
from mia.i18n import t

log = logging.getLogger(__name__)
MISSED = "visit.missed_check_in"
MISSED_OUT = "visit.missed_check_out"
OVERTIME = "timesheet.overtime"
UNSTAFFED = "alert.unstaffed_visits"
PLAN = "notification.daily_plan"
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
    """The branch's supervisors, or its admins and owners when it has none; each once."""
    found = _people(session, branch_id, "supervisor")
    if not found:
        found = _people(session, branch_id, "admin") + _people(session, branch_id, "owner")
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
        if visit.planned_start < now - dt.timedelta(days=1) or _marked(session, MISSED, visit.id):
            continue
        info = visit_info(session, visit, branch.timezone)
        _mark(session, branch.id, MISSED, ("visit", visit.id), {"planned_start": info.start})
        names = []
        for pid in visit.assigned_person_ids:
            person = session.get(Person, pid)
            if person is None:
                continue
            names.append(person.name)
            if person.status != "active":
                continue  # nothing to a person who left; the supervisors still hear
            text = t(
                "alert.missed_check_in", person.language, location=info.location, time=info.start
            )
            _send(session, person, [TextBlock(text=text)], urgent=True)
        for sup in supervisors(session, branch.id):
            text = t(
                "alert.missed_check_in_supervisor",
                sup.language,
                name=", ".join(names) or "?",
                location=info.location,
                time=info.start,
            )
            _send(session, sup, [TextBlock(text=text)], urgent=True)
        count += 1
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
            text = t(
                "alert.missed_check_out", person.language, location=info.location, time=info.end
            )
            _send(session, person, [TextBlock(text=text)], urgent=True)
        for sup in supervisors(session, branch.id):
            text = t(
                "alert.missed_check_out_supervisor",
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
            TextBlock(text=t("alert.unstaffed_intro", lang, count=len(rows))),
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


def daily_plan(session: Session, now: dt.datetime) -> int:
    """From the plan time on, once a day: everyone assigned tomorrow gets a card of their
    visits (people without visits get nothing). Returns how many plans went out."""
    return _each_branch(session, now, _plan_in)


def run_due(session: Session, now: dt.datetime) -> int:
    """Every alert, after the timesheet drafts are built; returns how many went out."""
    timesheets.build_due(session, now)
    return (
        missed_check_ins(session, now)
        + missed_check_outs(session, now)
        + overtime(session, now)
        + unstaffed_visits(session, now)
        + daily_plan(session, now)
    )
