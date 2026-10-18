"""The `mia` command: migrate, seed, serve, chat, decide, inbox, tick, geocode, person,
invite, channels, backup, verify-db, keys, auth, skills, agent."""

import argparse
import asyncio
import datetime as dt
import os
from pathlib import Path

from alembic.config import Config
from sqlmodel import Session, col, select

from mia.core.models import Person
from mia.i18n import SUPPORTED
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
    from importlib import import_module

    from mia.core import orgconfig
    from mia.core.db import session_scope

    template_seed = import_module(f"mia.templates.{orgconfig.load().template}.seed")

    with session_scope() as session:
        if template_seed.is_seeded(session):
            print("already seeded; delete the database file to start over")
            return 0
        branch = template_seed.seed(session)
    print(f"seeded demo branch {branch.name} ({branch.id})")
    return 0


def import_data(args: argparse.Namespace) -> int:
    from pathlib import Path

    from mia.core import events
    from mia.core.db import session_scope
    from mia.core.models import Actor, Branch
    from mia.templates.cleaning import importer
    from mia.templates.cleaning.seed import is_seeded

    path = Path(args.file)
    try:
        data = importer.parse(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"{path}: {exc}") from exc
    with session_scope() as session:
        try:
            if not is_seeded(session):
                branch = importer.bootstrap(session, data)
            else:
                found = session.get(Branch, _only_branch_id(session, args.branch))
                if found is None:
                    raise SystemExit(f"no branch {args.branch}")
                branch = found
            counts = importer.load(session, data, branch)
        except ValueError as exc:
            session.rollback()
            raise SystemExit(f"{path}: {exc}") from exc
        events.emit(
            session,
            "data.imported",
            ("branch", branch.id),
            None,
            {**counts.model_dump(), "file": path.name},
            Actor.system(branch.id),
        )
    print(
        f"imported into {branch.name}: {counts.people} person(s), {counts.clients} client(s), "
        f"{counts.locations} location(s), {counts.jobs} job(s)"
    )
    return 0


def serve(args: argparse.Namespace) -> int:
    import uvicorn

    from mia.api.deps import check_mode

    check_mode(get_settings())
    # The node never downloads models (ADR 013); training processes do not go through serve.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
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
    from mia.agents.shift_supervisor.agent import get_agent
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
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor

    with session_scope() as session:
        person = _find_person(session, args.as_person)
        try:
            # Shell access is full access: the CLI counts as a fresh step-up (ADR 011).
            row = approvals.decide(
                session,
                args.approval_id,
                Actor.person(person),
                args.outcome,
                args.reason,
                stepped_up_at=utcnow(),
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
                    "agent_id": row.agent_id or "",
                    "blocks": row.blocks,
                }
            )
            print(f"\n[{row.created_at:%H:%M}] {reply.text()}")
    return 0


def tick(_args: argparse.Namespace) -> int:
    from mia.api.main import run_due_work

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
                language_known=not args.ask_language,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"added {person.name} ({person.id})")
    return 0


def agent_scaffold(args: argparse.Namespace) -> int:
    from mia.agents import scaffold

    try:
        written = scaffold.run(
            NODE_DIR.parent,
            args.agent_id,
            label_en=args.label_en,
            label_fi=args.label_fi,
            roles=args.roles,
            description=args.description,
            force=args.force,
        )
    except (ValueError, FileExistsError) as exc:
        raise SystemExit(str(exc)) from exc
    for path in written:
        print(path.relative_to(NODE_DIR.parent))
    return 0


def learned(args: argparse.Namespace) -> int:
    from mia.chat import route_memory
    from mia.core.db import session_scope, utcnow
    from mia.i18n import t

    with session_scope() as session:
        branch_id = _only_branch_id(session, args.branch)
        now = utcnow()
        keys = route_memory.recall(session, branch_id, now)
        counted = route_memory.counts(session, branch_id, now)
        for key, agent in sorted(keys.items()):
            print(t("cli.learned.row", "en", agent=agent, route=key, count=counted[(key, agent)]))
        if not keys:
            print(t("cli.learned.none", "en"))
    return 0


