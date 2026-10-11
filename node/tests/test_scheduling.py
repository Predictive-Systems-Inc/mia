"""Scheduling core: recurrence, generation, assignment rules, check-in and out, week, inbox."""

import datetime as dt

import pytest
from sqlmodel import Session, select

from mia.core import scheduling, store
from mia.core.db import utcnow
from mia.core.models import Actor, Approval, Branch, Event, Job, Location, Person, Visit

MON = dt.date(2026, 10, 12)  # a Monday
TODAY = dt.datetime.now(dt.UTC).date()


def test_recurrence_rules() -> None:
    assert scheduling.occurs_on("FREQ=DAILY", MON, MON + dt.timedelta(days=3))
    assert scheduling.occurs_on("FREQ=WEEKLY;BYDAY=MO,TH", MON, MON + dt.timedelta(days=3))
    assert not scheduling.occurs_on("FREQ=WEEKLY;BYDAY=MO,TH", MON, MON + dt.timedelta(days=1))
    assert scheduling.occurs_on("FREQ=DAILY;INTERVAL=3", MON, MON + dt.timedelta(days=6))
    assert not scheduling.occurs_on("FREQ=DAILY;INTERVAL=3", MON, MON + dt.timedelta(days=4))
    assert not scheduling.occurs_on("FREQ=DAILY;UNTIL=20261013", MON, MON + dt.timedelta(days=2))
    assert scheduling.occurs_on("FREQ=DAILY;UNTIL=20261013", MON, MON + dt.timedelta(days=1))
    for bad in ("FREQ=MONTHLY", "nonsense", "FREQ=WEEKLY"):
        with pytest.raises(ValueError):
            scheduling.validate_rule(bad)
    scheduling.validate_rule("FREQ=WEEKLY;BYDAY=TU")


def test_interval_anchors_on_the_job_creation_date() -> None:
    rule = "FREQ=WEEKLY;BYDAY=MO;INTERVAL=2"
    assert scheduling.occurs_on(rule, MON, MON)
    assert not scheduling.occurs_on(rule, MON, MON + dt.timedelta(days=7))
    assert scheduling.occurs_on(rule, MON, MON + dt.timedelta(days=14))
    # Anchored on a Wednesday: the first Monday on or after it starts the count.
    wed = MON + dt.timedelta(days=2)
    assert scheduling.occurs_on(rule, wed, MON + dt.timedelta(days=7))
    assert not scheduling.occurs_on(rule, wed, MON + dt.timedelta(days=14))


def _future(session: Session, branch: Branch) -> list[Visit]:
    return list(
        session.exec(
            select(Visit).where(Visit.branch_id == branch.id).where(Visit.date > TODAY)
        ).all()
    )


