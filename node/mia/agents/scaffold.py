"""`mia agent scaffold`: render a new agent package from _template/ and wire it into the shared
files (registry, stubs, labels, policy, schema, layout). Deterministic; refuses to overwrite a
file unless force. Each shared-file edit is a pure `edit_*` function that leaves its file
unchanged when its line is already there, so a forced rerun edits nothing twice.

The templates are .tmpl files so the architecture scan of mia/**/*.py never reads them, and this
module spells no agent id (rule 15): ids arrive as arguments."""

import ast
import json
import re
import textwrap
from collections.abc import Callable
from pathlib import Path
from string import Template

from mia.core.models import STANDARD_VERSION
from mia.core.people import HUMAN_ROLES

TEMPLATE = Path(__file__).resolve().parent / "_template"
ID = re.compile(r"^[a-z][a-z0-9_]*$")
MODULES = ("fil", "ceb", "ilo", "hil", "war", "bcl", "pam", "pag")  # i18n beyond en and fi
LABEL = re.compile(r'^\s+"agent\.[a-z0-9_]+\.label": ')


def _targets(agent_id: str) -> dict[str, str]:
    """Template file (relative to _template/) -> output path (relative to the repo root)."""
    pkg = f"node/mia/agents/{agent_id}"
    out = {
        str(p.relative_to(TEMPLATE)): f"{pkg}/{p.relative_to(TEMPLATE)}".removesuffix(".tmpl")
        for p in sorted(TEMPLATE.rglob("*.tmpl"))
    }
    out["test_chat.py.tmpl"] = f"node/tests/test_{agent_id}_chat.py"
    out["eval_cases.py.tmpl"] = f"node/tests/evals/{agent_id}_cases.py"
    out["test_evals.py.tmpl"] = f"node/tests/evals/test_{agent_id}_evals.py"
    return out


