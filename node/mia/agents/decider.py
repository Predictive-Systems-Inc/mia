"""The generic half of the Jev decider (spec 2026-10-17-jev-decider), shared by the agents.

An agent supplies its ACTIONS, an argument mapping and a request builder; this module reads the
answers, applies the threshold and sends the request. decide() runs no tool. The request leaves
only through the egress transport (rule 6), which pseudonymises it and writes egress_log and
usage; the caller sets the egress context and holds no write lock (rule 11). parse() is pure.
"""

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from mia.chat.route_memory import key_of
from mia.core import jev
from mia.core.egress import EgressBlocked, Pseudonymiser, current_context
from mia.core.events import mask_phones
from mia.core.jev import JevError
from mia.settings import get_settings

NOT_STATED = "not_stated"
# ponytail: one threshold for every action, set from the dev split (Task 7); per action if the
# measurement shows writes need a higher bar than reads.
THRESHOLD = 0.6


@dataclass(frozen=True)
class Action:
    description: str
    tool: str | None  # the tool name without the agent prefix; None for clarify and reply_only
    slots: tuple[str, ...] = ()
    label_key: str | None = None  # the "Did you mean" button label; None is never offered


class DecideError(JevError):
    """Jev answered outside the request's options."""


class Alternative(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    probability: float
    missing: str | None = None


class Decision(BaseModel):
    action: str  # what code does: an action id, clarify after a low confidence
    # the tool input (clarify: the top pick's, maybe partial); reply_only: {"kind"}
    args: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    raw_action: str = ""  # Jev's own pick, before the threshold
    alternatives: list[Alternative] = Field(default_factory=list)
    missing: str | None = None  # a required input that was not found
    phrasebook_version: int | None = None  # the phrasebook a Jev decision read (chat.phrases)
    guarded: bool = False  # an agent's own guard asks: a phrase never overrides it


class Reader:
    """Reads the slot answers one action uses, checking each against the request's options."""

    def __init__(self, answers: dict[str, Any], q: Any) -> None:
        self.answers, self.q = answers, q
        self.confidences: list[float] = []

    def pick(
        self,
        slot: str,
        options: dict[str, str] | set[str],
        fallback: bool = False,
        count_unstated: bool = False,
    ) -> str | None:
        """The chosen option, or None when not stated. Only a stated value counts toward the
        confidence (not stated means the tool's default applies), unless count_unstated: for
        slots whose default is consequential (an absence's day and person). With fallback=True
        an uncertain value is dropped instead, for slots that code can resolve another way."""
        answer = self.answers[slot]
        value = str(answer["choice"])
        if value != NOT_STATED and value not in options:
            raise DecideError(f"{slot}: {value!r} is not an option")
        confidence = float(answer["confidence"])
        if value == NOT_STATED:
            if count_unstated:
                self.confidences.append(confidence)
            return None
        if fallback and confidence < THRESHOLD:
            return None
        self.confidences.append(confidence)
        return value

    def yes(self, slot: str) -> bool:
        p = float(self.answers[slot]["noul"])
        self.confidences.append(max(p, 1 - p))
        return p >= 0.5


def parse(
    answers: dict[str, Any],
    q: Any,
    *,
    actions: Mapping[str, Action],
    args: Callable[[str, Reader], tuple[dict[str, Any], str | None]],
    threshold: float = THRESHOLD,
) -> Decision:
    """Turn Jev's answers into a Decision. The confidence is the least certain judgment the
    chosen action used; below the threshold, or with a required input missing, the decision is
    clarify with up to three alternatives (the top pick first). Raises DecideError for an
    answer outside the options."""
    try:
        top = answers["action"]
        raw = str(top["choice"])
        if raw not in actions:
            raise DecideError(f"action: {raw!r} is not an option")
        probabilities = {str(k): float(v) for k, v in top["probabilities"].items()}
        reader = Reader(answers, q)
        picked_args, missing = args(raw, reader)
        confidence = min([float(top["confidence"]), *reader.confidences])
        ranked = sorted(probabilities.items(), key=lambda kv: -kv[1])
        alternatives: list[Alternative] = []
        for action, p in ranked:
            if action == "clarify" or action not in actions or p < 0.05:
                continue
            alt_reader = Reader(answers, q)
            alt_args, alt_missing = args(action, alt_reader)
            if alt_missing is None and min(alt_reader.confidences, default=1.0) < threshold:
                alt_missing = "uncertain"  # a button must not carry the input that was in doubt
            alternatives.append(
                Alternative(action=action, args=alt_args, probability=p, missing=alt_missing)
            )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise DecideError(f"unexpected answer: {exc!r}") from exc
    if raw == "clarify" or missing is not None or confidence < threshold:
        return Decision(
            action="clarify",
            args=picked_args,  # partial when an input is missing: a question can complete it
            confidence=confidence,
            raw_action=raw,
            alternatives=alternatives[:3],
            missing=missing,
        )
    others = [a for a in alternatives if a.action != raw][:3]
    return Decision(
        action=raw, args=picked_args, confidence=confidence, raw_action=raw, alternatives=others
    )


def pseudonymised(body: dict[str, Any], pseudo: Pseudonymiser) -> dict[str, Any]:
    """The request with names replaced in the values that can carry them (the state, lists of
    strings item by item, and the option descriptions) and nowhere else, and every mobile
    number in the state replaced by "<number>" (events.mask_phones, no digit left) so no agent
    sends one out: question keys, option ids and instructions leave as they are. The shared
    pseudonymiser also takes words that start with a name (a "Per" takes "person"), so it never
    sees the whole body."""

    def clean(v: Any) -> Any:
        if isinstance(v, str):
            return pseudo.apply(mask_phones(v, keep_last=0))
        if isinstance(v, list):
            return [
                pseudo.apply(mask_phones(x, keep_last=0)) if isinstance(x, str) else x for x in v
            ]
        return v

    state = {k: clean(v) for k, v in body["state"].items()}
    questions = {
        qid: {**q, "criteria": {key: pseudo.apply(text) for key, text in q["criteria"].items()}}
        for qid, q in body["questions"].items()
    }
    return {**body, "state": state, "questions": questions}


async def decide(
    q: Any,
    *,
    build_request: Callable[[Any, str], dict[str, Any]],
    parse: Callable[[dict[str, Any]], Decision],
) -> Decision:
    """One Jev request for the query. Raises JevUnreachable when Jev cannot be reached, and
    JevError (DecideError for an answer outside the options) when no usable answer came."""
    try:
        ctx = current_context()
    except EgressBlocked as exc:
        raise JevError(str(exc)) from exc
    pseudo = await asyncio.to_thread(Pseudonymiser.for_branch, ctx.session, ctx.actor.branch_id)
    book = await asyncio.to_thread(_phrasebook, ctx.session, ctx.actor.branch_id, ctx.agent_id)
    version, taught, examples = book
    body = with_examples(build_request(q, get_settings().MIA_JEV_MODEL), examples)
    decision = parse(await jev.ask(pseudonymised(body, pseudo)))
    hinted = honour(decision, taught.get(key_of(str(getattr(q, "message", "")))))
    return hinted.model_copy(update={"phrasebook_version": version})


def _phrasebook(
    session: Any, branch_id: str, agent_id: str
) -> tuple[int, dict[str, str], dict[str, list[str]]]:
    """(the branch's version, message key to this agent's phrase action when that action only
    reads, examples per action from owner- or admin-taught phrases)."""
    from mia.chat import phrases  # chat imports the agents; the agents read chat lazily

    version, found = phrases.snapshot(session, branch_id)
    reads = phrases.reads(agent_id)
    picks = {p.key: p.action for p in found if p.agent_id == agent_id and p.action in reads}
    return version, picks, phrases.examples(found, agent_id)


def with_examples(body: dict[str, Any], examples: Mapping[str, list[str]]) -> dict[str, Any]:
    """The request with each action's taught examples (quoted message text, data: rule 8)
    appended to that action's option text: the `action` choice, or an `is_<action>` yes-or-no
    question's yes. Nothing else changes; an action with no example keeps its text."""
    if not examples:
        return body

    def said(action: str, text: str) -> str:
        found = examples.get(action)
        if not found:
            return text
        quoted = "; ".join(json.dumps(x, ensure_ascii=False) for x in found)
        return f"{text} Messages taught to mean this: {quoted}."

    questions = dict(body["questions"])
    if isinstance(action_q := questions.get("action"), dict):
        criteria = {k: said(k, v) for k, v in action_q["criteria"].items()}
        questions["action"] = {**action_q, "criteria": criteria}
    for qid, q in questions.items():
        if qid.startswith("is_") and "true" in q.get("criteria", {}):
            questions[qid] = {
                **q,
                "criteria": {**q["criteria"], "true": said(qid[3:], q["criteria"]["true"])},
            }
    return {**body, "questions": questions}


def honour(decision: Decision, taught: str | None) -> Decision:
    """The decision with the phrase's action for the message's key (a read: _phrasebook
    passes no other) taken when Jev was unsure: a clarify from Jev's own pick or a low
    confidence (never a guarded one, nor one with a missing input) whose alternatives include
    the action with no missing or uncertain input. Otherwise the decision unchanged."""
    if taught is None or decision.action != "clarify" or decision.missing is not None:
        return decision
    if decision.guarded:
        return decision
    if decision.raw_action != "clarify" and decision.confidence >= THRESHOLD:
        return decision  # an agent's guard asked: the phrase never bypasses it
    for alt in decision.alternatives:
        if alt.action == taught and alt.missing is None:
            return Decision(
                action=taught,
                args=alt.args,
                confidence=alt.probability,
                raw_action=decision.raw_action,
                alternatives=[a for a in decision.alternatives if a.action != taught],
            )
    return decision
