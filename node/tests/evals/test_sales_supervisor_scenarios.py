"""Sales supervisor chat scenarios (run with: MIA_DECIDER=jev uv run pytest
node/tests/evals/test_sales_supervisor_scenarios.py -m evals; needs MIA_TYPESAFE_KEY).

The shift supervisor's runner (test_shift_supervisor_evals.py) is hard-wired to its manifest,
the cleaning seed and its LLM agent, so this is its copy for the sales manifest: each scenario
in agents/sales_supervisor/tests/scenarios.yaml runs RUNS times on a fresh copy of Ferino's
seeded demo, at 15:00 in Manila (before closing, so the business date is today), through the
whole chat turn with real Jev. Tool calls (names, order, statuses, inputs) are asserted; the
suite passes when the pass rate meets the manifest's tests.min_pass_rate."""

import asyncio
import functools
import os
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlmodel import Session, col, select

from mia.agents.sales_supervisor import AGENT_DIR, MANIFEST
from mia.chat.service import run_turn
from mia.core import db, orgconfig
from mia.core.models import Event, Person
from mia.schema import create_all
from mia.settings import get_settings
from mia.templates.retail.seed import seed

pytestmark = pytest.mark.evals

RUNS = int(os.environ.get("MIA_EVAL_RUNS", "1"))
SCENARIOS: list[dict[str, Any]] = yaml.safe_load(
    (AGENT_DIR / MANIFEST.tests["suite"]).read_text(encoding="utf-8")
)
TOOL_PREFIX = MANIFEST.id + "."


@pytest.fixture
def template_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Ferino's seeded once, with the sales supervisor as the org's only agent."""
    monkeypatch.setenv("MIA_ORG", "ferinos")
    get_settings.cache_clear()
    only = orgconfig.OrgSettings(agents=[MANIFEST.id])
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    path = tmp_path / "template.db"
    engine = db.get_engine(f"sqlite:///{path}")
    create_all(engine)
    with Session(engine) as session:
        seed(session)
        session.commit()
    engine.dispose()
    return path


def _person(session: Session, first_name: str) -> Person:
    rows = session.exec(select(Person)).all()
    return next(p for p in rows if p.name.split()[0] == first_name)


def _judge(expected: list[dict[str, Any]], calls: list[dict[str, Any]], text: str) -> list[str]:
    if [c["tool"] for c in calls] != [e["tool"] for e in expected]:
        got = [c["tool"] for c in calls]
        return [f"tools {got} != {[e['tool'] for e in expected]} (reply: {text[:160]!r})"]
    failures = []
    for exp, call in zip(expected, calls, strict=True):
        status = call["output"].get("status", "ok")
        if status not in ("denied", "invalid", "approval_required"):
            status = "ok"
        if status != exp.get("status", "ok"):
            failures.append(f"{exp['tool']} status {status} != {exp.get('status', 'ok')}")
        if any(call["args"].get(k) != v for k, v in exp.get("args", {}).items()):
            failures.append(f"{exp['tool']} args {call['args']} lack {exp['args']}")
    return failures


async def _run_once(scenario: dict[str, Any], db_path: Path) -> list[str]:
    """Run one scenario; return a list of failures (empty means pass)."""
    engine = db.get_engine(f"sqlite:///{db_path}")
    with Session(engine, expire_on_commit=False) as session:
        sender = _person(session, scenario["as"])
        thread: str | None = None
        for text in scenario.get("setup", []):
            thread = (await run_turn(session, None, sender, text, thread)).thread_id
            session.commit()
        mark = session.exec(select(Event).order_by(col(Event.id).desc())).first()
        assert mark is not None
        reply = await run_turn(session, None, sender, scenario["message"], thread)
        session.commit()
        after = select(Event).where(Event.action == "tool.called").where(Event.id > mark.id)
        calls = [
            {
                "tool": e.entity_id.removeprefix(TOOL_PREFIX),
                "args": (e.before or {})["input"],
                "output": (e.after or {})["output"],
            }
            for e in session.exec(after.order_by(col(Event.id)))
        ]
    text = reply.text()
    failures = _judge(scenario["tools"], calls, text)
    failures += [f"reply lacks {f!r}" for f in scenario.get("reply_contains", []) if f not in text]
    return failures


def test_scenarios_are_well_formed() -> None:
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) and len(ids) >= 10
    for s in SCENARIOS:
        assert {"id", "as", "message", "tools"} <= set(s), s["id"]


def test_sales_supervisor_pass_rate(
    template_db: Path, tmp_path: Path, manila_at: Callable[[int, int], datetime]
) -> None:
    settings = get_settings()
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")
    manila_at(15, 0)
    results: dict[str, list[list[str]]] = {}
    for scenario in SCENARIOS:
        for run in range(RUNS):
            path = tmp_path / f"{scenario['id']}-{run}.db"
            shutil.copy(template_db, path)
            results.setdefault(scenario["id"], []).append(asyncio.run(_run_once(scenario, path)))
            db.reset_engines()
    total = sum(len(runs) for runs in results.values())
    passed = sum(1 for runs in results.values() for failures in runs if not failures)
    report = [
        f"{sid}: {sum(1 for f in runs if not f)}/{len(runs)} {next((f for f in runs if f), '')}"
        for sid, runs in results.items()
    ]
    print(f"\n{MANIFEST.id} scenarios: {passed}/{total} runs passed\n" + "\n".join(report))
    assert passed / total >= MANIFEST.tests["min_pass_rate"], "\n".join(report)
