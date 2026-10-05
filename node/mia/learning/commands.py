"""`mia skills ...` command implementations; the CLI only parses arguments.

Every command returns an exit code: 0 ok, 1 a reported error, 2 a missing optional dependency.
"""

import argparse
from importlib import import_module
from pathlib import Path

from pydantic import ValidationError
from sqlmodel import select

from mia.core.db import session_scope
from mia.core.models import Actor, Branch
from mia.learning import catalogue
from mia.learning.checks import check_records
from mia.learning.harvest import harvest
from mia.learning.package import PromotionRefused, promote
from mia.learning.public import load_public
from mia.learning.schema import Record, RoleSpec, load_records, load_role, write_records
from mia.learning.splits import assign_train_dev

AGENTS = Path(__file__).resolve().parent.parent / "agents"
LEARNING_PKGS = {"torch", "transformers", "accelerate", "onnx"}
LEARNING_HINT = "install the learning group: uv sync --group learning"


def skill_dir(role: str) -> Path:
    return AGENTS / role / "skill"


def _role_spec(role: str) -> RoleSpec | None:
    """The role's spec, or None after printing why it cannot be used."""
    path = skill_dir(role) / "role.yaml"
    if not path.exists():
        print(f"role.yaml not found in {path.parent}")
        return None
    try:
        return load_role(path)
    except (ValidationError, ValueError) as exc:
        print(f"role.yaml is invalid: {exc}")
        return None


def validate(args: argparse.Namespace) -> int:
    """Prints every error and warning; returns 1 if there is any error."""
    folder = skill_dir(args.role)
    role = _role_spec(args.role)
    if role is None:
        return 1
    errors: list[str] = []
    if (folder / "public.yaml").exists():
        try:
            load_public(folder / "public.yaml")
        except (ValidationError, ValueError) as exc:
            errors.append(f"public.yaml: {exc}")
    records: list[Record] = []
    for s in ("train", "dev", "test"):
        path = folder / "data" / f"{s}.jsonl"
        if not path.exists():
            continue
        try:
            records += load_records(path)
        except ValueError as exc:  # pydantic ValidationError and JSON errors are ValueErrors
            print(f"error: {path}: {exc}")
            return 1
    conversation = [c.id for c in catalogue.conversation_intents()]
    report = check_records(role, records, conversation)
    errors += report.errors
    for line in errors:
        print(f"error: {line}")
    for line in report.warnings:
        print(f"warning: {line}")
    print(f"{len(records)} records, {len(errors)} errors, {len(report.warnings)} warnings")
    return 1 if errors else 0


def split(args: argparse.Namespace) -> int:
    """Writes train.jsonl and dev.jsonl from reviewed.jsonl (dropped records excluded)."""
    folder = skill_dir(args.role)
    role = _role_spec(args.role)
    if role is None:
        return 1
    reviewed_path = folder / "data" / "reviewed.jsonl"
    if not reviewed_path.exists():
        print(f"reviewed.jsonl not found in {reviewed_path.parent}")
        return 1
    reviewed = [r for r in load_records(reviewed_path) if r.review.status != "dropped"]
    try:
        out = assign_train_dev(role, reviewed, seed=args.seed)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    # ponytail: test.jsonl is owned by the generator, so only train and dev are written.
    for name in ("train", "dev"):
        write_records(folder / "data" / f"{name}.jsonl", [r for r in out if r.split == name])
    print(" ".join(f"{n}={sum(r.split == n for r in out)}" for n in ("train", "dev")))
    return 0


def train(args: argparse.Namespace) -> int:
    """Runs mia.learning.train, or prints the install hint and returns 2 when it is missing."""
    try:
        train_role = import_module("mia.learning.train").train_role
    except ModuleNotFoundError as exc:
        # Only a missing training module or learning-group package; a bug inside it must surface.
        if exc.name != "mia.learning.train" and (exc.name or "").split(".")[0] not in LEARNING_PKGS:
            raise
        print(LEARNING_HINT)
        return 2
    card = train_role(skill_dir(args.role), base_model=args.base_model, with_real=args.with_real)
    print(f"{card.role}@{card.version}: gate {'passed' if card.gate.passed else 'failed'}")
    for f in card.gate.failures:
        print(f"  {f}")
    return 0


def _only_branch_id() -> str | None:
    """The id of the single branch, or None after printing why there is not exactly one."""
    with session_scope() as session:
        branches = session.exec(select(Branch)).all()
    if len(branches) != 1:
        print(f"the database has {len(branches)} branches; run `mia seed` or fix the data")
        return None
    return branches[0].id


def promote_cmd(args: argparse.Namespace) -> int:
    """Promotes through package.promote (which emits the event); 1 with the reason if refused."""
    branch_id = _only_branch_id()
    if branch_id is None:
        return 1
    with session_scope() as session:
        try:
            card = promote(
                session, Actor.system(branch_id), args.role, args.version, args.signed_by
            )
        except PromotionRefused as exc:
            print(str(exc))
            return 1
    print(f"{card.role}@{card.version} is active (signed by {card.signed_by})")
    return 0


def harvest_cmd(args: argparse.Namespace) -> int:
    branch_id = _only_branch_id()
    if branch_id is None:
        return 1
    with session_scope() as session:
        found = harvest(session, args.role, branch_id)
    print(f"{len(found)} new candidates")
    return 0


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    skills = sub.add_parser("skills", help="role skill models").add_subparsers(
        dest="skills_command", required=True
    )
    p = skills.add_parser("validate", help="check a role's data")
    p.add_argument("role")
    p.set_defaults(func=validate)
    p = skills.add_parser("split", help="assign train and dev from reviewed.jsonl")
    p.add_argument("role")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=split)
    p = skills.add_parser("train", help="train, calibrate, evaluate and package")
    p.add_argument("role")
    p.add_argument("--base-model", default=None)
    p.add_argument("--with-real", action="store_true")
    p.set_defaults(func=train)
    p = skills.add_parser("promote", help="make a signed, gate-passing version active")
    p.add_argument("role")
    p.add_argument("version")
    p.add_argument("--signed-by", required=True)
    p.set_defaults(func=promote_cmd)
    p = skills.add_parser("harvest", help="collect clarification choices as candidates")
    p.add_argument("role")
    p.set_defaults(func=harvest_cmd)
