"""Real-Jev inventory manager decider evaluation, asserted with the D40 bar of tests/evals/gate.py.
Run the fresh gate half (the D40 rerun):
MIA_EVAL_HALVES=gate MIA_DECIDER=jev uv run pytest node/tests/evals/test_inventory_manager_evals.py -m evals -s
(needs MIA_TYPESAFE_KEY; skips while the case list is empty). MIA_EVAL_HALVES picks the halves
(default "tune,gate"; "tune" for a tuning run, "gate" for the gate run); a spent row (the 19 Oct
sets, both halves ran) is never run. Each case runs build_query and decider.decide on Ferino's
seeded demo through egress (pseudonymised, rule 6). The gate reads the fresh gate half only; the
tune half is for tuning the action descriptions. Scores: right (the expected action; for a
count, order or delivery the expected (name, quantity) pairs, for a report the expected kind; a
waste without a reason is right when Mia asks the reason, a waste with no number when Mia asks
how many, a how-many-left question when it is the on_hand question of the item), wrong (another
action at >= the threshold), wrong_items (the expected action with other items, kind or a
guessed reason: a wrong write, counted apart), ask (clarify or another missing input), other
(an error). The short half (D42), printed per language, its one assertion no wrong write
(gate.wrong_writes):
MIA_EVAL_HALVES=short MIA_DECIDER=jev uv run pytest node/tests/evals/test_inventory_manager_evals.py -m evals -s"""

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
from mia.agents.inventory_manager import MANIFEST, decider
from mia.agents.inventory_manager.actions import build_query
from mia.agents.inventory_manager.decider import ON_HAND
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person, UsageCloudRequest
from mia.settings import get_settings
from mia.templates.retail.models import RetailIngredient, RetailItem
from tests.evals import gate
from tests.evals.cases import write_results
from tests.evals.inventory_manager_cases import CASES, GATED_LANGS, Case

pytestmark = pytest.mark.evals

SCORES = ("right", "wrong", "wrong_items", "ask", "other")
PURPOSE = f"{MANIFEST.id}.decide.eval"
SENDERS = {"clerk": "Ana", "supervisor": "Marites", "owner": "Rosa"}
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
Ferinos = tuple[Branch, dict[str, Person]]


def _report_path(now: dt.datetime) -> Path:
    """The raw file for a run at `now` (local time); never overwrites an earlier run."""
    path = RESEARCH / f"{MANIFEST.id.replace('_', '-')}-{now:%Y-%m-%d-%H%M}.raw.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    return path


def _selected(cases: list[Case], halves: str) -> list[Case]:
    """The cases of the named halves (comma-separated); a spent row never."""
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
        today=dt.datetime.now(ZoneInfo(branch.timezone)).date(),
        lang=case.lang,
        manifest=MANIFEST,
    )


async def _one(
    i: int, case: Case, engine: Engine, person_id: str, sem: asyncio.Semaphore
) -> dict[str, Any]:
    """One decided case; its egress purpose carries the case index so its tokens can be found
    afterwards. Backs off on overload rather than raise concurrency."""
    result: dict[str, Any] = {"i": i, **case.__dict__, "action": None, "error": "not run"}
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
    return result


def _found(args: dict[str, Any], names: dict[str, str]) -> tuple[str, list[tuple[Any, ...]]]:
    """The kind and the (name, quantity) pairs a decision's args would write: a report's
    events, or an order's or a delivery's lines; an on_hand question (one event, no quantity)
    is kind on_hand."""
    if args.get(ON_HAND):
        ref = str(args.get("item_id") or args.get("ingredient_id"))
        return ON_HAND, [(names.get(ref, "?"), args.get("quantity"))]
    rows = args.get("events") or args.get("lines") or []
    pairs = [
        (names.get(str(e.get("item_id") or e.get("ingredient_id")), "?"), e.get("quantity"))
        for e in rows
    ]
    return (rows[0].get("kind") or "") if rows else "", pairs


def _score(r: dict[str, Any]) -> str:
    """right, wrong, wrong_items, ask or other (the module docstring)."""
    if r["error"] is not None:
        return "other"
    expected_missing = r["expected_missing"]
    action = r["action"]
    if action == "clarify":
        asks_expected = r["missing"] is not None and r["missing"] == expected_missing
        if not asks_expected or r["confidence"] < THRESHOLD:
            return "ask"
        action = r["raw_action"]  # the reason buttons: the turn asks what is missing
    if action != r["expected_action"]:
        return "wrong" if r["confidence"] >= THRESHOLD else "other"
    if r["missing"] != expected_missing:
        return "wrong_items"  # a guessed reason
    if r["found_kind"] != r["expected_kind"] and r["expected_kind"]:
        return "wrong_items"
    expected = Counter(tuple(p) for p in r["expected_items"])
    return "right" if Counter(tuple(p) for p in r["found_items"]) == expected else "wrong_items"


