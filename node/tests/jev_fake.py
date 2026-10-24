"""A fake Jev for tests: answers every question of a request, the given ones as given."""

import json
from collections.abc import Callable
from typing import Any

import httpx


def choice(
    value: str, confidence: float = 0.95, probabilities: dict[str, float] | None = None
) -> dict[str, Any]:
    return {
        "type": "choice",
        "choice": value,
        "confidence": confidence,
        "probabilities": probabilities or {value: confidence},
    }


def answers_for(
    body: dict[str, Any],
    action: str,
    confidence: float = 0.95,
    probabilities: dict[str, float] | None = None,
    **slots: Any,
) -> dict[str, Any]:
    """Answers for every question in body: `action`, the given slots (a float for a noul, a
    dict from `choice` for a slot at its own confidence), and not_stated (or the first option,
    or no) for the rest."""
    out: dict[str, Any] = {}
    for qid, q in body["questions"].items():
        if qid == "action":
            out[qid] = choice(action, confidence, probabilities)
        elif q["type"] == "noul":
            out[qid] = {"type": "noul", "noul": float(slots.get(qid, 0.0))}
        elif qid in slots:
            given = slots[qid]
            out[qid] = given if isinstance(given, dict) else choice(given)
        else:
            first = "not_stated" if "not_stated" in q["criteria"] else next(iter(q["criteria"]))
            out[qid] = choice(first)
    return out


def fake_jev(
    answer: Callable[[dict[str, Any]], dict[str, Any]],
    seen: list[dict[str, Any]] | None = None,
    status: int = 200,
) -> httpx.MockTransport:
    """A transport that records each request body in `seen` and answers with `answer(body)`."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if seen is not None:
            seen.append(body)
        if status != 200:
            return httpx.Response(status, json={"error": "fake"})
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "answers": answer(body),
                "usage": {"input_tokens": 100, "output_tokens": 12},
            },
        )

    return httpx.MockTransport(handler)
