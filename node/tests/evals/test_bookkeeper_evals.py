"""Real-Jev bookkeeper decider evaluation, asserted with the Q40 bar of tests/evals/gate.py.
Run: MIA_DECIDER=jev uv run pytest node/tests/evals/test_bookkeeper_evals.py -m evals -s
(needs MIA_TYPESAFE_KEY). Each case runs build_query and decider.decide on Ferino's seeded demo
(the bk_shop fixture, seeded on the case set's TODAY) through egress (pseudonymised, rule 6),
with today pinned to TODAY, never the run date. A case acts as the agent for a seeded person
with the case's role (supervisor Marites, owner Rosa). MIA_EVAL_HALVES picks the halves (default
"tune,gate"; "tune" for a tuning run, "gate" for the gate run). Each result keeps Jev's own pick
(raw_action), the tool input, the seconds and the usage-row tokens. The gate reads the gate half
only; the tune half is for tuning the action descriptions."""

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
from mia.agents.bookkeeper import MANIFEST, decider
from mia.agents.bookkeeper.actions import build_query
from mia.agents.decider import THRESHOLD
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person, UsageCloudRequest
from mia.settings import get_settings
from tests.conftest import Shop
from tests.evals import gate
from tests.evals.bookkeeper_cases import CASES, GATED_LANGS, TODAY, Case

pytestmark = pytest.mark.evals

SCORES = ("right", "wrong", "ask", "other")
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
PURPOSE = f"{MANIFEST.id}.decide.eval"
AMOUNT_ARG = {"cash_count": "counted"}  # every other action's amount is "amount"


def _report_path(now: dt.datetime, folder: Path = RESEARCH) -> Path:
    """The raw file for a run at `now` (local time); never overwrites an earlier run."""
    path = folder / f"{MANIFEST.id.replace('_', '-')}-{now:%Y-%m-%d-%H%M}.raw.json"
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
                result["confidence"] = decision.confidence
                result["seconds"] = time.perf_counter() - start
            except (jev.JevError, TimeoutError) as exc:
                result["error"] = str(exc) or type(exc).__name__
            session.commit()  # the egress log and usage rows
    return result


def _score(r: dict[str, Any]) -> str:
    """right (the action and its expected inputs: the amount, the provider, the category and
    the petty cash kind), wrong (another input, or another action at >= the threshold), ask
    (clarify or a missing input), or other (an error, or another action below the threshold)."""
    if r["error"] is not None:
        return "other"
    if r["action"] == "clarify" or r["missing"] is not None:
        return "ask"
    if r["action"] != r["expected_action"]:
        return "wrong" if r["confidence"] >= THRESHOLD else "other"
    args = r["args"]
    got = {
        "amount": args.get(AMOUNT_ARG.get(r["action"], "amount")),
        "provider": args.get("provider"),
        "category": args.get("category"),
        "kind": args.get("kind"),
    }
    return "right" if all(got[k] == v for k, v in r["expected"].items()) else "wrong"


def _row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    return {"n": len(rows), **{s: round(sum(r["score"] == s for r in rows) / n, 3) for s in SCORES}}


def _senders(staff: dict[str, Person]) -> dict[str, str]:
    """The person id per case role: supervisor Marites, owner Rosa."""
    return {"supervisor": staff["Marites"].id, "owner": staff["Rosa"].id}


def test_decider(engine: Engine, session: Session, bk_shop: Shop) -> None:
    settings = get_settings()
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    cases = _selected(CASES, os.environ.get("MIA_EVAL_HALVES", "tune,gate"))
    senders = _senders(bk_shop.people)

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(4)
        jobs = (_one(i, c, engine, senders[c.role], sem) for i, c in enumerate(cases))
        return list(await asyncio.gather(*jobs))

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
    text = json.dumps(
        {"gated": gated, "results": results}, ensure_ascii=False, indent=1, default=str
    )
    report.write_text(text + "\n", encoding="utf-8")
    if gated_rows:  # a tune-only run has no gate to assert
        failed = gate.gate_failures(gated)  # the Q40 bar, as the router's
        assert not failed, failed
