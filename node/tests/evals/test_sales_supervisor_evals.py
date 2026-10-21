"""Real-Jev sales supervisor decider evaluation (spec 2026-10-19-sales-supervisor, section 9).
Run: MIA_DECIDER=jev uv run pytest node/tests/evals/test_sales_supervisor_evals.py -m evals -s
(needs MIA_TYPESAFE_KEY). Synthetic data only (D18). Each case runs build_query and
decider.decide on Ferino's seeded demo, through egress (pseudonymised, rule 6). Prints per
language, scenario and half: right (the expected action with the expected items), wrong (another
action at >= the threshold), wrong_items (the expected action with other items), ask (clarify
or a missing input), other (an error), p50 and p95 latency and tokens per message. The gate
asserts run over the gate half only; the tune half is for tuning the action descriptions.

MIA_EVAL_HALVES picks the halves (default "tune,gate"; "tune" for a tuning run, "gate" for the
gate run); the spent half (rows scored in an earlier run) never runs. The fresh gate half, for
the D40 rerun:
MIA_EVAL_HALVES=gate MIA_DECIDER=jev uv run pytest node/tests/evals/test_sales_supervisor_evals.py -m evals -s"""

import asyncio
import datetime as dt
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps
from mia.agents.decider import THRESHOLD
from mia.agents.sales_supervisor import MANIFEST, decider
from mia.agents.sales_supervisor.actions import build_query
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person, UsageCloudRequest
from mia.settings import get_settings
from mia.templates.retail.models import RetailItem
from tests.evals.gate import gate_failures
from tests.evals.sales_cases import CASES, GATED_LANGS, Case

pytestmark = pytest.mark.evals

SCORES = ("right", "wrong", "wrong_items", "ask", "other")
PURPOSE = f"{MANIFEST.id}.decide.eval"
CONCURRENCY = 4
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
SENDERS = {"clerk": "Ana", "supervisor": "Marites", "owner": "Rosa"}
Ferinos = tuple[Branch, dict[str, Person]]


def _report_path(now: dt.datetime, folder: Path = RESEARCH) -> Path:
    """The raw file for a run at `now` (local time), sales-supervisor-<date>-<HHMM>.raw.json;
    raises FileExistsError when it exists, so a run never overwrites an earlier one."""
    path = folder / f"sales-supervisor-{now:%Y-%m-%d-%H%M}.raw.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    return path


def _selected(cases: list[Case], halves: str) -> list[Case]:
    """The cases of the named halves (comma-separated); the spent half never."""
    wanted = set(halves.split(",")) - {"spent"}
    return [c for c in cases if c.half in wanted]


def _needs_jev() -> None:
    settings = get_settings()
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")


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


def _items(action: str, args: dict[str, Any], names: dict[str, str]) -> list[tuple[str, int]]:
    """The (item name, quantity) pairs a count or correction would record."""
    if action not in ("report_sales", "correct_sales"):
        return []
    counts = (args.get("items") or []) if action == "report_sales" else [args]
    return [(names.get(str(c.get("item_id")), "?"), int(c.get("quantity") or 0)) for c in counts]


async def _one(
    i: int, case: Case, engine: Engine, person_id: str, sem: asyncio.Semaphore
) -> dict[str, Any]:
    """One decided case: the decision, latency and any error. Each case has its own session,
    and its egress purpose carries the case index so its tokens can be found afterwards."""
    result: dict[str, Any] = {"i": i, **case.__dict__, "kind": "error", "action": None}
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
            for attempt in range(4):  # back off on overload rather than raise concurrency
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
                result |= {"kind": "decided", "error": None, "action": decision.action}
                result |= {"raw_action": decision.raw_action, "missing": decision.missing}
                result |= {"confidence": decision.confidence, "args": decision.args}
                result["seconds"] = time.perf_counter() - start
                break
            session.commit()  # the egress log and usage rows
    return result


def _score(r: dict[str, Any]) -> str:
    """right, wrong (another action at >= the threshold), wrong_items (the expected action with
    other items: a wrong write, counted apart), ask (clarify or a missing input), other."""
    if r["kind"] == "error":
        return "other"
    if r["action"] == "clarify" or r["missing"] is not None:
        return "ask"
    if r["action"] == r["expected_action"]:
        expected = Counter(tuple(p) for p in r["expected_items"])
        return "right" if Counter(r["items"]) == expected else "wrong_items"
    return "wrong" if r["confidence"] >= THRESHOLD else "other"


