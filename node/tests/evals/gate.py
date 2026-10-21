"""The D40 gate bar, shared by the router and the agent decider eval harnesses, and the short
half's one rule (D42, no wrong write) with its shape checks, shared by the agent harnesses and
their shape tests."""

import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from functools import cache
from importlib import import_module
from pathlib import Path
from typing import Any

# Languages whose strings are machine drafts (Q28 to Q35); one leaves when its native review lands.
DRAFTED = frozenset({"ceb", "ilo", "hil", "war", "bcl", "pam", "pag"})
RIGHT_MIN = {"full": 0.80, "drafted": 0.65}
ASK_MAX = {"full": 0.15, "drafted": 0.30}


def _shortfalls(lang: str, v: dict[str, Any]) -> list[str]:
    tier = "drafted" if lang in DRAFTED else "full"
    out = []
    if v.get("wrong", 0.0) > 0.02:
        out.append(f"{lang} wrong {v['wrong']}")
    if v["right"] < RIGHT_MIN[tier]:
        out.append(f"{lang} right {v['right']}")
    if v["ask"] > ASK_MAX[tier]:
        out.append(f"{lang} ask {v['ask']}")
    return out


def gate_failures(gated: dict[str, Any]) -> list[str]:
    """The blocking bar (D41) on a fresh gate half: wrong at most 2% overall (hard) and, for
    every language that is not a machine draft (en, fi, fil), wrong at most 2%, right at least
    80% and ask at most 15%, greetings left out. Empty when the gate passes. The drafted
    languages are measured by gate_reported and never block until their native review lands."""
    failed = [f"wrong {gated['all']['wrong']}"] if gated["all"]["wrong"] > 0.02 else []
    for lang, v in gated["by_language"].items():
        if lang not in DRAFTED:
            failed.extend(_shortfalls(lang, v))
    return failed


def gate_reported(gated: dict[str, Any]) -> list[str]:
    """The D40 reading of the machine-drafted languages (wrong at most 2%, right at least 65%,
    ask at most 30%): reported in every gate report, never asserted (D41)."""
    reported = []
    for lang, v in gated["by_language"].items():
        if lang in DRAFTED:
            reported.extend(_shortfalls(lang, v))
    return reported


# The short half (D42): twelve short en and twelve short fil messages per agent in each agent's
# cases file (half "short"), as staff type on a phone. Expected "ask" for the two ambiguous ones.
ASK = "ask"
SHORT_LANGS = ("en", "fil")
EVALS = Path(__file__).parent
RESEARCH = EVALS.parents[2] / "docs" / "research"
ShortRow = tuple[str, str, str, str, int | None, int | None]  # lang text action item amount number


def actions(agent: str) -> dict[str, Any]:
    """The agent's offered actions (the retail ones for the shift supervisor at Ferino's)."""
    module = import_module(f"mia.agents.{agent}.actions")
    return dict(module.RETAIL_ACTIONS if agent == "shift_supervisor" else module.ACTIONS)


def writes(agent: str, action: str | None) -> bool:
    """True when the action's tool declares a write in the agent's manifest; "ask", clarify and
    the tool-less actions never write."""
    found = actions(agent).get(action or "")
    if found is None or found.tool is None:
        return False
    manifest = import_module(f"mia.agents.{agent}").MANIFEST
    return any(tool.name == found.tool and tool.writes for tool in manifest.tools)


def decided(r: dict[str, Any]) -> str | None:
    """The decided action of a result: "ask" for clarify or a missing input, None on an error."""
    if r.get("error") is not None:
        return None
    return ASK if r["action"] == "clarify" or r.get("missing") is not None else r["action"]


def wrong_writes(results: Iterable[dict[str, Any]], agent: str) -> list[dict[str, Any]]:
    """The short rows whose decided action writes a row and is not the expected one (D42): the
    short half's only assertion. Rows of the other halves are never counted."""
    return [
        r
        for r in results
        if r["half"] == "short"
        and (got := decided(r)) != r["expected_action"]
        and writes(agent, got)
    ]


