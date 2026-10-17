"""Jev action eval on the intent set: does Jev pick the dispatcher action a message needs?

Every message of the split goes through decide() on the seeded demo database, as the cleaner
Juha or the supervisor Sanna (by the record's role). The expected action comes from the intent:
dispatcher intents map to their tool, every other intent (other agents, conversation, other)
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

from mia.agents.dispatcher import actions, decider
from mia.chat.service import _prepare
from mia.core.egress import egress_context
from mia.core.models import Branch, Person
from mia.settings import get_settings
from tests.evals.intents import load_dataset

pytestmark = pytest.mark.evals

INTENT_ACTION = {
    "dispatcher.report_absence": "record_absence",
    "dispatcher.absence_scope": "record_absence",
    "dispatcher.my_visits": "get_my_visits",
    "dispatcher.find_cover": "find_replacements",
    "dispatcher.assign": "assign_cover",
    "dispatcher.cover_reply": "respond_to_cover",
    "dispatcher.check_in": "check_in",
    "dispatcher.check_out": "check_out",
    "dispatcher.visit_details": "visit_details",
    "dispatcher.cannot_access_site": "report_site_problem",
    "dispatcher.site_problem": "report_site_problem",
    "dispatcher.checklist": "checklist",
    "dispatcher.send_photos": "reply_only",
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
    n = len(results)
    tools = set(INTENT_ACTION.values()) - {"reply_only"}
    disp = [x for x in results if x["intent"].startswith("dispatcher.")]
    secs = sorted(x["seconds"] for x in results if x["seconds"])
    summary = {
        "split": SPLIT,
        "lang": LANG,
        "messages": n,
        "raw_accuracy": sum(x["raw"] == x["expected"] for x in results) / n,
        "acted_accuracy": sum(x["acted"] == x["expected"] for x in results) / n,
        "clarify_rate": sum(x["acted"] == "clarify" for x in results) / n,
        "wrong_tool_rate": sum(x["acted"] in tools and x["acted"] != x["expected"] for x in results)
        / n,
        "dispatcher_raw_accuracy": sum(x["raw"] == x["expected"] for x in disp) / max(len(disp), 1),
        "errors": sum(x["acted"] == "error" for x in results),
        "latency_p50": secs[len(secs) // 2] if secs else 0.0,
        "latency_p95": secs[int(len(secs) * 0.95)] if secs else 0.0,
        "confusions": Counter(
            f"{x['expected']} -> {x['raw']}" for x in results if x["raw"] != x["expected"]
        ).most_common(15),
    }
    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    if path := os.environ.get("MIA_EVAL_REPORT"):
        Path(path).write_text(
            json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
