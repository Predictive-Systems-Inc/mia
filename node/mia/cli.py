"""The `mia` command: migrate, seed, serve, chat, decide, inbox, tick, geocode, person,
invite."""

import argparse
import asyncio

from alembic.config import Config
from sqlmodel import Session, col, select

from mia.core.models import Person
from mia.settings import NODE_DIR, get_settings


def _alembic_config() -> Config:

    cfg = Config(str(NODE_DIR / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(NODE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().db_url)
    return cfg


def migrate(_args: argparse.Namespace) -> int:
    from alembic import command

    get_settings().MIA_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(), "head")
    print(f"database ready: {get_settings().MIA_DB_PATH}")
    return 0


def seed(_args: argparse.Namespace) -> int:
    from mia.core.db import session_scope
    from mia.templates.cleaning.seed import is_seeded
    from mia.templates.cleaning.seed import seed as run_seed

    with session_scope() as session:
        if is_seeded(session):
            print("already seeded; delete the database file to start over")
            return 0
        branch = run_seed(session)
    print(f"seeded demo branch {branch.name} ({branch.id})")
    return 0


def serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("mia.api.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def _find_person(session: Session, who: str | None) -> Person:
    people = session.exec(select(Person).order_by(col(Person.id))).all()
    if not people:
        raise SystemExit("no people in the database; run `uv run mia seed` first")
    if who is None:
        staff = [p for p in people if "staff" in p.roles]
        return staff[0] if staff else people[0]
    low = who.lower()
    for p in people:
        if p.id == who or p.name.lower() == low or p.name.split()[0].lower() == low:
            return p
    raise SystemExit(f"no person matches {who!r}; try one of: " + ", ".join(p.name for p in people))


def chat(args: argparse.Namespace) -> int:
    from mia.agents.dispatcher.agent import get_agent
    from mia.chat.service import run_turn
    from mia.core.db import session_scope

    async def one_turn() -> None:
        with session_scope() as session:
            person = _find_person(session, args.as_person)
            reply = await run_turn(session, get_agent(), person, args.text, args.thread)
            print(f"[{person.name} -> Mia]  {args.text}")
            print(reply.text())
            print(f"\n(thread {reply.thread_id}; continue with --thread {reply.thread_id})")

    asyncio.run(one_turn())
    return 0


def decide(args: argparse.Namespace) -> int:
    from mia.core import approvals
    from mia.core.db import session_scope
    from mia.core.models import Actor

    with session_scope() as session:
        person = _find_person(session, args.as_person)
        try:
            row = approvals.decide(
                session, args.approval_id, Actor.person(person), args.outcome, args.reason
            )
        except approvals.ApprovalError as exc:
            print(f"refused: {exc}")
            return 1
    print(f"approval {row.id}: {row.status} by {person.name}")
    return 0


def inbox(args: argparse.Namespace) -> int:
    from mia.chat.blocks import ChatReply
    from mia.chat.channels import NOTIFICATION
    from mia.core.db import session_scope
    from mia.core.models import Message, Thread

    with session_scope() as session:
        person = _find_person(session, args.as_person)
        rows = session.exec(
            select(Message)
            .join(Thread, col(Thread.id) == col(Message.thread_id))
            .where(Thread.person_id == person.id)
            .where(Message.role == NOTIFICATION)
            .order_by(col(Message.id))
        ).all()
        print(f"Messages from Mia to {person.name}: {len(rows)}")
        for row in rows:
            reply = ChatReply.model_validate(
                {
                    "thread_id": row.thread_id,
                    "message_id": row.id,
                    "agent_id": "dispatcher",
                    "blocks": row.blocks,
                }
            )
            print(f"\n[{row.created_at:%H:%M}] {reply.text()}")
    return 0


def tick(_args: argparse.Namespace) -> int:
    from mia.api.main import run_due_work
    from mia.channels.whatsapp import register_if_configured

    register_if_configured(get_settings())
    advanced, sent = asyncio.run(run_due_work())
    print(f"advanced {advanced} cover request(s), sent {sent} channel message(s)")
    return 0


def geocode(_args: argparse.Namespace) -> int:
    from mia.core import geocoding
    from mia.core.db import session_scope
    from mia.core.models import Actor, Branch

    async def run() -> int:
        missing_total = 0
        with session_scope() as session:
            for branch in session.exec(select(Branch)).all():
                updated, missing = await geocoding.fill_missing(session, Actor.system(branch.id))
                print(f"{branch.name}: geocoded {updated}")
                for address in missing:
                    print(f"  not found: {address}")
                missing_total += len(missing)
        return 1 if missing_total else 0

    try:
        return asyncio.run(run())
    except geocoding.GeocodingError as exc:
        print(f"geocoding failed: {exc}")
        return 1


def _only_branch_id(session: Session, branch_id: str | None) -> str:
    from mia.core.models import Branch

    if branch_id:
        return branch_id
    branches = session.exec(select(Branch)).all()
    if len(branches) != 1:
        raise SystemExit("pass --branch: the database has " + str(len(branches)) + " branches")
    return branches[0].id


def person_add(args: argparse.Namespace) -> int:
    from mia.core import people
    from mia.core.db import session_scope
    from mia.core.models import Actor

    with session_scope() as session:
        branch_id = _only_branch_id(session, args.branch)
        try:
            person = people.add_person(
                session,
                Actor.system(branch_id),
                branch_id=branch_id,
                name=args.name,
                roles=args.roles,
                language=args.lang,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"added {person.name} ({person.id})")
    return 0


def _match_one(session: Session, who: str) -> Person:
    """Exact id or full name, else a unique name prefix. Exits listing matches when ambiguous."""
    people = session.exec(select(Person).order_by(col(Person.name))).all()
    low = who.lower().strip()
    exact = [p for p in people if p.id == who or p.name.lower() == low]
    found = exact or [
        p for p in people if any(part.lower().startswith(low) for part in [p.name, *p.name.split()])
    ]
    if len(found) == 1:
        return found[0]
    if not found:
        raise SystemExit(f"no person matches {who!r}")
    raise SystemExit(f"{who!r} matches several people: " + ", ".join(p.name for p in found))


def invite(args: argparse.Namespace) -> int:
    from mia.channels import linking
    from mia.core.db import session_scope
    from mia.core.models import Actor

    with session_scope() as session:
        person = _match_one(session, args.name)
        actor = (
            Actor.person(_match_one(session, args.as_person))
            if args.as_person
            else Actor.system(person.branch_id)
        )
        try:
            code = linking.create_code(session, actor, person, "invite")
        except linking.LinkingError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"invite for {person.name}, valid 7 days, single use")
        print(f"  link: {linking.invite_link(code)}")
        print(f"  or send this text to Mia on WhatsApp: LINK {code}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mia", description="Mia Node command line")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="create or upgrade the SQLite database").set_defaults(
        func=migrate
    )
    sub.add_parser("seed", help="load demo data").set_defaults(func=seed)
    p = sub.add_parser("serve", help="start the API and chat page")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=serve)
    p = sub.add_parser("chat", help="send one chat message")
    p.add_argument("text")
    p.add_argument(
        "--as", dest="as_person", help="person name, first name or id (default: first cleaner)"
    )
    p.add_argument("--thread", help="continue a thread")
    p.set_defaults(func=chat)
    p = sub.add_parser("decide", help="approve or reject an approval (stand-in for the inbox)")
    p.add_argument("approval_id")
    p.add_argument("outcome", choices=["approved", "rejected"])
    p.add_argument("--as", dest="as_person", required=True)
    p.add_argument("--reason")
    p.set_defaults(func=decide)
    p = sub.add_parser("inbox", help="show messages Mia sent to a person")
    p.add_argument("--as", dest="as_person", required=True)
    p.set_defaults(func=inbox)
    sub.add_parser("tick", help="advance due cover confirmations once").set_defaults(func=tick)
    sub.add_parser(
        "geocode", help="geocode home bases and sites that have no coordinates"
    ).set_defaults(func=geocode)
    p = sub.add_parser("invite", help="create a WhatsApp invite link for a person")
    p.add_argument("name")
    p.add_argument("--as", dest="as_person", help="the inviting supervisor (told about problems)")
    p.set_defaults(func=invite)
    person = sub.add_parser("person", help="manage people").add_subparsers(
        dest="person_command", required=True
    )
    p = person.add_parser("add", help="add a person")
    p.add_argument("name")
    p.add_argument("--role", dest="roles", action="append", required=True)
    p.add_argument("--lang", default="fi", choices=["fi", "en"])
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=person_add)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for `uv run mia`."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
