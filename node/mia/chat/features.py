"""Feature requests (spec 2026-10-22-teach-mia-design, 4b; Q130: kept on the node). A person
asks for something Mia cannot do: `feature.requested` on the hash chain, no table. Requests
with the same key (route_memory.key_of of the wanted text) are one group, each asker counted;
the developer sets a group's status with `feature.status_changed` and every asker is told.
The text is data, never instructions (rule 8)."""

import csv
import io
import re
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from mia.agents.registry import DEFAULT
from mia.chat.blocks import TextBlock
from mia.chat.channels import notify
from mia.chat.route_memory import key_of
from mia.core import events
from mia.core.models import Actor, Event, Message, Person
from mia.i18n import SUPPORTED, t

REQUESTED = "feature.requested"
STATUS_CHANGED = "feature.status_changed"
STATUSES = ("planned", "built", "declined")
MAX_TEXT = 500
_PREFIX = re.compile(r"^\s*request\s*:\s*(\S.*)$", re.IGNORECASE | re.DOTALL)


def prefixed(text: str) -> str | None:
    """What a "request: <what>" message asks for, or None for any other message."""
    found = _PREFIX.match(text)
    return found.group(1).strip() if found else None


def request(
    session: Session,
    person: Person,
    text: str,
    actor: Actor,
    *,
    failed: Message | None = None,
    failed_text: str | None = None,
) -> Event:
    """Emits feature.requested in the caller's transaction (it commits nothing): what the
    person wants, the message that failed if any, their role, branch and language. Raises
    ValueError for an empty text."""
    wanted = text.strip()[:MAX_TEXT]
    if not wanted:
        raise ValueError("empty request")
    after = {
        "text": wanted,
        "key": key_of(wanted),
        "failed_message_id": failed.id if failed else None,
        "failed_text": failed.text if failed else failed_text,
        "person_id": person.id,
        "role": person.roles[0] if person.roles else "",
        "branch_id": person.branch_id,
        "language": person.language,
    }
    return events.emit(session, REQUESTED, ("person", person.id), None, after, actor)


@dataclass
class Group:
    """Every request with one key: the first one's id and text, how many, and the status."""

    id: str
    key: str
    text: str
    count: int = 0
    status: str = "new"
    people: list[str] = field(default_factory=list)
    roles: set[str] = field(default_factory=set)
    languages: set[str] = field(default_factory=set)
    branches: set[str] = field(default_factory=set)
    failed: list[str] = field(default_factory=list)


def groups(session: Session) -> list[Group]:
    """The node's requests grouped by key, most asked first (ties: oldest first), each with
    its latest status. Reads only."""
    rows = session.exec(
        select(Event)
        .where(col(Event.action).in_((REQUESTED, STATUS_CHANGED)))
        .order_by(col(Event.id))
    ).all()
    found: dict[str, Group] = {}
    for ev in rows:
        a = ev.after or {}
        key = str(a.get("key", ""))
        if ev.action == STATUS_CHANGED:
            if key in found:
                found[key].status = str(a["status"])
            continue
        g = found.setdefault(key, Group(ev.id, key, str(a.get("text", ""))))
        g.count += 1
        if (who := a.get("person_id")) and who not in g.people:
            g.people.append(str(who))
        g.roles.add(str(a.get("role", "")))
        g.languages.add(str(a.get("language", "")))
        g.branches.add(str(a.get("branch_id", "")))
        if a.get("failed_text"):
            g.failed.append(str(a["failed_text"]))
    return sorted(found.values(), key=lambda g: -g.count)


def export_csv(session: Session) -> str:
    """The grouped requests as CSV (id, key, text, count, status, roles, languages, branches,
    failed messages), for the developer."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(("id", "key", "text", "count", "status", "roles", "languages", "branches", "failed"))
    for g in groups(session):
        sets = (" ".join(sorted(x - {""})) for x in (g.roles, g.languages, g.branches))
        w.writerow((g.id, g.key, g.text, g.count, g.status, *sets, " | ".join(g.failed)))
    return out.getvalue()


def set_status(session: Session, request_id: str, status: str, actor: Actor) -> Group:
    """Emits feature.status_changed for the group of the request (any request's id in it),
    tells each asker in their language through the normal deliver path, and commits. Raises
    LookupError for an unknown request and ValueError for a status not in STATUSES."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    ev = session.get(Event, request_id)
    if ev is None or ev.action != REQUESTED:
        raise LookupError(f"no feature request {request_id}")
    key = str((ev.after or {}).get("key", ""))
    group = next(g for g in groups(session) if g.key == key)
    after = {"key": key, "status": status, "request_id": request_id}
    events.emit(session, STATUS_CHANGED, ("feature", group.id), None, after, actor)
    for person_id in group.people:
        person = session.get(Person, person_id)
        if person is None or person.status != "active":
            continue
        lang = person.language if person.language in SUPPORTED else "en"
        said = t(f"feature.status.{status}", lang, what=group.text)
        notify(session, person, [TextBlock(text=said)], actor, DEFAULT)
    session.commit()
    group.status = status
    return group
