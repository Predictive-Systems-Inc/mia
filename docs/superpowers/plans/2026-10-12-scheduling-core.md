# Scheduling Core and Approvals Inbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Visits exist four weeks ahead from each job's recurrence, the office assigns people under the eligibility rules (an approval when a rule breaks), cleaners check in and out, and the office reads its inbox and week view over the API.

**Architecture:** One service module `core/scheduling.py` (recurrence as pure functions, generation, eligibility data, assign, unassign, check-in, check-out, week, inbox) writing through `store`; one router `api/schedule.py` on `PersonAuth` with `rbac.require`; the dispatcher's tools reuse the shared `candidate_data`. No new tables (Q20, Q21), no dependency.

**Tech Stack:** Python 3.12, FastAPI, SQLModel. No new dependency.

**Spec:** docs/superpowers/specs/2026-10-12-scheduling-core-design.md (assumptions Q19 to Q22 in docs/questions.md).

## Global Constraints

- CLAUDE.md rules 1, 4, 7, 10, 11, 13: writes through `store`, `rbac.require` on every route, scheduling decisions are Python functions with unit tests, ISO times with zone, short write transactions, sessions through `Depends`.
- Eligibility is `scoring.ineligibility` (dispatcher) over `CandidateData`; the same reasons the dispatcher gives.
- Generation horizon 28 days; one visit per (job, date); new visits `planned` with a copied assignee or `unfilled`.
- Check-in window: from 2 hours before `planned_start` until `planned_end` plus 4 hours; only an assigned person (or a supervisor on their behalf); check-out only from `in_progress`.
- Override approval type `schedule.assignment_override`, approver roles `["admin", "owner"]`, channel `app_only`, subject the visit, evidence `{"person_id", "person", "reasons"}`.
- Policy additions: `supervisor` `data:core.visit write`; `staff` `data:core.visit write_own`.
- Check after every task: `uv run ruff check . && uv run ruff format . && uv run mypy node/mia && uv run pytest`.

## Review Focus

1. A job whose rule is `FREQ=WEEKLY;BYDAY=MO;INTERVAL=2` created on a Monday must produce visits every other Monday, not every Monday. Pinned in Task 1 (`test_interval_anchors_on_the_job_creation_date`).
2. Running generation twice on the same day must not duplicate any visit, and running it after a visit was cancelled must not resurrect it. Pinned in Task 1 (`test_generate_is_idempotent_and_leaves_cancelled_visits`).
3. Assigning a person who is already on the visit must be a no-op, not a second entry. Pinned in Task 2 (`test_assign_twice_is_a_no_op`).
4. A check-in at 07:55 for an 08:00 visit on a Helsinki winter day (DST boundary irrelevant to UTC math) must pass; at 05:59 it must fail with the window reason. Pinned in Task 3 (`test_check_in_window`).
5. A supervisor's inbox must not show a money approval they cannot decide (roles admin, owner). Pinned in Task 3 (`test_inbox_filters_by_role_and_escalation`).

## File Structure

- Create `node/mia/core/scheduling.py`: recurrence, `candidate_data`, `generate`, `assign`, `unassign`, `check_in`, `check_out`, `week`, `inbox`, `ScheduleError`, `Assignment`, the override handler.
- Create `node/mia/api/schedule.py`: `/schedule`, `/visits/{id}/assign|unassign|check-in|check-out`, `/approvals`.
- Modify `node/mia/templates/cleaning/seed.py` (use `scheduling.occurs_on`), `node/mia/agents/dispatcher/tools.py` (use `scheduling.candidate_data`), `node/mia/api/main.py` (router, daily generation in `run_due_work`), `node/mia/cli.py` (`mia schedule generate`), `node/config/policies/policy.csv`, `node/mia/static/index.html` (week panel), `docs/layout.md`, `README.md`, `docs/plan.md`.
- Tests: `node/tests/test_scheduling.py` (services), `node/tests/test_schedule_api.py` (routes, CLI, ticker).

---

### Task 1: Recurrence and visit generation

**Files:**
- Create: `node/mia/core/scheduling.py` (part 1)
- Modify: `node/mia/templates/cleaning/seed.py`, `node/mia/cli.py`, `node/mia/api/main.py`
- Test: `node/tests/test_scheduling.py`, `node/tests/test_schedule_api.py` (CLI and ticker parts)

**Interfaces:**
- Produces: `occurs_on(rule: str, anchor: date, day: date) -> bool`, `validate_rule(rule) -> None` (ValueError), `local_dt(day, hhmm, tz) -> datetime`, `generate(session, actor, branch, *, days=28, today=None) -> list[Visit]`, `generate_due(session, now) -> int` (runs `generate` for every branch once per local day; returns new visits), `WEEKDAYS`.

- [ ] **Step 1: Write the failing tests**

`node/tests/test_scheduling.py`:

```python
"""Scheduling core: recurrence, generation, assignment rules, check-in and out, week, inbox."""

import datetime as dt

import pytest
from sqlmodel import Session, select

from mia.core import scheduling, store
from mia.core.db import utcnow
from mia.core.models import Actor, Branch, Event, Job, Location, Person, Visit

MON = dt.date(2026, 10, 12)  # a Monday


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
            select(Visit).where(Visit.branch_id == branch.id).where(Visit.date > dt.date.today())
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
    kamppi = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()  # daily, Juha
    new = scheduling.generate(session, actor, branch, days=28)
    mine = [v for v in new if v.job_id == kamppi.id]
    assert mine and all(v.assigned_person_ids == [people["Juha"].id] for v in mine)
    assert all(v.status == "planned" for v in mine)
    # A job nobody has done yet: unfilled.
    loc = session.exec(select(Location)).first()
    assert loc is not None
    job = store.insert(
        session,
        Job(branch_id=branch.id, location_id=loc.id, name="New site", recurrence="FREQ=DAILY",
            start_time="10:00", duration_minutes=60, required_skills=["general"]),
        actor,
    )
    new = scheduling.generate(session, actor, branch, days=28)
    fresh = [v for v in new if v.job_id == job.id]
    assert len(fresh) == 28 and all(v.status == "unfilled" and v.assigned_person_ids == [] for v in fresh)


def test_generate_skips_a_bad_rule_and_warns(
    session: Session, branch: Branch, people: dict[str, Person], caplog: pytest.LogCaptureFixture
) -> None:
    actor = Actor.person(people["Sanna"])
    loc = session.exec(select(Location)).first()
    assert loc is not None
    store.insert(
        session,
        Job(branch_id=branch.id, location_id=loc.id, name="Odd", recurrence="FREQ=MONTHLY",
            start_time="10:00", duration_minutes=60),
        actor,
    )
    new = scheduling.generate(session, actor, branch, days=7)
    assert new and "Odd" in caplog.text and "FREQ=MONTHLY" in caplog.text


def test_generate_due_runs_once_per_local_day(session: Session, branch: Branch) -> None:
    now = utcnow()
    first = scheduling.generate_due(session, now)
    assert first > 0
    assert scheduling.generate_due(session, now + dt.timedelta(hours=1)) == 0
    assert scheduling.generate_due(session, now + dt.timedelta(days=1)) >= 0  # a new day runs again
```

