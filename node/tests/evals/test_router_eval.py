"""Real-Jev router evaluation (spec 2026-10-18, Testing). Run from the repo root (the key,
MIA_TYPESAFE_KEY, comes from the root .env): uv run pytest node/tests/evals/test_router_eval.py
-m evals -s --no-cov. MIA_EVAL_HALVES picks the halves (default "tune,gate"; "tune" for a tuning
run, "gate" for the gate run); the spent half is never run. The D40 rerun on the full Ferino's
agent list (GATE_FERINOS_SEEDS and GATE_FERINOS_CONTEXT, the fresh gate half only):
MIA_EVAL_HALVES=gate uv run pytest node/tests/evals/test_router_eval.py::test_router -m evals -s
--no-cov. No org setting or fixture selects the agents: every case routes over ROSTER, every
registered agent, which is the eight of config/org/ferinos (test_router_cases pins that), and
the router request does not read MIA_ORG. Synthetic data only (D18). Prints per language,
agent, group and half: right at >= 0.6, wrong at >= 0.6, ask-back rate, real messages answered
as small talk, p50 and p95 latency, and cost (tokens) per message. The gate asserts run over the
gate half only; the tune half is for tuning descriptions and thresholds."""

import asyncio
import datetime as dt
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from mia.agents.registry import AGENTS
from mia.chat import deferred
from mia.chat.agent_router import build_request, decide
from mia.chat.service import run_turn
from mia.core import jev, orgconfig
from mia.core.db import utcnow
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Event, Person, UsageCloudRequest
from mia.settings import get_settings
from tests.evals.cases import new_run, write_results
from tests.evals.gate import gate_failures
from tests.evals.router_cases import CASES, GATED_LANGS, Case

pytestmark = pytest.mark.evals

ROSTER = list(AGENTS)  # every agent the node can route to, so a new one is never missed
SCORES = ("right", "wrong", "ask", "small_talk", "other")
PURPOSE = "chat.route.eval"
CONCURRENCY = 4
RESEARCH = Path(__file__).parents[3] / "docs" / "research"


def _report_path(now: dt.datetime, folder: Path = RESEARCH) -> Path:
    """The raw file for a run at `now` (local time), router-<date>-<HHMM>.raw.json; raises
    FileExistsError when it exists, so a run never overwrites an earlier one."""
    path = folder / f"router-{now:%Y-%m-%d-%H%M}.raw.json"
    return new_run(path)  # neither the raw json nor its results CSV may exist


def _selected(cases: list[Case], halves: str = "tune,gate") -> list[Case]:
    """The cases of the named halves (comma-separated) a run scores, never the spent half."""
    wanted = set(halves.split(",")) - {"spent"}
    return [c for c in cases if c.half in wanted]


def _needs_key() -> None:
    if not get_settings().MIA_TYPESAFE_KEY:
        pytest.skip("MIA_TYPESAFE_KEY is not set")


async def _one(i: int, case: Case, engine: Engine, branch: Branch, sem: asyncio.Semaphore) -> Any:
    """One routed case: its route, latency and any error. Each case has its own session, and
    its egress purpose carries the case index so its tokens can be found afterwards."""
    agents = [AGENTS[a] for a in ROSTER]
    active = AGENTS[case.active] if case.active else None
    # Unpseudonymised: build_request and jev.ask directly (not agent_router.route), so names in
    # the intent rows reach Jev as written, which production does not do.
    body = build_request(case.text, agents, active, case.previous, get_settings().MIA_JEV_MODEL)
    result: dict[str, Any] = {"i": i, **case.__dict__, "kind": "error", "agent": None}
    async with sem:
        with Session(engine, expire_on_commit=False) as session:
            ctx = EgressContext(
                session=session,
                actor=Actor.system(branch.id),
                organisation_id=branch.organisation_id,
                agent_id="router",
                purpose=f"{PURPOSE}/{i}",
                level="pseudonymised",
                provider="typesafe",
            )
            for attempt in range(4):  # back off on overload rather than raise concurrency
                start = time.perf_counter()
                try:
                    with egress_context(ctx):
                        answers = await asyncio.wait_for(jev.ask(body), timeout=30)
                    route = decide(answers, agents, case.active)
                except (jev.JevUnreachable, TimeoutError) as exc:
                    result["error"] = str(exc) or type(exc).__name__
                    if attempt < 3:
                        await asyncio.sleep(5 * (attempt + 1))
                    continue
                except jev.JevError as exc:
                    result["error"] = str(exc)
                    break
                result |= {"kind": route.kind, "agent": route.agent_id, "error": None}
                result["picked"] = answers["agent"]["choice"]  # Jev's pick, before the threshold
                result |= {"confidence": route.confidence, "seconds": time.perf_counter() - start}
                break
    return result


def _score(r: dict[str, Any]) -> str:
    """right, wrong (another agent at >= 0.6), ask, small_talk (a real message answered as small
    talk: a miss, counted apart from wrong), or other (kept a wrong agent, an error)."""
    if r["kind"] == "ask":
        return "ask"
    if r["kind"] == "error":
        return "other"
    if r["kind"] == "small_talk":
        return "right" if r["expected"] in ("any", "small_talk") else "small_talk"
    if r["expected"] == "any" or r["agent"] == r["expected"]:
        return "right"
    return "wrong" if r["kind"] in ("switch", "chosen") else "other"


