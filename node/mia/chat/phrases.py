"""The phrasebook: message keys Mia learned to mean one agent's action (spec
2026-10-22-teach-mia-design, phase 1). Event-sourced like route_memory, no table: a tester's
pick on the phones page writes `phrase.taught`, a tap on an agent's "Did you mean" writes
`phrase.confirmed`, `phrase.retired` withdraws a key. The phrasebook is the fold of those
events and its version is their count. Only teachable actions (a tool whose risk is not money,
external or delete) are ever learned. Keys are route_memory.key_of; the text is data (rule 8).
"""

import csv
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path

from sqlmodel import Session, col, func, select

from mia.agents.decider import Action
from mia.chat.route_memory import key_of
from mia.core import events
from mia.core.models import Actor, Event, Message, Thread
from mia.i18n import t

TAUGHT = "phrase.taught"
RETIRED = "phrase.retired"
CONFIRMED = "phrase.confirmed"
ALL = (TAUGHT, RETIRED, CONFIRMED)
UNTEACHABLE = frozenset({"money", "external", "delete"})
EXAMPLES = 3  # taught examples per action in the decider's option text


class TeachError(ValueError):
    """The target is not a teachable action of the agent."""


def actions_of(agent_id: str) -> dict[str, Action]:
    """The agent's decider actions (the shift supervisor's for the organisation's template);
    empty for an agent without a decider."""
    try:
        module = import_module(f"mia.agents.{agent_id}.actions")
    except ModuleNotFoundError:
        return {}
    found = module.actions_for() if hasattr(module, "actions_for") else module.ACTIONS
    return dict(found)


def teachable(agent_id: str) -> dict[str, Action]:
    """The agent's actions a phrase may name: offered as a button (a label), run by a tool,
    and that tool's risk is not money, external or delete (manifest tool rows)."""
    from mia.agents.registry import AGENTS  # the registry imports the agents, which import chat

    spec = AGENTS.get(agent_id)
    if spec is None:
        return {}
    risks = {tool.name: tool.risk for tool in spec.manifest.tools}
    return {
        name: a
        for name, a in actions_of(agent_id).items()
        if a.label_key and a.tool and risks.get(a.tool, "money") not in UNTEACHABLE
    }


@dataclass
class Phrase:
    """One key of a branch's phrasebook: taught (outranks taps) or learned from taps."""

    key: str
    agent_id: str
    action: str
    text: str
    taught: bool
    branch_id: str | None  # None: every branch
    confidence: int = 0  # taps for this (agent, action) minus taps for any other
    taps: int = 0
    lang: str = "en"
    role: str = ""


@dataclass
class _Key:
    taught: Event | None = None
    taps: list[tuple[str, str]] = field(default_factory=list)


def _events(session: Session, branch_id: str) -> Sequence[Event]:
    """The phrase events that apply to the branch, oldest first: confirmations at the branch,
    teaches and retirements at the branch or at every branch."""
    rows = session.exec(
        select(Event).where(col(Event.action).in_(ALL)).order_by(col(Event.id))
    ).all()
    out = []
    for ev in rows:
        scope = (ev.after or {}).get("branch_id", ev.branch_id)
        here = ev.branch_id == branch_id if ev.action == CONFIRMED else scope in (None, branch_id)
        if here:
            out.append(ev)
    return out


def version(session: Session) -> int:
    """The phrasebook version: how many phrase events the node has (append-only, so it only
    grows)."""
    return int(session.exec(select(func.count()).where(col(Event.action).in_(ALL))).one())


