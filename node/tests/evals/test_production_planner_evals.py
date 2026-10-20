"""Real-Jev production planner decider evaluation, asserted with the Q40 bar of tests/evals/gate.py.
Run: MIA_DECIDER=jev uv run pytest node/tests/evals/test_production_planner_evals.py -m evals -s
(needs MIA_TYPESAFE_KEY; skips while the case list is empty). Each case runs build_query and
decider.decide on Ferino's seeded demo through egress (pseudonymised, rule 6). The gate reads
the gate half only; the tune half is for tuning the action descriptions."""

import asyncio
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from mia.agents.base import AgentDeps
from mia.agents.decider import THRESHOLD
from mia.agents.production_planner import MANIFEST, decider
from mia.agents.production_planner.actions import build_query
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person
from mia.settings import get_settings
from tests.evals import gate
from tests.evals.production_planner_cases import CASES, GATED_LANGS, Case

pytestmark = pytest.mark.evals

SCORES = ("right", "wrong", "ask", "other")
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
Ferinos = tuple[Branch, dict[str, Person]]


def _report_path(now: dt.datetime) -> Path:
    """The raw file for a run at `now` (local time); never overwrites an earlier run."""
    path = RESEARCH / f"{MANIFEST.id.replace('_', '-')}-{now:%Y-%m-%d-%H%M}.raw.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    return path


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
        today=dt.datetime.now(ZoneInfo(branch.timezone)).date(),
        lang=case.lang,
        manifest=MANIFEST,
    )


async def _one(case: Case, engine: Engine, person_id: str, sem: asyncio.Semaphore) -> Any:
    result: dict[str, Any] = {**case.__dict__, "action": None, "error": None}
    async with sem:
        with Session(engine, expire_on_commit=False) as session:
            deps = _deps(session, case, person_id)
            query = await asyncio.to_thread(build_query, deps, case.text, case.previous)
            ctx = EgressContext(
                session=session,
                actor=deps.actor,
                organisation_id=deps.organisation_id,
                agent_id=MANIFEST.id,
                purpose=f"{MANIFEST.id}.decide.eval",
                level="pseudonymised",
                provider="typesafe",
            )
            try:
                with egress_context(ctx):
                    decision = await asyncio.wait_for(decider.decide(query), timeout=30)
                result |= {"action": decision.action, "missing": decision.missing}
                result["confidence"] = decision.confidence
            except (jev.JevError, TimeoutError) as exc:
                result["error"] = str(exc) or type(exc).__name__
            session.commit()  # the egress log and usage rows
    return result


def _score(r: dict[str, Any]) -> str:
    """right, wrong (another action at >= the threshold), ask (clarify or a missing input), or
    other (an error, or another action below the threshold)."""
    if r["error"] is not None:
        return "other"
    if r["action"] == "clarify" or r["missing"] is not None:
        return "ask"
    if r["action"] == r["expected_action"]:
        return "right"
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

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(4)
        return list(await asyncio.gather(*(_one(c, engine, senders[c.role], sem) for c in CASES)))

    results = asyncio.run(run())
    for r in results:
        r["score"] = _score(r)
    gated_rows = [r for r in results if r["half"] == "gate" and r["lang"] in GATED_LANGS]
    by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in gated_rows:
        by_lang[r["lang"]].append(r)
    gated = {
        "all": _row(gated_rows),
        "by_language": {k: _row(v) for k, v in sorted(by_lang.items())},
    }
    print(json.dumps(gated, indent=1))
    text = json.dumps({"gated": gated, "results": results}, ensure_ascii=False, indent=1)
    report.write_text(text + "\n", encoding="utf-8")
    failed = gate.gate_failures(gated)  # the Q40 bar, as the router's
    assert not failed, failed
