"""Guards for the architecture rules in CLAUDE.md that can be checked mechanically."""

import re
from pathlib import Path

MIA = Path(__file__).resolve().parent.parent / "mia"


def _py_files(*exclude: str) -> list[Path]:
    return [
        p
        for p in MIA.rglob("*.py")
        if not any(part in exclude for part in p.relative_to(MIA).parts)
    ]


def test_no_table_writes_outside_core_and_templates() -> None:
    """Rule 1: grep for session.add outside mia/core and mia/templates returns nothing."""
    offenders = [str(p) for p in _py_files("core", "templates") if "session.add" in p.read_text()]
    assert offenders == []


def test_no_provider_sdk_outside_egress_and_model_factory() -> None:
    """Rule 6: agents and tools never import a provider SDK or an HTTP client directly."""
    pattern = re.compile(
        r"^\s*(import|from)\s+(openai|anthropic|google\.genai|httpx|requests)\b", re.MULTILINE
    )
    allowed = {
        MIA / "core" / "egress.py",
        MIA / "core" / "geocoding.py",
        MIA / "agents" / "base.py",
        MIA / "agents" / "dispatcher" / "agent.py",
    }
    offenders = [str(p) for p in _py_files() if p not in allowed and pattern.search(p.read_text())]
    assert offenders == []


def test_no_em_dashes_in_code_comments_or_docs() -> None:
    docs = Path(__file__).resolve().parents[2] / "docs"
    files = list(MIA.rglob("*.py")) + list(docs.rglob("adr/*.md"))
    offenders = [str(p) for p in files if "—" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_public_functions_have_docstrings() -> None:
    """Style rule: docstrings state what a function guarantees (core, chat, agents, channels)."""
    import ast

    missing = []
    for p in MIA.rglob("*.py"):
        if p.relative_to(MIA).parts[0] not in ("core", "chat", "agents", "channels"):
            continue
        for node in ast.parse(p.read_text(encoding="utf-8")).body:
            is_func = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            if is_func and not node.name.startswith("_") and ast.get_docstring(node) is None:
                missing.append(f"{p.relative_to(MIA)}:{node.lineno} {node.name}")
    assert missing == []
