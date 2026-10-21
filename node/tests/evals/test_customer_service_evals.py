"""Real-Jev customer service decider evaluation, asserted with the Q40 bar of tests/evals/gate.py.
Run: MIA_DECIDER=jev uv run pytest node/tests/evals/test_customer_service_evals.py -m evals -s
(needs MIA_TYPESAFE_KEY; skips while the case list is empty). Each case runs build_query on its
side (customer for scenarios 1 to 7, staff for 8) and decider.decide on Ferino's seeded demo
(the cs fixture, seeded on TODAY) through egress (pseudonymised, rule 6), with today pinned to
the case set's TODAY. MIA_EVAL_HALVES picks the halves (default "tune,gate"; "tune" for a tuning
run); the spent gate half of run 1 is never run. A customer case acts for the seeded customer Mila, a staff case for a
seeded clerk or supervisor. Each result keeps Jev's own pick (raw_action), the seconds and the
usage-row tokens. The gate reads the gate half only; the tune half is for tuning the action
descriptions. The short half (D42), its side by its role, printed per language, its one
assertion no wrong write (gate.wrong_writes):
MIA_EVAL_HALVES=short MIA_DECIDER=jev uv run pytest node/tests/evals/test_customer_service_evals.py -m evals -s"""

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

from mia.agents.customer_service import MANIFEST, decider, public
from mia.agents.customer_service.actions import build_query
from mia.agents.customer_service.models import Customer
from mia.agents.decider import THRESHOLD
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person, UsageCloudRequest
from mia.settings import get_settings
from mia.templates.retail.models import RetailItem
from tests.conftest import Shop
from tests.evals import gate
from tests.evals.cases import new_run, write_results
from tests.evals.customer_service_cases import CASES, GATED_LANGS, TODAY, Case, on

pytestmark = pytest.mark.evals

SCORES = ("right", "wrong", "ask", "other")
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
PURPOSE = f"{MANIFEST.id}.decide.eval"


def _report_path(now: dt.datetime, folder: Path = RESEARCH) -> Path:
    """The raw file for a run at `now` (local time); never overwrites an earlier run."""
    path = folder / f"{MANIFEST.id.replace('_', '-')}-{now:%Y-%m-%d-%H%M}.raw.json"
    return new_run(path)  # neither the raw json nor its results CSV may exist


def _selected(cases: list[Case], halves: str) -> list[Case]:
    """The cases of the named halves (comma-separated); the spent gate half never."""
    wanted = set(halves.split(",")) - {"spent"}
    return [c for c in cases if c.half in wanted]


def _side(case: Case) -> str:
    """The customer side for the seeded customer, else the staff side (scenario 8)."""
    return "customer" if case.role == "customer" else "staff"


async def _one(
    i: int, case: Case, engine: Engine, actor: Actor, names: dict[str, str], sem: asyncio.Semaphore
) -> Any:
    """One decided case; its egress purpose carries the case index so its tokens can be found
    afterwards. Order lines are kept as (item name, quantity)."""
    result: dict[str, Any] = {"i": i, **case.__dict__, "action": None, "error": None}
    async with sem:
        with Session(engine, expire_on_commit=False) as session:
            branch = session.get(Branch, actor.branch_id)
            assert branch is not None
            query = await asyncio.to_thread(
                build_query, session, branch, _side(case), case.text, case.previous, TODAY,
                case.lang,
            )  # fmt: skip
            ctx = EgressContext(
                session=session,
                actor=actor,
                organisation_id=branch.organisation_id,
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
                lines = decision.args.get("lines") or []
                result["lines"] = [[names.get(ln["item_id"]), ln["quantity"]] for ln in lines]
                result["seconds"] = time.perf_counter() - start
                result["confidence"] = decision.confidence
            except (jev.JevError, TimeoutError) as exc:
                result["error"] = str(exc) or type(exc).__name__
            session.commit()  # the egress log and usage rows
    return result


def _score(r: dict[str, Any]) -> str:
    """right (the action and, for place_order, the lines, the time and the day; for
    language_switch the language), wrong (another line, time, day or language, or another action
    at >= the threshold), ask (clarify or a missing input),
    or other (an error, or another action below the threshold)."""
    if r["error"] is not None:
        return "other"
    if r["action"] == "clarify" or r["missing"] is not None:
        return "ask"
    if r["action"] == r["expected_action"]:
        if r["action"] == "language_switch":
            return "right" if r["args"].get("language") == r["expected_language"] else "wrong"
        if r["action"] != "place_order":
            return "right"
        lines = [list(line) for line in r["expected_lines"]]
        same = r["lines"] == lines and r["args"].get("time") == r["expected_time"]
        return "right" if same and r["args"].get("day") == on(r["expected_day"]) else "wrong"
    return "wrong" if r["confidence"] >= THRESHOLD else "other"


def _row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    return {"n": len(rows), **{s: round(sum(r["score"] == s for r in rows) / n, 3) for s in SCORES}}


def _actors(session: Session, staff: dict[str, Person]) -> dict[str, Actor]:
    """The actor per case role: the agent for the seeded customer Mila, or for a seeded staff
    member with that role."""
    mila = next(c for c in session.exec(select(Customer)) if (c.name or "").startswith("Mila"))
    actors = {"customer": public.customer_actor(mila)}
    for role in {c.role for c in CASES} - {"customer"}:
        person = next(p for p in staff.values() if role in p.roles)
        actors[role] = Actor.person(person).as_agent(MANIFEST.roles.agent_role)
    return actors


def test_decider(engine: Engine, session: Session, cs: Shop) -> None:
    settings = get_settings()
    if not CASES:
        pytest.skip("no cases yet")
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    cases = _selected(CASES, os.environ.get("MIA_EVAL_HALVES", "tune,gate"))
    actors = _actors(session, cs.people)
    names = {i.id: i.name for i in session.exec(select(RetailItem))}

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(4)
        return list(
            await asyncio.gather(
                *(_one(i, c, engine, actors[c.role], names, sem) for i, c in enumerate(cases))
            )
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
    if gated_rows:  # a tune-only run has no gate to assert
        failed = gate.gate_failures(gated)  # the Q40 bar, as the router's
        assert not failed, failed