def forget(args: argparse.Namespace) -> int:
    from mia.chat import route_memory
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor
    from mia.i18n import t

    with session_scope() as session:
        branch_id = _only_branch_id(session, args.branch)
        key = route_memory.forget(session, branch_id, args.key, Actor.system(branch_id), utcnow())
    print(t("cli.forgotten", "en", route=key) if key else t("cli.learned.none", "en"))
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
        if get_settings().MIA_WA_NUMBER:
            print(f"  link: {linking.invite_link(code)}")
        else:
            print("  (no link: set MIA_WA_NUMBER to Mia's WhatsApp number for a wa.me link)")
        print(f"  or send this text to Mia on WhatsApp: LINK {code}")
    return 0


def channels_sim(args: argparse.Namespace) -> int:
    """Send one message as if it came from a phone on the simulated channel; print Mia's replies."""
    from mia.channels import outbox, registry
    from mia.channels.base import InboundMessage
    from mia.channels.inbound import handle_inbound
    from mia.channels.simulator import SimAdapter
    from mia.core import store
    from mia.core.db import session_scope, utcnow
    from mia.core.ids import new_id
    from mia.core.models import Actor, ChannelInbound, Principal

    sim = registry.get("sim")
    if not isinstance(sim, SimAdapter) or sim not in registry.enabled():
        raise SystemExit("the sim channel is off: set channels.sim.enabled in the org settings")
    msg = InboundMessage(
        channel="sim",
        address=args.sender,
        channel_message_id=new_id(),
        text=args.text,
        received_at=utcnow(),
    )
    actor = Actor(principal=Principal(type="system", id="channel:sim"), branch_id="")
    with session_scope() as session:
        row = ChannelInbound(
            channel="sim",
            channel_message_id=msg.channel_message_id,
            address=msg.address,
            body=msg.model_dump(mode="json"),
        )
        inbound_id = store.insert(session, row, actor, action="channel.received").id

    def show(title: str) -> None:
        mine = [p for p in sim.sent if p.address == args.sender]
        if mine:
            print(title)
        for payload in mine:
            body = payload.body
            print(f"[Mia -> {payload.address}] ({body.get('kind')})")
            print(body.get("text") or body.get("name") or "")
            for option in body.get("buttons") or body.get("rows") or []:
                print(f"  [{option}]")
        sim.sent.clear()

    async def waiting() -> None:
        await outbox.send_due(utcnow(), on_demand_for=args.sender)

    async def reply() -> None:
        await handle_inbound(inbound_id)
        await outbox.send_due(utcnow(), on_demand_for=args.sender)

    asyncio.run(waiting())
    show("-- waiting for this number --")
    asyncio.run(reply())
    show("-- reply --")
    return 0


def backup(args: argparse.Namespace) -> int:
    """Write a consistent copy of the live database to a new file (SQLite online backup, safe
    while the node runs). Never overwrites an existing file."""
    import sqlite3
    from contextlib import closing
    from pathlib import Path

    src_path, dest = get_settings().MIA_DB_PATH, Path(args.dest)
    if not src_path.is_file():
        raise SystemExit(f"no database at {src_path}")
    if dest.exists():
        raise SystemExit(f"{dest} exists; choose a new file name")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(src_path)) as src, closing(sqlite3.connect(dest)) as out:
        src.backup(out)
    print(f"backup written: {dest}")
    return 0