def by_language(
    rows: Iterable[dict[str, Any]], row: Callable[[list[dict[str, Any]]], dict[str, Any]]
) -> dict[str, Any]:
    """A harness's own score row (`row`) per language of `rows`, the table a run prints."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[r["lang"]].append(r)
    return {lang: row(v) for lang, v in sorted(grouped.items())}


def _fold(text: str) -> str:
    return text.casefold().strip()


@cache
def _seed() -> tuple[frozenset[str], dict[str, frozenset[str]], frozenset[str]]:
    """The seeded codes and names, each item's codes by casefolded name, and the menu tokens."""
    from mia.agents.parsing import menu_tokens
    from mia.templates.retail.seed import INGREDIENTS, ITEMS

    named = {
        _fold(name): frozenset(map(_fold, codes)) for name, codes, *_ in [*ITEMS, *INGREDIENTS]
    }
    codes = frozenset(named) | frozenset(c for cs in named.values() for c in cs)
    menu = frozenset(menu_tokens((name, codes) for name, codes, _ in ITEMS))
    return codes, named, menu


def short_failures(agent: str, rows: list[ShortRow]) -> list[str]:
    """What is wrong with an agent's short half, empty when well formed: twelve rows per
    language (en and fil only) with two asks, one to six lowercase unpunctuated words, unique
    texts, an expected action the agent offers (or "ask"), an amount the agent's parser finds,
    an item that is seeded and typed (its code, or one of its seeded name's codes) and a number
    that is typed."""
    from mia.agents.bookkeeper import words
    from mia.agents.parsing import find_prices

    codes, named, menu = _seed()
    offered = actions(agent)
    out = []
    counts = Counter(lang for lang, *_ in rows)
    asks = Counter(lang for lang, _, action, *_ in rows if action == ASK)
    if counts != dict.fromkeys(SHORT_LANGS, 12) or asks != dict.fromkeys(SHORT_LANGS, 2):
        out.append(f"counts {dict(counts)}, asks {dict(asks)}")
    texts = [_fold(text) for _, text, *_ in rows]
    out += [f"repeated {t}" for t, n in Counter(texts).items() if n > 1]
    for lang, text, action, item, amount, number in rows:
        tokens = text.split()
        if not 1 <= len(tokens) < 7 or text != text.lower().strip():
            out.append(f"not short and lowercase: {text}")
        if set(text) & set(".,!?;:'\""):
            out.append(f"punctuated: {text}")
        if action != ASK and action not in offered:
            out.append(f"no action {action}: {text}")
        if amount is not None:
            if agent == "bookkeeper":
                found = set(words.amounts(text, lang).values())
            else:
                found = {a for _, a in find_prices(text, lang, menu)}
            if amount not in found:
                out.append(f"amount {amount} not in {found}: {text}")
        typed = named.get(_fold(item), frozenset({_fold(item)}))
        if item and not (_fold(item) in codes and typed & set(tokens)):
            out.append(f"item {item} not seeded and typed: {text}")
        if number is not None and str(number) not in tokens:
            out.append(f"number {number} not typed: {text}")
    return out


@cache
def _other_texts() -> frozenset[str]:
    """Every text of the other halves of every eval case file, of the intents dataset and of
    every raw run file but its short rows."""
    found: set[str] = set()
    for path in EVALS.glob("*_cases.py"):
        if not path.stem.startswith("test_"):
            module = import_module(f"tests.evals.{path.stem}")
            found |= {_fold(c.text) for c in module.CASES if getattr(c, "half", "") != "short"}
    for line in (EVALS / "intents.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            found.add(_fold(json.loads(line)["text"]))
    for path in RESEARCH.glob("*.raw.json"):
        rows = json.loads(path.read_text(encoding="utf-8")).get("results", [])
        found |= {
            _fold(r["text"])
            for r in rows
            if isinstance(r, dict) and "text" in r and r.get("half") != "short"
        }
    return frozenset(found)


def short_reused(texts: Iterable[str]) -> list[str]:
    """The short texts that are also in another half, the intents dataset or a raw file."""
    return sorted({_fold(t) for t in texts} & _other_texts())
