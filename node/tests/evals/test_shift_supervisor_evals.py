"""Shift supervisor evaluation suite (run with: uv run pytest node/tests/evals -m evals).

Each scenario in agents/shift_supervisor/tests/scenarios.yaml (or the suite named by MIA_EVAL_SUITE,
such as tests/scenarios_en.yaml) runs RUNS times on a fresh copy of the seeded demo database. Tool calls (names, order, statuses, inputs) are asserted exactly; the
suite passes when the pass rate over all runs meets the manifest's tests.min_pass_rate.
By default the agent runs on the deterministic rules FunctionModel; set MIA_EVAL_MODEL to a
gateway route to evaluate a real model through the egress layer.
"""

import asyncio
import datetime as dt
import os
import shutil
from pathlib import Path
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
import yaml
from pydantic_ai import models
from pydantic_ai.exceptions import AgentRunError
from sqlmodel import Session, select

from mia.agents.shift_supervisor import tools
from mia.agents.shift_supervisor.agent import AGENT_DIR, MANIFEST, create_agent
from mia.chat.service import run_turn
from mia.core import db, people
from mia.core.models import Actor, Event, Person
from mia.learning.checks import hint_language
from mia.schema import create_all
from mia.templates.cleaning.seed import seed

pytestmark = pytest.mark.evals

RUNS = int(os.environ.get("MIA_EVAL_RUNS", "5"))
# A real model is the point of MIA_EVAL_MODEL; conftest blocks model requests otherwise.
if os.environ.get("MIA_EVAL_MODEL"):
    models.ALLOW_MODEL_REQUESTS = True
# MIA_DECIDER=jev runs the suite through Jev (spec 2026-10-17-jev-decider); needs MIA_TYPESAFE_KEY.
# MIA_EVAL_SUITE picks another suite in the agent folder (tests/scenarios_en.yaml: English only).
SUITE = os.environ.get("MIA_EVAL_SUITE") or MANIFEST.tests["suite"]
SCENARIOS: list[dict[str, Any]] = yaml.safe_load((AGENT_DIR / SUITE).read_text(encoding="utf-8"))
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
    """Expected args are a subset of the actual ones; a name may be given in full ("Maria" matches
    "Maria Mäkinen")."""

    def same(want: Any, got: Any) -> bool:
        if isinstance(want, str) and isinstance(got, str):
            return got.lower().startswith(want.lower())
        return bool(want == got)

    return all(same(v, actual.get(k)) for k, v in expected.items())


def _eval_clock() -> dt.datetime:
    """Today at 09:30 in the seed's time zone: Juha's Kamppi visit (09:00) is current, so the
    field-work scenarios meet a visit whatever the wall clock says (the suite was passing only
    through its "no visit" alternatives outside working hours, and failing after midnight)."""
    now = dt.datetime.now(ZoneInfo("Europe/Helsinki"))
    return now.replace(hour=9, minute=30, second=0, microsecond=0)


def _judge(
    expected: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    scenario: dict[str, Any],
    reply_text: str,
) -> list[str]:
    failures: list[str] = []
    if [c["tool"] for c in calls] != [e["tool"] for e in expected]:
        failures.append(
            f"tools {[c['tool'] for c in calls]} != {[e['tool'] for e in expected]}"
            f" (reply: {reply_text[:160]!r})"
        )
        return failures
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
    return failures


