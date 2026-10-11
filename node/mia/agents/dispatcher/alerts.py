"""Proactive alerts on the ticker (plan item 6): a missed check-in, tomorrow's unstaffed
visits, and the evening daily plan. All code (rule 7); messages go through notify, so the app
keeps a copy and channels get them under the quiet-hours rules. Each alert fires once: the
marker is an event, so a restart never repeats one.
"""

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.dispatcher.agent import MANIFEST
from mia.agents.dispatcher.rules import _visit_card
from mia.agents.dispatcher.tools import visit_info
from mia.chat.blocks import Block, TextBlock
from mia.chat.channels import notify
from mia.core import events
from mia.core.models import Actor, Branch, Event, Person, Visit
from mia.core.orgconfig import load as load_org
from mia.i18n import t

MISSED = "visit.missed_check_in"
UNSTAFFED = "alert.unstaffed_visits"
PLAN = "notification.daily_plan"


def _actor(branch_id: str) -> Actor:
    return Actor.system(branch_id)


def _marked(session: Session, action: str, entity_id: str, day: dt.date | None = None) -> bool:
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


def _supervisors(session: Session, branch_id: str) -> list[Person]:
    """The branch's supervisors, or its admins and owners when it has none."""
    found = _people(session, branch_id, "supervisor")
    if not found:
        found = [
            p for p in _people(session, branch_id, "admin") + _people(session, branch_id, "owner")
        ]
    return found


def _send(session: Session, person: Person, blocks: list[Block], *, urgent: bool) -> None:
    notify(session, person, blocks, _actor(person.branch_id), MANIFEST.id, urgent=urgent)


def missed_check_ins(session: Session, now: dt.datetime) -> int:
    """Planned visits that started more than the grace period ago without a check-in: ask
    the cleaner, tell the supervisors. Once per visit. Returns how many were alerted."""
    count = 0
    for branch in session.exec(select(Branch)).all():
        grace = dt.timedelta(minutes=load_org().alerts.check_in_grace_minutes)
        rows = session.exec(
            select(Visit)
            .where(Visit.branch_id == branch.id)
            .where(Visit.status == "planned")
            .where(col(Visit.planned_start) <= now - grace)
            .where(col(Visit.planned_start) >= now - dt.timedelta(days=1))
            .order_by(col(Visit.planned_start))
        ).all()
        for visit in rows:
            if not visit.assigned_person_ids or _marked(session, MISSED, visit.id):
                continue
            info = visit_info(session, visit, branch.timezone)
            _mark(session, branch.id, MISSED, ("visit", visit.id), {"planned_start": info.start})
            for pid in visit.assigned_person_ids:
                person = session.get(Person, pid)
                if person is None or person.status != "active":
                    continue
                text = t(
                    "alert.missed_check_in",
                    person.language,
                    location=info.location,
                    time=info.start,
                )
                _send(session, person, [TextBlock(text=text)], urgent=True)
                for sup in _supervisors(session, branch.id):
                    text = t(
                        "alert.missed_check_in_supervisor",
                        sup.language,
                        name=person.name,
                        location=info.location,
                        time=info.start,
                    )
                    _send(session, sup, [TextBlock(text=text)], urgent=True)
            count += 1
    return count


def unstaffed_visits(session: Session, now: dt.datetime) -> int:
    """From the check time on, once a day: tomorrow's unfilled visits as a card to the
    supervisors. Returns 1 when the card went out."""
    count = 0
    for branch in session.exec(select(Branch)).all():
        local = now.astimezone(ZoneInfo(branch.timezone))
        if local.time() < load_org().alerts.unstaffed_check_time:
            continue
        if _marked(session, UNSTAFFED, branch.id, local.date()):
            continue
        tomorrow = local.date() + dt.timedelta(days=1)
        rows = session.exec(
            select(Visit)
            .where(Visit.branch_id == branch.id)
            .where(Visit.date == tomorrow)
            .where(Visit.status == "unfilled")
            .order_by(col(Visit.planned_start))
        ).all()
        if not rows:
            continue
        _mark(
            session,
            branch.id,
            UNSTAFFED,
            ("branch", branch.id),
            {"date": local.date().isoformat(), "visits": len(rows)},
        )
        infos = [visit_info(session, v, branch.timezone).model_dump(mode="json") for v in rows]
        for sup in _supervisors(session, branch.id):
            lang = sup.language
            blocks: list[Block] = [
                TextBlock(text=t("alert.unstaffed_intro", lang, count=len(rows))),
                _visit_card(infos, t("alert.unstaffed_title", lang), lang),
            ]
            _send(session, sup, blocks, urgent=False)
        count += 1
    return count


def daily_plan(session: Session, now: dt.datetime) -> int:
    """From the plan time on, once a day: each cleaner's visits tomorrow as a card. People
    without visits get nothing. Returns how many plans went out."""
    count = 0
    for branch in session.exec(select(Branch)).all():
        local = now.astimezone(ZoneInfo(branch.timezone))
        if local.time() < load_org().alerts.daily_plan_time:
            continue
        tomorrow = local.date() + dt.timedelta(days=1)
        rows = session.exec(
            select(Visit)
            .where(Visit.branch_id == branch.id)
            .where(Visit.date == tomorrow)
            .where(Visit.status != "cancelled")
            .order_by(col(Visit.planned_start))
        ).all()
        for person in _people(session, branch.id, "staff"):
            mine = [v for v in rows if person.id in v.assigned_person_ids]
            if not mine or _marked(session, PLAN, person.id, local.date()):
                continue
            _mark(
                session,
                branch.id,
                PLAN,
                ("person", person.id),
                {"date": local.date().isoformat(), "visits": len(mine)},
            )
            infos = [visit_info(session, v, branch.timezone).model_dump(mode="json") for v in mine]
            lang = person.language
            blocks: list[Block] = [
                TextBlock(text=t("plan.intro", lang, count=len(mine))),
                _visit_card(infos, t("plan.title", lang), lang),
            ]
            _send(session, person, blocks, urgent=False)
            count += 1
    return count


def run_due(session: Session, now: dt.datetime) -> int:
    """All three alerts; returns how many messages or cards went out."""
    return (
        missed_check_ins(session, now) + unstaffed_visits(session, now) + daily_plan(session, now)
    )