def entries(session: Session, branch_id: str) -> list[Phrase]:
    """The branch's live phrases: a taught key (latest teach, not retired since), else a key
    whose taps since its last retirement lead one teachable (agent, action) by at least one
    and whose latest tap agrees. Reads only."""
    # ponytail: a scan of every phrase event per call; index or cache past thousands of them.
    keys: dict[str, _Key] = {}
    for ev in _events(session, branch_id):
        a = ev.after or {}
        key = str(a.get("key", ""))
        if ev.action == RETIRED:
            keys.pop(key, None)
        elif ev.action == TAUGHT:
            keys.setdefault(key, _Key()).taught = ev
        else:
            keys.setdefault(key, _Key()).taps.append((str(a["agent_id"]), str(a["action"])))
    out: list[Phrase] = []
    for key, k in keys.items():
        if k.taught is not None:
            a = k.taught.after or {}
            pair = (str(a["agent_id"]), str(a["action"]))
            out.append(
                Phrase(
                    key,
                    *pair,
                    text=str(a.get("text", key)),
                    taught=True,
                    branch_id=a.get("branch_id"),
                    confidence=k.taps.count(pair) + 1,
                    taps=len(k.taps),
                    lang=str(a.get("lang", "en")),
                    role=str(a.get("role", "")),
                )
            )
            continue
        if not k.taps:
            continue
        counts = Counter(k.taps)
        (lead, n), *_ = counts.most_common(1)
        confidence = n - (len(k.taps) - n)
        if confidence >= 1 and k.taps[-1] == lead and lead[1] in teachable(lead[0]):
            out.append(
                Phrase(key, *lead, text=key, taught=False, branch_id=branch_id,
                       confidence=confidence, taps=len(k.taps))
            )  # fmt: skip
    return out


def phrasebook(session: Session, branch_id: str) -> tuple[int, dict[str, tuple[str, str]]]:
    """(version, key to (agent id, action)) for the branch. Reads only."""
    return version(session), {p.key: (p.agent_id, p.action) for p in entries(session, branch_id)}


def examples(session: Session, branch_id: str, agent_id: str) -> dict[str, list[str]]:
    """Up to EXAMPLES phrase texts per action of the agent at the branch, newest first."""
    out: dict[str, list[str]] = {}
    for p in reversed(entries(session, branch_id)):
        if p.agent_id == agent_id and len(out.setdefault(p.action, [])) < EXAMPLES:
            out[p.action].append(p.text)
    return out


def teach(
    session: Session,
    actor: Actor,
    branch_id: str | None,
    text: str,
    agent_id: str,
    action: str,
    *,
    lang: str = "en",
    role: str = "",
) -> Event:
    """Emits phrase.taught for the key of `text` at the branch (None: every branch) and
    commits. Raises TeachError for an action that is not one of the agent's teachable
    actions (an unknown one, or one whose tool risks money, external or delete)."""
    if action not in actions_of(agent_id):
        raise TeachError(f"{agent_id} has no action {action}")
    if action not in teachable(agent_id):
        raise TeachError(f"{agent_id}.{action} cannot be taught")
    key = key_of(text)
    if not key:
        raise TeachError("empty text")
    after = {
        "key": key,
        "text": text.strip(),
        "agent_id": agent_id,
        "action": action,
        "branch_id": branch_id,
        "lang": lang,
        "role": role,
    }
    ev = events.emit(session, TAUGHT, ("phrase", key), None, after, actor)
    session.commit()
    return ev


def retire(session: Session, actor: Actor, branch_id: str | None, text: str) -> Event:
    """Emits phrase.retired for the key of `text` (a message or a printed key) at the branch
    (None: every branch) and commits: the teach and the taps before it stop counting."""
    key = key_of(text)
    after = {"key": key, "branch_id": branch_id}
    ev = events.emit(session, RETIRED, ("phrase", key), None, after, actor)
    session.commit()
    return ev


