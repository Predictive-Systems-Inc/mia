"""Print the test paths a change affects, one per line, ALL for the full suite, or nothing.

Usage (from the repository root):
    uv run python node/tests/affected.py                  # against origin/main
    uv run python node/tests/affected.py --base HEAD~3
    uv run python node/tests/affected.py --staged         # the index against HEAD
    uv run python node/tests/affected.py --worktree       # staged, unstaged and untracked files

A changed module selects the test files that import it, directly or through other modules (a
reverse import graph built with ast over node/mia and node/tests). Importing a.b.c runs a and a.b
too, so a package's __init__ counts for every module under it. conftest.py's imports are left out
of the graph (they would select everything); a conftest change runs everything instead.
Stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Shared foundations: a change here prints ALL. Fixtures every test uses, the data standard and
# its write path (db, models, events, store, schema), permissions and approvals, organisation
# settings, the i18n strings every reply goes through, migrations, dependencies and the config
# folder (policies, org settings). Patterns are fnmatch globs on repo-relative paths.
FOUNDATIONS = (
    "node/tests/conftest.py",
    "node/tests/*/conftest.py",
    "node/tests/day.py",
    "node/tests/jev_fake.py",
    "node/mia/__init__.py",
    "node/mia/settings.py",
    "node/mia/schema.py",
    "node/mia/core/db.py",
    "node/mia/core/models.py",
    "node/mia/core/events.py",
    "node/mia/core/store.py",
    "node/mia/core/rbac.py",
    "node/mia/core/approvals.py",
    "node/mia/core/orgconfig.py",
    "node/mia/i18n/*",
    "node/migrations/*",
    "node/config/*",
    "pyproject.toml",
    "uv.lock",
)
ARCHITECTURE_TEST = "node/tests/test_architecture.py"
EVAL_CASES = "node/tests/evals/cases/*.csv"
EVALS_DIR = "node/tests/evals"
# Files tests read by path rather than import: the pattern also selects the test.
READ_BY_PATH = {
    "node/tests/evals/cases/*.csv": EVALS_DIR,
    "node/mia/agents/*/manifest.yaml": "node/tests/test_rbac.py",
    ".claude/skills/mia-build-agent/*": "node/tests/test_skill_files.py",
    ".claude/skills/mia-train-role/*": "node/tests/learning/test_skill_files.py",
}


def module_name(path: str) -> str | None:
    """The dotted module for a repo-relative .py path under node/, or None."""
    p = Path(path)
    if p.suffix != ".py" or p.parts[:1] != ("node",):
        return None
    parts = list(p.with_suffix("").parts[1:])
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or None


def owning_module(path: str, modules: set[str]) -> str | None:
    """The nearest package that holds a non-Python file (a manifest, prompt or scenario)."""
    parts = list(Path(path).parts[1:-1])
    while parts:
        if ".".join(parts) in modules:
            return ".".join(parts)
        parts.pop()
    return None


def imports_of(source: str, name: str, is_package: bool, modules: set[str]) -> set[str]:
    """The known modules a module's source imports, plus its parent packages."""
    found: set[str] = set()
    package = name if is_package else name.rpartition(".")[0]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join([*anchor, base] if base else anchor)
            targets = [base] + [f"{base}.{alias.name}" for alias in node.names]
        else:
            continue
        for target in targets:
            # `import mia.core.events` or `from mia.core import x`: take the longest known prefix.
            parts = target.split(".")
            while parts and ".".join(parts) not in modules:
                parts.pop()
            if parts:
                found.add(".".join(parts))
    parts = name.split(".")[:-1]
    while parts:
        found.add(".".join(parts))
        parts.pop()
    found.discard(name)
    return found


def build_graph(root: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Module name to path, and module to the modules that import it (reverse edges)."""
    paths: dict[str, str] = {}
    for base in ("node/mia", "node/tests"):
        for file in sorted((root / base).rglob("*.py")):
            rel = file.relative_to(root).as_posix()
            name = module_name(rel)
            if name and "__pycache__" not in rel:
                paths[name] = rel
    modules = set(paths)
    importers: dict[str, set[str]] = defaultdict(set)
    for name, rel in paths.items():
        if Path(rel).name == "conftest.py":
            continue
        source = (root / rel).read_text(encoding="utf-8")
        for dep in imports_of(source, name, rel.endswith("__init__.py"), modules):
            importers[dep].add(name)
    return paths, importers


def is_test(path: str) -> bool:
    """A pytest file: node/tests/**/test_*.py."""
    return path.startswith("node/tests/") and Path(path).name.startswith("test_")


def affected(changed: list[str], root: Path = ROOT) -> list[str]:
    """The sorted test paths to run for the changed repo-relative paths; ["ALL"] for the suite."""
    if any(fnmatch(path, pattern) for path in changed for pattern in FOUNDATIONS):
        return ["ALL"]
    paths, importers = build_graph(root)
    modules = set(paths)
    selected: set[str] = set()
    seeds: set[str] = set()
    for path in changed:
        exists = (root / path).exists()
        selected.update(test for glob, test in READ_BY_PATH.items() if fnmatch(path, glob))
        if not path.startswith("node/"):
            if path.startswith("docs/") or path.endswith(".md"):
                continue  # docs only
            return ["ALL"]  # CI, deploy, .env.example and the like: not in the graph
        if fnmatch(path, EVAL_CASES):
            continue
        if path.startswith("node/mia/"):
            selected.add(ARCHITECTURE_TEST)
            agent = Path(path).parts[3] if path.startswith("node/mia/agents/") else ""
            if agent and (root / "node/mia/agents" / agent / "tests").is_dir():
                selected.add(f"node/mia/agents/{agent}/tests")
        if is_test(path) and path.endswith(".py"):
            if exists:
                selected.add(path)
            continue
        name = module_name(path)
        if name is None:
            name = owning_module(path, modules)
            if name is None or name == "mia":
                return ["ALL"]  # a data file the graph cannot place
        elif name not in modules and exists:
            return ["ALL"]
        seeds.add(name)
    seen = set(seeds)
    queue = list(seeds)
    while queue:
        for importer in importers.get(queue.pop(), ()):
            if importer not in seen:
                seen.add(importer)
                queue.append(importer)
    selected.update(paths[m] for m in seen if m in paths and is_test(paths[m]))
    return sorted(selected)


def changed_files(args: argparse.Namespace) -> list[str]:
    """Repo-relative paths git reports changed (renames as a delete plus an add)."""

    def git(*cmd: str) -> list[str]:
        out = subprocess.run(["git", *cmd], cwd=ROOT, check=True, capture_output=True, text=True)
        return [line for line in out.stdout.splitlines() if line]

    diff = ("diff", "--name-only", "--no-renames")
    if args.staged:
        return git(*diff, "--cached")
    if args.worktree:
        return sorted(
            set(git(*diff, "HEAD")) | set(git("ls-files", "--others", "--exclude-standard"))
        )
    return git(*diff, f"{args.base}...HEAD")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--base", default="origin/main", help="git ref to diff against")
    group.add_argument("--staged", action="store_true", help="the index against HEAD")
    group.add_argument("--worktree", action="store_true", help="all uncommitted changes")
    parser.add_argument(
        "--paths", action="store_true", help="print node/tests instead of ALL (for xargs pytest)"
    )
    args = parser.parse_args(argv)
    result = affected(changed_files(args))
    if args.paths and result == ["ALL"]:
        result = ["node/tests"]
    for line in result:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
