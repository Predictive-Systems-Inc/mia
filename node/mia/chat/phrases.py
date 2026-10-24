"""The phrasebook: message keys Mia learned to mean one agent's action (spec
2026-10-22-teach-mia-design, phase 1). Event-sourced like route_memory, no table: a tester's
pick on the phones page writes `phrase.taught`, a tap on an agent's "Did you mean" writes
`phrase.confirmed`, `phrase.retired` withdraws a key. The phrasebook is the fold of those
events at the branch and its version is their count there. Only teachable actions (a tool whose
risk is not money, external or delete) are ever learned, and a phrase picks the action for the
decider only when that action reads (writes keep their question). Only phrases an owner or
admin taught become examples in the decider's option text; tapped phrases never do. Keys are
route_memory.key_of and need a letter (a bare number is never a phrase); the text is data
(rule 8).
"""

import csv
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from mia.agents.decider import Action
from mia.agents.sales_supervisor import MANIFEST as SALES
from mia.chat.route_memory import key_of
from mia.core import events
from mia.core.models import Actor, Event, Message, Thread
from mia.i18n import t

TAUGHT = "phrase.taught"
RETIRED = "phrase.retired"
CONFIRMED = "phrase.confirmed"
# Saved report forms (teach-Mia 4c): a report question's form, never its figures, kept for its
# message key and run again with no model request; folded here beside the phrases.
REPORT_SAVED = "report.saved"
REPORT_RETIRED = "report.retired"
REPORTS = (REPORT_SAVED, REPORT_RETIRED)
REPORT_AGENT = SALES.id  # the one agent with a report form today
REPORTS_CSV = "sales_supervisor_reports.csv"  # the saved reports as rows (text, key, form)
ALL = (TAUGHT, RETIRED, CONFIRMED, *REPORTS)
UNTEACHABLE = frozenset({"money", "external", "delete"})
EXAMPLES = 3  # taught examples per action in the decider's option text
EXAMPLE_ROLES = frozenset({"owner", "admin"})  # whose taught phrases become examples
EXAMPLE_CHARS = 60  # a longer phrase is never an example (the short-half shape)
_LETTER = re.compile(r"[^\W\d_]")


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


def reads(agent_id: str) -> set[str]:
    """The agent's teachable actions whose tool only reads: the ones a phrase may pick for
    the decider."""
    from mia.agents.registry import AGENTS

    spec = AGENTS.get(agent_id)
    if spec is None:
        return set()
    # a read tool that still declares writes (hr_officer's resend_payslip sends a message) is
    # not a pure read, so a phrase never picks it
    pure = {t.name for t in spec.manifest.tools if t.risk == "read" and not t.writes}
    return {name for name, a in teachable(agent_id).items() if str(a.tool) in pure}


def has_letter(key: str) -> bool:
    """True when the key has a letter: "#" (a bare number) or "?" is never a phrase."""
    return bool(_LETTER.search(key))


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
    roles: tuple[str, ...] = ()  # the teacher's roles (taught phrases)


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


def version(session: Session, branch_id: str) -> int:
    """The branch's phrasebook version: how many phrase events apply to it (append-only, so it
    only grows)."""
    return len(_events(session, branch_id))


def snapshot(session: Session, branch_id: str) -> tuple[int, list[Phrase]]:
    """(version, entries) for the branch from one read of its phrase events."""
    found = _events(session, branch_id)
    return len(found), _fold(found, branch_id)


def entries(session: Session, branch_id: str) -> list[Phrase]:
    """The branch's live phrases: a taught key (latest teach, not retired since), else a key
    whose taps since its last retirement lead one teachable (agent, action) by at least one
    and whose latest tap agrees. Reads only."""
    return snapshot(session, branch_id)[1]


