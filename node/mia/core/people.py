"""People: adding and deactivating persons. Writes go through store and emit events."""

from sqlmodel import Session

from mia.core import assignments, store
from mia.core.models import Actor, Branch, Person
from mia.i18n import SUPPORTED as LANGUAGES

HUMAN_ROLES = ("owner", "admin", "supervisor", "staff", "clerk", "accountant", "viewer")


def add_person(
    session: Session,
    actor: Actor,
    *,
    branch_id: str,
    name: str,
    roles: list[str],
    language: str = "fi",
    skills: list[str] | None = None,
    language_known: bool = True,
) -> Person:
    """Create an active person and emit `person.created`; with language_known (the default)
    also `person.language_chosen`, so the person is never asked for their language.

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
    store.insert(session, person, actor)
    return set_language(session, actor, person, language) if language_known else person


def set_language(session: Session, actor: Actor, person: Person, language: str) -> Person:
    """Set the person's reply language and emit `person.language_chosen` (also when it is the
    language they already had: the event says the choice is made). Raises ValueError for a
    language outside LANGUAGES, before anything is written."""
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
    return store.update(
        session, person, {"language": language}, actor, action="person.language_chosen"
    )


def set_roles(session: Session, actor: Actor, person: Person, roles: list[str]) -> Person:
    """Replace the person's roles and emit `person.roles_changed`; losing the supervisor role
    first ends their open kiosk assignments (assignments.end_all, D50). Raises ValueError for
    no roles or an unknown one, before anything is written."""
    if not roles or any(r not in HUMAN_ROLES for r in roles):
        raise ValueError(f"roles must be one or more of {', '.join(HUMAN_ROLES)}")
    if assignments.ASSIGNABLE in person.roles and assignments.ASSIGNABLE not in roles:
        assignments.end_all(session, actor, person)
    return store.update(
        session, person, {"roles": list(roles)}, actor, action="person.roles_changed"
    )


def deactivate(session: Session, actor: Actor, person: Person) -> Person:
    """Mark a person inactive; end their open kiosk assignments (D50); revoke their devices,
    sessions and channel identities; emit `person.deactivated`."""
    from mia.channels.linking import revoke_all  # channels depend on core, not the reverse
    from mia.core.auth import revoke_everything
    from mia.core.db import utcnow

    assignments.end_all(session, actor, person)
    revoke_everything(session, actor, person, utcnow())
    revoke_all(session, actor, person)
    return store.update(session, person, {"status": "inactive"}, actor, action="person.deactivated")