def _row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    secs = sorted(r["seconds"] for r in rows if r.get("seconds"))
    count = {s: sum(r["score"] == s for r in rows) for s in SCORES}
    return {
        "n": n,
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
    """The rows the gate asserts read: the gate half of the gated languages only. `all` (wrong)
    has every row; `by_language` (right, ask) leaves out the greetings and thanks (`any`), which
    are reported apart in `any`."""
    rows = [r for r in results if r["half"] == "gate" and r["lang"] in GATED_LANGS]
    real = [r for r in rows if r["expected"] != "any"]
    greetings = [r for r in rows if r["expected"] == "any"]
    return {
        "all": _row(rows),
        "by_language": _table(real, "lang"),
        "any": _row(greetings) if greetings else {},
    }


def _print(title: str, table: dict[str, Any]) -> None:
    print(f"\n{title}\n{'':18}{'n':>5}", "".join(f"{s[:5]:>7}" for s in SCORES), end="")
    print(f"{'err':>5}{'p50':>6}{'p95':>6}{'tok':>6}")
    for k, v in table.items():
        print(f"{k:18}{v['n']:>5}", "".join(f"{v[s]:>7}" for s in SCORES), end="")
        print(f"{v['errors']:>5}{v['p50']:>6}{v['p95']:>6}{v['tokens']:>6}")


def test_router(engine: Engine, branch: Branch) -> None:
    _needs_key()
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    cases = _selected(CASES, os.environ.get("MIA_EVAL_HALVES", "tune,gate"))

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(CONCURRENCY)
        return await asyncio.gather(*(_one(i, c, engine, branch, sem) for i, c in enumerate(cases)))

    results = asyncio.run(run())
    with Session(engine) as session:
        usage = session.exec(
            select(UsageCloudRequest).where(col(UsageCloudRequest.task).startswith(PURPOSE))
        ).all()
    tokens = {int(u.task.rsplit("/", 1)[1]): u.input_tokens + u.output_tokens for u in usage}
    for r in results:
        r["tokens"], r["score"] = tokens.get(r["i"], 0), _score(r)
    summary = {
        "model": get_settings().MIA_JEV_MODEL,
        "agents": ROSTER,
        "all": _row(results),
        "by_language": _table(results, "lang"),
        "by_agent": _table(results, "expected"),
        "by_group": _table(results, "group"),
        "by_half": _table(results, "half"),
    }
    summary["gated"] = _gated(results)
    for name in ("by_language", "by_agent", "by_group", "by_half"):
        _print(f"{name} (all languages, reported)", summary[name])
    _print("all languages (reported)", {"all": summary["all"]})
    _print("gated languages, gate half, no greetings (asserted)", summary["gated"]["by_language"])
    _print("gated languages, gate half (wrong asserted)", {"all": summary["gated"]["all"]})
    if summary["gated"]["any"]:
        _print("gated languages, gate half, greetings (reported)", {"any": summary["gated"]["any"]})
    report.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    write_results(report, results, intent="expected", predicted="agent")  # a spreadsheet
    assert not gate_failures(summary["gated"]), gate_failures(summary["gated"])


def test_deferral_and_recovery(
    session: Session, people: dict[str, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One real router turn, then the network is cut: the next message is deferred, and
    retry_due with the real transport resumes it."""
    _needs_key()
    monkeypatch.setenv("MIA_DECIDER", "jev")  # the router's gate (D18)
    get_settings.cache_clear()
    monkeypatch.setattr(
        orgconfig,
        "load",
        lambda org=None: orgconfig.OrgSettings(agents=["shift_supervisor", "sales_supervisor"]),
    )
    sanna = people["Sanna"]
    first = asyncio.run(run_turn(session, None, sanna, "How much have we sold so far today?"))
    session.commit()
    assert first.blocks

    def cut(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cut", request=request)

    real = jev._inner
    monkeypatch.setattr(jev, "_inner", lambda: httpx.MockTransport(cut))
    asyncio.run(run_turn(session, None, sanna, "We sold 12 puto bumbong", first.thread_id))
    session.commit()
    deferrals = session.exec(select(Event).where(Event.action == deferred.DEFERRED)).all()
    assert len(deferrals) == 1

    monkeypatch.setattr(jev, "_inner", real)
    assert asyncio.run(deferred.retry_due(utcnow())) == 1
    session.expire_all()
    (resumed,) = session.exec(select(Event).where(Event.action == deferred.RESUMED)).all()
    assert resumed.after and not resumed.after["expired"] and "failed" not in resumed.after
    assert session.exec(select(Event).where(Event.action == deferred.ENDED)).all()
    routed = session.exec(select(UsageCloudRequest).where(UsageCloudRequest.task == "chat.route"))
    assert [u.result for u in routed] == [
        "success",
        "success",
    ]  # the first turn and the resumed one