def verify_db(args: argparse.Namespace) -> int:
    """Check a database copy (a Litestream restore or a `mia backup` file) without changing it:
    SQLite integrity, the events hash chain, the migration revision and row counts per table.
    Returns 0 only when the file opens, integrity is ok and the chain verifies."""
    from pathlib import Path

    from sqlalchemy import create_engine, inspect
    from sqlalchemy.exc import DatabaseError

    from mia.core.events import verify_chain

    path = Path(args.path)
    if not path.is_file():
        print(f"FAILED: no database at {path}")
        return 1
    engine = create_engine(f"sqlite:///file:{path.resolve()}?mode=ro&uri=true")
    try:
        with engine.connect() as conn:
            integrity = conn.exec_driver_sql("PRAGMA integrity_check").scalar()
            tables = sorted(inspect(conn).get_table_names())
            counts = {
                t: conn.exec_driver_sql(f'SELECT count(*) FROM "{t}"').scalar() for t in tables
            }
            revision = (
                conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                if "alembic_version" in tables
                else None
            )
        with Session(engine) as session:
            chain = "events" in tables and verify_chain(session)
    except DatabaseError as exc:
        print(f"FAILED: cannot read {path}: {exc.orig}")
        return 1
    finally:
        engine.dispose()
    print(f"database: {path}")
    print(f"integrity: {integrity}")
    print(f"migration: {revision or 'none'}")
    print(f"events chain: {'intact' if chain else 'BROKEN or missing'}")
    for table, n in counts.items():
        print(f"  {table}: {n}")
    ok = integrity == "ok" and chain
    print("OK: restore verified" if ok else "FAILED: restore is not usable")
    return 0 if ok else 1


def _enrol_link(code: str) -> str:
    return f"{get_settings().MIA_PUBLIC_URL.rstrip('/')}/auth/enrol/{code}"


def billing_export(args: argparse.Namespace) -> int:
    import sys

    from mia.core import billing, events
    from mia.core.db import session_scope
    from mia.core.models import Actor

    try:
        year, month = (int(x) for x in args.month.split("-"))
        dt.date(year, month, 1)
    except ValueError as exc:
        raise SystemExit("--month must be YYYY-MM") from exc
    with session_scope() as session:
        branch_id = _only_branch_id(session, args.branch)
        rows = billing.summary(session, branch_id, year, month)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="") as f:
                billing.write_csv(rows, f)
        else:
            billing.write_csv(rows, sys.stdout)
        events.emit(
            session,
            "billing.exported",
            ("billing", f"{year}-{month:02d}"),
            None,
            {"month": f"{year}-{month:02d}", "rows": len(rows)},
            Actor.system(branch_id),
        )
    print(
        f"exported {len(rows)} row(s) for {year}-{month:02d}"
        + (f" to {args.out}" if args.out else "")
    )
    return 0


def payroll_export(args: argparse.Namespace) -> int:
    import sys

    from mia.agents.shift_supervisor import timesheets
    from mia.core import events
    from mia.core.db import session_scope
    from mia.core.models import Actor

    try:
        start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    except ValueError as exc:
        raise SystemExit("--from and --to must be YYYY-MM-DD") from exc
    if end < start:
        raise SystemExit("--to must not be before --from")
    with session_scope() as session:
        branch_id = _only_branch_id(session, args.branch)
        rows = timesheets.payroll_rows(session, branch_id, start, end)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="") as f:
                timesheets.write_csv(rows, f)
        else:
            timesheets.write_csv(rows, sys.stdout)
        events.emit(
            session,
            "payroll.exported",
            ("payroll", f"{start.isoformat()}_{end.isoformat()}"),
            None,
            {"from": start.isoformat(), "to": end.isoformat(), "rows": len(rows)},
            Actor.system(branch_id),
        )
    print(
        f"exported {len(rows)} row(s) for {start.isoformat()} to {end.isoformat()}"
        + (f" to {args.out}" if args.out else "")
    )
    return 0


def schedule_generate(args: argparse.Namespace) -> int:
    from mia.core import scheduling
    from mia.core.db import session_scope
    from mia.core.models import Actor, Branch

    with session_scope() as session:
        branch = session.get(Branch, _only_branch_id(session, args.branch))
        assert branch is not None
        new = scheduling.generate(session, Actor.system(branch.id), branch, days=args.days)
    print(f"generated {len(new)} visit(s) for the next {args.days} days")
    return 0


