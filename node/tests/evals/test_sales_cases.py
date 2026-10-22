"""The sales supervisor eval set is well formed (offline; the real-Jev run is
test_sales_supervisor_evals.py)."""

import json
from collections import Counter
from pathlib import Path

from mia.agents.parsing import menu_tokens, pre_parse, strip_receipt
from mia.agents.sales_supervisor.actions import ACTIONS, breakdown_of
from mia.templates.retail.seed import ITEMS as MENU
from tests.evals import gate
from tests.evals.cases import HEADER, header, read
from tests.evals.sales_cases import CASES, GATED_LANGS, SCENARIOS

RESEARCH = Path(__file__).parents[3] / "docs" / "research"
PER_HALF = {"tune": 5, "gate": 5, "spent": 20}
LONG = [c for c in CASES if c.half != "short"]
SHORT = [c for c in CASES if c.half == "short"]


def _folded(half: str) -> set[str]:
    return {c.text.casefold().strip() for c in CASES if c.half == half}


def test_ten_cases_per_language_scenario_and_half() -> None:
    """Ten fresh messages per language and scenario (five tune, five gate), twenty spent."""
    counts = Counter((c.lang, c.scenario, c.half) for c in LONG)
    assert set(counts) == {
        (lang, s, h) for lang in GATED_LANGS for s in SCENARIOS for h in PER_HALF
    }
    assert all(n == PER_HALF[half] for (_, _, half), n in counts.items()), counts


def test_no_text_appears_in_both_halves() -> None:
    """The fresh halves share no text (casefolded), and neither repeats a spent one."""
    tune, gate, spent = _folded("tune"), _folded("gate"), _folded("spent")
    assert not tune & gate, tune & gate
    assert not (tune | gate) & spent, (tune | gate) & spent


def test_no_fresh_text_was_ever_scored() -> None:
    """No fresh text (casefolded) is in any earlier sales supervisor run's raw file."""
    # The spent runs, named (a later run's file scores the fresh rows).
    raws = [
        RESEARCH / f"sales-supervisor-2026-10-19-{t}.raw.json"
        for t in ("0243", "0245", "0349", "0353")
    ]
    assert raws
    scored = {
        r["text"].casefold().strip()
        for path in raws
        for r in json.loads(path.read_text(encoding="utf-8"))["results"]
    }
    seen = (_folded("tune") | _folded("gate")) & scored
    assert not seen, seen


def test_the_halves_are_selected_by_name_and_the_spent_half_never() -> None:
    from tests.evals.test_sales_supervisor_evals import _selected

    assert {c.half for c in _selected(CASES, "tune")} == {"tune"}
    assert {c.half for c in _selected(CASES, "gate")} == {"gate"}
    assert not any(c.half == "spent" for c in _selected(CASES, "tune,gate,spent"))
    assert {c.half for c in _selected(CASES, "short")} == {"short"}


def test_a_tune_only_run_has_an_empty_gate() -> None:
    from tests.evals.test_sales_supervisor_evals import _gated

    gated = _gated([{"half": "tune", "lang": "fil", "score": "right", "kind": "ok", "tokens": 1}])
    assert gated["all"]["n"] == 0 and gated["all"]["wrong"] == 0
    assert gated["by_language"] == {}


def test_expected_actions_are_actions_and_counts_name_items() -> None:
    for c in CASES:
        assert c.expected_action in ACTIONS or (c.half == "short" and c.expected_action == "ask")
        assert bool(c.expected_items) == (c.expected_action in ITEM_ACTIONS)


def test_receipt_rows_run_on_a_receipts_kiosk_and_type_the_receipt_number() -> None:
    """The receipt rows carry source receipts (every other row counts), and the number a void
    or refund row types is the one code strips from it (rule 7: code reads the number)."""
    receipt = {"record_receipt", "void_receipt", "refund_receipt", "read_receipts"}
    for c in CASES:
        assert c.source == ("receipts" if c.expected_action in receipt else "counts"), c
    rows = [r for r in read("sales_supervisor") if r.intent in ("void_receipt", "refund_receipt")]
    assert len(rows) == 4
    for r in rows:
        assert strip_receipt(r.message).receipt_no == r.extra["receipt_no"], r


# Words in the cases that name an item but are no name word or short code: Jev maps them.
SYNONYMS = {"Box of 4": {"boxes", "kahon"}}
ITEM_ACTIONS = ("report_sales", "correct_sales", "record_receipt", "refund_receipt")


def test_counts_parse_to_the_expected_groups() -> None:
    """Code splits the numbers (rule 7): each count case gives one group per expected item, in
    order, with the expected quantity and a word of that item (a name word or a short code); a
    correction gives exactly one group, the new quantity."""
    tokens = menu_tokens((name, codes) for name, codes, _ in MENU)
    of_item = {
        name: menu_tokens([(name, codes)]) | SYNONYMS.get(name, set()) for name, codes, _ in MENU
    }
    for c in CASES:
        if c.expected_action not in ITEM_ACTIONS:
            continue
        groups, _ = pre_parse(strip_receipt(c.text).text, tokens)
        assert len(groups) == len(c.expected_items), c
        for group, (item, quantity) in zip(groups, c.expected_items, strict=True):
            assert group.quantity == quantity, c
            assert of_item[item] & set(group.words.split()), (c, group)


def test_why_answers_follow_the_why_question() -> None:
    assert all(c.previous for c in CASES if c.expected_action == "why_answer")


def test_no_tagalog() -> None:
    assert not any("tagalog" in c.text.casefold() for c in CASES)


def test_the_short_half_is_short_and_new() -> None:
    """D42: eighteen en and eighteen fil (gate.SHORT_ROWS), two asks each, short and
    unpunctuated, an offered action, the first expected item seeded and typed with its count,
    no text in another half or a raw file."""
    first = [c.expected_items[0] if c.expected_items else ("", None) for c in SHORT]
    rows = [
        (c.lang, c.text, c.expected_action, i, None, n)
        for c, (i, n) in zip(SHORT, first, strict=True)
    ]
    assert not gate.short_failures("sales_supervisor", rows)
    assert not gate.short_reused(c.text for c in SHORT)


def test_the_csv_has_the_shared_header_and_every_row_parses() -> None:
    assert header("sales_supervisor") == HEADER and len(read("sales_supervisor")) == len(CASES)


def test_a_breakdown_in_extra_is_what_code_reads() -> None:
    """Each short sales_period row's extra "breakdown" (absent: none) is breakdown_of's."""
    rows = [r for r in read("sales_supervisor") if r.half == "short"]
    period = [r for r in rows if r.intent == "sales_period"]
    assert sum("breakdown" in r.extra for r in period) == 2
    assert all(breakdown_of(r.message) == r.extra.get("breakdown") for r in period)