def _row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1  # a tune-only run has no gate rows
    secs = sorted(r["seconds"] for r in rows if r.get("seconds"))
    count = {s: sum(r["score"] == s for r in rows) for s in SCORES}
    return {
        "n": len(rows),
        **{s: round(c / n, 3) for s, c in count.items()},
        "errors": sum(r["kind"] == "error" for r in rows),
        "p50": round(secs[len(secs) // 2], 2) if secs else 0.0,
        "p95": round(secs[int(len(secs) * 0.95)], 2) if secs else 0.0,
        "tokens": round(sum(r["tokens"] for r in rows) / n),
    }


def _table(results: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        groups[r[key]].append(r)
    return {k: _row(v) for k, v in sorted(groups.items())}


def _gated(results: list[dict[str, Any]]) -> dict[str, Any]:
    """The rows the gate asserts read: the fresh gate half of the gated languages (spent rows
    never run)."""
    rows = [r for r in results if r["half"] == "gate" and r["lang"] in GATED_LANGS]
    return {
        "all": _row(rows),
        "by_language": _table(rows, "lang"),
        "by_scenario": _table(rows, "scenario"),
    }


def _confusions(results: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """The ten most common misses as 'expected -> got (score)'."""
    misses = Counter(
        f"{r['expected_action']} -> {r['raw_action'] or r['action']} ({r['score']})"
        for r in results
        if r["score"] != "right"
    )
    return misses.most_common(10)


def _print(title: str, table: dict[str, Any]) -> None:
    print(f"\n{title}\n{'':14}{'n':>5}", "".join(f"{s[:7]:>8}" for s in SCORES), end="")
    print(f"{'err':>5}{'p50':>6}{'p95':>6}{'tok':>6}")
    for k, v in table.items():
        print(f"{k:14}{v['n']:>5}", "".join(f"{v[s]:>8}" for s in SCORES), end="")
        print(f"{v['errors']:>5}{v['p50']:>6}{v['p95']:>6}{v['tokens']:>6}")


def test_sales_supervisor_decider(engine: Engine, session: Session, ferinos: Ferinos) -> None:
    _needs_jev()
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    _, staff = ferinos
    senders = {role: staff[name].id for role, name in SENDERS.items()}
    names = {i.id: i.name for i in session.exec(select(RetailItem)).all()}
    cases = _selected(CASES, os.environ.get("MIA_EVAL_HALVES", "tune,gate"))

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(CONCURRENCY)
        return await asyncio.gather(
            *(_one(i, c, engine, senders[c.role], sem) for i, c in enumerate(cases))
        )

    started = time.perf_counter()
    results = asyncio.run(run())
    wall = time.perf_counter() - started
    usage = session.exec(
        select(UsageCloudRequest).where(col(UsageCloudRequest.task).startswith(PURPOSE))
    ).all()
    tokens = {int(u.task.rsplit("/", 1)[1]): u.input_tokens + u.output_tokens for u in usage}
    for r in results:
        r["items"] = _items(r["action"] or "", r.get("args") or {}, names)
        r["tokens"], r["score"] = tokens.get(r["i"], 0), _score(r)
    summary = {
        "model": get_settings().MIA_JEV_MODEL,
        "wall_seconds": round(wall, 1),
        "all": _row(results),
        "by_language": _table(results, "lang"),
        "by_scenario": _table(results, "scenario"),
        "by_half": _table(results, "half"),
        "gated": _gated(results),
        "confusions": _confusions(results),
    }
    for name in ("by_language", "by_scenario", "by_half"):
        _print(f"{name} (both halves, reported)", summary[name])
    _print("gate half by language (asserted)", summary["gated"]["by_language"])
    _print("gate half by scenario", summary["gated"]["by_scenario"])
    _print("gate half (asserted)", {"all": summary["gated"]["all"]})
    print(f"\nconfusions: {summary['confusions']}\nwall {wall:.0f} s")
    report.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    failed = gate_failures(summary["gated"])  # the Q40 bar, as the router's
    assert not failed, failed
