"""Guards for the architecture rules in CLAUDE.md that can be checked mechanically."""

import re
from pathlib import Path

import pytest

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
    """Rule 6: only egress, geocoding, the model factory and channel transport touch HTTP."""
    pattern = re.compile(
        r"^\s*(import|from)\s+(openai|anthropic|google\.genai|httpx|requests)\b", re.MULTILINE
    )
    allowed = {
        MIA / "core" / "egress.py",
        MIA / "core" / "geocoding.py",
        MIA / "agents" / "base.py",
        MIA / "agents" / "shift_supervisor" / "agent.py",
        MIA / "core" / "jev.py",  # builds its client on EgressTransport
        MIA / "channels" / "transport.py",  # rule 6: the only HTTP exit for channels
        MIA / "channels" / "whatsapp" / "adapter.py",  # builds its client on ChannelTransport
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


def test_agents_and_chat_never_import_a_specific_channel() -> None:
    """Pluggable channels: agents and chat use mia.channels.service only, never an adapter."""
    pattern = re.compile(r"^\s*(from|import)\s+mia\.channels\.(whatsapp|simulator)\b", re.MULTILINE)
    offenders = [
        str(p)
        for p in MIA.rglob("*.py")
        if p.relative_to(MIA).parts[0] in ("agents", "chat") and pattern.search(p.read_text())
    ]
    assert offenders == []


def test_channel_adapters_reach_http_only_through_channel_transport() -> None:
    """Every adapter that makes HTTP requests builds its client on ChannelTransport."""
    for p in (MIA / "channels").rglob("adapter.py"):
        text = p.read_text()
        if "httpx.AsyncClient(" in text:
            assert "transport=ChannelTransport(" in text, p


def test_skills_runtime_never_imports_huggingface_hub() -> None:
    """The node runtime reads local model files only; nothing under mia/skills may fetch from HF."""
    import ast

    offenders = []
    for p in (MIA / "skills").rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n.split(".")[0] == "huggingface_hub" for n in names):
                offenders.append(f"{p.relative_to(MIA)}:{node.lineno}")
    assert offenders == []


def test_serve_defaults_hf_hub_offline_and_keeps_an_explicit_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`mia serve` defaults HF_HUB_OFFLINE to 1 before uvicorn starts; an explicit value wins."""
    import argparse
    import os

    import uvicorn

    from mia import cli

    seen: list[str | None] = []
    monkeypatch.setattr(
        uvicorn, "run", lambda *a, **k: seen.append(os.environ.get("HF_HUB_OFFLINE"))
    )
    args = argparse.Namespace(host="127.0.0.1", port=1, reload=False)
    monkeypatch.setenv("HF_HUB_OFFLINE", "x")  # so teardown removes what serve sets
    monkeypatch.delenv("HF_HUB_OFFLINE")
    cli.serve(args)
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    cli.serve(args)
    assert seen == ["1", "0"]


def test_dockerfile_sets_hf_hub_offline() -> None:
    """The node image runs offline for Hugging Face by default."""
    dockerfile = (MIA.parent.parent / "Dockerfile").read_text()
    assert "HF_HUB_OFFLINE=1" in dockerfile


def test_x_mia_actor_is_read_only_by_the_dev_dependency() -> None:
    """ADR 011: the header is accepted in one place, in dev mode."""
    offenders = [
        str(p)
        for p in _py_files()
        if "x-mia-actor" in p.read_text().lower() and p != MIA / "api" / "deps.py"
    ]
    assert offenders == []


def test_every_route_depends_on_auth_or_is_public() -> None:
    """Every route except /health, /, /auth/*, webhooks and /.well-known takes CurrentAuth."""
    from mia.api.main import app

    # /persons answers 404 outside dev mode (the chat page's actor picker).
    public = {
        "/health",
        "/",
        "/persons",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }

    def walk(routes: list[object]) -> list[object]:
        out: list[object] = []
        for r in routes:
            nested = getattr(r, "routes", None)
            out.extend(walk(nested) if nested else [r])
        return out

    for route in walk(list(app.routes)):
        path = getattr(route, "path", "")
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        if path in public or path.startswith(("/auth/", "/channels/", "/.well-known/")):
            continue
        names = {d.call.__name__ for d in dependant.dependencies}
        assert names & {"current_auth", "current_person", "current_client"}, path


def test_no_module_spells_an_agent_id() -> None:
    """Agent ids come from the manifest (rule 15); stubs.py holds the ids of agents with none."""
    from mia.agents.registry import AGENTS

    allowed = {
        MIA / "agents" / "stubs.py",
        MIA / "core" / "orgconfig.py",  # core cannot import agents; default roster spelled here
    }
    pattern = re.compile("|".join(rf"[\"']{re.escape(a)}[\"']" for a in AGENTS))
    offenders = [
        str(p.relative_to(MIA))
        for p in MIA.rglob("*.py")
        if p not in allowed and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_agent_tables_carry_the_agent_prefix_and_shared_tables_live_in_core() -> None:
    """Rule 9: a table defined in mia/agents/<id>/ is prefixed <id>_; the shared sales and
    stock tables (data standard 1.5) are defined in mia/core/models.py."""
    from sqlmodel import SQLModel

    import mia.schema  # noqa: F401  (every table module)

    homes = {m.local_table.name: m.class_.__module__ for m in SQLModel._sa_registry.mappers}
    offenders = [
        name
        for name, module in homes.items()
        if module.startswith("mia.agents.") and not name.startswith(module.split(".")[2] + "_")
    ]
    assert offenders == []
    for name in ("sales_counts", "sales_targets", "sales_notes", "stock_events"):
        assert homes.get(name) == "mia.core.models", name
