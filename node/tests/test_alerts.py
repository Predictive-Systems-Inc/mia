"""Alerts on the ticker: missed check-in, unstaffed visits tomorrow, the evening daily plan.
Each fires once, at its time of day, to the right people; the app copy (a notification
message) is what the tests read, so no channel is needed."""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from mia.agents.shift_supervisor import alerts
from mia.chat.channels import NOTIFICATION
from mia.core import scheduling, store
from mia.core.models import Actor, Branch, Job, Message, Person, Thread, Visit


def _notes(session: Session, person: Person) -> list[Message]:
    session.expire_all()
    rows = session.exec(
        select(Message)
        .join(Thread, Thread.id == Message.thread_id)  # type: ignore[arg-type]
        .where(Thread.person_id == person.id)
        .where(Message.role == NOTIFICATION)
        .order_by(Message.id)  # type: ignore[arg-type]
    ).all()
    return list(rows)


def _local(branch: Branch, day: dt.date, hhmm: str) -> dt.datetime:
    return scheduling.local_dt(day, hhmm, branch.timezone)


def _today(branch: Branch) -> dt.date:
    return dt.datetime.now(ZoneInfo(branch.timezone)).date()


def test_missed_check_in_alerts_cleaner_and_supervisor_once(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    juha, sanna = people["Juha"], people["Sanna"]
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    visit = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == _today(branch))
    ).one()
    assert juha.id in visit.assigned_person_ids and visit.status == "planned"
    # The ticker passes UTC; SQLite compares ISO strings, so the query must not lean on them.
    early = (visit.planned_start + dt.timedelta(minutes=5)).astimezone(dt.UTC)
    alerts.missed_check_ins(session, early)  # other, earlier visits may alert; this one not
    assert not alerts._marked(session, alerts.MISSED, visit.id)  # inside the grace period
    late = (visit.planned_start + dt.timedelta(minutes=20)).astimezone(dt.UTC)
    assert alerts.missed_check_ins(session, late) == 1
    assert alerts._marked(session, alerts.MISSED, visit.id)
    assert "Kamppi shop" in _notes(session, juha)[-1].text
    assert (
        "Juha" in _notes(session, sanna)[-1].text
        and "Kamppi shop" in _notes(session, sanna)[-1].text
    )
    before = len(_notes(session, juha))
    assert alerts.missed_check_ins(session, late + dt.timedelta(minutes=30)) == 0  # once
    assert len(_notes(session, juha)) == before
    # A visit that was checked in never alerts.
    other = session.exec(
        select(Visit)
        .where(Visit.date == _today(branch))
        .where(Visit.id != visit.id)
        .where(Visit.status == "planned")
    ).first()
    assert other is not None
    person = session.get(Person, other.assigned_person_ids[0])
    assert person is not None
    scheduling.check_in(session, Actor.person(person), other, person, other.planned_start)
    assert alerts.missed_check_ins(session, other.planned_start + dt.timedelta(hours=1)) == 0


def test_unstaffed_visits_tomorrow_go_to_supervisors_once_after_the_check_time(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    sanna = people["Sanna"]
    today = _today(branch)
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    tomorrow = today + dt.timedelta(days=1)
    visit = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == tomorrow)
    ).one()
    scheduling.unassign(session, Actor.person(sanna), visit, people["Juha"])
    assert visit.status == "unfilled"
    assert alerts.unstaffed_visits(session, _local(branch, today, "14:00")) == 0  # before 15:00
    assert alerts.unstaffed_visits(session, _local(branch, today, "15:30")) == 1
    note = _notes(session, sanna)[-1]
    assert any(b["type"] == "card" for b in note.blocks) and "Kamppi shop" in str(note.blocks)
    assert alerts.unstaffed_visits(session, _local(branch, today, "18:00")) == 0  # once a day
    assert alerts.unstaffed_visits(session, _local(branch, tomorrow, "15:30")) == 0  # all staffed


def test_daily_plan_to_each_cleaner_with_visits_once(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    today = _today(branch)
    assert alerts.daily_plan(session, _local(branch, today, "16:00")) == 0  # before 17:00
    sent = alerts.daily_plan(session, _local(branch, today, "17:30"))
    assert sent >= 1
    juha = _notes(session, people["Juha"])[-1]
    assert any(b["type"] == "card" for b in juha.blocks) and "Kamppi shop" in str(juha.blocks)
    assert _notes(session, people["Sanna"]) == []  # no visits: no plan
    assert alerts.daily_plan(session, _local(branch, today, "19:00")) == 0  # once a day


def test_run_due_runs_all_three_from_the_ticker(session: Session, branch: Branch) -> None:
    import asyncio

    from mia.api.main import run_due_work

    asyncio.run(run_due_work())  # no error; what it sends depends on the clock
    assert alerts.run_due(session, _local(branch, _today(branch), "03:00")) >= 0


def test_missed_check_in_of_a_deactivated_cleaner_still_reaches_the_supervisor(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core import people as people_service

    juha, sanna = people["Juha"], people["Sanna"]
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    visit = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == _today(branch))
    ).one()
    people_service.deactivate(session, Actor.person(people["Helena"]), juha)
    late = (visit.planned_start + dt.timedelta(minutes=20)).astimezone(dt.UTC)
    assert alerts.missed_check_ins(session, late) >= 1
    assert any("Kamppi shop" in n.text for n in _notes(session, sanna))
    assert _notes(session, juha) == []  # nothing to a person who left


def test_supervisor_gets_one_message_per_visit_and_once_per_person(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    juha, mikael, sanna = people["Juha"], people["Mikael"], people["Sanna"]
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    visit = session.exec(
        select(Visit).where(Visit.job_id == job.id).where(Visit.date == _today(branch))
    ).one()
    store.update(session, visit, {"assigned_person_ids": [juha.id, mikael.id]}, Actor.person(sanna))
    # Sanna is also an owner for this test: the fallback list must not alert her twice.
    store.update(session, sanna, {"roles": ["supervisor", "owner"]}, Actor.person(people["Helena"]))
    late = (visit.planned_start + dt.timedelta(minutes=20)).astimezone(dt.UTC)
    alerts.missed_check_ins(session, late)
    mine = [n for n in _notes(session, sanna) if "Kamppi shop" in n.text]
    assert len(mine) == 1 and "Juha" in mine[0].text and "Mikael" in mine[0].text


def test_daily_plan_reaches_anyone_assigned(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    sanna = people["Sanna"]
    today = _today(branch)
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    visit = session.exec(
        select(Visit)
        .where(Visit.job_id == job.id)
        .where(Visit.date == today + dt.timedelta(days=1))
    ).one()
    store.update(session, visit, {"assigned_person_ids": [sanna.id]}, Actor.person(sanna))
    alerts.daily_plan(session, _local(branch, today, "17:30"))
    plan = _notes(session, sanna)[-1]
    assert "Kamppi shop" in str(plan.blocks)
    assert not any(b.get("sensitive") for b in plan.blocks) and "Access" not in str(plan.blocks)


def test_a_bad_branch_does_not_silence_the_others(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core.models import Actor as A

    bad = store.insert(
        session,
        Branch(organisation_id=branch.organisation_id, name="Broken", timezone="Nowhere/Bad"),
        A.system(branch.id),
    )
    assert bad.id
    today = _today(branch)
    assert (
        alerts.daily_plan(session, _local(branch, today, "17:30")) >= 1
    )  # the good branch still runs
