"""Kiosk assignments (data standard 1.10, ADR 024, D50): the extra branches a supervisor works
at beside their home branch. branches_of is the one branch scope of a person (home plus
active assignments); rbac's callers, approvals and the alerts use it. Writes go through store
and emit events."""

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, or_, select

from mia.core import db, rbac, store
from mia.core.models import Actor, Branch, BranchAssignment, Person

ASSIGNMENTS = rbac.Resource(kind="data", name=BranchAssignment.__tablename__)
ASSIGNABLE = "supervisor"  # clerks keep one kiosk; owner and admin already read every one


class AssignmentError(ValueError):
    """A refused assignment; the code is not_supervisor, other_organisation, not_a_kiosk,
    home_branch, already_assigned, not_assigned or dates."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def local_day(branch: Branch) -> dt.date:
    """Today on the branch's clock (db.utcnow looked up per call, so a test's pin holds)."""
    return db.utcnow().astimezone(ZoneInfo(branch.timezone)).date()


def _active(day: dt.date) -> tuple[Any, Any]:
    """The where clauses of an assignment active on day."""
    return (
        col(BranchAssignment.from_date) <= day,
        or_(col(BranchAssignment.to_date).is_(None), col(BranchAssignment.to_date) > day),
    )


def branches_of(session: Session, person: Person, day: dt.date) -> set[str]:
    """The person's home branch plus every branch of an assignment active on day (from_date
    at or before day, to_date after it or open). Assignments count only while the person is
    an active supervisor. Reads only."""
    home = {person.branch_id}
    if ASSIGNABLE not in person.roles or person.status != "active":
        return home
    stmt = select(BranchAssignment.branch_id).where(BranchAssignment.person_id == person.id)
    return home | set(session.exec(stmt.where(*_active(day))))


def actor_branches(session: Session, actor: Actor, day: dt.date | None = None) -> set[str]:
    """actor.branch_id plus, for the person behind the actor, branches_of on day (default:
    today at actor.branch_id). An actor with no person row keeps its one branch."""
    person = session.get(Person, actor.person_id) if actor.person_id else None
    if person is None:
        return {actor.branch_id}
    if day is None:
        branch = session.get(Branch, actor.branch_id)
        day = local_day(branch) if branch is not None else db.utcnow().date()
    return {actor.branch_id} | branches_of(session, person, day)


def assigned_to(session: Session, branch_id: str, day: dt.date) -> list[Person]:
    """The active supervisors assigned to the branch on day (never its own people), by id."""
    ids = select(BranchAssignment.person_id).where(BranchAssignment.branch_id == branch_id)
    rows = session.exec(
        select(Person).where(col(Person.id).in_(ids.where(*_active(day)))).order_by(col(Person.id))
    )
    return [p for p in rows if p.status == "active" and ASSIGNABLE in p.roles]


def open_assignment(session: Session, person_id: str, branch_id: str) -> BranchAssignment | None:
    """The person's open assignment (no to_date) to the branch, if any."""
    return session.exec(
        select(BranchAssignment)
        .where(BranchAssignment.person_id == person_id)
        .where(BranchAssignment.branch_id == branch_id)
        .where(col(BranchAssignment.to_date).is_(None))
    ).first()


def _same_organisation(session: Session, person: Person, branch: Branch) -> bool:
    home = session.get(Branch, person.branch_id)
    return home is not None and home.organisation_id == branch.organisation_id


def assign(
    session: Session,
    actor: Actor,
    person: Person,
    branch: Branch,
    from_date: dt.date,
    *,
    tool_call_id: str | None = None,
) -> BranchAssignment:
    """Assign the supervisor to the kiosk from from_date (event assignment.created). Only an
    owner or admin (write_all on branch_assignments; PermissionDenied). Raises
    AssignmentError before any write: not_supervisor (an inactive person or one without the
    supervisor role), other_organisation, not_a_kiosk (a branch that sells nothing, such as
    a commissary), home_branch, already_assigned (an open one)."""
    from mia.core.sales import is_kiosk  # sales imports this module

    rbac.get_rbac().require(actor, ASSIGNMENTS, "write_all", session=session)
    if ASSIGNABLE not in person.roles or person.status != "active":
        raise AssignmentError("not_supervisor")
    if not _same_organisation(session, person, branch):
        raise AssignmentError("other_organisation")
    if not is_kiosk(session, branch.id):
        raise AssignmentError("not_a_kiosk")
    if branch.id == person.branch_id:
        raise AssignmentError("home_branch")
    if open_assignment(session, person.id, branch.id) is not None:
        raise AssignmentError("already_assigned")
    row = BranchAssignment(branch_id=branch.id, person_id=person.id, from_date=from_date)
    return store.insert(session, row, actor, action="assignment.created", tool_call_id=tool_call_id)


def unassign(
    session: Session,
    actor: Actor,
    person: Person,
    branch: Branch,
    to_date: dt.date,
    *,
    tool_call_id: str | None = None,
) -> BranchAssignment:
    """End the person's open assignment to the branch: it holds until the day before to_date
    (event assignment.ended). Only an owner or admin (PermissionDenied). Raises
    AssignmentError not_assigned without an open one, dates for a to_date before its
    from_date."""
    rbac.get_rbac().require(actor, ASSIGNMENTS, "write_all", session=session)
    row = open_assignment(session, person.id, branch.id)
    if row is None:
        raise AssignmentError("not_assigned")
    if to_date < row.from_date:
        raise AssignmentError("dates")
    return store.update(
        session,
        row,
        {"to_date": to_date},
        actor,
        action="assignment.ended",
        tool_call_id=tool_call_id,
    )


def end_all(session: Session, actor: Actor, person: Person) -> list[BranchAssignment]:
    """End every open assignment of the person today on their home branch's clock (one not
    begun yet ends on its from_date, so it never holds), each through unassign with its
    event. For deactivation and a lost supervisor role: an old assignment never comes back
    on reactivation. PermissionDenied for an actor without write_all."""
    home = session.get(Branch, person.branch_id)
    today = local_day(home) if home is not None else db.utcnow().date()
    rows = session.exec(
        select(BranchAssignment)
        .where(BranchAssignment.person_id == person.id)
        .where(col(BranchAssignment.to_date).is_(None))
        .order_by(col(BranchAssignment.id))
    ).all()
    ended = []
    for row in rows:
        branch = session.get(Branch, row.branch_id)
        assert branch is not None  # a foreign key
        ended.append(unassign(session, actor, person, branch, max(today, row.from_date)))
    return ended
