"""Dispatcher evaluation suite (run with: uv run pytest node/tests/evals -m evals).

Each scenario in agents/dispatcher/tests/scenarios.yaml runs RUNS times on a fresh copy of the
seeded demo database. Tool calls (names, order, statuses, inputs) are asserted exactly; the
suite passes when the pass rate over all runs meets the manifest's tests.min_pass_rate.
By default the agent runs on the deterministic rules FunctionModel; set MIA_EVAL_MODEL to a
gateway route to evaluate a real model through the egress layer.
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlmodel import Session, select

from mia.agents.dispatcher.agent import AGENT_DIR, MANIFEST, create_agent
from mia.agents.dispatcher.classifier import detect_language
from mia.chat.service import run_turn
from mia.core import db
from mia.core.models import Event, Person
from mia.schema import create_all
from mia.settings import get_settings
from mia.templates.cleaning.seed import seed

pytestmark = pytest.mark.evals

RUNS = int(os.environ.get("MIA_EVAL_RUNS", "5"))
SCENARIOS: list[dict[str, Any]] = yaml.safe_load(
    (AGENT_DIR / MANIFEST.tests["suite"]).read_text(encoding="utf-8")
)
TOOL_PREFIX = MANIFEST.id + "."


@pytest.fixture(scope="module")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("evals") / "template.db"
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


def _subset(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(actual.get(k) == v for k, v in expected.items())


async def _run_once(scenario: dict[str, Any], db_path: Path) -> list[str]:
    """Run one scenario; return a list of failures (empty means pass)."""
    agent = create_agent(os.environ.get("MIA_EVAL_MODEL", "test"))
    engine = db.get_engine(f"sqlite:///{db_path}")
    failures: list[str] = []
    with Session(engine, expire_on_commit=False) as session:
        sender = _person(session, scenario["as"])
        thread_id = None
        for line in scenario.get("setup", []):
            text, _, who = line.partition("|")
            person = _person(session, who) if who else sender
            reply = await run_turn(session, agent, person, text, None if who else thread_id)
            thread_id = thread_id if who else reply.thread_id
            session.commit()
        mark = session.exec(select(Event).order_by(Event.id.desc())).first()  # type: ignore[union-attr]
        reply = await run_turn(session, agent, sender, scenario["message"], thread_id)
        session.commit()
        after = select(Event).where(Event.action == "tool.called").where(Event.id > mark.id)  # type: ignore[operator, union-attr]
        calls = [
            {
                "tool": e.entity_id.removeprefix(TOOL_PREFIX),
                "args": e.before["input"],  # type: ignore[index]
                "output": e.after["output"],  # type: ignore[index]
            }
            for e in session.exec(after.order_by(Event.id))  # type: ignore[arg-type]
        ]
    expected = scenario["tools"]
    if [c["tool"] for c in calls] != [e["tool"] for e in expected]:
        failures.append(f"tools {[c['tool'] for c in calls]} != {[e['tool'] for e in expected]}")
    else:
        for exp, call in zip(expected, calls, strict=True):
            status = call["output"].get("status", "ok")
            if status not in ("denied", "invalid", "approval_required"):
                status = "ok"
            if status != exp.get("status", "ok"):
                failures.append(f"{exp['tool']} status {status} != {exp.get('status', 'ok')}")
            if not _subset(exp.get("args", {}), call["args"]):
                failures.append(f"{exp['tool']} args {call['args']} lack {exp['args']}")
            if "first_candidate" in scenario and call["tool"] == "find_replacements":
                names = [c["name"] for c in call["output"].get("candidates", [])]
                if not names or names[0] != scenario["first_candidate"]:
                    failures.append(f"first candidate {names[:1]} != {scenario['first_candidate']}")
    text = reply.text()
    if "reply_lang" in scenario:
        prose = " ".join(b.text for b in reply.blocks if b.type == "text")
        if detect_language(prose, "?") != scenario["reply_lang"]:
            failures.append(f"reply language is not {scenario['reply_lang']}: {prose!r}")
    for fragment in scenario.get("reply_contains", []):
        if fragment not in text:
            failures.append(f"reply lacks {fragment!r}")
    return failures


def test_scenarios_are_well_formed() -> None:
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) and len(ids) >= 30
    for s in SCENARIOS:
        assert {"id", "as", "message", "tools"} <= set(s), s["id"]


def test_dispatcher_pass_rate(template_db: Path, tmp_path: Path) -> None:
    results: dict[str, list[list[str]]] = {}
    for scenario in SCENARIOS:
        for run in range(RUNS):
            path = tmp_path / f"{scenario['id']}-{run}.db"
            shutil.copy(template_db, path)
            results.setdefault(scenario["id"], []).append(asyncio.run(_run_once(scenario, path)))
            db.reset_engines()
    total = sum(len(runs) for runs in results.values())
    passed = sum(1 for runs in results.values() for failures in runs if not failures)
    rate = passed / total
    report = [
        f"{sid}: {sum(1 for f in runs if not f)}/{len(runs)} {next((f for f in runs if f), '')}"
        for sid, runs in results.items()
    ]
    print(
        f"\ndispatcher evals: {passed}/{total} runs passed ({rate:.1%}), model={get_settings().MIA_MODEL}"
    )
    print("\n".join(report))
    assert rate >= MANIFEST.tests["min_pass_rate"], "\n".join(
        r for r in report if not r.split(": ")[1].startswith(f"{RUNS}/")
    )
