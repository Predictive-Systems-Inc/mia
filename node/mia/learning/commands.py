"""`mia skills ...` command implementations; the CLI only parses arguments.

Every command returns an exit code: 0 ok, 1 a reported error, 2 a missing optional dependency.
"""

import argparse
import asyncio
import datetime as dt
import json
from importlib import import_module
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlmodel import select

from mia.core.db import session_scope
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch
from mia.learning import catalogue
from mia.learning.checks import check_records
from mia.learning.generate import Cell, generate, plan_cells
from mia.learning.harvest import harvest
from mia.learning.overlap import (
    Item,
    analyse,
    recall_at,
    render,
    review_pairs,
    unfindable,
)
from mia.learning.package import PromotionRefused, promote
from mia.learning.public import load_public
from mia.learning.schema import (
    OTHER,
    Record,
    RoleSpec,
    Split,
    load_records,
    load_role,
    write_records,
)
from mia.learning.splits import assign_train_dev
from mia.settings import get_settings

AGENTS = Path(__file__).resolve().parent.parent / "agents"
LEARNING_PKGS = {"torch", "transformers", "accelerate", "onnx"}
GENERATOR_PROMPT = (
    Path(__file__).resolve().parents[3] / ".claude/skills/mia-train-role/prompts/generator.md"
)
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
    intents = catalogue.conversation_intents()
    examples = [e for c in intents for e in c.examples]
    report = check_records(role, records, [c.id for c in intents], examples)
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


def _learning_module(name: str) -> Any:
    """The learning-group module, or None after printing the install hint. Only a missing
    module or learning-group package counts; a bug inside the module must surface."""
    try:
        return import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name and (exc.name or "").split(".")[0] not in LEARNING_PKGS:
            raise
        print(LEARNING_HINT)
        return None


def train(args: argparse.Namespace) -> int:
    """Runs mia.learning.train, or prints the install hint and returns 2 when it is missing."""
    module = _learning_module("mia.learning.train")
    if module is None:
        return 2
    card = module.train_role(
        skill_dir(args.role), base_model=args.base_model, with_real=args.with_real
    )
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


def _filter_cells(role: RoleSpec, cells: list[Cell], only: str) -> list[Cell] | None:
    """Cells matching --only (intent ids and language codes); None after printing a bad value."""
    langs = {v for v in only.split(",") if v in role.languages}
    intents = {v for v in only.split(",") if v and v not in langs}
    unknown = intents - {i.id for i in role.intents} - {OTHER}
    if unknown or not (langs or intents):
        print(f"--only: unknown value(s) {sorted(unknown) or [only]}; use intent ids or languages")
        return None
    return [
        c for c in cells if (not intents or c.intent in intents) and (not langs or c.lang in langs)
    ]


def _output_path(folder: Path, split_name: str) -> Path:
    """The canonical file, or a timestamped sibling when it exists (reviewed data is kept)."""
    data = folder / "data"
    canonical = data / ("test.jsonl" if split_name == "test" else "generated.jsonl")
    if not canonical.exists():
        return canonical
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return data / f"generated-{split_name}-{stamp}.jsonl"


def _run_teacher(
    role: RoleSpec,
    cells: list[Cell],
    model: str,
    prompt: str,
    split_name: Split,
    drops: dict[str, int],
) -> list[Record] | None:
    """Runs the teacher; local routes need no egress context, others log through egress."""

    def run() -> list[Record]:
        return asyncio.run(generate(role, cells, model, prompt, split=split_name, drops=drops))

    if model.startswith("local/"):
        return run()
    with session_scope() as session:
        branches = session.exec(select(Branch)).all()
        if len(branches) != 1:
            print(f"the database has {len(branches)} branches; run `mia seed` or fix the data")
            return None
        ctx = EgressContext(
            session=session,
            actor=Actor.system(branches[0].id),
            organisation_id=branches[0].organisation_id,
            agent_id="learning.generate",
            purpose="skill-generation",
            level=get_settings().MIA_EGRESS_LEVEL,
        )
        with egress_context(ctx):
            return run()


def generate_cmd(args: argparse.Namespace) -> int:
    """Teacher generation for a role; 1 with a message on any error, never a traceback."""
    role = _role_spec(args.role)
    if role is None:
        return 1
    prompt_path = Path(args.prompt) if args.prompt else GENERATOR_PROMPT
    if not prompt_path.exists():
        print(f"generator prompt not found: {prompt_path}")
        return 1
    planned = plan_cells(role, args.split, args.per_cell)
    cells = _filter_cells(role, planned, args.only) if args.only else planned
    if cells is None:
        return 1
    drops: dict[str, int] = {}
    try:
        records = _run_teacher(
            role, cells, args.model, prompt_path.read_text(encoding="utf-8"), args.split, drops
        )
    except Exception as exc:  # noqa: BLE001  model, route and network failures all end here
        print(f"generation failed: {type(exc).__name__}: {exc}")
        return 1
    if records is None:
        return 1
    path = _output_path(skill_dir(args.role), args.split)
    write_records(path, records)
    dropped = ", ".join(f"{n} {why}" for why, n in sorted(drops.items())) or "none"
    print(f"{len(records)} records in {len(cells)} cells written to {path}; dropped: {dropped}")
    return 0


