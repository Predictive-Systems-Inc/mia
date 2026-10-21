"""Real-Jev production planner decider evaluation, asserted with the Q40 bar of tests/evals/gate.py.
Run: MIA_DECIDER=jev uv run pytest node/tests/evals/test_production_planner_evals.py -m evals -s
(needs MIA_TYPESAFE_KEY). Each case runs build_query and decider.decide on Ferino's seeded demo
(the pp_shop fixture on PP_TODAY at 10:00 Manila, tomorrow's plan drafted) through egress
(pseudonymised, rule 6), with today pinned to TODAY, never the run date. A case acts as the
agent for the seeded person of its role (head Nonoy of the commissary, owner Rosa, driver Berto,
supervisor Marites of the Mall kiosk). MIA_EVAL_HALVES picks the halves (default "tune,gate";
"tune" for a tuning run, "gate" for the gate run); the spent rows (scored by the 0747 and 0748
runs) are never selected. The fresh gate half, for the D40 rerun:
MIA_EVAL_HALVES=gate MIA_DECIDER=jev uv run pytest node/tests/evals/test_production_planner_evals.py -m evals -s
Each result keeps Jev's own pick (raw_action), its slot picks resolved to an item name, a kiosk
name, a direction and a number, the seconds and the usage-row tokens. The gate reads the fresh gate half only.
The short half (D42), printed per language, its one assertion no wrong write (gate.wrong_writes):
MIA_EVAL_HALVES=short MIA_DECIDER=jev uv run pytest node/tests/evals/test_production_planner_evals.py -m evals -s"""

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

from mia.agents import decider as shared
from mia.agents.base import AgentDeps
from mia.agents.decider import NOT_STATED, THRESHOLD
from mia.agents.production_planner import MANIFEST, decider, tools
from mia.agents.production_planner.actions import Query, build_query, commissary
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person, UsageCloudRequest
from mia.settings import get_settings
from mia.templates.retail.models import RetailItem
from tests.conftest import PP_TOMORROW, Shop
from tests.evals import gate
from tests.evals.production_planner_cases import CASES, GATED_LANGS, TODAY, Case

pytestmark = pytest.mark.evals

SCORES = ("right", "wrong", "ask", "other")
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
PURPOSE = f"{MANIFEST.id}.decide.eval"
SENDERS = {"head": "Nonoy", "owner": "Rosa", "driver": "Berto", "kiosk": "Marites", "clerk": "Ana"}


def _report_path(now: dt.datetime, folder: Path = RESEARCH) -> Path:
    """The raw file for a run at `now` (local time); never overwrites an earlier run."""
    path = folder / f"{MANIFEST.id.replace('_', '-')}-{now:%Y-%m-%d-%H%M}.raw.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    return path


def _selected(cases: list[Case], halves: str) -> list[Case]:
    """The cases of the named halves (comma-separated); never a spent row."""
    wanted = set(halves.split(",")) - {"spent"}
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


def _resolved(answers: dict[str, Any], q: Query, names: dict[str, str]) -> dict[str, Any]:
    """What Jev's slot picks mean for scoring: the item's name, the kiosk's name, the direction
    key and the number its id names in the query (None when not stated or not an option). Pure."""

    def pick(slot: str, options: dict[str, Any]) -> Any:
        choice = str(answers.get(slot, {}).get("choice", NOT_STATED))
        return options.get(choice)

    return {
        "item": pick("item", names),
        "kiosk": pick("kiosk", q.kiosks),
        "direction": pick("direction", {d: d for d in ("add", "remove", "set")}),
        "number": pick("number", q.numbers),
    }


async def _one(
    i: int,
    case: Case,
    engine: Engine,
    person_id: str,
    names: dict[str, str],
    picks: dict[str, Any],
    sem: asyncio.Semaphore,
) -> Any:
    """One decided case; its egress purpose carries the case index so its tokens can be found
    afterwards, and its message id the index so its slot answers can be."""
    result: dict[str, Any] = {"i": i, **case.__dict__, "action": None, "error": None}
    async with sem:
        with Session(engine, expire_on_commit=False) as session:
            deps = _deps(session, case, person_id)
            query = await asyncio.to_thread(
                build_query, deps, case.text, case.previous, message_id=str(i)
            )
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
                result["resolved"] = _resolved(picks.get(str(i), {}), query, names)
            except (jev.JevError, TimeoutError) as exc:
                result["error"] = str(exc) or type(exc).__name__
            session.commit()  # the egress log and usage rows
    return result


def _score(r: dict[str, Any]) -> str:
    """right (the action and, where the scenario has them, the item, kiosk, direction and
    number), wrong (another of those, or another action at >= the threshold), ask (clarify or a
    missing input), or other (an error, or another action below the threshold)."""
    if r["error"] is not None:
        return "other"
    if r["action"] == "clarify" or r["missing"] is not None:
        return "ask"
    if r["action"] != r["expected_action"]:
        return "wrong" if r["confidence"] >= THRESHOLD else "other"
    got = r["resolved"]
    return "right" if all(got.get(k) == v for k, v in r["expected"].items()) else "wrong"


def _row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    return {"n": len(rows), **{s: round(sum(r["score"] == s for r in rows) / n, 3) for s in SCORES}}


def test_decider(
    engine: Engine, session: Session, pp_shop: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    cases = _selected(CASES, os.environ.get("MIA_EVAL_HALVES", "tune,gate"))
    senders = {role: pp_shop.people[name].id for role, name in SENDERS.items()}
    home = commissary(session, pp_shop.kiosk.organisation_id)
    assert home is not None
    tools.draft_plan(session, home, PP_TOMORROW)  # the plan the tools edit at 10:00
    session.commit()
    names = {i.id: i.name for i in session.exec(select(RetailItem))}
    picks: dict[str, Any] = {}  # message id -> Jev's answers, as decide parsed them
    parse = shared.parse

    def capture(answers: dict[str, Any], q: Query, **kw: Any) -> shared.Decision:
        picks.setdefault(str(q.message_id), answers)
        return parse(answers, q, **kw)

    monkeypatch.setattr(shared, "parse", capture)

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(4)
        jobs = (_one(i, c, engine, senders[c.role], names, picks, sem) for i, c in enumerate(cases))
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
    short = [r for r in results if r["half"] == "short"]
    if short:
        print(json.dumps({"short": gate.by_language(short, _row)}, indent=1))
    text = json.dumps(
        {"gated": gated, "results": results}, ensure_ascii=False, indent=1, default=str
    )
    report.write_text(text + "\n", encoding="utf-8")
    wrong = gate.wrong_writes(results, MANIFEST.id)
    assert not wrong, [(r["text"], gate.decided(r)) for r in wrong]  # D42, the short half
    if gated_rows:  # a tune-only run has no gate to assert
        failed = gate.gate_failures(gated)  # the Q40 bar, as the router's
        assert not failed, failed
