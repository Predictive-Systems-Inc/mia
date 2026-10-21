"""Real-Jev short-message check (D42), the one hard rule: no wrong write.
Run: MIA_DECIDER=jev uv run pytest node/tests/evals/test_short_evals.py -m evals -s
(needs MIA_TYPESAFE_KEY; MIA_SHORT_AGENTS=bookkeeper,hr_officer runs a subset). Every case of
short_cases.py runs its agent's build_query and decider.decide on Ferino's seeded demo (the
pp_shop fixture, tomorrow's plan drafted as the production planner's harness does) through
egress (pseudonymised, rule 6), with today pinned to TODAY, never the run date. A case acts as
the agent for a seeded person with the case's role (the production planner's supervisor is the
commissary head Nonoy), or for the seeded customer Mila. Each result keeps Jev's own pick and
confidence, the decided action, the missing input and wrong_write (the decided action writes a
row and is not the expected one). The raw file is docs/research/short-<local minute>.raw.json.
The only assertion is no wrong write; right, wrong and ask are printed, never a bar."""

import asyncio
import datetime as dt
import json
import os
import time
from collections import defaultdict
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from mia.agents.base import AgentDeps
from mia.agents.customer_service import public
from mia.agents.customer_service.actions import build_query as cs_build_query
from mia.agents.customer_service.models import Customer
from mia.agents.production_planner import tools as pp_tools
from mia.agents.production_planner.actions import commissary
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person
from mia.settings import get_settings
from tests.conftest import PP_TOMORROW, Shop
from tests.evals.short_cases import AGENTS, ASK, CASES, TODAY, Case, writes

pytestmark = pytest.mark.evals

RESEARCH = Path(__file__).parents[3] / "docs" / "research"
OUTCOMES = ("right", "wrong", "ask", "error")
SENDERS = {"owner": "Rosa", "supervisor": "Marites", "clerk": "Ana", "staff": "Berto"}
HEAD = {"production_planner": {"supervisor": "Nonoy"}}  # the commissary head


def _report_path(now: dt.datetime, folder: Path = RESEARCH) -> Path:
    """The raw file for a run at `now` (local time); never overwrites an earlier run."""
    path = folder / f"short-{now:%Y-%m-%d-%H%M}.raw.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    return path


def _selected(cases: list[Case], agents: str) -> list[Case]:
    """The cases of the named agents (comma-separated); every agent when empty."""
    wanted = set(agents.split(",")) - {""} or set(AGENTS)
    unknown = wanted - set(AGENTS)
    assert not unknown, f"MIA_SHORT_AGENTS names no agent: {unknown}"
    return [c for c in cases if c.agent in wanted]


def _person(session: Session, people: dict[str, Person], case: Case) -> Person:
    name = HEAD.get(case.agent, {}).get(case.role, SENDERS[case.role])
    person = session.get(Person, people[name].id)
    assert person is not None and case.role in person.roles
    return person


async def _query(session: Session, case: Case, people: dict[str, Person]) -> tuple[Any, Actor, str]:
    """The agent's decider query, the actor the request goes out for and its organisation."""
    manifest = import_module(f"mia.agents.{case.agent}").MANIFEST
    if case.agent == "customer_service":
        if case.role == "customer":
            mila = next(
                c for c in session.exec(select(Customer)) if (c.name or "").startswith("Mila")
            )
            actor, side = public.customer_actor(mila), "customer"
        else:
            person = _person(session, people, case)
            actor, side = Actor.person(person).as_agent(manifest.roles.agent_role), "staff"
        branch = session.get(Branch, actor.branch_id)
        assert branch is not None
        query = await asyncio.to_thread(
            cs_build_query, session, branch, side, case.text, case.previous, TODAY, case.lang
        )
        return query, actor, branch.organisation_id
    person = _person(session, people, case)
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    deps = AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(manifest.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=TODAY,
        lang=case.lang,
        manifest=manifest,
    )
    build = import_module(f"mia.agents.{case.agent}.actions").build_query
    query = await asyncio.to_thread(build, deps, case.text, case.previous)
    return query, deps.actor, deps.organisation_id