def test_generate_is_idempotent_and_leaves_cancelled_visits(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    actor = Actor.person(people["Sanna"])
    before = len(_future(session, branch))  # the seed made 7 days
    new = scheduling.generate(session, actor, branch, days=28)
    assert new and all(v.status in ("planned", "unfilled") for v in new)
    assert len(_future(session, branch)) == before + len(new)
    assert scheduling.generate(session, actor, branch, days=28) == []
    victim = new[0]
    store.update(session, victim, {"status": "cancelled"}, actor, action="visit.cancelled")
    assert scheduling.generate(session, actor, branch, days=28) == []
    assert session.exec(select(Event).where(Event.action == "visit.generated")).first()


def test_generate_copies_the_last_assignee_when_eligible_else_unfilled(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    actor = Actor.person(people["Sanna"])
    kamppi = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()  # daily
    new = scheduling.generate(session, actor, branch, days=28)
    mine = [v for v in new if v.job_id == kamppi.id]
    assert mine and all(v.assigned_person_ids == [people["Juha"].id] for v in mine)
    assert all(v.status == "planned" for v in mine)
    loc = session.exec(select(Location)).first()
    assert loc is not None
    job = store.insert(
        session,
        Job(
            branch_id=branch.id,
            location_id=loc.id,
            name="New site",
            recurrence="FREQ=DAILY",
            start_time="10:00",
            duration_minutes=60,
            required_skills=["general"],
        ),
        actor,
    )
    new = scheduling.generate(session, actor, branch, days=28)
    fresh = [v for v in new if v.job_id == job.id]
    assert len(fresh) == 28
    assert all(v.status == "unfilled" and v.assigned_person_ids == [] for v in fresh)


def test_generate_skips_a_bad_rule_and_warns(
    session: Session,
    branch: Branch,
    people: dict[str, Person],
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor = Actor.person(people["Sanna"])
    loc = session.exec(select(Location)).first()
    assert loc is not None
    store.insert(
        session,
        Job(
            branch_id=branch.id,
            location_id=loc.id,
            name="Odd",
            recurrence="FREQ=MONTHLY",
            start_time="10:00",
            duration_minutes=60,
        ),
        actor,
    )
    new = scheduling.generate(session, actor, branch, days=10)  # the seed covers 7 days
    assert new and "Odd" in caplog.text and "FREQ=MONTHLY" in caplog.text


def test_generate_due_runs_once_per_local_day(session: Session, branch: Branch) -> None:
    now = utcnow()
    first = scheduling.generate_due(session, now)
    assert first > 0
    assert scheduling.generate_due(session, now + dt.timedelta(hours=1)) == 0
    assert scheduling.generate_due(session, now + dt.timedelta(days=1)) >= 0


def _visit(session: Session, branch: Branch, name: str, offset: int = 1) -> Visit:
    job = session.exec(select(Job).where(Job.name == name)).one()
    day = TODAY + dt.timedelta(days=offset)
    row = session.exec(select(Visit).where(Visit.job_id == job.id).where(Visit.date == day)).first()
    if row is None:
        start = scheduling.local_dt(day, job.start_time, branch.timezone)
        row = store.insert(
            session,
            Visit(
                branch_id=branch.id,
                job_id=job.id,
                location_id=job.location_id,
                date=day,
                planned_start=start,
                planned_end=start + dt.timedelta(minutes=job.duration_minutes),
                status="unfilled",
            ),
            Actor.system(branch.id),
        )
    return row


def test_assign_eligible_replaces_and_add_keeps(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(
        session, branch, "Kamppi shop clean", offset=10
    )  # beyond the seeded week: an open visit
    out = scheduling.assign(session, sanna, visit, people["Aino"])
    assert out.approval_id is None and visit.assigned_person_ids == [people["Aino"].id]
    assert visit.status == "planned"
    scheduling.assign(session, sanna, visit, people["Mikael"], add=True)
    assert visit.assigned_person_ids == [people["Aino"].id, people["Mikael"].id]
    scheduling.assign(session, sanna, visit, people["Juha"])
    assert visit.assigned_person_ids == [people["Juha"].id]
    assert session.exec(select(Event).where(Event.action == "visit.assigned")).first()


def test_assign_twice_is_a_no_op(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(
        session, branch, "Kamppi shop clean", offset=10
    )  # beyond the seeded week: an open visit
    scheduling.assign(session, sanna, visit, people["Aino"])
    events = len(session.exec(select(Event).where(Event.action == "visit.assigned")).all())
    scheduling.assign(session, sanna, visit, people["Aino"], add=True)
    scheduling.assign(session, sanna, visit, people["Aino"])
    assert visit.assigned_person_ids == [people["Aino"].id]
    assert len(session.exec(select(Event).where(Event.action == "visit.assigned")).all()) == events


def test_rule_breaking_assignment_needs_an_approval_then_applies(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core import approvals

    sanna = Actor.person(people["Sanna"])
    visit = _visit(
        session, branch, "Kamppi shop clean", offset=10
    )  # beyond the seeded week: an open visit  # 09:00; Liisa works 10 to 18
    out = scheduling.assign(session, sanna, visit, people["Liisa"])
    assert out.approval_id and visit.assigned_person_ids == [] and visit.status == "unfilled"
    assert any("availab" in r for r in out.reasons), out.reasons
    approval = session.get(Approval, out.approval_id)
    assert approval is not None and approval.type == "schedule.assignment_override"
    assert approval.approver_roles == ["admin", "owner"] and approval.channel == "app_only"
    assert approval.evidence["person_id"] == people["Liisa"].id and approval.evidence["reasons"]
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(session, approval.id, sanna, "approved", stepped_up_at=utcnow())
    helena = Actor.person(people["Helena"])
    approvals.decide(session, approval.id, helena, "approved", stepped_up_at=utcnow())
    session.refresh(visit)
    assert visit.assigned_person_ids == [people["Liisa"].id] and visit.status == "planned"


def test_assign_reasons_cover_each_rule(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(
        session, branch, "Kamppi shop clean", offset=10
    )  # beyond the seeded week: an open visit
    scheduling.assign(session, sanna, visit, people["Aino"])
    other = _visit(
        session, branch, "Kalasatama morning clean", offset=10
    )  # beyond the seeded week: an open visit
    store.update(
        session,
        other,
        {"planned_start": visit.planned_start, "planned_end": visit.planned_end},
        sanna,
    )
    reasons = scheduling.ineligibility(session, branch, other, people["Aino"])
    assert any("double" in r or "booked" in r for r in reasons), reasons
    job = session.get(Job, other.job_id)
    assert job is not None
    store.update(session, job, {"required_skills": ["windows"]}, sanna)
    reasons = scheduling.ineligibility(session, branch, other, people["Mikael"])
    assert any("skill" in r for r in reasons), reasons
    from mia.agents.dispatcher.models import Absence

    store.insert(
        session,
        Absence(
            branch_id=branch.id,
            person_id=people["Mikael"].id,
            date=other.date,
            reported_by=people["Mikael"].id,
        ),
        sanna,
    )
    reasons = scheduling.ineligibility(session, branch, other, people["Mikael"])
    assert any("absent" in r for r in reasons), reasons
    store.update(session, people["Mikael"], {"status": "inactive"}, sanna)
    with pytest.raises(scheduling.ScheduleError, match="not active"):
        scheduling.assign(session, sanna, other, people["Mikael"])


def test_unassign_empties_to_unfilled(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(
        session, branch, "Kamppi shop clean", offset=10
    )  # beyond the seeded week: an open visit
    scheduling.assign(session, sanna, visit, people["Aino"])
    scheduling.unassign(session, sanna, visit, people["Aino"])
    assert visit.assigned_person_ids == [] and visit.status == "unfilled"
    with pytest.raises(scheduling.ScheduleError, match="not assigned"):
        scheduling.unassign(session, sanna, visit, people["Aino"])
