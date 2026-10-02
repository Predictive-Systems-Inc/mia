"""Adding people: a core write service with an event, validated input."""

import pytest
from sqlmodel import Session, select

from mia.core import people
from mia.core.models import Actor, Branch, Event, Person


def test_add_person_creates_row_and_event(session: Session, branch: Branch) -> None:
    actor = Actor.system(branch.id)
    person = people.add_person(
        session, actor, branch_id=branch.id, name="Aada Koski", roles=["staff"], language="fi"
    )
    session.commit()

    assert session.get(Person, person.id) is not None
    event = session.exec(select(Event).where(Event.entity_id == person.id)).one()
    assert (event.action, event.actor_id) == ("person.created", "system")


@pytest.mark.parametrize(
    ("name", "roles", "language"),
    [
        (" ", ["staff"], "fi"),
        ("Aada", ["janitor"], "fi"),
        ("Aada", [], "fi"),
        ("Aada", ["staff"], "xx"),
    ],
)
def test_add_person_rejects_bad_input(
    session: Session, branch: Branch, name: str, roles: list[str], language: str
) -> None:
    with pytest.raises(ValueError):
        people.add_person(
            session,
            Actor.system(branch.id),
            branch_id=branch.id,
            name=name,
            roles=roles,
            language=language,
        )


def test_add_person_rejects_unknown_branch(session: Session, branch: Branch) -> None:
    with pytest.raises(ValueError):
        people.add_person(
            session, Actor.system(branch.id), branch_id="nope", name="Aada", roles=["staff"]
        )


def test_deactivate_sets_status(session: Session, branch: Branch) -> None:
    person = people.add_person(
        session, Actor.system(branch.id), branch_id=branch.id, name="Aada", roles=["staff"]
    )
    people.deactivate(session, Actor.system(branch.id), person)
    assert person.status == "inactive"