def _read_dataset(path: Path) -> list[Item] | None:
    """Items of an eval-format jsonl (id, intent, text per line); None after printing why not."""
    if not path.is_file():
        print(f"error: {path}: file not found")
        return None
    items: list[Item] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            items.append(Item(id=row["id"], intent=row["intent"], text=row["text"]))
        except json.JSONDecodeError:
            print(f"error: {path}: line {n}: invalid JSON")
            return None
        except (KeyError, TypeError):
            print(f"error: {path}: line {n}: needs id, intent and text")
            return None
    return items


def _overlap_items(args: argparse.Namespace) -> tuple[list[Item], str, Path] | None:
    """Items, embedding model and report path for a dataset or a role; None after a message."""
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")
    if args.dataset:
        items = _read_dataset(Path(args.dataset))
        if items is None:
            return None
        model = args.embedding_model or RoleSpec.model_fields["embedding_model"].default
        return items, model, Path(args.out) if args.out else Path(f"overlap-{stamp}.md")
    role = _role_spec(args.role)
    if role is None:
        return None
    data = skill_dir(args.role) / "data"
    items = [
        Item(id=r.id, intent=r.intent, text=r.text)
        for s in ("train", "dev", "test", "reviewed")
        if (data / f"{s}.jsonl").exists()
        for r in load_records(data / f"{s}.jsonl")
    ]
    out = Path(args.out) if args.out else skill_dir(args.role) / "reports" / f"overlap-{stamp}.md"
    return items, args.embedding_model or role.embedding_model, out


def overlap_cmd(args: argparse.Namespace) -> int:
    """Embedding overlap report for a role's records or an eval-format dataset (id, intent,
    text per line), plus the shared conversation examples unless --no-conversation."""
    if not args.role and not args.dataset:
        print("give a role or --dataset")
        return 1
    embed = _learning_module("mia.learning.embed")
    if embed is None:
        return 2
    loaded = _overlap_items(args)
    if loaded is None:
        return 1
    items, model, out = loaded
    if not args.no_conversation:
        items += [
            Item(id=f"{c.id}/example/{n}", intent=c.id, text=e)
            for c in catalogue.conversation_intents()
            for n, e in enumerate(c.examples)
        ]
    if not items:
        print("no records to compare")
        return 1
    emb = embed.Embedder(model)([i.text for i in items])
    expected: set[frozenset[str]] = set()
    if args.expect:
        if not Path(args.expect).is_file():
            print(f"error: {args.expect}: file not found")
            return 1
        expected = review_pairs(Path(args.expect).read_text(encoding="utf-8"))
    lost = unfindable(expected, {i.intent for i in items})
    expected -= lost
    text = render(analyse(items, emb))
    if args.expect:
        lines = []
        if lost:
            names = ", ".join(" / ".join(sorted(p)) for p in sorted(lost, key=sorted))
            lines.append(f"unfindable: {len(lost)} pairs (no records): {names}")
        at = recall_at(items, emb, expected)
        scores = ", ".join(f"recall@{k} {f'{r:.2f}' if expected else 'n/a'}" for k, r in at.items())
        lines.append(f"{scores} ({len(expected)} findable pairs)")
        print("\n".join(lines))
        text += "\n" + "\n".join(lines) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(out)
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
    p = skills.add_parser("generate", help="teacher-model synthetic data per coverage cell")
    p.add_argument("role")
    p.add_argument("--model", required=True, help="local/<model> or a gateway route")
    p.add_argument("--split", choices=["train", "test"], default="train")
    p.add_argument("--per-cell", type=int, default=None)
    p.add_argument("--only", default=None, help="comma list of intent ids and languages")
    p.add_argument("--prompt", default=None, help="generator prompt file")
    p.set_defaults(func=generate_cmd)
    p = skills.add_parser("overlap", help="embedding overlap review of intents")
    p.add_argument("role", nargs="?", default=None)
    p.add_argument("--dataset", default=None, help="eval-format jsonl: id, intent, text")
    p.add_argument("--embedding-model", default=None)
    p.add_argument("--expect", default=None, help="review markdown whose pairs must be found")
    p.add_argument("--no-conversation", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=overlap_cmd)