`node/tests/test_schedule_api.py` (CLI and ticker parts; the routes come in Task 4):

```python
"""Schedule over the API and the CLI; daily generation on the ticker."""

import asyncio

import pytest
from sqlmodel import Session, select

from mia.cli import main
from mia.core.models import Visit


def test_cli_generate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate"]) == 0 and main(["seed"]) == 0
    assert main(["schedule", "generate", "--days", "14"]) == 0
    out = capsys.readouterr().out
    assert "generated" in out
    assert main(["schedule", "generate", "--days", "14"]) == 0
    assert "generated 0" in capsys.readouterr().out


def test_ticker_generates_once_a_day(session: Session, branch: object) -> None:
    from mia.api.main import run_due_work

    before = len(session.exec(select(Visit)).all())
    asyncio.run(run_due_work())
    session.expire_all()
    after = len(session.exec(select(Visit)).all())
    assert after > before
    asyncio.run(run_due_work())
    session.expire_all()
    assert len(session.exec(select(Visit)).all()) == after
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/test_scheduling.py node/tests/test_schedule_api.py --no-cov -q`
Expected: ModuleNotFoundError `mia.core.scheduling`.

- [ ] **Step 3: The module (part 1)**

```python
"""Scheduling core (plan item 4, Sprint 2): recurrence rules, visit generation, eligibility,
assignment, check-in and check-out, the week view and the approvals inbox.

Guarantees: scheduling decisions are code (rule 7); every write goes through store and emits
an event; one visit per (job, date); a rule-breaking assignment needs an approval
(`schedule.assignment_override`, admin or owner, app only) and the visit does not change
until it is approved.
"""

import datetime as dt
import logging
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from mia.agents.dispatcher import scoring
from mia.core import approvals, store
from mia.core.models import (
    Actor,
    Approval,
    Availability,
    Branch,
    Job,
    Location,
    Person,
    Visit,
    WorkLimit,
)

log = logging.getLogger(__name__)
WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
HORIZON_DAYS = 28
OVERRIDE_TYPE = "schedule.assignment_override"
OVERRIDE_ROLES = ["admin", "owner"]
CHECK_IN_EARLY = dt.timedelta(hours=2)
CHECK_IN_LATE = dt.timedelta(hours=4)


class ScheduleError(RuntimeError):
    """A refused scheduling operation; the message is the reason."""


# ---- recurrence (pure) -------------------------------------------------------------------


def _parts(rule: str) -> dict[str, str]:
    try:
        parts = dict(p.split("=", 1) for p in rule.split(";") if p)
    except ValueError as exc:
        raise ValueError(f"unsupported recurrence {rule!r}") from exc
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        raise ValueError(f"unsupported recurrence {rule!r}")
    if freq == "WEEKLY" and not parts.get("BYDAY"):
        raise ValueError(f"weekly recurrence needs BYDAY: {rule!r}")
    if any(d not in WEEKDAYS for d in parts.get("BYDAY", "MO").split(",")):
        raise ValueError(f"unknown weekday in {rule!r}")
    if int(parts.get("INTERVAL", "1")) < 1:
        raise ValueError(f"INTERVAL must be positive: {rule!r}")
    if "UNTIL" in parts:
        dt.datetime.strptime(parts["UNTIL"][:8], "%Y%m%d")
    return parts


def validate_rule(rule: str) -> None:
    """Raise ValueError unless the rule is FREQ=DAILY or FREQ=WEEKLY;BYDAY=.. with an optional
    INTERVAL and UNTIL."""
    _parts(rule)


def occurs_on(rule: str, anchor: dt.date, day: dt.date) -> bool:
    """True when the rule has an occurrence on `day`. INTERVAL counts days (DAILY) or weeks
    (WEEKLY) from `anchor` (the job's creation date, local)."""
    parts = _parts(rule)
    if day < anchor:
        return False
    if "UNTIL" in parts and day > dt.datetime.strptime(parts["UNTIL"][:8], "%Y%m%d").date():
        return False
    interval = int(parts.get("INTERVAL", "1"))
    if parts["FREQ"] == "DAILY":
        return (day - anchor).days % interval == 0
    if WEEKDAYS[day.weekday()] not in parts["BYDAY"].split(","):
        return False
    week_of = lambda d: (d - dt.timedelta(days=d.weekday()))  # noqa: E731 - the Monday
    return ((week_of(day) - week_of(anchor)).days // 7) % interval == 0


def local_dt(day: dt.date, hhmm: str, tz: str) -> dt.datetime:
    """A local wall-clock time on a day, in the branch time zone."""
    hour, minute = map(int, hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=ZoneInfo(tz))


# ---- generation ------------------------------------------------------------------------


def _anchor(job: Job, tz: str) -> dt.date:
    return job.created_at.astimezone(ZoneInfo(tz)).date()


def _last_assignees(session: Session, job: Job, day: dt.date) -> list[str]:
    """Who did this job most recently on the same weekday (the copied assignment, Q21)."""
    rows = session.exec(
        select(Visit)
        .where(Visit.job_id == job.id)
        .where(col(Visit.date) < day)
        .where(Visit.status != "cancelled")
        .order_by(col(Visit.date).desc())
        .limit(14)
    ).all()
    for v in rows:
        if v.date.weekday() == day.weekday() and v.assigned_person_ids:
            return list(v.assigned_person_ids)
    return list(rows[0].assigned_person_ids) if rows else []


def generate(
    session: Session,
    actor: Actor,
    branch: Branch,
    *,
    days: int = HORIZON_DAYS,
    today: dt.date | None = None,
) -> list[Visit]:
    """Create the missing visits of every job for the next `days` days. Existing (job, date)
    pairs are left alone, cancelled ones included. New visits copy the last assignment on the
    same weekday when that person is still eligible, else they are `unfilled`."""
    tz = branch.timezone
    today = today or dt.datetime.now(ZoneInfo(tz)).date()
    jobs = session.exec(select(Job).where(Job.branch_id == branch.id)).all()
    existing = {
        (v.job_id, v.date)
        for v in session.exec(
            select(Visit).where(Visit.branch_id == branch.id).where(col(Visit.date) >= today)
        )
    }
    new: list[Visit] = []
    for job in jobs:
        try:
            validate_rule(job.recurrence)
        except ValueError as exc:
            log.warning("job %s (%s) skipped: %s", job.name, job.id, exc)
            continue
        anchor = _anchor(job, tz)
        for offset in range(days):
            day = today + dt.timedelta(days=offset)
            if (job.id, day) in existing or not occurs_on(job.recurrence, anchor, day):
                continue
            start = local_dt(day, job.start_time, tz)
            visit = Visit(
                branch_id=branch.id,
                job_id=job.id,
                location_id=job.location_id,
                date=day,
                planned_start=start,
                planned_end=start + dt.timedelta(minutes=job.duration_minutes),
                status="unfilled",
            )
            people = [
                p
                for pid in _last_assignees(session, job, day)
                if (p := session.get(Person, pid)) is not None and p.status == "active"
            ]
            keep = [p.id for p in people if not ineligibility(session, branch, visit, p)]
            if keep:
                visit.assigned_person_ids = keep
                visit.status = "planned"
            new.append(store.insert(session, visit, actor, action="visit.generated"))
            existing.add((job.id, day))
    return new


_generated_on: dict[str, dt.date] = {}


def generate_due(session: Session, now: dt.datetime) -> int:
    """Run generation for every branch once per local day (the ticker). Returns new visits."""
    count = 0
    for branch in session.exec(select(Branch)).all():
        local_day = now.astimezone(ZoneInfo(branch.timezone)).date()
        if _generated_on.get(branch.id) == local_day:
            continue
        count += len(generate(session, Actor.system(branch.id), branch, today=local_day))
        _generated_on[branch.id] = local_day
    return count


def reset_generation() -> None:
    """Forget the per-day marker (tests)."""
    _generated_on.clear()
```

