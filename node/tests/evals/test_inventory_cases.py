"""The inventory manager eval set is well formed (offline; the real-Jev run is
test_inventory_manager_evals.py)."""

import json
from collections import Counter
from pathlib import Path

from mia.agents.inventory_manager.actions import ACTIONS
from mia.agents.parsing import menu_tokens, pre_parse, strip_times
from mia.templates.retail.seed import INGREDIENTS, ITEMS
from tests.evals import gate
from tests.evals.cases import HEADER, header, read
from tests.evals.inventory_manager_cases import CASES, FRESH, GATED_LANGS, SCENARIOS, SYNONYMS

ROWS = [(name, codes) for name, codes, *_ in ITEMS] + [(n, c) for n, c, *_ in INGREDIENTS]
NAMES = {name for name, _ in ROWS}
COUNTED = ("report_stock", "place_order", "receive")
RESEARCH = Path(__file__).parents[3] / "docs" / "research"
LONG = [c for c in CASES if c.half != "short"]
SHORT = [c for c in CASES if c.half == "short"]


def _texts(half: str) -> set[str]:
    return {c.text.casefold().strip() for c in CASES if c.half == half}


def test_five_fresh_cases_per_language_scenario_and_half_and_twenty_spent() -> None:
    fresh = Counter((c.lang, c.scenario, c.half) for c in LONG if c.half != "spent")
    assert set(fresh) == {
        (lang, s, h) for lang in GATED_LANGS for s in FRESH for h in ("tune", "gate")
    }
    assert set(fresh.values()) == {5}
    spent = Counter((c.lang, c.scenario) for c in CASES if c.half == "spent")
    assert set(spent) == {(lang, s) for lang in GATED_LANGS for s in SCENARIOS}
    assert set(spent.values()) == {20}


def test_no_text_appears_in_both_halves() -> None:
    """The fresh tune and gate halves share no text, and neither shares one with a spent row."""
    tune, gate, spent = _texts("tune"), _texts("gate"), _texts("spent")
    assert not tune & gate, tune & gate
    assert not (tune | gate) & spent, (tune | gate) & spent


def test_no_fresh_text_was_ever_scored() -> None:
    """No fresh text is in any earlier inventory manager run (the spent raw files, named)."""
    # The spent runs, named (a later run's file scores the fresh rows).
    raws = [
        RESEARCH / f"inventory-manager-2026-10-19-{t}.raw.json"
        for t in ("0554", "0558", "0653", "0656")
    ]
    assert raws
    scored = {
        r["text"].casefold().strip()
        for path in raws
        for r in json.loads(path.read_text(encoding="utf-8"))["results"]
    }
    fresh = _texts("tune") | _texts("gate")
    assert not fresh & scored, fresh & scored


def test_the_halves_are_selected_by_name_and_the_spent_half_never() -> None:
    from tests.evals.test_inventory_manager_evals import _selected

    assert {c.half for c in _selected(CASES, "tune")} == {"tune"}
    assert {c.half for c in _selected(CASES, "gate")} == {"gate"}
    assert not any(c.half == "spent" for c in _selected(CASES, "tune,gate,spent"))
    assert {c.half for c in _selected(CASES, "short")} == {"short"}


def test_no_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_expected_actions_kinds_and_names() -> None:
    for c in LONG:
        assert c.expected_action in ACTIONS, c
        assert bool(c.expected_items) == (c.expected_action in COUNTED), c
        assert bool(c.expected_kind) == (c.expected_action == "report_stock"), c
        assert {name for name, _ in c.expected_items} <= NAMES, c


def test_counts_parse_to_the_expected_groups() -> None:
    """Code splits the numbers (rule 7): a counted case gives one group per expected pair, in
    order, with its quantity and a word of that item; a pair without a quantity is a message
    with no number (Jev's `item` question), so exactly one pair and no group."""
    tokens = menu_tokens(ROWS)
    words = {name: menu_tokens([(name, codes)]) | SYNONYMS.get(name, set()) for name, codes in ROWS}
    for c in CASES:
        if c.expected_action not in COUNTED:
            continue
        groups, _ = pre_parse(strip_times(c.text), tokens)  # as build_query
        if c.expected_items[0][1] is None:
            assert len(c.expected_items) == 1 and not groups, (c, groups)
            continue
        assert len(groups) == len(c.expected_items), (c, groups)
        for group, (name, quantity) in zip(groups, c.expected_items, strict=True):
            assert group.quantity == quantity, (c, group)
            assert words[name] & set(group.words.split()), (c, group)