def _fold(found: Sequence[Event], branch_id: str) -> list[Phrase]:
    # ponytail: a scan of every phrase event per turn; index or cache past thousands of them.
    keys: dict[str, _Key] = {}
    for ev in found:
        a = ev.after or {}
        key = str(a.get("key", ""))
        if not has_letter(key) or ev.action in REPORTS:  # a bare-number key is never a phrase
            continue
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
                    roles=tuple(a.get("roles") or ([a["role"]] if a.get("role") else [])),
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
    v, found = snapshot(session, branch_id)
    return v, {p.key: (p.agent_id, p.action) for p in found}


def examples(found: Sequence[Phrase], agent_id: str) -> dict[str, list[str]]:
    """Up to EXAMPLES texts per action of the agent, newest first, only from phrases taught
    by an owner or admin and at most EXAMPLE_CHARS long (a tapped phrase is never one)."""
    out: dict[str, list[str]] = {}
    for p in reversed(found):
        if not (p.taught and EXAMPLE_ROLES & set(p.roles) and len(p.text) <= EXAMPLE_CHARS):
            continue
        if p.agent_id == agent_id and len(out.setdefault(p.action, [])) < EXAMPLES:
            out[p.action].append(p.text)
    return {k: v for k, v in out.items() if v}


def teach(
    session: Session,
    actor: Actor,
    branch_id: str | None,
    text: str,
    agent_id: str,
    action: str,
    *,
    lang: str = "en",
    roles: Sequence[str] = (),
) -> Event:
    """Emits phrase.taught for the key of `text` at the branch (None: every branch) and
    commits; `roles` are the teacher's. Raises TeachError for an action that is not one of the
    agent's teachable actions (an unknown one, or one whose tool risks money, external or
    delete) and for a text with no letter."""
    if action not in actions_of(agent_id):
        raise TeachError(f"{agent_id} has no action {action}")
    if action not in teachable(agent_id):
        raise TeachError(f"{agent_id}.{action} cannot be taught")
    key = key_of(text)
    if not has_letter(key):
        raise TeachError("a phrase needs a word, not only numbers")
    after = {
        "key": key,
        "text": text.strip(),
        "agent_id": agent_id,
        "action": action,
        "branch_id": branch_id,
        "lang": lang,
        "roles": list(roles),
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
    of Something else, of another question, with no message before it, or for a message with
    no letter (a bare number) writes nothing."""
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
    if original is None or not has_letter(key_of(original.text)):
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


def _saved(found: Sequence[Event]) -> dict[str, dict[str, Any]]:
    """The live saved reports by key from report events oldest first: the latest
    report.saved of a key unless a report.retired came after it."""
    out: dict[str, dict[str, Any]] = {}
    for ev in found:
        a = ev.after or {}
        if ev.action == REPORT_RETIRED:
            out.pop(str(a.get("key")), None)
        elif ev.action == REPORT_SAVED:
            out[str(a.get("key"))] = a
    return out


def saved_reports(session: Session, branch_id: str) -> dict[str, dict[str, Any]]:
    """The branch's live saved reports, key to the report.saved payload (key, text, form,
    agent_id, branch_id). Reads only."""
    return _saved(_events(session, branch_id))


def saved_report(session: Session, branch_id: str, key: str) -> dict[str, Any] | None:
    """The live saved form for the message key at the branch, or None. Reads only."""
    found = saved_reports(session, branch_id).get(key)
    return dict(found["form"]) if found else None


def _emit_saved(
    session: Session, actor: Actor, branch_id: str | None, text: str, form: dict[str, Any],
    message_id: str | None = None,
) -> Event:  # fmt: skip
    key = key_of(text)
    if not has_letter(key):
        raise TeachError("a saved report needs a word, not only numbers")
    after = {
        "key": key,
        "text": text.strip(),
        "agent_id": REPORT_AGENT,
        "form": form,
        "branch_id": branch_id,
        "message_id": message_id,
        "person_id": actor.person_id,
    }
    return events.emit(session, REPORT_SAVED, ("report", key), None, after, actor)


def save_report(
    session: Session, actor: Actor, branch_id: str, message: Message, form: dict[str, Any]
) -> Event:
    """Emits report.saved (in the caller's transaction) for the key of the message at the
    branch with the answered form. Raises TeachError for a key with no letter."""
    return _emit_saved(session, actor, branch_id, message.text, form, message.id)


def retire_report(session: Session, actor: Actor, branch_id: str | None, key: str) -> Event:
    """Emits report.retired for the key at the branch (None: every branch) and commits."""
    after = {"key": key_of(key), "branch_id": branch_id}
    ev = events.emit(session, REPORT_RETIRED, ("report", key_of(key)), None, after, actor)
    session.commit()
    return ev


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


def _export_reports(session: Session, folder: Path) -> int:
    """Appends each live saved report of every branch to <folder>/REPORTS_CSV (text, key,
    form as JSON; the header written when the file is new) unless its key is there."""
    from mia.core.models import Branch

    path = folder / REPORTS_CSV
    present: set[str] = set()
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            present = {r["key"] for r in csv.DictReader(f)}
    rows = []
    for branch_id in session.exec(select(Branch.id).order_by(col(Branch.id))):
        for key, a in saved_reports(session, branch_id).items():
            if key not in present:
                present.add(key)
                rows.append({"text": a.get("text", key), "key": key, "form": json.dumps(a["form"])})
    if rows or not path.exists():
        new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, ["text", "key", "form"], lineterminator="\n")
            if new:
                writer.writeheader()
            writer.writerows(rows)
    return len(rows)


def _import_reports(session: Session, folder: Path, branch_id: str, every: bool) -> int:
    """Replays each row of <folder>/REPORTS_CSV as report.saved by the system actor unless
    that key's form is saved at the branch already."""
    path = folder / REPORTS_CSV
    if not path.exists():
        return 0
    live = saved_reports(session, branch_id)
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    added = 0
    for r in rows:
        form = json.loads(r["form"])
        if live.get(key_of(r["text"]), {}).get("form") == form:
            continue
        _emit_saved(session, Actor.system(branch_id), None if every else branch_id, r["text"], form)
        live[key_of(r["text"])] = {"form": form}
        added += 1
    session.commit()
    return added


def export_rows(session: Session, folder: Path) -> int:
    """Appends each taught phrase as a short-half row of <folder>/<agent>.csv (intent the
    action, lang the teacher's, extra {"scenario": "taught", "taught": true}) unless a row
    with that intent and message is there; the header is kept; and each saved report to
    <folder>/REPORTS_CSV. Returns the rows added."""
    added = _export_reports(session, folder)
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
               "role": p.roles[0] if p.roles else "", "extra": extra}  # fmt: skip
        with path.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, header, lineterminator="\n").writerow(
                {k: row.get(k, "") for k in header}
            )
        added += 1
    return added


def import_rows(session: Session, folder: Path, branch_id: str, *, every: bool = False) -> int:
    """Replays every row of <folder>/<agent>.csv whose extra says "taught": true as a
    phrase.taught at the branch (every branch with every=True) by the system actor, the row's
    role as the teacher's, skipping phrases already taught there; then the saved reports of
    <folder>/REPORTS_CSV as report.saved. Returns how many were taught or saved."""
    live = {(p.key, p.agent_id, p.action) for p in entries(session, branch_id) if p.taught}
    actor = Actor.system(branch_id)
    taught = 0
    for path in sorted(folder.glob("*.csv")):
        if path.name == REPORTS_CSV:
            continue
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            extra = json.loads(r.get("extra") or "{}")
            if not (isinstance(extra, dict) and extra.get("taught") is True):
                continue
            if (key_of(r["message"]), path.stem, r["intent"]) in live:
                continue
            role = [r["role"]] if r.get("role") else []
            teach(session, actor, None if every else branch_id, r["message"], path.stem,
                  r["intent"], lang=r.get("lang") or "en", roles=role)  # fmt: skip
            live.add((key_of(r["message"]), path.stem, r["intent"]))
            taught += 1
    return taught + _import_reports(session, folder, branch_id, every)
