"""Jev action eval on the intent set: does Jev pick the shift supervisor action a message needs?

Every message of the split goes through decide() on the seeded demo database, as the cleaner
Juha or the supervisor Sanna (by the record's role). The expected action comes from the intent:
shift supervisor intents map to their tool, every other intent (other agents, conversation, other)
to reply_only. Run with:
  MIA_TYPESAFE_KEY=... uv run pytest node/tests/evals/test_jev_action_eval.py -m evals -s
MIA_EVAL_INTENT_SPLIT=train|test|all (default test; the threshold is tuned on train),
MIA_EVAL_INTENT_LANG=en|fi (default en), MIA_EVAL_REPORT=<path> writes JSON.
"""

import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session, select

from mia.agents.shift_supervisor import actions, decider
from mia.chat.service import _prepare
from mia.core.egress import egress_context
from mia.core.models import Branch, Person
from mia.settings import get_settings
from tests.evals.intents import load_dataset

pytestmark = pytest.mark.evals

INTENT_ACTION = {
    "shift_supervisor.report_absence": "record_absence",
    "shift_supervisor.absence_scope": "record_absence",
    "shift_supervisor.my_visits": "get_my_visits",
    "shift_supervisor.find_cover": "find_replacements",
    "shift_supervisor.assign": "assign_cover",
    "shift_supervisor.cover_reply": "respond_to_cover",
    "shift_supervisor.check_in": "check_in",
    "shift_supervisor.check_out": "check_out",
    "shift_supervisor.visit_details": "visit_details",
    "shift_supervisor.cannot_access_site": "report_site_problem",
    "shift_supervisor.site_problem": "report_site_problem",
    "shift_supervisor.checklist": "checklist",
    "shift_supervisor.send_photos": "reply_only",
}
SPLIT = os.environ.get("MIA_EVAL_INTENT_SPLIT", "test")
LANG = os.environ.get("MIA_EVAL_INTENT_LANG", "en")


def _sender(session: Session, role: str) -> Person:
    first = "Sanna" if role == "supervisor" else "Juha"
    return next(p for p in session.exec(select(Person)).all() if p.name.split()[0] == first)


async def _one(session: Session, text: str, role: str) -> tuple[str, str, float, float]:
    """(raw action, decided action, confidence, seconds) for one message."""
    _thread, _past, deps, ctx = _prepare(session, _sender(session, role), text, None)
    query = actions.build_query(deps, text, "")
    start = time.perf_counter()
    with egress_context(ctx):
        d = await decider.decide(query)
    return d.raw_action, d.action, d.confidence, time.perf_counter() - start


def test_jev_actions(session: Session, branch: Branch) -> None:
    if not get_settings().MIA_TYPESAFE_KEY:
        pytest.skip("MIA_TYPESAFE_KEY is not set")
    rows = [r for r in load_dataset(lang=LANG) if SPLIT == "all" or r.split == SPLIT]
    results: list[dict[str, Any]] = []
    for r in rows:  # ponytail: sequential (one Session); a pool of sessions if it is too slow
        expected = INTENT_ACTION.get(r.intent, "reply_only")
        try:
            raw, acted, conf, secs = asyncio.run(_one(session, r.text, r.role))
        except decider.DecideError as exc:
            raw, acted, conf, secs = f"error: {exc}", "error", 0.0, 0.0
        session.commit()
        results.append(
            {
                "id": r.id,
                "intent": r.intent,
                "expected": expected,
                "raw": raw,
                "acted": acted,
                "confidence": conf,
                "seconds": secs,
            }
        )
    tools = set(INTENT_ACTION.values()) - {"reply_only"}
    # In scope: the shift supervisor intents that are built (INTENT_ACTION). Everything else (other
    # agents, unbuilt shift supervisor intents, conversation) is judged only on whether a tool ran.
    ins = [x for x in results if x["intent"] in INTENT_ACTION]
    out = [x for x in results if x["intent"] not in INTENT_ACTION]

    def rate(rows: list[dict[str, Any]], hit: Any) -> float:
        return sum(1 for x in rows if hit(x)) / max(len(rows), 1)

    secs = sorted(x["seconds"] for x in results if x["seconds"])
    summary = {
        "split": SPLIT,
        "lang": LANG,
        "messages": len(results),
        "in_scope": len(ins),
        "in_scope_raw_accuracy": rate(ins, lambda x: x["raw"] == x["expected"]),
        "in_scope_acted_accuracy": rate(ins, lambda x: x["acted"] == x["expected"]),
        "in_scope_clarify_rate": rate(ins, lambda x: x["acted"] == "clarify"),
        "in_scope_wrong_tool_rate": rate(
            ins, lambda x: x["acted"] in tools and x["acted"] != x["expected"]
        ),
        "out_of_scope": len(out),
        "out_of_scope_tool_rate": rate(out, lambda x: x["acted"] in tools),
        "errors": sum(x["acted"] == "error" for x in results),
        "latency_p50": secs[len(secs) // 2] if secs else 0.0,
        "latency_p95": secs[int(len(secs) * 0.95)] if secs else 0.0,
        "in_scope_confusions": Counter(
            f"{x['intent']} -> {x['raw']}" for x in ins if x["raw"] != x["expected"]
        ).most_common(10),
        "out_of_scope_tools": Counter(
            f"{x['intent']} -> {x['acted']}" for x in out if x["acted"] in tools
        ).most_common(10),
    }
    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    if path := os.environ.get("MIA_EVAL_REPORT"):
        Path(path).write_text(
            json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