def _router_literal(text: str) -> str:
    """text as the Python literal after `    router_description=`, as ruff formats it: one
    string when the line fits 100 columns, else a parenthesised string of two or more lines."""
    one = json.dumps(text, ensure_ascii=False)
    if len(one) <= 100 - len("    router_description=,"):
        return one
    width = 100 - 8 - 3  # the indent, the quotes and the leading space
    pieces = textwrap.wrap(text, min(width, len(text) // 2 + 10), break_long_words=False)
    lines = [json.dumps(p if i == 0 else f" {p}", ensure_ascii=False) for i, p in enumerate(pieces)]
    return "(\n" + "".join(f"        {line}\n" for line in lines) + "    )"


def stub_description(stubs: str, agent_id: str) -> str | None:
    """The router description of a stub in stubs.py's DESCRIPTIONS, or None when it has none."""
    for node in ast.parse(stubs).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DESCRIPTIONS":
            value = ast.literal_eval(node.value)
            return value.get(agent_id) if isinstance(value, dict) else None
    return None


def edit_registry(text: str, agent_id: str) -> str:
    """registry.py with the agent's SPEC imported (sorted among the agent imports) and added
    last to BUILT."""
    const = agent_id.upper()
    line = f"from mia.agents.{agent_id}.turn import SPEC as {const}"
    if line in text:
        return text
    lines = text.splitlines(keepends=True)
    agents = [i for i, x in enumerate(lines) if x.startswith("from mia.agents.")]
    at = next((i for i in agents if lines[i].split()[1] > f"mia.agents.{agent_id}.turn"), None)
    lines.insert(agents[-1] + 1 if at is None else at, line + "\n")
    out = "".join(lines)
    start = out.index("BUILT = [\n")
    end = out.index("]\n", start)
    return out[:end] + f"    {const},\n" + out[end:]


def edit_stubs(text: str, agent_id: str) -> str:
    """stubs.py without the agent's `"<id>": (...)` entry in DESCRIPTIONS (unchanged if none)."""
    lines = text.splitlines(keepends=True)
    key = f'    "{agent_id}": (\n'
    if key not in lines:
        return text
    start = lines.index(key)
    end = lines.index("    ),\n", start)
    return "".join(lines[:start] + lines[end + 1 :])


def _after_label_groups(text: str, entry: Callable[[int], str], marker: str) -> str:
    """text with entry(n) inserted after the last line of the n-th group of agent labels."""
    if marker in text:
        return text
    lines = text.splitlines(keepends=True)
    ends = [
        i
        for i, x in enumerate(lines)
        if LABEL.match(x) and (i + 1 == len(lines) or not LABEL.match(lines[i + 1]))
    ]
    for n, i in reversed(list(enumerate(ends))):
        lines.insert(i + 1, entry(n))
    return "".join(lines)


def edit_strings(text: str, agent_id: str, label_en: str, label_fi: str) -> str:
    """strings.py with `agent.<id>.label` after the labels of en (the first group) and fi."""
    key = f'"agent.{agent_id}.label"'
    labels = (label_en, label_fi)
    return _after_label_groups(
        text, lambda n: f"        {key}: {json.dumps(labels[n], ensure_ascii=False)},\n", key
    )


def edit_module(text: str, agent_id: str, label_en: str) -> str:
    """One further-language module with the English label (a draft until reviewed, Q28 to Q35)."""
    key = f'"agent.{agent_id}.label"'
    label = json.dumps(label_en, ensure_ascii=False)
    return _after_label_groups(text, lambda n: f"    {key}: {label},\n", key)


def edit_policy(text: str, agent_id: str, roles: list[str]) -> str:
    """policy.csv with `p, <role>, *, agent:<id>, use, allow` for each role not yet there,
    after the last agent use line."""
    new = [f"p, {r}, *, agent:{agent_id}, use, allow\n" for r in roles]
    lines = text.splitlines(keepends=True)
    new = [x for x in new if x not in lines]
    uses = [i for i, x in enumerate(lines) if ", agent:" in x and ", use, " in x]
    at = uses[-1] + 1 if uses else len(lines)
    return "".join(lines[:at] + new + lines[at:])


def edit_schema(text: str, agent_id: str) -> str:
    """schema.py importing the agent's models, the `import mia.` block kept sorted."""
    line = f"import mia.agents.{agent_id}.models\n"
    if line.strip() in text:
        return text
    lines = text.splitlines(keepends=True)
    block = [i for i, x in enumerate(lines) if x.startswith("import mia.")]
    sorted_block = sorted([*(lines[i] for i in block), line], key=lambda x: x.split()[1])
    return "".join(lines[: block[0]] + sorted_block + lines[block[-1] + 1 :])


def edit_layout(text: str, agent_id: str, label_en: str) -> str:
    """docs/layout.md with one line for the package, before the `<role>/skill/` line."""
    name = f"        {agent_id}/"
    if name in text:
        return text
    line = f"{name.ljust(28)}{label_en}: the mia agent scaffold shape (turn.py, actions.py, ...)\n"
    lines = text.splitlines(keepends=True)
    at = next((i for i, x in enumerate(lines) if x.startswith("        <role>/skill/")), None)
    return text if at is None else "".join(lines[:at] + [line] + lines[at:])


def run(
    root: Path,
    agent_id: str,
    *,
    label_en: str,
    label_fi: str,
    roles: list[str],
    description: str,
    force: bool = False,
) -> list[Path]:
    """Render the package and its tests under `root` (the repository root) and apply the shared
    edits; returns every file written. Raises ValueError for a bad id, role, label or a missing
    description (a stub's own is used when empty), FileExistsError when a rendered file exists
    and not force. Nothing is written unless every check passed."""
    agents = root / "node/mia/agents"
    if not ID.match(agent_id) or (agents / f"{agent_id}.py").exists():
        raise ValueError(f"agent id must match {ID.pattern} and not be a module: {agent_id!r}")
    if not roles or any(r not in HUMAN_ROLES for r in roles):
        raise ValueError(f"roles must be one or more of {', '.join(HUMAN_ROLES)}")
    if not label_en.strip() or not label_fi.strip():
        raise ValueError("--label-en and --label-fi are required")
    stubs_py = agents / "stubs.py"
    description = description.strip() or stub_description(stubs_py.read_text(), agent_id) or ""
    if not description:
        raise ValueError("--description is required for an agent that is not a stub")
    values = {
        "agent_id": agent_id,
        "AGENT_CONST": agent_id.upper(),
        "label_en": label_en,
        "label_lower": label_en.lower(),
        "label_yaml": json.dumps(label_en, ensure_ascii=False),
        "description": description,
        "router_description": _router_literal(description),
        "roles": ", ".join(roles),
        "standard_version": STANDARD_VERSION,
    }
    rendered = {
        root / out: Template((TEMPLATE / src).read_text(encoding="utf-8")).substitute(values)
        for src, out in _targets(agent_id).items()
    }
    existing = [str(p.relative_to(root)) for p in rendered if p.exists()]
    if existing and not force:
        raise FileExistsError(f"refusing to overwrite (pass --force): {', '.join(existing)}")
    i18n = root / "node/mia/i18n"
    edits: dict[Path, Callable[[str], str]] = {
        agents / "registry.py": lambda s: edit_registry(s, agent_id),
        stubs_py: lambda s: edit_stubs(s, agent_id),
        i18n / "strings.py": lambda s: edit_strings(s, agent_id, label_en, label_fi),
        **{i18n / f"{m}.py": lambda s: edit_module(s, agent_id, label_en) for m in MODULES},
        root / "node/config/policies/policy.csv": lambda s: edit_policy(s, agent_id, roles),
        root / "node/mia/schema.py": lambda s: edit_schema(s, agent_id),
        root / "docs/layout.md": lambda s: edit_layout(s, agent_id, label_en),
    }
    for path, edit in edits.items():
        before = path.read_text(encoding="utf-8")
        after = edit(before)
        if after != before:
            rendered[path] = after
    for path, text in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return list(rendered)
