"""The `mia` command: migrate, seed, serve, chat, decide."""

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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for `uv run mia`."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