def auth_bootstrap(args: argparse.Namespace) -> int:
    from mia.core import auth, people
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor, Person

    with session_scope() as session:
        branch_id = _only_branch_id(session, args.branch)
        rows = session.exec(select(Person).where(Person.branch_id == branch_id)).all()
        owners = [p for p in rows if "owner" in p.roles and p.status == "active"]
        able = [p for p in owners if auth.credential(session, p.id, "password") is not None]
        if able:
            print(f"an owner can already sign in ({able[0].name}); use `mia auth reset` instead")
            return 1
        actor = Actor.system(branch_id)
        if owners:
            person = owners[0]  # an owner without a login yet (a seeded or imported branch)
        else:
            person = people.add_person(
                session,
                actor,
                branch_id=branch_id,
                name=args.name or args.email.split("@")[0],
                roles=["owner"],
                language=args.lang,
            )
        code = auth.start_enrolment(session, actor, person, utcnow(), via="cli")
    print(
        f"owner {person.name}: set the password (email {args.email}) and TOTP through this "
        f"link (24 hours, single use):\n  {_enrol_link(code)}"
    )
    return 0


def auth_reset(args: argparse.Namespace) -> int:
    from mia.core import auth
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor

    with session_scope() as session:
        person = _match_one(session, args.name)
        actor = Actor.system(person.branch_id)
        code = auth.start_enrolment(session, actor, person, utcnow(), reason="reset", via="cli")
    print(
        f"sessions of {person.name} ended. Enrolment link (24 hours, single use):\n"
        f"  {_enrol_link(code)}"
    )
    return 0


def auth_link(args: argparse.Namespace) -> int:
    from mia.core import auth
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor

    with session_scope() as session:
        person = _match_one(session, args.name)
        url = auth.send_login_link(session, Actor.system(person.branch_id), person, utcnow())
    if url is None:
        print(f"{person.name} has no active channel identity; send an invite first")
        return 1
    print(f"login link sent to {person.name} (10 minutes, single use): {url}")
    return 0


