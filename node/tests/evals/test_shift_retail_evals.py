"""Real-Jev retail shift supervisor decider evaluation, asserted with the Q40 bar of
tests/evals/gate.py. The fresh gate half (the D40 rerun) runs once with
MIA_EVAL_HALVES=gate MIA_DECIDER=jev uv run pytest node/tests/evals/test_shift_retail_evals.py -m evals -s
(needs MIA_TYPESAFE_KEY). Each case runs build_query and decider.decide on Ferino's
seeded demo (the rs_shop fixture: MIA_ORG=ferinos, so is_retail() holds and RETAIL_ACTIONS are
offered, seeded on the case set's TODAY) through egress (pseudonymised, rule 6), with today
pinned to TODAY, never the run date. A case acts as the agent for a seeded person with the
case's role (clerk Ana, supervisor Marites of the Mall kiosk, supervisor Jun of the Street stall);
an assign_cover case answers Mia's list for Pao's stall shift tomorrow (the sender's last
find_replacements visit). MIA_EVAL_HALVES picks the halves of the fresh rows (default
"tune,gate"; "tune" for a tuning run, "gate" for the gate run); the spent rows, scored in the
runs of 21 Oct 2026, are never selected. Each result keeps Jev's own pick (raw_action), the tool
input and what it resolves to, the seconds and the usage-row tokens. The gate reads the gate
half only; the tune half is for tuning the retail action descriptions."""

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
from mia.agents.shift_supervisor import MANIFEST, decider
from mia.agents.shift_supervisor.actions import build_query
from mia.agents.shift_supervisor.rules import is_retail
from mia.core import jev
from mia.core.egress import EgressContext, egress_context
from mia.core.models import Actor, Branch, Person, UsageCloudRequest, Visit
from mia.settings import get_settings
from tests.conftest import Shop
from tests.evals import gate
from tests.evals.shift_retail_cases import CASES, GATED_LANGS, TODAY, Case

pytestmark = pytest.mark.evals

SCORES = ("right", "wrong", "ask", "other")
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
PURPOSE = f"{MANIFEST.id}.retail.decide.eval"


def _report_path(now: dt.datetime, folder: Path = RESEARCH) -> Path:
    """The raw file for a run at `now` (local time); never overwrites an earlier run."""
    path = folder / f"{MANIFEST.id.replace('_', '-')}-retail-{now:%Y-%m-%d-%H%M}.raw.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    return path


def _selected(cases: list[Case], halves: str) -> list[Case]:
    """The cases of the named halves (comma-separated); never a spent case, whatever is named."""
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


def _resolved(args: dict[str, Any], names: dict[str, str], dates: dict[str, str]) -> dict[str, Any]:
    """What a tool input means for scoring: the person's first name (a person_name, or the
    assign_cover candidate's), the date (a date, or the picked visit's), the incident kind and
    the corrected end time. Pure."""
    name = args.get("person_name") or names.get(args.get("candidate_id") or "")
    return {
        "person": name.split()[0] if name else None,
        "date": args.get("date") or dates.get(args.get("visit_id") or ""),
        "kind": args.get("kind"),
        "time": args.get("end"),
    }


async def _one(
    i: int, case: Case, engine: Engine, person_id: str, cover: str, sem: asyncio.Semaphore
) -> Any:
    """One decided case; its egress purpose carries the case index so its tokens can be found
    afterwards."""
    result: dict[str, Any] = {"i": i, **case.__dict__, "action": None, "error": None}
    async with sem:
        with Session(engine, expire_on_commit=False) as session:
            deps = _deps(session, case, person_id)
            query = await asyncio.to_thread(build_query, deps, case.text, case.previous)
            if case.expected_action == "assign_cover":
                query.last_cover_visit = cover
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
                visit = session.get(Visit, decision.args.get("visit_id") or "")
                dates = {visit.id: visit.date.isoformat()} if visit else {}
                result["resolved"] = _resolved(decision.args, query.people, dates)
            except (jev.JevError, TimeoutError) as exc:
                result["error"] = str(exc) or type(exc).__name__
            session.commit()  # the egress log and usage rows
    return result


def _score(r: dict[str, Any]) -> str:
    """right (the action and its expected inputs: the person, the date, the incident kind and
    the corrected time), wrong (another input, or another action at >= the threshold), ask
    (clarify or a missing input), or other (an error, or another action below the threshold)."""
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


def _senders(staff: dict[str, Person]) -> dict[str, str]:
    """The person id per case role."""
    ids = {"clerk": "Ana", "supervisor": "Marites", "stall_supervisor": "Jun"}
    return {role: staff[name].id for role, name in ids.items()}


def _pao_tomorrow(session: Session, pao: Person) -> str:
    """Pao's stall visit tomorrow: the shift Mia listed cover for."""
    rows = session.exec(select(Visit).where(Visit.date == TODAY + dt.timedelta(days=1))).all()
    return next(v.id for v in rows if pao.id in v.assigned_person_ids)


def test_decider(engine: Engine, session: Session, rs_shop: Shop) -> None:
    settings = get_settings()
    if not settings.MIA_TYPESAFE_KEY or settings.MIA_DECIDER != "jev":
        pytest.skip("needs MIA_TYPESAFE_KEY and MIA_DECIDER=jev")
    assert is_retail()  # MIA_ORG=ferinos: the retail actions, not the cleaning ones
    report = _report_path(dt.datetime.now().astimezone())  # before the run, not after it
    cases = _selected(CASES, os.environ.get("MIA_EVAL_HALVES", "tune,gate"))
    senders = _senders(rs_shop.people)
    cover = _pao_tomorrow(session, rs_shop.people["Pao"])

    async def run() -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(4)
        jobs = (_one(i, c, engine, senders[c.role], cover, sem) for i, c in enumerate(cases))
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
