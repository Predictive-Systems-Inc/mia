"""Scheduling core: recurrence, generation, assignment rules, check-in and out, week, inbox."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, select

from mia.core import scheduling, store
from mia.core.db import utcnow
from mia.core.models import Actor, Approval, Branch, Event, Job, Location, Person, Visit

MON = dt.date(2026, 10, 12)  # a Monday
TODAY = dt.datetime.now(ZoneInfo("Europe/Helsinki")).date()


def test_recurrence_rules() -> None:
    assert scheduling.occurs_on("FREQ=DAILY", MON, MON + dt.timedelta(days=3))
    assert scheduling.occurs_on("FREQ=WEEKLY;BYDAY=MO,TH", MON, MON + dt.timedelta(days=3))
    assert not scheduling.occurs_on("FREQ=WEEKLY;BYDAY=MO,TH", MON, MON + dt.timedelta(days=1))
    assert scheduling.occurs_on("FREQ=DAILY;INTERVAL=3", MON, MON + dt.timedelta(days=6))
    assert not scheduling.occurs_on("FREQ=DAILY;INTERVAL=3", MON, MON + dt.timedelta(days=4))
    assert not scheduling.occurs_on("FREQ=DAILY;UNTIL=20261013", MON, MON + dt.timedelta(days=2))
    assert scheduling.occurs_on("FREQ=DAILY;UNTIL=20261013", MON, MON + dt.timedelta(days=1))
    for bad in (
        "FREQ=MONTHLY",
        "nonsense",
        "FREQ=WEEKLY",
        "FREQ=DAILY;COUNT=5",
        "FREQ=DAILY;WKST=SU",
    ):
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


def test_generate_due_runs_once_per_local_day_after_three(
    session: Session, branch: Branch, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zoneinfo import ZoneInfo

    calls: list[dt.date] = []
    real = scheduling.generate

    def spy(s: Session, actor: Actor, b: Branch, **kw: object) -> list[Visit]:
        calls.append(kw["today"])  # type: ignore[arg-type]
        return real(s, actor, b, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(scheduling, "generate", spy)
    zone = ZoneInfo(branch.timezone)
    night = dt.datetime(2026, 10, 20, 0, 30, tzinfo=zone)
    assert scheduling.generate_due(session, night) == 0 and calls == []  # before 03:00: wait
    morning = dt.datetime(2026, 10, 20, 3, 5, tzinfo=zone)
    assert scheduling.generate_due(session, morning) > 0 and calls == [dt.date(2026, 10, 20)]
    scheduling.generate_due(session, morning + dt.timedelta(hours=5))
    assert calls == [dt.date(2026, 10, 20)]  # once a day
    scheduling.generate_due(session, morning + dt.timedelta(days=1))
    assert calls == [dt.date(2026, 10, 20), dt.date(2026, 10, 21)]  # the next day runs again


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
    from mia.core.models import Absence

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


def test_check_in_window(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    juha = people["Juha"]
    visit = _visit(session, branch, "Kamppi shop clean", offset=10)
    scheduling.assign(session, Actor.person(people["Sanna"]), visit, juha)
    me = Actor.person(juha)
    early = visit.planned_start - dt.timedelta(hours=2, minutes=1)
    with pytest.raises(scheduling.ScheduleError, match="too early"):
        scheduling.check_in(session, me, visit, juha, early)
    with pytest.raises(scheduling.ScheduleError, match="not assigned"):
        scheduling.check_in(session, me, visit, people["Aino"], visit.planned_start)
    late = visit.planned_end + dt.timedelta(hours=4, minutes=1)
    with pytest.raises(scheduling.ScheduleError, match="too late"):
        scheduling.check_in(session, me, visit, juha, late)
    at = visit.planned_start - dt.timedelta(minutes=5)
    scheduling.check_in(session, me, visit, juha, at)
    assert visit.status == "in_progress" and visit.actual_start == at
    with pytest.raises(scheduling.ScheduleError, match="in_progress"):
        scheduling.check_in(session, me, visit, juha, at)
    with pytest.raises(scheduling.ScheduleError, match="not assigned"):
        scheduling.check_out(session, me, visit, people["Aino"], at)
    done = at + dt.timedelta(minutes=50)
    scheduling.check_out(session, me, visit, juha, done)
    assert visit.status == "completed" and visit.actual_end == done
    actions = {e.action for e in session.exec(select(Event))}
    assert {"visit.checked_in", "visit.checked_out"} <= actions


def test_check_out_needs_in_progress(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    juha = people["Juha"]
    visit = _visit(session, branch, "Kamppi shop clean", offset=10)
    scheduling.assign(session, Actor.person(people["Sanna"]), visit, juha)
    with pytest.raises(scheduling.ScheduleError, match="planned"):
        scheduling.check_out(session, Actor.person(juha), visit, juha, visit.planned_end)


def test_week_filters(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    start = TODAY
    everyone = scheduling.week(session, branch.id, start)
    assert everyone and all(start <= v.date <= start + dt.timedelta(days=6) for v in everyone)
    assert everyone == sorted(everyone, key=lambda v: v.planned_start)
    juha = scheduling.week(session, branch.id, start, person_id=people["Juha"].id)
    assert juha and all(people["Juha"].id in v.assigned_person_ids for v in juha)
    loc = everyone[0].location_id
    here = scheduling.week(session, branch.id, start, location_id=loc)
    assert here and all(v.location_id == loc for v in here)


def test_inbox_filters_by_role_and_escalation(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core import approvals

    sanna, helena = Actor.person(people["Sanna"]), Actor.person(people["Helena"])
    juha = Actor.person(people["Juha"])
    money = approvals.request(
        session, "payout", ("visit", "V"), "money", sanna, ["admin", "owner"], risk="money"
    )
    ops = approvals.request(session, "swap", ("visit", "V"), "swap", juha, ["supervisor"])
    assert [a.id for a in scheduling.inbox(session, sanna)] == [ops.id]
    assert {a.id for a in scheduling.inbox(session, helena)} == {money.id, ops.id}
    store.update(session, ops, {"status": "escalated", "escalate_to": ["owner"]}, sanna)
    assert ops.id in {a.id for a in scheduling.inbox(session, helena)}
    assert ops.id in {a.id for a in scheduling.inbox(session, sanna)}


def test_generate_takes_the_write_lock_before_reading(
    session: Session, branch: Branch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two writers (the ticker and `mia schedule generate`) must not both read the same set of
    existing visits: the lock comes first (rule 11)."""
    from mia.core import events

    order: list[str] = []
    real_lock, real_exec = events.write_lock, Session.exec

    def lock(s: Session) -> None:
        order.append("lock")
        real_lock(s)

    def exec_(self: Session, *a: object, **k: object) -> object:
        order.append("exec")
        return real_exec(self, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(events, "write_lock", lock)
    monkeypatch.setattr(Session, "exec", exec_)
    scheduling.generate(session, Actor.system(branch.id), branch, days=10)
    assert order and order[0] == "lock"


def test_inbox_hides_the_actors_own_requests(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    helena, sanna = Actor.person(people["Helena"]), Actor.person(people["Sanna"])
    visit = _visit(session, branch, "Kamppi shop clean", offset=10)
    out = scheduling.assign(session, sanna, visit, people["Liisa"])  # outside her hours
    assert out.approval_id  # a supervisor's own (an owner's shows to the owner, D37)
    assert out.approval_id not in {a.id for a in scheduling.inbox(session, sanna)}
    aki = Actor.person(
        store.insert(
            session, Person(branch_id=branch.id, name="Aki Admin", roles=["admin"]), helena
        )
    )
    assert out.approval_id in {a.id for a in scheduling.inbox(session, aki)}


def test_repeated_rule_breaking_assign_reuses_the_open_approval(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(session, branch, "Kamppi shop clean", offset=10)
    first = scheduling.assign(session, sanna, visit, people["Liisa"])
    second = scheduling.assign(session, sanna, visit, people["Liisa"])
    assert first.approval_id and second.approval_id == first.approval_id


def test_generate_prefers_the_same_weekday_however_far_back(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    """A MO,TH job with different cleaners: a new Monday copies the Monday cleaner even when
    the last fourteen visits hold no Monday."""
    actor = Actor.person(people["Sanna"])
    loc = session.exec(select(Location)).first()
    assert loc is not None
    job = store.insert(
        session,
        Job(
            branch_id=branch.id,
            location_id=loc.id,
            name="Split",
            recurrence="FREQ=WEEKLY;BYDAY=MO,TH",
            start_time="11:00",
            duration_minutes=60,
        ),
        actor,
    )
    monday = TODAY - dt.timedelta(days=TODAY.weekday() + 7 * 10)  # ten weeks back
    start = scheduling.local_dt(monday, "11:00", branch.timezone)
    store.insert(
        session,
        Visit(
            branch_id=branch.id,
            job_id=job.id,
            location_id=loc.id,
            date=monday,
            planned_start=start,
            planned_end=start + dt.timedelta(hours=1),
            assigned_person_ids=[people["Aino"].id],
            status="completed",
        ),
        actor,
    )
    for weeks in range(1, 16):  # fifteen later Thursdays with Mikael
        thu = monday + dt.timedelta(days=3) + dt.timedelta(weeks=weeks - 1)
        if thu >= TODAY:
            break
        start = scheduling.local_dt(thu, "11:00", branch.timezone)
        store.insert(
            session,
            Visit(
                branch_id=branch.id,
                job_id=job.id,
                location_id=loc.id,
                date=thu,
                planned_start=start,
                planned_end=start + dt.timedelta(hours=1),
                assigned_person_ids=[people["Mikael"].id],
                status="completed",
            ),
            actor,
        )
    new = scheduling.generate(session, actor, branch, days=14)
    mondays = [v for v in new if v.job_id == job.id and v.date.weekday() == 0]
    assert mondays and all(v.assigned_person_ids == [people["Aino"].id] for v in mondays)


def test_the_inbox_shows_an_owner_their_own_request_but_not_a_supervisor(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core import approvals

    def ask(person: Person) -> str:
        actor = Actor.person(person)
        return approvals.request(
            session, "demo", ("visit", "V1"), "x", actor, ["supervisor", "owner"]
        ).id

    helena, sanna = Actor.person(people["Helena"]), Actor.person(people["Sanna"])
    owners, supervisors = ask(people["Helena"]), ask(people["Sanna"])
    assert owners in {a.id for a in scheduling.inbox(session, helena)}  # D37
    assert supervisors not in {a.id for a in scheduling.inbox(session, sanna)}
    assert supervisors in {a.id for a in scheduling.inbox(session, helena)}