`ineligibility(session, branch, visit, person)` and `candidate_data` come in Task 2; for Task 1 define `ineligibility` as it will be (it is part of the same module, so write both now; Task 2 adds the tests for it and the dispatcher switch).

Seed: replace its own `occurs_on`, `local_dt` and `WEEKDAYS` with imports from `mia.core.scheduling` (`occurs_on(rrule, today - dt.timedelta(days=14), day)`, the anchor being the first seeded day). CLI: `mia schedule generate [--days N]` → `schedule_generate` running `generate` for the only branch (`_only_branch_id`) with `Actor.system`, printing `generated N visit(s)`. `main.run_due_work`: before the cover tick, `generated = await asyncio.to_thread(_generate)` where `_generate` opens a session and calls `scheduling.generate_due(session, utcnow())`; return value stays a 2-tuple (the ticker's callers read two counts) and the count is logged. conftest: reset `scheduling.reset_generation()` in the autouse fixture.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run pytest node/tests/test_scheduling.py node/tests/test_schedule_api.py --no-cov -q`, then the full check line. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "scheduling: recurrence rules and visit generation; mia schedule generate; daily generation on the ticker"
```

---

### Task 2: Eligibility, assign and unassign (with the override approval)

**Files:**
- Modify: `node/mia/core/scheduling.py` (part 2), `node/mia/agents/dispatcher/tools.py` (use `scheduling.candidate_data`)
- Test: `node/tests/test_scheduling.py`

**Interfaces:**
- Produces: `candidate_data(session, branch, visit, *, include_assigned=False, only: set[str] | None = None) -> list[scoring.CandidateData]`, `ineligibility(session, branch, visit, person) -> list[str]`, `Assignment(visit: Visit, approval_id: str | None, reasons: list[str])`, `assign(session, actor, visit, person, *, add=False, override_approved=False) -> Assignment`, `unassign(session, actor, visit, person) -> Visit`, `on_override_approved` registered for `OVERRIDE_TYPE`.
- The dispatcher's `candidate_data(session, deps, visit, *, include_assigned=False)` becomes a one-line wrapper on `scheduling.candidate_data(session, deps.branch, visit, include_assigned=include_assigned)`.

- [ ] **Step 1: Write the failing tests**

Append to `node/tests/test_scheduling.py`:

```python
def _visit(session: Session, branch: Branch, name: str, offset: int = 1) -> Visit:
    job = session.exec(select(Job).where(Job.name == name)).one()
    day = dt.date.today() + dt.timedelta(days=offset)
    row = session.exec(select(Visit).where(Visit.job_id == job.id).where(Visit.date == day)).first()
    if row is None:
        start = scheduling.local_dt(day, job.start_time, branch.timezone)
        row = store.insert(
            session,
            Visit(branch_id=branch.id, job_id=job.id, location_id=job.location_id, date=day,
                  planned_start=start, planned_end=start + dt.timedelta(minutes=job.duration_minutes),
                  status="unfilled"),
            Actor.system(branch.id),
        )
    return row


def test_assign_eligible_replaces_and_add_keeps(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(session, branch, "Kamppi shop clean", offset=2)
    out = scheduling.assign(session, sanna, visit, people["Aino"])
    assert out.approval_id is None and visit.assigned_person_ids == [people["Aino"].id]
    assert visit.status == "planned"
    out = scheduling.assign(session, sanna, visit, people["Mikael"], add=True)
    assert visit.assigned_person_ids == [people["Aino"].id, people["Mikael"].id]
    scheduling.assign(session, sanna, visit, people["Juha"])
    assert visit.assigned_person_ids == [people["Juha"].id]
    assert session.exec(select(Event).where(Event.action == "visit.assigned")).first()


def test_assign_twice_is_a_no_op(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(session, branch, "Kamppi shop clean", offset=2)
    scheduling.assign(session, sanna, visit, people["Aino"])
    events = len(session.exec(select(Event).where(Event.action == "visit.assigned")).all())
    scheduling.assign(session, sanna, visit, people["Aino"], add=True)
    assert visit.assigned_person_ids == [people["Aino"].id]
    assert len(session.exec(select(Event).where(Event.action == "visit.assigned")).all()) == events


def test_rule_breaking_assignment_needs_an_approval_then_applies(
    session: Session, branch: Branch, people: dict[str, Person]
) -> None:
    from mia.core import approvals

    sanna = Actor.person(people["Sanna"])
    visit = _visit(session, branch, "Kamppi shop clean", offset=2)  # 09:00; Liisa works 10 to 18
    out = scheduling.assign(session, sanna, visit, people["Liisa"])
    assert out.approval_id and visit.assigned_person_ids == [] and visit.status == "unfilled"
    assert any("availab" in r for r in out.reasons)
    approval = session.get(Approval, out.approval_id)
    assert approval is not None and approval.type == "schedule.assignment_override"
    assert approval.approver_roles == ["admin", "owner"] and approval.channel == "app_only"
    assert approval.evidence["person_id"] == people["Liisa"].id and approval.evidence["reasons"]
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(session, approval.id, sanna, "approved", stepped_up_at=utcnow())
    approvals.decide(session, approval.id, Actor.person(people["Helena"]), "approved", stepped_up_at=utcnow())
    session.refresh(visit)
    assert visit.assigned_person_ids == [people["Liisa"].id] and visit.status == "planned"


def test_assign_reasons_cover_each_rule(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(session, branch, "Kamppi shop clean", offset=2)
    # Double-booked: Juha already has the same slot elsewhere? Give Aino the Kamppi slot, then
    # a second visit at the same time at Kalasatama.
    scheduling.assign(session, sanna, visit, people["Aino"])
    other = _visit(session, branch, "Kalasatama office clean", offset=2)
    store.update(session, other, {"planned_start": visit.planned_start, "planned_end": visit.planned_end}, sanna)
    reasons = scheduling.ineligibility(session, branch, other, people["Aino"])
    assert any("double" in r or "booked" in r for r in reasons)
    # Skills: a job needing a skill the person lacks.
    store.update(session, other, {"required_skills": ["windows"]}, sanna)
    assert any("skill" in r for r in scheduling.ineligibility(session, branch, other, people["Mikael"]))
    # Absent: recorded through the dispatcher's table.
    from mia.agents.dispatcher.models import Absence

    store.insert(session, Absence(branch_id=branch.id, person_id=people["Mikael"].id, date=other.date, reported_by=people["Mikael"].id), sanna)
    assert any("absent" in r for r in scheduling.ineligibility(session, branch, other, people["Mikael"]))
    # Inactive people are never eligible.
    store.update(session, people["Mikael"], {"status": "inactive"}, sanna)
    with pytest.raises(scheduling.ScheduleError, match="not active"):
        scheduling.assign(session, sanna, other, people["Mikael"])


def test_unassign_empties_to_unfilled(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    sanna = Actor.person(people["Sanna"])
    visit = _visit(session, branch, "Kamppi shop clean", offset=2)
    scheduling.assign(session, sanna, visit, people["Aino"])
    scheduling.unassign(session, sanna, visit, people["Aino"])
    assert visit.assigned_person_ids == [] and visit.status == "unfilled"
    with pytest.raises(scheduling.ScheduleError, match="not assigned"):
        scheduling.unassign(session, sanna, visit, people["Aino"])
```

Check `Approval` is imported at the top of the test file (add it to the models import). Look at the seed for Liisa's availability (10:00 to 18:00 per the dispatcher tests) and the job names (`Kalasatama office clean` exists in the seed's JOBS list; adjust the name to the seed if it differs).

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/test_scheduling.py -k "assign or unassign or reasons" --no-cov -q`
Expected: AttributeError `assign`.

- [ ] **Step 3: The module (part 2)**

Append to `node/mia/core/scheduling.py`:

```python
# ---- eligibility -------------------------------------------------------------------------


def _slot(session: Session, visit: Visit, tz: str) -> scoring.Slot:
    zone = ZoneInfo(tz)
    loc = session.get(Location, visit.location_id)
    where = (loc.lat, loc.lon) if loc and loc.lat is not None and loc.lon is not None else None
    return scoring.Slot(visit.planned_start.astimezone(zone), visit.planned_end.astimezone(zone), where)


def candidate_data(
    session: Session,
    branch: Branch,
    visit: Visit,
    *,
    include_assigned: bool = False,
    only: set[str] | None = None,
) -> list[scoring.CandidateData]:
    """Everything scoring needs for the active staff of the branch (or `only` those ids):
    availability windows, hour limits, this week's bookings, absences, site history."""
    from mia.agents.dispatcher.models import Absence  # absences are the dispatcher's records

    tz = branch.timezone
    week_start = visit.date - dt.timedelta(days=visit.date.weekday())
    week_end = week_start + dt.timedelta(days=6)
    persons = session.exec(
        select(Person).where(Person.branch_id == branch.id).where(Person.status == "active")
    ).all()
    week_visits = [
        v
        for v in session.exec(
            select(Visit)
            .where(Visit.branch_id == branch.id)
            .where(col(Visit.date) >= week_start)
            .where(col(Visit.date) <= week_end)
            .where(Visit.status != "cancelled")
        ).all()
        if v.id != visit.id
    ]
    slots = {v.id: _slot(session, v, tz) for v in week_visits}
    past_here = session.exec(
        select(Visit).where(Visit.location_id == visit.location_id).where(Visit.status == "completed")
    ).all()
    result = []
    for p in persons:
        if "staff" not in p.roles or (only is not None and p.id not in only):
            continue
        if p.id in visit.assigned_person_ids and not include_assigned:
            continue
        windows = {
            a.weekday: (dt.time.fromisoformat(a.start), dt.time.fromisoformat(a.end))
            for a in session.exec(select(Availability).where(Availability.person_id == p.id))
        }
        limit = session.exec(select(WorkLimit).where(WorkLimit.person_id == p.id)).first()
        absences = session.exec(select(Absence).where(Absence.person_id == p.id)).all()
        home = (p.home_lat, p.home_lon) if p.home_lat is not None and p.home_lon is not None else None
        result.append(
            scoring.CandidateData(
                person_id=p.id,
                name=p.name,
                skills=list(p.skills),
                windows=windows,
                max_daily_minutes=limit.max_daily_minutes if limit else 600,
                max_weekly_minutes=limit.max_weekly_minutes if limit else 2400,
                booked=[slots[v.id] for v in week_visits if p.id in v.assigned_person_ids],
                absent_dates={a.date for a in absences},
                site_visits=sum(1 for v in past_here if p.id in v.assigned_person_ids),
                home=home,
            )
        )
    return result


def ineligibility(session: Session, branch: Branch, visit: Visit, person: Person) -> list[str]:
    """Why the person may not take the visit (empty when they may): the dispatcher's reasons
    plus missing skills. An inactive or non-staff person gets one reason."""
    if person.status != "active":
        return ["person is not active"]
    if "staff" not in person.roles:
        return ["not a staff member"]
    job = session.get(Job, visit.job_id)
    data = candidate_data(session, branch, visit, include_assigned=True, only={person.id})
    if not data:
        return ["person is not active"]
    reasons = scoring.ineligibility(data[0], _slot(session, visit, branch.timezone))
    missing = sorted(set(job.required_skills if job else []) - set(person.skills))
    if missing:
        reasons.append("missing skills: " + ", ".join(missing))
    return reasons


# ---- assignment --------------------------------------------------------------------------


@dataclass(frozen=True)
class Assignment:
    visit: Visit
    approval_id: str | None
    reasons: list[str]


def _apply(session: Session, actor: Actor, visit: Visit, person: Person, add: bool, **kw: str | None) -> Visit:
    ids = list(visit.assigned_person_ids) if add else []
    if person.id in ids:
        return visit
    ids.append(person.id)
    return store.update(
        session, visit, {"assigned_person_ids": ids, "status": "planned"}, actor,
        action="visit.assigned", approval_id=kw.get("approval_id"),
    )


def assign(
    session: Session,
    actor: Actor,
    visit: Visit,
    person: Person,
    *,
    add: bool = False,
    override_approved: bool = False,
) -> Assignment:
    """Put the person on the visit (replacing the assignees unless `add`). Eligible: done and
    `visit.assigned`. Not eligible: an override approval is created and the visit is unchanged
    until an admin or owner approves it. ScheduleError for an inactive person or a visit that
    is not open."""
    if visit.status not in ("planned", "unfilled"):
        raise ScheduleError(f"visit is {visit.status}")
    if person.status != "active":
        raise ScheduleError("person is not active")
    if person.id in visit.assigned_person_ids and (add or visit.assigned_person_ids == [person.id]):
        return Assignment(visit, None, [])
    branch = session.get(Branch, visit.branch_id)
    assert branch is not None
    reasons = [] if override_approved else ineligibility(session, branch, visit, person)
    if reasons:
        approval = approvals.request(
            session,
            OVERRIDE_TYPE,
            ("visit", visit.id),
            f"Assign {person.name} to a visit outside the rules: " + "; ".join(reasons),
            actor,
            OVERRIDE_ROLES,
            "app_only",
            evidence={"person_id": person.id, "person": person.name, "reasons": reasons, "add": add},
        )
        return Assignment(visit, approval.id, reasons)
    return Assignment(_apply(session, actor, visit, person, add), None, [])


def unassign(session: Session, actor: Actor, visit: Visit, person: Person) -> Visit:
    """Take the person off the visit; nobody left makes it `unfilled`."""
    if person.id not in visit.assigned_person_ids:
        raise ScheduleError("person is not assigned to this visit")
    ids = [i for i in visit.assigned_person_ids if i != person.id]
    status = visit.status if ids else "unfilled"
    return store.update(
        session, visit, {"assigned_person_ids": ids, "status": status}, actor, action="visit.unassigned"
    )


def on_override_approved(session: Session, approval: Approval, decider: Actor) -> None:
    """Approval handler: apply the assignment the office asked for."""
    visit = session.get(Visit, approval.subject_id)
    person = session.get(Person, str(approval.evidence.get("person_id")))
    if visit is None or person is None or visit.status not in ("planned", "unfilled"):
        return
    _apply(session, decider, visit, person, bool(approval.evidence.get("add")), approval_id=approval.id)


approvals.register_handler(OVERRIDE_TYPE, on_override_approved)
```

In `node/mia/agents/dispatcher/tools.py`, replace the body of `candidate_data` with `return scheduling.candidate_data(session, deps.branch, visit, include_assigned=include_assigned)` and delete `_slot` there (import `from mia.core import scheduling`; drop the now-unused imports of `Absence`, `Availability`, `WorkLimit`, `ZoneInfo` if nothing else uses them). The dispatcher's `_slot` callers switch to `scheduling._slot` or, cleaner, scheduling exports `slot_of(session, visit, tz)`; name it `slot_of` in scheduling and use it from both.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run pytest node/tests/test_scheduling.py node/tests/test_tools.py node/tests/test_cover.py --no-cov -q`, then the full check line. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "scheduling: eligibility shared with the dispatcher, assign and unassign, override approval"
```

---

### Task 3: Check-in, check-out, week view and inbox

**Files:**
- Modify: `node/mia/core/scheduling.py` (part 3)
- Test: `node/tests/test_scheduling.py`

**Interfaces:**
- Produces: `check_in(session, actor, visit, person, now) -> Visit`, `check_out(session, actor, visit, person, now) -> Visit`, `week(session, branch_id, start, *, person_id=None, location_id=None) -> list[Visit]`, `inbox(session, actor) -> list[Approval]`.

- [ ] **Step 1: Write the failing tests**

Append to `node/tests/test_scheduling.py`:

```python
def test_check_in_window(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    juha = people["Juha"]
    visit = _visit(session, branch, "Kamppi shop clean", offset=1)
    scheduling.assign(session, Actor.person(people["Sanna"]), visit, juha)
    early = visit.planned_start - dt.timedelta(hours=2, minutes=1)
    with pytest.raises(scheduling.ScheduleError, match="too early"):
        scheduling.check_in(session, Actor.person(juha), visit, juha, early)
    with pytest.raises(scheduling.ScheduleError, match="not assigned"):
        scheduling.check_in(session, Actor.person(juha), visit, people["Aino"], visit.planned_start)
    late = visit.planned_end + dt.timedelta(hours=4, minutes=1)
    with pytest.raises(scheduling.ScheduleError, match="too late"):
        scheduling.check_in(session, Actor.person(juha), visit, juha, late)
    at = visit.planned_start - dt.timedelta(minutes=5)
    scheduling.check_in(session, Actor.person(juha), visit, juha, at)
    assert visit.status == "in_progress" and visit.actual_start == at
    with pytest.raises(scheduling.ScheduleError, match="in_progress"):
        scheduling.check_in(session, Actor.person(juha), visit, juha, at)
    with pytest.raises(scheduling.ScheduleError, match="not assigned"):
        scheduling.check_out(session, Actor.person(juha), visit, people["Aino"], at)
    done = at + dt.timedelta(minutes=50)
    scheduling.check_out(session, Actor.person(juha), visit, juha, done)
    assert visit.status == "completed" and visit.actual_end == done
    actions = {e.action for e in session.exec(select(Event))}
    assert {"visit.checked_in", "visit.checked_out"} <= actions


def test_check_out_needs_in_progress(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    juha = people["Juha"]
    visit = _visit(session, branch, "Kamppi shop clean", offset=1)
    scheduling.assign(session, Actor.person(people["Sanna"]), visit, juha)
    with pytest.raises(scheduling.ScheduleError, match="planned"):
        scheduling.check_out(session, Actor.person(juha), visit, juha, visit.planned_end)


def test_week_filters(session: Session, branch: Branch, people: dict[str, Person]) -> None:
    start = dt.date.today()
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
    money = approvals.request(session, "payout", ("visit", "V"), "money", sanna, ["admin", "owner"], risk="money")
    ops = approvals.request(session, "swap", ("visit", "V"), "swap", Actor.person(people["Juha"]), ["supervisor"])
    assert [a.id for a in scheduling.inbox(session, sanna)] == [ops.id]
    assert {a.id for a in scheduling.inbox(session, helena)} == {money.id, ops.id}  # owner outranks all
    # Escalated: the escalate_to roles see it too.
    store.update(session, ops, {"status": "escalated", "escalate_to": ["owner"]}, sanna)
    assert ops.id in {a.id for a in scheduling.inbox(session, helena)}
    assert ops.id in {a.id for a in scheduling.inbox(session, sanna)}  # still a supervisor's
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/test_scheduling.py -k "check or week or inbox" --no-cov -q`
Expected: AttributeError `check_in`.

- [ ] **Step 3: The module (part 3)**

```python
# ---- check-in and check-out ------------------------------------------------------------


def check_in(session: Session, actor: Actor, visit: Visit, person: Person, now: dt.datetime) -> Visit:
    """Mark the visit in progress for an assigned person, from 2 hours before the planned
    start until 4 hours after the planned end."""
    if person.id not in visit.assigned_person_ids:
        raise ScheduleError("person is not assigned to this visit")
    if visit.status != "planned":
        raise ScheduleError(f"visit is {visit.status}")
    if now < visit.planned_start - CHECK_IN_EARLY:
        raise ScheduleError("too early to check in")
    if now > visit.planned_end + CHECK_IN_LATE:
        raise ScheduleError("too late to check in")
    return store.update(
        session, visit, {"actual_start": now, "status": "in_progress"}, actor, action="visit.checked_in"
    )


def check_out(session: Session, actor: Actor, visit: Visit, person: Person, now: dt.datetime) -> Visit:
    """Complete a visit in progress for an assigned person."""
    if person.id not in visit.assigned_person_ids:
        raise ScheduleError("person is not assigned to this visit")
    if visit.status != "in_progress":
        raise ScheduleError(f"visit is {visit.status}")
    return store.update(
        session, visit, {"actual_end": now, "status": "completed"}, actor, action="visit.checked_out"
    )


# ---- reading ------------------------------------------------------------------------------


def week(
    session: Session,
    branch_id: str,
    start: dt.date,
    *,
    person_id: str | None = None,
    location_id: str | None = None,
) -> list[Visit]:
    """Seven days of visits from `start`, by planned start; optionally one person's or one
    site's."""
    stmt = (
        select(Visit)
        .where(Visit.branch_id == branch_id)
        .where(col(Visit.date) >= start)
        .where(col(Visit.date) <= start + dt.timedelta(days=6))
        .order_by(col(Visit.planned_start))
    )
    if location_id is not None:
        stmt = stmt.where(Visit.location_id == location_id)
    rows = list(session.exec(stmt).all())
    if person_id is not None:
        rows = [v for v in rows if person_id in v.assigned_person_ids]
    return rows


def inbox(session: Session, actor: Actor) -> list[Approval]:
    """Pending and escalated approvals the actor may decide (approver roles, or the escalation
    roles once escalated), oldest first. Owners outrank everyone (policy.csv hierarchy)."""
    from mia.core.rbac import get_rbac

    enforcer = get_rbac().enforcer
    mine = set(actor.principal.roles)
    for role in list(mine):
        mine.update(enforcer.get_implicit_roles_for_user(role, "*"))
    out = []
    for approval in approvals.pending(session, actor.branch_id):
        roles = set(approval.approver_roles)
        if approval.status == "escalated":
            roles |= set(approval.escalate_to)
        if roles & mine:
            out.append(approval)
    return out
```

Casbin's `get_implicit_roles_for_user(role, domain)` returns the roles a role inherits through `g` lines (owner → admin → supervisor → staff); verify the method name against the installed pycasbin (`enforcer.get_implicit_roles_for_user`), and if the domain matching function makes `"*"` fail, use `get_roles_for_user_in_domain`.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run pytest node/tests/test_scheduling.py --no-cov -q`, then the full check line. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "scheduling: check-in and check-out, the week view and the approvals inbox"
```

---

### Task 4: API routes, policy, the week panel

**Files:**
- Create: `node/mia/api/schedule.py`
- Modify: `node/mia/api/main.py` (include router), `node/config/policies/policy.csv`, `node/mia/static/index.html`
- Test: `node/tests/test_schedule_api.py`

**Interfaces:**
- Routes as in spec section 5; bodies `AssignIn(person_id: str, add: bool = False)`, `PersonIn(person_id: str | None = None)`; `VisitCard(id, date, start, end, job, location, address, assignees: list[{id, name}], status)`; `ApprovalCard(id, type, summary, evidence, requester_id, created_at, expires_at, status, channel)`.

- [ ] **Step 1: Write the failing tests**

Append to `node/tests/test_schedule_api.py`:

```python
import datetime as dt

from fastapi.testclient import TestClient

from mia.api.main import app
from mia.core import scheduling, store
from mia.core.models import Actor, Branch, Job, Person


@pytest.fixture
def client(branch: object) -> TestClient:
    return TestClient(app)


def _visit_id(session: Session, branch: Branch, offset: int = 2) -> str:
    job = session.exec(select(Job).where(Job.name == "Kamppi shop clean")).one()
    actor = Actor.system(branch.id)
    scheduling.generate(session, actor, branch, days=7)
    day = dt.date.today() + dt.timedelta(days=offset)
    from mia.core.models import Visit as V

    row = session.exec(select(V).where(V.job_id == job.id).where(V.date == day)).one()
    session.commit()
    return row.id


def test_week_view_and_permissions(client: TestClient, session: Session, branch: Branch, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    login(client, people["Juha"])
    res = client.get("/schedule")
    assert res.status_code == 200
    cards = res.json()
    assert cards and all(people["Juha"].id in [a["id"] for a in c["assignees"]] for c in cards)
    assert {"id", "date", "start", "end", "job", "location", "address", "assignees", "status"} <= set(cards[0])
    assert client.get(f"/schedule?person_id={people['Aino'].id}").status_code == 403
    sup = TestClient(app)
    login(sup, people["Sanna"])
    assert len(sup.get("/schedule").json()) >= len(cards)
    assert sup.get(f"/schedule?person_id={people['Aino'].id}").status_code == 200
    assert sup.get("/schedule?start=2026-13-01").status_code == 422


def test_assign_unassign_and_override_over_http(client: TestClient, session: Session, branch: Branch, people: dict[str, Person], login) -> None:  # type: ignore[no-untyped-def]
    visit_id = _visit_id(session, branch)
    login(client, people["Juha"])
    assert client.post(f"/visits/{visit_id}/assign", json={"person_id": people["Aino"].id}).status_code == 403
    sup = TestClient(app)
    login(sup, people["Sanna"])
    res = sup.post(f"/visits/{visit_id}/assign", json={"person_id": people["Aino"].id})
    assert res.status_code == 200 and res.json()["approval_id"] is None
    res = sup.post(f"/visits/{visit_id}/assign", json={"person_id": people["Liisa"].id})
    assert res.status_code == 200 and res.json()["approval_id"] and res.json()["reasons"]
    assert sup.get("/approvals").json() == []  # a supervisor cannot decide it
    admin = TestClient(app)
    login(admin, people["Helena"], stepped_up=True)
    inbox = admin.get("/approvals").json()
    assert [a["id"] for a in inbox] == [res.json()["approval_id"]] and inbox[0]["type"] == "schedule.assignment_override"
    assert admin.post(f"/approvals/{inbox[0]['id']}/decide", json={"outcome": "approved"}).status_code == 200
    assert [a["id"] for a in sup.get(f"/schedule?person_id={people['Liisa'].id}").json()[0]["assignees"]] == [people["Liisa"].id]
    assert sup.post(f"/visits/{visit_id}/unassign", json={"person_id": people["Liisa"].id}).status_code == 200
    res = sup.post(f"/visits/{visit_id}/unassign", json={"person_id": people["Liisa"].id})
    assert res.status_code == 409 and "not assigned" in res.json()["detail"]
    assert sup.post("/visits/nope/assign", json={"person_id": people["Aino"].id}).status_code == 404


def test_check_in_and_out_over_http(client: TestClient, session: Session, branch: Branch, people: dict[str, Person], login, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    visit_id = _visit_id(session, branch, offset=1)
    from mia.core.models import Visit as V

    visit = session.get(V, visit_id)
    assert visit is not None
    scheduling.assign(session, Actor.person(people["Sanna"]), visit, people["Juha"])
    session.commit()
    from mia.api import schedule as api

    monkeypatch.setattr(api, "utcnow", lambda: visit.planned_start - dt.timedelta(minutes=10))
    login(client, people["Juha"])
    assert client.post(f"/visits/{visit_id}/check-in").status_code == 200
    aino = TestClient(app)
    login(aino, people["Aino"])
    assert aino.post(f"/visits/{visit_id}/check-out").status_code == 403  # not her visit
    sup = TestClient(app)
    login(sup, people["Sanna"])
    monkeypatch.setattr(api, "utcnow", lambda: visit.planned_end)
    res = sup.post(f"/visits/{visit_id}/check-out", json={"person_id": people["Juha"].id})
    assert res.status_code == 200 and res.json()["status"] == "completed"
    assert client.post(f"/visits/{visit_id}/check-in").status_code == 409
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest node/tests/test_schedule_api.py --no-cov -q`
Expected: 404 on `/schedule`.

- [ ] **Step 3: The router**

```python
"""Schedule routes (plan item 4): the week view, assignment, check-in and check-out, and the
approvals inbox. Every route takes the signed-in person and checks RBAC (rule 4)."""

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from mia.api.deps import AuthContext, DbSession, PersonAuth
from mia.core import scheduling
from mia.core.db import utcnow
from mia.core.models import Branch, Job, Location, Person, Visit
from mia.core.rbac import PermissionDenied, Resource, get_rbac

router = APIRouter(tags=["schedule"])


class AssignIn(BaseModel):
    person_id: str = Field(max_length=26)
    add: bool = False


class PersonIn(BaseModel):
    person_id: str | None = Field(default=None, max_length=26)


class Assignee(BaseModel):
    id: str
    name: str


class VisitCard(BaseModel):
    id: str
    date: dt.date
    start: str
    end: str
    job: str
    location: str
    address: str
    assignees: list[Assignee]
    status: str


class AssignOut(BaseModel):
    visit: VisitCard
    approval_id: str | None
    reasons: list[str]


class ApprovalCard(BaseModel):
    id: str
    type: str
    summary: str
    evidence: dict[str, object]
    requester_id: str
    created_at: dt.datetime
    expires_at: dt.datetime | None
    status: str
    channel: str


def _person(ctx: AuthContext) -> Person:
    assert ctx.person is not None
    return ctx.person


def _require(session: Session, ctx: AuthContext, action: str, owner_id: str | None) -> None:
    try:
        get_rbac().require(
            ctx.actor, Resource(kind="data", name="core.visit", owner_id=owner_id), action, session=session
        )
    except PermissionDenied as exc:
        raise HTTPException(403, "not allowed") from exc


def _card(session: Session, visit: Visit, tz: str) -> VisitCard:
    zone = ZoneInfo(tz)
    job = session.get(Job, visit.job_id)
    loc = session.get(Location, visit.location_id)
    people = [session.get(Person, pid) for pid in visit.assigned_person_ids]
    return VisitCard(
        id=visit.id,
        date=visit.date,
        start=visit.planned_start.astimezone(zone).isoformat(),
        end=visit.planned_end.astimezone(zone).isoformat(),
        job=job.name if job else "?",
        location=loc.name if loc else "?",
        address=loc.address if loc else "",
        assignees=[Assignee(id=p.id, name=p.name) for p in people if p is not None],
        status=visit.status,
    )


def _branch(session: Session, ctx: AuthContext) -> Branch:
    branch = session.get(Branch, ctx.actor.branch_id)
    assert branch is not None
    return branch


def _visit(session: Session, ctx: AuthContext, visit_id: str) -> Visit:
    visit = session.get(Visit, visit_id)
    if visit is None or visit.branch_id != ctx.actor.branch_id:
        raise HTTPException(404, "visit not found")
    return visit


def _target(session: Session, ctx: AuthContext, person_id: str) -> Person:
    person = session.get(Person, person_id)
    if person is None or person.branch_id != ctx.actor.branch_id:
        raise HTTPException(404, "person not found")
    return person


@router.get("/schedule", response_model=list[VisitCard])
def schedule(
    session: DbSession,
    ctx: PersonAuth,
    start: dt.date | None = None,
    person_id: str | None = None,
    location_id: str | None = None,
) -> list[VisitCard]:
    """Seven days of visits from `start` (today). Staff see their own; the office sees the
    branch, one person or one site."""
    me = _person(ctx)
    branch = _branch(session, ctx)
    start = start or dt.datetime.now(ZoneInfo(branch.timezone)).date()
    if person_id is None and location_id is None:
        allowed = get_rbac().check(ctx.actor, Resource(kind="data", name="core.visit"), "read")
        person_id = None if allowed else me.id
    _require(session, ctx, "read", person_id)
    rows = scheduling.week(session, branch.id, start, person_id=person_id, location_id=location_id)
    return [_card(session, v, branch.timezone) for v in rows]


@router.post("/visits/{visit_id}/assign", response_model=AssignOut)
def assign(session: DbSession, ctx: PersonAuth, visit_id: str, body: AssignIn) -> AssignOut:
    """Assign a person; an override approval comes back when a rule breaks (409 otherwise)."""
    visit = _visit(session, ctx, visit_id)
    _require(session, ctx, "write", None)
    person = _target(session, ctx, body.person_id)
    try:
        out = scheduling.assign(session, ctx.actor, visit, person, add=body.add)
    except scheduling.ScheduleError as exc:
        raise HTTPException(409, str(exc)) from exc
    tz = _branch(session, ctx).timezone
    return AssignOut(visit=_card(session, out.visit, tz), approval_id=out.approval_id, reasons=out.reasons)


@router.post("/visits/{visit_id}/unassign", response_model=VisitCard)
def unassign(session: DbSession, ctx: PersonAuth, visit_id: str, body: AssignIn) -> VisitCard:
    """Take a person off a visit."""
    visit = _visit(session, ctx, visit_id)
    _require(session, ctx, "write", None)
    person = _target(session, ctx, body.person_id)
    try:
        row = scheduling.unassign(session, ctx.actor, visit, person)
    except scheduling.ScheduleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _card(session, row, _branch(session, ctx).timezone)


def _attendance(session: Session, ctx: AuthContext, visit_id: str, body: PersonIn | None, fn: str) -> VisitCard:
    visit = _visit(session, ctx, visit_id)
    me = _person(ctx)
    person = _target(session, ctx, body.person_id) if body and body.person_id else me
    # Own visit: write_own against the assignees; someone else's: write.
    owner = me.id if person.id == me.id and me.id in visit.assigned_person_ids else None
    _require(session, ctx, "write", owner)
    try:
        row = getattr(scheduling, fn)(session, ctx.actor, visit, person, utcnow())
    except scheduling.ScheduleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _card(session, row, _branch(session, ctx).timezone)


@router.post("/visits/{visit_id}/check-in", response_model=VisitCard)
def check_in(session: DbSession, ctx: PersonAuth, visit_id: str, body: PersonIn | None = None) -> VisitCard:
    """The acting person (or, for the office, `person_id`) arrives at the site."""
    return _attendance(session, ctx, visit_id, body, "check_in")


@router.post("/visits/{visit_id}/check-out", response_model=VisitCard)
def check_out(session: DbSession, ctx: PersonAuth, visit_id: str, body: PersonIn | None = None) -> VisitCard:
    """The visit is finished."""
    return _attendance(session, ctx, visit_id, body, "check_out")


@router.get("/approvals", response_model=list[ApprovalCard])
def approvals_inbox(session: DbSession, ctx: PersonAuth) -> list[ApprovalCard]:
    """The approvals the signed-in person may decide, oldest first."""
    return [
        ApprovalCard(
            id=a.id, type=a.type, summary=a.summary, evidence=a.evidence, requester_id=a.requester_id,
            created_at=a.created_at, expires_at=a.expires_at, status=a.status, channel=a.channel,
        )
        for a in scheduling.inbox(session, ctx.actor)
    ]
```

`policy.csv`: `p, staff, *, data:core.visit, write_own, allow` under staff and `p, supervisor, *, data:core.visit, write, allow` under supervisor. `main.py`: `app.include_router(schedule_router)`. `index.html`: a "Week" details panel under the header that, once signed in (required) or an actor is picked (dev), fetches `/schedule` and renders a table (date, time, job, site, assignees, status); re-fetch when the actor changes. Add to `test_chat.py::test_health_and_page` the assertion `"/schedule" in page`.

- [ ] **Step 4: Run the tests, then the full suite**

Run: `uv run pytest node/tests/test_schedule_api.py node/tests/test_architecture.py --no-cov -q`, then the full check line. Expected: PASS (the architecture test accepts the new routes because they take `PersonAuth`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "schedule API: week view, assign and unassign, check-in and check-out, approvals inbox; week panel on the page"
```

---

### Task 5: Docs

**Files:**
- Modify: `docs/layout.md` (core/scheduling, api/schedule), `README.md` (Commands: `mia schedule generate`; a "Scheduling" paragraph with the routes), `docs/plan.md` (item 4 status: core built, board and timesheets open), `docs/capabilities.md` (no change: the chat intents check_in and check_out stay "Built: no"; the services exist), `docs/decisions.md` (D34: scheduling core built on Q19 to Q22; timesheets wait for Q20).

- [ ] **Step 1: Make the edits, run the full check line, commit**

```bash
git add -A
git commit -m "docs: scheduling core (layout, README, plan status, D34)"
```

## Self-review notes

- Spec coverage: section 3 (Task 1), 4 (Tasks 1 to 3), 5 (Task 4), 6 (Task 1), 7 (Task 4), 8 (every task's tests).
- Types: `Assignment`, `VisitCard`, `ApprovalCard`, `ScheduleError` defined once; `slot_of` is the shared name for the visit slot (Task 2 renames the plan's `_slot`).
- Review Focus: each line names its test.