def _outcome(r: dict[str, Any]) -> tuple[str, str | None, bool]:
    """(right, wrong, ask or error; the decided action, "ask" for clarify or a missing input;
    wrong_write). An expected ask that asks is right."""
    if r["error"] is not None:
        return "error", None, False
    got = ASK if r["action"] == "clarify" or r["missing"] is not None else r["action"]
    wrong_write = got != r["expected_action"] and writes(r["agent"], got)
    if got == r["expected_action"]:
        return "right", got, False
    return ("ask" if got == ASK else "wrong"), got, wrong_write


async def _one(
    i: int, case: Case, engine: Engine, people: dict[str, Person], sem: asyncio.Semaphore
) -> dict[str, Any]:
    """One decided case; backs off on overload rather than raise concurrency."""
    result: dict[str, Any] = {"i": i, **case.__dict__, "expected": case.expected_action}
    result |= {"action": None, "raw_action": None, "confidence": None, "missing": None}
    result |= {"args": None, "error": "not run"}
    async with sem:
        with Session(engine, expire_on_commit=False) as session:
            query, actor, organisation_id = await _query(session, case, people)
            decider = import_module(f"mia.agents.{case.agent}.decider")
            ctx = EgressContext(
                session=session,
                actor=actor,
                organisation_id=organisation_id,
                agent_id=case.agent,
                purpose=f"short.{case.agent}.decide.eval/{i}",
                level="pseudonymised",
                provider="typesafe",
            )
            for attempt in range(4):
                start = time.perf_counter()
                try:
                    with egress_context(ctx):
                        decision = await asyncio.wait_for(decider.decide(query), timeout=30)
                except (jev.JevUnreachable, TimeoutError) as exc:
                    result["error"] = str(exc) or type(exc).__name__
                    if attempt < 3:
                        await asyncio.sleep(5 * (attempt + 1))
                    continue
                except jev.JevError as exc:
                    result["error"] = str(exc)
                    break
                result |= {"error": None, "action": decision.action, "missing": decision.missing}
                result |= {"raw_action": decision.raw_action, "confidence": decision.confidence}
                result |= {"args": decision.args, "seconds": time.perf_counter() - start}
                break
            session.commit()  # the egress log and usage rows
    result["outcome"], result["decided"], result["wrong_write"] = _outcome(result)
    return result


def _table(results: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        rows[r[key]].append(r)
    return {
        k: {"n": len(v), **{o: sum(r["outcome"] == o for r in v) for o in OUTCOMES}}
        | {"wrong_writes": sum(r["wrong_write"] for r in v)}
        for k, v in sorted(rows.items())
    }


def _print(title: str, table: dict[str, dict[str, int]]) -> None:
    cols = ("n", *OUTCOMES, "wrong_writes")
    print(f"\n{title:20}", "".join(f"{c[:12]:>13}" for c in cols))
    for k, v in table.items():
        print(f"{k:20}", "".join(f"{v[c]:>13}" for c in cols))


def test_short_messages(engine: Engine, session: Session, pp_shop: Shop) -> None:
    settings = get_settings()
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    cases = _selected(CASES, os.environ.get("MIA_SHORT_AGENTS", ""))
    home = commissary(session, pp_shop.kiosk.organisation_id)
    assert home is not None
    pp_tools.draft_plan(session, home, PP_TOMORROW)  # the plan the planner's tools edit
    session.commit()

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(4)
        jobs = (_one(i, c, engine, pp_shop.people, sem) for i, c in enumerate(cases))
        return list(await asyncio.gather(*jobs))

    results = asyncio.run(run())
    summary = {"by_agent": _table(results, "agent"), "by_language": _table(results, "lang")}
    _print("agent", summary["by_agent"])
    _print("language", summary["by_language"])
    text = json.dumps(
        {"summary": summary, "results": results}, ensure_ascii=False, indent=1, default=str
    )
    report.write_text(text + "\n", encoding="utf-8")
    wrong = [(r["agent"], r["text"], r["decided"]) for r in results if r["wrong_write"]]
    assert not wrong, wrong  # D42: no wrong write, the only rule