def test_scoring() -> None:
    """The harness scoring offline: a waste without a reason is right when Mia asks it, a
    guessed reason or another item is a wrong write, a sure other action is wrong."""
    from tests.evals.test_inventory_manager_evals import _score

    base = {"error": None, "expected_action": "report_stock", "expected_kind": "waste"}
    base |= {"expected_items": [("Ube", 4)], "expected_missing": "reason", "confidence": 0.9}
    asked = base | {"action": "clarify", "raw_action": "report_stock", "missing": "reason"}
    asked |= {"found_kind": "waste", "found_items": [("Ube", 4)]}
    assert _score(asked) == "right"
    assert _score(asked | {"confidence": 0.5}) == "ask"
    assert _score(asked | {"action": "report_stock", "missing": None}) == "wrong_items"
    assert _score(asked | {"found_items": [("Classic", 4)]}) == "wrong_items"
    assert _score(asked | {"missing": "item_0"}) == "ask"
    other = asked | {"action": "place_order", "raw_action": "place_order", "missing": None}
    assert _score(other) == "wrong"
    assert _score(asked | {"error": "boom"}) == "other"
    # a waste with no number: right when Mia asks how many
    many = asked | {"expected_items": [("Ube", None)], "expected_missing": "quantity"}
    many |= {"missing": "quantity", "found_items": [("Ube", None)]}
    assert _score(many) == "right"
    assert _score(many | {"action": "report_stock", "missing": None}) == "wrong_items"


def test_on_hand_is_found_and_scored() -> None:
    """A how-many-left question: the on_hand event is found as kind on_hand with no quantity."""
    from tests.evals.test_inventory_manager_evals import _found, _score

    args = {"kind": "count", "item_id": "u", "ingredient_id": None, "quantity": None}
    kind, items = _found(args | {"on_hand": True}, {"u": "Ube"})
    assert (kind, items) == ("on_hand", [("Ube", None)])
    r = {"error": None, "expected_action": "report_stock", "expected_kind": "on_hand"}
    r |= {"expected_items": [("Ube", None)], "expected_missing": None, "confidence": 0.9}
    r |= {"action": "report_stock", "raw_action": "report_stock", "missing": None}
    assert _score(r | {"found_kind": kind, "found_items": items}) == "right"
    assert _score(r | {"found_kind": "low", "found_items": items}) == "wrong_items"


def test_the_short_half_is_short_and_new() -> None:
    """D42: twelve en and twelve fil, two asks each, short and unpunctuated, an offered action,
    the first expected item seeded and typed with its count, no text in another half or a raw
    file (test_counts_parse_to_the_expected_groups reads every pair)."""
    first = [c.expected_items[0] if c.expected_items else ("", None) for c in SHORT]
    rows = [
        (c.lang, c.text, c.expected_action, i, None, n)
        for c, (i, n) in zip(SHORT, first, strict=True)
    ]
    assert not gate.short_failures("inventory_manager", rows)
    assert not gate.short_reused(c.text for c in SHORT)
    assert {name for c in SHORT for name, _ in c.expected_items} <= NAMES


def test_the_csv_has_the_shared_header_and_every_row_parses() -> None:
    assert header("inventory_manager") == HEADER and len(read("inventory_manager")) == len(CASES)


def test_an_on_hand_read_is_not_a_wrong_write() -> None:
    """report_stock marked on_hand runs the on_hand read and writes nothing ("ilan pa ube",
    expected ask): never a wrong write. The same action unmarked is one."""
    from tests.evals.test_inventory_manager_evals import _wrong_writes

    r = {"half": "short", "error": None, "missing": None, "expected_action": "ask"}
    r |= {"action": "report_stock", "score": "wrong"}
    event = {"kind": "count", "item_id": "u", "quantity": None}
    assert not _wrong_writes([r | {"args": event | {"on_hand": True}}])
    assert _wrong_writes([r | {"args": {"events": [event | {"quantity": 3}]}}])
