"""People: adding and deactivating persons. Writes go through store and emit events."""

from sqlmodel import Session

from mia.core import store
from mia.core.models import Actor, Branch, Person

HUMAN_ROLES = ("owner", "admin", "supervisor", "staff", "accountant", "viewer")
LANGUAGES = ("fi", "en")


def add_person(
    session: Session,
    actor: Actor,
    *,
    branch_id: str,
    name: str,
    roles: list[str],
    language: str = "fi",
    skills: list[str] | None = None,
) -> Person:
    """Create an active person and emit `person.created`.

    Raises ValueError for an empty name, no roles, an unknown role or language, or an unknown
    branch, before anything is written.
    """
    name = " ".join(name.split())
    if not name:
        raise ValueError("name is required")
    if not roles or any(r not in HUMAN_ROLES for r in roles):
        raise ValueError(f"roles must be one or more of {', '.join(HUMAN_ROLES)}")
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
    if session.get(Branch, branch_id) is None:
        raise ValueError(f"unknown branch {branch_id!r}")
    person = Person(
        branch_id=branch_id, name=name, roles=list(roles), language=language, skills=skills or []
    )
    return store.insert(session, person, actor)


def deactivate(session: Session, actor: Actor, person: Person) -> Person:
    """Mark a person inactive and emit `person.deactivated`."""
    return store.update(session, person, {"status": "inactive"}, actor, action="person.deactivated")
