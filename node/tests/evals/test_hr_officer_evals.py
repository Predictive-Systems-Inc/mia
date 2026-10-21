"""Real-Jev hr officer decider evaluation, asserted with the Q40 bar of tests/evals/gate.py.
Run: MIA_DECIDER=jev MIA_ORG=ferinos uv run pytest
node/tests/evals/test_hr_officer_evals.py -m evals -s (needs MIA_TYPESAFE_KEY; skips while the
case list is empty). Each case runs build_query and decider.decide on Ferino's seeded demo
through egress (pseudonymised, rule 6), with today pinned to the case set's TODAY. Each result
keeps Jev's own pick (raw_action), the seconds and the usage-row tokens. The gate reads the
gate half only; the tune half is for tuning the action descriptions. MIA_EVAL_HALVES picks the
halves (default "tune,gate"). The short half (D42), printed per language, its one assertion no
wrong write (gate.wrong_writes):
MIA_EVAL_HALVES=short MIA_DECIDER=jev uv run pytest node/tests/evals/test_hr_officer_evals.py -m evals -s"""

import asyncio
import datetime as dt
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.agents.decider import THRESHOLD
from mia.agents.hr_officer import MANIFEST, decider
from mia.agents.hr_officer.actions import build_query
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person, UsageCloudRequest
from mia.settings import get_settings
from tests.evals import gate
from tests.evals.cases import write_results
from tests.evals.hr_officer_cases import CASES, GATED_LANGS, TODAY, Case, on

pytestmark = pytest.mark.evals

SCORES = ("right", "wrong", "ask", "other")
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
Ferinos = tuple[Branch, dict[str, Person]]
PURPOSE = f"{MANIFEST.id}.decide.eval"


def _report_path(now: dt.datetime) -> Path:
    """The raw file for a run at `now` (local time); never overwrites an earlier run."""
    path = RESEARCH / f"{MANIFEST.id.replace('_', '-')}-{now:%Y-%m-%d-%H%M}.raw.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    return path


def _selected(cases: list[Case], halves: str) -> list[Case]:
    """The cases of the named halves (comma-separated)."""
    wanted = set(halves.split(","))
    return [c for c in cases if c.half in wanted]


def _deps(session: Session, case: Case, person_id: str) -> AgentDeps:
    person = session.get(Person, person_id)
    assert person is not None
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=TODAY,
        lang=case.lang,
        manifest=MANIFEST,
    )


async def _one(i: int, case: Case, engine: Engine, person_id: str, sem: asyncio.Semaphore) -> Any:
    """One decided case; its egress purpose carries the case index so its tokens can be found
    afterwards."""
    result: dict[str, Any] = {"i": i, **case.__dict__, "action": None, "error": None}
    async with sem:
        with Session(engine, expire_on_commit=False) as session:
            deps = _deps(session, case, person_id)
            query = await asyncio.to_thread(build_query, deps, case.text, case.previous)
            ctx = EgressContext(
                session=session,
                actor=deps.actor,
                organisation_id=deps.organisation_id,
                agent_id=MANIFEST.id,
                purpose=f"{PURPOSE}/{i}",
                level="pseudonymised",
                provider="typesafe",
            )
            start = time.perf_counter()
            try:
                with egress_context(ctx):
                    decision = await asyncio.wait_for(decider.decide(query), timeout=30)
                result |= {"action": decision.action, "missing": decision.missing}
                result |= {"args": decision.args, "raw_action": decision.raw_action}
                result["seconds"] = time.perf_counter() - start
                result["confidence"] = decision.confidence
            except (jev.JevError, TimeoutError) as exc:
                result["error"] = str(exc) or type(exc).__name__
            session.commit()  # the egress log and usage rows
    return result


def _score(r: dict[str, Any]) -> str:
    """right (the action and every expected input), wrong (another input, or another action at
    >= the threshold), ask (clarify or a missing input), or other (an error, or another action
    below the threshold)."""
    if r["error"] is not None:
        return "other"
    if r["action"] == "clarify" or r["missing"] is not None:
        return "ask"
    if r["action"] == r["expected_action"]:
        slots = r["expected_slots"].items()
        return "right" if all(r["args"].get(k) == on(v) for k, v in slots) else "wrong"
    return "wrong" if r["confidence"] >= THRESHOLD else "other"


def _row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    return {"n": len(rows), **{s: round(sum(r["score"] == s for r in rows) / n, 3) for s in SCORES}}


def test_decider(engine: Engine, session: Session, ferinos: Ferinos) -> None:
    settings = get_settings()
    if not CASES:
        pytest.skip("no cases yet")
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    _, staff = ferinos
    senders = {c.role: next(p.id for p in staff.values() if c.role in p.roles) for c in CASES}
    selected = _selected(CASES, os.environ.get("MIA_EVAL_HALVES", "tune,gate"))

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(4)
        cases = enumerate(selected)
        return list(
            await asyncio.gather(*(_one(i, c, engine, senders[c.role], sem) for i, c in cases))
        )

    results = asyncio.run(run())
    usage = session.exec(
        select(UsageCloudRequest).where(col(UsageCloudRequest.task).startswith(PURPOSE))
    ).all()
    tokens = {int(u.task.rsplit("/", 1)[1]): u.input_tokens + u.output_tokens for u in usage}
    for r in results:
        r["tokens"], r["score"] = tokens.get(r["i"], 0), _score(r)
    gated_rows = [r for r in results if r["half"] == "gate" and r["lang"] in GATED_LANGS]
    by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in gated_rows:
        by_lang[r["lang"]].append(r)
    gated = {
        "all": _row(gated_rows),
        "by_language": {k: _row(v) for k, v in sorted(by_lang.items())},
    }
    print(json.dumps(gated, indent=1))
    short = [r for r in results if r["half"] == "short"]
    if short:
        print(json.dumps({"short": gate.by_language(short, _row)}, indent=1))
    text = json.dumps({"gated": gated, "results": results}, ensure_ascii=False, indent=1)
    report.write_text(text + "\n", encoding="utf-8")
    write_results(report, results)  # a spreadsheet of the run
    wrong = gate.wrong_writes(results, MANIFEST.id)
    assert not wrong, [(r["text"], gate.decided(r)) for r in wrong]  # D42, the short half
    if gated_rows:  # a tune-only or short-only run has no gate to assert
        failed = gate.gate_failures(gated)  # the Q40 bar, as the router's
        assert not failed, failed