def auth_client_add(args: argparse.Namespace) -> int:
    from mia.core import auth
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor

    with session_scope() as session:
        branch_id = _only_branch_id(session, args.branch)
        try:
            row, secret = auth.create_client(
                session, Actor.system(branch_id), args.name, args.roles, utcnow()
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    print(f"client {row.name} registered. Shown once:\n  client_id: {row.client_id}")
    print(f"  client_secret: {secret}")
    return 0


def auth_client_revoke(args: argparse.Namespace) -> int:
    from mia.core import auth
    from mia.core.db import session_scope, utcnow
    from mia.core.models import Actor, AuthClient

    with session_scope() as session:
        row = session.exec(select(AuthClient).where(AuthClient.client_id == args.client_id)).first()
        if row is None:
            raise SystemExit(f"no client {args.client_id}")
        auth.revoke_client(session, Actor.system(row.branch_id), row, utcnow())
    print(f"client {args.client_id} revoked")
    return 0


def auth_unlock(args: argparse.Namespace) -> int:
    from mia.core import auth
    from mia.core.db import session_scope, utcnow

    with session_scope() as session:
        auth.unlock_login(session, args.login, utcnow())
    print(f"{auth.normalise_login(args.login)} unlocked")
    return 0


def keys_init(args: argparse.Namespace) -> int:
    from mia.core import keys

    path = args.path or get_settings().MIA_MASTER_KEY_FILE
    if path is None:
        raise SystemExit("give a path or set MIA_MASTER_KEY_FILE")
    try:
        keys.generate(Path(path))
    except keys.MasterKeyError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"master key written to {path} (mode 400). Back it up outside the data folder.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mia", description="Mia Node command line")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="create or upgrade the SQLite database").set_defaults(
        func=migrate
    )
    sub.add_parser("seed", help="load demo data").set_defaults(func=seed)
    p = sub.add_parser("import", help="people, clients, sites and jobs from a YAML file")
    p.add_argument("file")
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=import_data)
    p = sub.add_parser("backup", help="write a consistent copy of the database to a new file")
    p.add_argument("dest")
    p.set_defaults(func=backup)
    p = sub.add_parser(
        "verify-db", help="check a restored copy: integrity, events chain, row counts"
    )
    p.add_argument("path")
    p.set_defaults(func=verify_db)
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
    channels = sub.add_parser("channels", help="messaging channels").add_subparsers(
        dest="channels_command", required=True
    )
    p = channels.add_parser("sim", help="send a message on the simulated channel")
    p.add_argument("text")
    p.add_argument("--from", dest="sender", required=True, help="the phone number it comes from")
    p.set_defaults(func=channels_sim)
    person = sub.add_parser("person", help="manage people").add_subparsers(
        dest="person_command", required=True
    )
    p = person.add_parser("add", help="add a person")
    p.add_argument("name")
    p.add_argument("--role", dest="roles", action="append", required=True)
    p.add_argument("--lang", default="fi", choices=SUPPORTED)
    p.add_argument(
        "--ask-language",
        action="store_true",
        help="leave the language unchosen: Mia asks it in the first chat (channel sign-up)",
    )
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=person_add)
    agent = sub.add_parser("agent", help="agent packages").add_subparsers(
        dest="agent_command", required=True
    )
    p = agent.add_parser("scaffold", help="render a new agent package and wire it in")
    p.add_argument("agent_id", help="snake_case job title, e.g. inventory_manager")
    p.add_argument("--label-en", required=True)
    p.add_argument("--label-fi", required=True)
    p.add_argument("--role", dest="roles", action="append", required=True)
    p.add_argument("--description", default="", help="router description (a stub's by default)")
    p.add_argument("--force", action="store_true", help="overwrite the rendered files")
    p.set_defaults(func=agent_scaffold)
    p = sub.add_parser("learned", help="routes Mia learned from 'Is this about' taps")
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=learned)
    p = sub.add_parser("forget", help="forget one learned route (two new taps relearn it)")
    p.add_argument("key")
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=forget)
    bill = sub.add_parser("billing", help="billing exports").add_subparsers(
        dest="billing_command", required=True
    )
    p = bill.add_parser("export", help="completed work per client and site for a month, as CSV")
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--out", help="file path (default: stdout)")
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=billing_export)
    pay = sub.add_parser("payroll", help="payroll exports").add_subparsers(
        dest="payroll_command", required=True
    )
    p = pay.add_parser("export", help="approved timesheets for a period, as CSV")
    p.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    p.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
    p.add_argument("--out", help="file path (default: stdout)")
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=payroll_export)
    sched = sub.add_parser("schedule", help="visits and assignments").add_subparsers(
        dest="schedule_command", required=True
    )
    p = sched.add_parser("generate", help="create the missing visits from the job recurrences")
    p.add_argument("--days", type=int, default=28)
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=schedule_generate)
    auth_p = sub.add_parser("auth", help="authentication").add_subparsers(
        dest="auth_command", required=True
    )
    p = auth_p.add_parser("bootstrap", help="create the first owner and print an enrolment link")
    p.add_argument("--email", required=True)
    p.add_argument("--name")
    p.add_argument("--lang", default="fi", choices=SUPPORTED)
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=auth_bootstrap)
    p = auth_p.add_parser("reset", help="end a person's sessions and print an enrolment link")
    p.add_argument("name")
    p.set_defaults(func=auth_reset)
    p = auth_p.add_parser("link", help="send a one-time login link to a person's WhatsApp")
    p.add_argument("name")
    p.set_defaults(func=auth_link)
    clients = auth_p.add_parser("client", help="outside agents and services").add_subparsers(
        dest="client_command", required=True
    )
    p = clients.add_parser("add", help="register a client; prints its credentials once")
    p.add_argument("name")
    p.add_argument("--role", dest="roles", action="append", required=True)
    p.add_argument("--branch", help="branch id (default: the only branch)")
    p.set_defaults(func=auth_client_add)
    p = clients.add_parser("revoke", help="revoke a client and its tokens")
    p.add_argument("client_id")
    p.set_defaults(func=auth_client_revoke)
    p = auth_p.add_parser("unlock", help="clear the lockout of a login")
    p.add_argument("login")
    p.set_defaults(func=auth_unlock)
    keys_p = sub.add_parser("keys", help="key material").add_subparsers(
        dest="keys_command", required=True
    )
    p = keys_p.add_parser("init", help="create the master key file")
    p.add_argument("path", nargs="?")
    p.set_defaults(func=keys_init)
    from mia.learning.commands import register as register_skills

    register_skills(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for `uv run mia`. Registers the configured channels, then runs the command."""
    from mia.channels.setup import register_configured

    args = build_parser().parse_args(argv)
    register_configured(get_settings())
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