async def _run_once(scenario: dict[str, Any], db_path: Path) -> list[str]:
    """Run one scenario; return a list of failures (empty means pass)."""
    agent = create_agent(os.environ.get("MIA_EVAL_MODEL", "test"))
    clock = _eval_clock()
    engine = db.get_engine(f"sqlite:///{db_path}")
    failures: list[str] = []
    with Session(engine, expire_on_commit=False) as session:
        sender = _person(session, scenario["as"])
        if "lang" in scenario:  # the sender's chosen reply language (ADR 016), as a tap sets it
            people.set_language(session, Actor.person(sender), sender, scenario["lang"])
            session.commit()
        threads: dict[str, str] = {}
        for line in scenario.get("setup", []):
            text, _, who = line.partition("|")
            person = _person(session, who) if who else sender
            reply = await run_turn(session, agent, person, text, threads.get(person.id))
            threads[person.id] = reply.thread_id
            session.commit()
        thread_id = threads.get(sender.id)
        mark = session.exec(select(Event).order_by(Event.id.desc())).first()  # type: ignore[union-attr]
        with mock.patch.object(tools, "utcnow", lambda: clock):
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
    text = reply.text()
    # The expected tools first; `or_tools` is the accepted alternative only when they fail.
    failures = _judge(scenario["tools"], calls, scenario, text)
    alternative = scenario.get("or_tools")
    if failures and alternative is not None and not _judge(alternative, calls, scenario, text):
        failures = []
    # A reply the hint words cannot place ("?", a card of site and item names) is not a wrong
    # language; only a reply that reads as the other language fails.
    found = hint_language(text, "?")
    if "reply_lang" in scenario and found not in ("?", scenario["reply_lang"]):
        # The whole reply (cards too): a model may answer with blocks and no separate text.
        failures.append(f"reply language is not {scenario['reply_lang']}: {text[:160]!r}")
    for kind in scenario.get("reply_blocks", []):
        if kind not in {b.type for b in reply.blocks}:
            failures.append(f"reply has no {kind} block")
    for fragment in scenario.get("reply_contains", []):
        if fragment not in text:
            failures.append(f"reply lacks {fragment!r}")
    return failures


def test_scenarios_are_well_formed() -> None:
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) and len(ids) >= 30
    for s in SCENARIOS:
        assert {"id", "as", "message", "tools"} <= set(s), s["id"]


def test_shift_supervisor_pass_rate(template_db: Path, tmp_path: Path) -> None:
    results: dict[str, list[list[str]]] = {}
    real_model = bool(os.environ.get("MIA_EVAL_MODEL")) or os.environ.get("MIA_DECIDER") == "jev"
    # llm_only: languages the deterministic rules model does not read (Filipino).
    for scenario in [s for s in SCENARIOS if real_model or not s.get("llm_only")]:
        for run in range(RUNS):
            path = tmp_path / f"{scenario['id']}-{run}.db"
            shutil.copy(template_db, path)
            try:
                failures = asyncio.run(_run_once(scenario, path))
            except AgentRunError as exc:  # a crashed turn is a failed run, not the end of the eval
                failures = [f"error {type(exc).__name__}: {str(exc)[:200]}"]
            results.setdefault(scenario["id"], []).append(failures)
            db.reset_engines()
    total = sum(len(runs) for runs in results.values())
    passed = sum(1 for runs in results.values() for failures in runs if not failures)
    rate = passed / total
    report = [
        f"{sid}: {sum(1 for f in runs if not f)}/{len(runs)} {next((f for f in runs if f), '')}"
        for sid, runs in results.items()
    ]
    decider_name = os.environ.get("MIA_DECIDER", "agent")
    print(
        f"\nshift_supervisor evals: {passed}/{total} runs passed ({rate:.1%}), suite={SUITE},"
        f" decider={decider_name}, model={os.environ.get('MIA_EVAL_MODEL', 'test')}"
    )
    by_lang: dict[str, list[int]] = {}
    for sid, runs in results.items():
        lang = sid.split("_")[0] if sid.split("_")[0] in ("fi", "en", "fil") else "other"
        tally = by_lang.setdefault(lang, [0, 0])
        tally[0] += sum(1 for f in runs if not f)
        tally[1] += len(runs)
    print("by language: " + ", ".join(f"{k} {p}/{n}" for k, (p, n) in sorted(by_lang.items())))
    print("\n".join(report))
    assert rate >= MANIFEST.tests["min_pass_rate"], "\n".join(
        r for r in report if not r.split(": ")[1].startswith(f"{RUNS}/")
    )