def _row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    secs = sorted(r["seconds"] for r in rows if r.get("seconds"))
    return {
        "n": len(rows),
        **{s: round(sum(r["score"] == s for r in rows) / n, 3) for s in SCORES},
        "errors": sum(r["error"] is not None for r in rows),
        "p50": round(secs[len(secs) // 2], 2) if secs else 0.0,
        "p95": round(secs[int(len(secs) * 0.95)], 2) if secs else 0.0,
        "tokens": round(sum(r["tokens"] for r in rows) / n),
    }


def _table(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    return {k: _row(v) for k, v in sorted(groups.items())}


def _confusions(results: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """The ten most common misses as 'expected -> got (score)'."""
    misses = Counter(
        f"{r['expected_action']} -> {r.get('raw_action') or r['action']} ({r['score']})"
        for r in results
        if r["score"] != "right"
    )
    return misses.most_common(10)


def _print(title: str, table: dict[str, Any]) -> None:
    print(f"\n{title}\n{'':16}{'n':>5}", "".join(f"{s[:7]:>8}" for s in SCORES), end="")
    print(f"{'err':>5}{'p50':>6}{'p95':>6}{'tok':>6}")
    for k, v in table.items():
        print(f"{k:16}{v['n']:>5}", "".join(f"{v[s]:>8}" for s in SCORES), end="")
        print(f"{v['errors']:>5}{v['p50']:>6}{v['p95']:>6}{v['tokens']:>6}")


def test_decider(engine: Engine, session: Session, ferinos: Ferinos) -> None:
    settings = get_settings()
    if not CASES:
        pytest.skip("no cases yet")
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    _, staff = ferinos
    senders = {role: staff[name].id for role, name in SENDERS.items()}
    names = {i.id: i.name for i in session.exec(select(RetailItem)).all()}
    names |= {i.id: i.name for i in session.exec(select(RetailIngredient)).all()}
    cases = _selected(CASES, os.environ.get("MIA_EVAL_HALVES", "tune,gate"))

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(4)
        return list(
            await asyncio.gather(
                *(_one(i, c, engine, senders[c.role], sem) for i, c in enumerate(cases))
            )
        )

    started = time.perf_counter()
    results = asyncio.run(run())
    wall = time.perf_counter() - started
    usage = session.exec(
        select(UsageCloudRequest).where(col(UsageCloudRequest.task).startswith(PURPOSE))
    ).all()
    tokens = {int(u.task.rsplit("/", 1)[1]): u.input_tokens + u.output_tokens for u in usage}
    for r in results:
        r["found_kind"], r["found_items"] = _found(r.get("args") or {}, names)
        r["tokens"], r["score"] = tokens.get(r["i"], 0), _score(r)
    gated_rows = [r for r in results if r["half"] == "gate" and r["lang"] in GATED_LANGS]
    tune_rows = [r for r in results if r["half"] == "tune"]
    gated = {
        "all": _row(gated_rows),
        "by_language": _table(gated_rows, "lang"),
        "by_scenario": _table(gated_rows, "scenario"),
    }
    summary = {
        "model": settings.MIA_JEV_MODEL,
        "wall_seconds": round(wall, 1),
        "gated": gated,
        "tune": {"all": _row(tune_rows), "by_language": _table(tune_rows, "lang")},
        "confusions": _confusions(results),
    }
    _print("tune half by language", summary["tune"]["by_language"])
    _print("gate half by language (asserted)", gated["by_language"])
    _print("gate half by scenario", gated["by_scenario"])
    _print("gate half (asserted)", {"all": gated["all"]})
    short = [r for r in results if r["half"] == "short"]
    if short:
        _print("short half by language (D42, no wrong write asserted)", _table(short, "lang"))
    print(f"\nconfusions: {summary['confusions']}\nwall {wall:.0f} s")
    text = json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1)
    report.write_text(text + "\n", encoding="utf-8")
    write_results(report, results)  # a spreadsheet of the run
    wrong = gate.wrong_writes(results, MANIFEST.id)
    assert not wrong, [(r["text"], gate.decided(r)) for r in wrong]  # D42, the short half
    if gated_rows:  # a tune-only run has no gate to assert
        failed = gate.gate_failures(gated)  # the D40 bar, as the router's
        assert not failed, failed