def confirm_tap(
    session: Session, actor: Actor, thread: Thread, question: Message, text: str
) -> None:
    """Emits phrase.confirmed (in the caller's transaction) when `text` taps an action of the
    agent's "Did you mean" (a decision.clarify_asked whose options include Something else)
    that is the thread's `question`; the key is that of the user message it asked about. A tap
    of Something else, of another question, or with no message before it writes nothing."""
    asked = session.exec(
        select(Event)
        .where(Event.action == "decision.clarify_asked")
        .where(Event.entity_id == thread.id)
        .order_by(col(Event.id).desc())
    ).first()
    after = (asked.after or {}) if asked is not None else {}
    options = after.get("options") or {}
    if after.get("message_id") != question.id or not isinstance(options, dict):
        return
    if not any(label in options for label in _something_else()):
        return
    chosen = options.get(text.strip())
    action = chosen.get("action") if isinstance(chosen, dict) else None
    if not action or action == "clarify" or question.agent_id is None:
        return
    original = session.exec(
        select(Message)
        .where(Message.thread_id == thread.id)
        .where(Message.role == "user")
        .where(col(Message.id) < question.id)
        .order_by(col(Message.id).desc())
    ).first()
    if original is None or not key_of(original.text):
        return
    key = key_of(original.text)
    confirmed = {
        "key": key,
        "agent_id": question.agent_id,
        "action": str(action),
        "message_id": original.id,
        "person_id": actor.person_id,
    }
    events.emit(session, CONFIRMED, ("phrase", key), None, confirmed, actor)


def _something_else() -> set[str]:
    from mia.i18n import SUPPORTED

    return {t("clarify.something_else", lang) for lang in SUPPORTED}


# ---- version control: phrases as eval rows (spec section 6) --------------------------------

CASE_LANGS = ("en", "fil", "fi")  # the eval CSVs' languages (tests/evals/cases/__init__.py)


def _taught_phrases(session: Session) -> list[Phrase]:
    """Every live taught phrase of every branch, each (key, agent, action) once."""
    from mia.core.models import Branch

    seen: set[tuple[str, str, str]] = set()
    out = []
    for branch_id in session.exec(select(Branch.id).order_by(col(Branch.id))):
        for p in entries(session, branch_id):
            if p.taught and (p.key, p.agent_id, p.action) not in seen:
                seen.add((p.key, p.agent_id, p.action))
                out.append(p)
    return out


def export_rows(session: Session, folder: Path) -> int:
    """Appends each taught phrase as a short-half row of <folder>/<agent>.csv (intent the
    action, lang the teacher's, extra {"scenario": "taught", "taught": true}) unless a row
    with that intent and message is there; the header is kept. Returns the rows added."""
    added = 0
    for p in _taught_phrases(session):
        path = folder / f"{p.agent_id}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or [])
            present = {(r["intent"], r["message"]) for r in reader}
        if (p.action, p.text) in present:
            continue
        # ponytail: a regional teacher's row is filed as fil (the CSVs hold en, fil and fi).
        lang = p.lang if p.lang in CASE_LANGS else "fil"
        extra = json.dumps({"scenario": "taught", "taught": True})
        row = {"intent": p.action, "message": p.text, "lang": lang, "half": "short",
               "role": p.role, "extra": extra}  # fmt: skip
        with path.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, header, lineterminator="\n").writerow(
                {k: row.get(k, "") for k in header}
            )
        added += 1
    return added


def import_rows(session: Session, folder: Path, branch_id: str) -> int:
    """Replays every row of <folder>/<agent>.csv whose extra says "taught": true as a
    phrase.taught for every branch by the system actor (branch_id is the actor's), skipping
    phrases already taught. Returns how many were taught."""
    live = {(p.key, p.agent_id, p.action) for p in entries(session, branch_id) if p.taught}
    actor = Actor.system(branch_id)
    taught = 0
    for path in sorted(folder.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            extra = json.loads(r.get("extra") or "{}")
            if not (isinstance(extra, dict) and extra.get("taught") is True):
                continue
            if (key_of(r["message"]), path.stem, r["intent"]) in live:
                continue
            teach(session, actor, None, r["message"], path.stem, r["intent"],
                  lang=r.get("lang") or "en", role=r.get("role") or "")  # fmt: skip
            live.add((key_of(r["message"]), path.stem, r["intent"]))
            taught += 1
    return taught
