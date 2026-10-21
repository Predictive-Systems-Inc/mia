"""The short-message set is well formed (offline; the real-Jev run is test_short_evals.py)."""

import asyncio
import json
from collections import Counter
from importlib import import_module
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from mia.agents.bookkeeper import words
from mia.agents.parsing import find_prices, menu_tokens
from mia.templates.retail.seed import INGREDIENTS, ITEMS
from tests.conftest import Shop
from tests.evals.short_cases import AGENTS, ASK, CASES, LANGS, actions, writes
from tests.evals.test_short_evals import _outcome, _query

EVALS = Path(__file__).parent
RESEARCH = EVALS.parents[2] / "docs" / "research"
CODES = {c.casefold() for name, codes, *_ in [*ITEMS, *INGREDIENTS] for c in [name, *codes]}
MENU = menu_tokens((name, codes) for name, codes, _ in ITEMS)


def _fold(text: str) -> str:
    return text.casefold().strip()


def _other_texts() -> set[str]:
    """Every text of the other case files, the intents dataset and the raw run files."""
    found = set()
    for path in EVALS.glob("*_cases.py"):
        if path.stem != "short_cases" and not path.stem.startswith("test_"):
            module = import_module(f"tests.evals.{path.stem}")
            found |= {_fold(c.text) for c in module.CASES}
    for line in (EVALS / "intents.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            found.add(_fold(json.loads(line)["text"]))
    for path in RESEARCH.glob("*.raw.json"):
        rows = json.loads(path.read_text(encoding="utf-8")).get("results", [])
        found |= {_fold(r["text"]) for r in rows if isinstance(r, dict) and "text" in r}
    return found


def test_twelve_per_agent_per_language() -> None:
    counts = Counter((c.agent, c.lang) for c in CASES)
    assert counts == {(a, lang): 12 for a in AGENTS for lang in LANGS}


def test_two_asks_per_agent_per_language() -> None:
    counts = Counter((c.agent, c.lang) for c in CASES if c.expected_action == ASK)
    assert counts == {(a, lang): 2 for a in AGENTS for lang in LANGS}


def test_expected_actions_exist_and_writes_match_the_manifest() -> None:
    for c in CASES:
        assert c.expected_action == ASK or c.expected_action in actions(c.agent), c
        assert c.writes == writes(c.agent, c.expected_action), c


def test_texts_are_short_lowercase_and_unpunctuated() -> None:
    for c in CASES:
        assert 1 <= len(c.text.split()) < 7, c.text
        assert c.text == c.text.lower().strip(), c.text
        assert not set(c.text) & set(".,!?;:'\""), c.text


def test_texts_are_unique_and_new() -> None:
    texts = [_fold(c.text) for c in CASES]
    assert len(texts) == len(set(texts)), Counter(texts).most_common(3)
    reused = set(texts) & _other_texts()
    assert not reused, sorted(reused)


def test_roles_are_seeded() -> None:
    allowed = {"owner", "supervisor", "clerk", "staff"}
    for c in CASES:
        assert c.role in (allowed | {"customer"} if c.agent == "customer_service" else allowed)


def test_expected_args_parse() -> None:
    """An amount is found by the agent's parser, an item code is a seeded item or ingredient
    and is typed in the text, a number is typed in the text."""
    for c in CASES:
        tokens = c.text.split()
        if c.amount is not None:
            if c.agent == "bookkeeper":
                found = set(words.amounts(c.text, c.lang).values())
            else:
                found = {a for _, a in find_prices(c.text, c.lang, MENU)}
            assert c.amount in found, (c.text, found)
        if c.item:
            assert c.item in CODES and c.item in tokens, c
        if c.number is not None:
            assert str(c.number) in tokens, c


def test_every_case_builds_its_query(engine: Engine, pp_shop: Shop) -> None:
    """The harness's sender and query for every case, offline (no Jev request)."""

    async def run() -> None:
        for c in CASES:
            with Session(engine) as session:
                query, _, organisation_id = await _query(session, c, pp_shop.people)
                assert query.message and organisation_id, c  # staff side scrubs customer names

    asyncio.run(run())


def test_a_wrong_write_is_a_writing_action_other_than_the_expected() -> None:
    row = {"error": None, "agent": "bookkeeper", "expected_action": ASK, "missing": None}
    assert _outcome(row | {"action": "cash_count"}) == ("wrong", "cash_count", True)
    assert _outcome(row | {"action": "balances"}) == ("wrong", "balances", False)
    assert _outcome(row | {"action": "clarify"}) == ("right", ASK, False)
    asked = row | {"expected_action": "cash_count", "action": "cash_count", "missing": "amount"}
    assert _outcome(asked) == ("ask", ASK, False)
