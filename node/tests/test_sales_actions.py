import dataclasses
import datetime as dt
from typing import Any

import pytest
from sqlmodel import Session, select

from mia.agents.decider import DecideError, Reader
from mia.agents.parsing import menu_tokens, pre_parse, was_corrected
from mia.agents.sales_supervisor.actions import (
    ACTIONS,
    NOULS,
    Query,
    _period,
    _target_start,
    breakdown_of,
    build_query,
    build_request,
)
from mia.agents.sales_supervisor.actions import offered as offered_on
from mia.agents.sales_supervisor.decider import _args, _parse
from mia.core.models import Branch, Person
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail.seed import ITEMS as MENU
from tests.test_sales_tools import deps_for

TODAY = dt.date(2026, 10, 19)  # a Monday
FERINOS = menu_tokens((name, codes) for name, codes, _ in MENU)


ITEMS = {"i1": "Special (sp)", "i2": "Classic (cl)"}
TOKENS = {"special", "sp", "classic", "cl"}


def query(message: str, why_asked: bool = False) -> Query:
    groups, total = pre_parse(message, TOKENS)
    return Query(
        message=message,
        previous_mia_message="",
        role="clerk",
        today=TODAY,
        groups=groups,
        total=total,
        items=ITEMS,
        branches={"b1": "Main"},
        periods={},
        why_asked=why_asked,
        corrected=was_corrected(message),
    )


def args(action: str, message: str, picks: dict[str, str], why_asked: bool = False) -> Any:
    answers = {
        k: {"choice": v, "confidence": 0.9}
        for k, v in {"item": "not_stated", "target_start": "not_stated", **picks}.items()
    }
    return _args(action, Reader(answers, query(message, why_asked)))


def test_report_sales_maps_each_group_to_an_item() -> None:
    out, missing = args(
        "report_sales",
        "3 sp 5 cl total 1450",
        {"item_0": "i1", "item_1": "i2"},
    )
    assert missing is None
    assert out["items"] == [
        {"item_id": "i1", "quantity": 3},
        {"item_id": "i2", "quantity": 5},
    ]
    assert out["total"] == 145000  # major units typed, minor units sent


def test_group_picked_none_is_missing() -> None:
    _, missing = args("report_sales", "3 xyz", {"item_0": "none"})
    assert missing == "item_0"


def test_why_answer_outside_the_why_flow_is_missing() -> None:
    assert args("why_answer", "good weather", {})[1] == "why"
    out, missing = args("why_answer", "good weather", {"theme": "other"}, why_asked=True)
    assert missing is None and out["text"] == "good weather"


def test_set_target_amount_from_total_and_periods() -> None:
    out, missing = args(
        "set_target", "target total 5000", {"target_period": "month", "branch": "not_stated"}
    )
    assert out["amount"] == 500000
    assert missing is None
    assert (out["period"], out["starts_on"], out["amount"], out["branch_id"]) == (
        "month",
        "2026-10-01",
        500000,
        None,
    )
    assert (
        args("set_target", "set a target", {"target_period": "day", "branch": "all"})[1] == "amount"
    )


def test_period_report_defaults_to_this_month_and_weekdays() -> None:
    out, _ = args("sales_period", "how are we", {"period": "not_stated", "branch": "all"})
    assert (out["start"], out["end"], out["branch_id"]) == ("2026-10-01", "2026-10-31", "all")
    out, _ = args("sales_period", "how was sunday", {"period": "sun", "branch": "not_stated"})
    assert out["start"] == out["end"] == "2026-10-18"


def test_target_amount_is_never_a_small_group_quantity() -> None:
    month = {"target_period": "month", "branch": "all"}
    out, _ = args("set_target", "target 480,000 for the mall", {**month, "item_0": "none"})
    assert out["amount"] == 48000000
    picks = {**month, "item_0": "none", "item_1": "none"}
    out, _ = args("set_target", "target for 3 days 5000", picks)
    assert out["amount"] == 500000
    assert args("set_target", "target 50", {**month, "item_0": "none"})[1] == "amount"
    assert args("set_target", "target 500 and 700", picks)[1] == "amount"


def test_a_number_of_a_menu_item_group_is_a_count_not_the_target() -> None:
    month = {"target_period": "month", "branch": "all"}
    assert args("set_target", "target 120 classic", {**month, "item_0": "i2"})[1] == "amount"
    out, missing = args(
        "set_target", "target 5000 for 120 classic", {**month, "item_0": "none", "item_1": "i2"}
    )
    assert missing is None and out["amount"] == 500000


def test_item_instructions_carry_no_message_text() -> None:
    message = "3 zorblax 5 quuxberry"
    request = build_request(query(message), "m")
    for question in request["questions"].values():
        for g in query(message).groups:
            assert g.raw not in question["instructions"]
            assert "zorblax" not in question["instructions"]
    assert request["questions"]["item_1"]["instructions"].count("index 1") == 1


def test_query_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        query("x").message = "y"  # type: ignore[misc]


def test_weekday_period_is_the_most_recent_one() -> None:
    monday = dt.date(2026, 10, 19)
    sat = dt.date(2026, 10, 17)
    assert _period("sat", monday, "en") == (sat, sat)
    assert _period("mon", monday, "en") == (monday, monday)  # today counts
    assert _period("sabado", monday, "ceb") == (sat, sat)
    assert _period("lauantai", monday, "fi") == (sat, sat)
    assert _period("last_month", monday, "en") == (dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert _period("whenever", monday, "en") is None


def test_period_criteria_are_in_the_persons_language() -> None:
    from mia.agents.sales_supervisor.actions import _periods

    assert "sabado" in _periods("fil")["sat"] and "lauantai" in _periods("fi")["sat"]
    assert "saturday" in _periods("de")["sat"] and set(_periods("ceb")) == set(_periods("en"))


def test_the_theme_question_is_asked_only_for_a_why_answer() -> None:
    assert "theme" not in build_request(query("x"), "m")["questions"]
    assert "theme" in build_request(query("x", why_asked=True), "m")["questions"]


def test_why_answer_themes_hold_the_confident_choice_else_other() -> None:
    out, missing = args("why_answer", "may concert", {"theme": "event"}, why_asked=True)
    assert missing is None and out["themes"] == ["event"]
    answers = {"theme": {"choice": "event", "confidence": 0.3}}
    out, _ = _args("why_answer", Reader(answers, query("ewan", True)))
    assert out["themes"] == ["other"]


# ---- final fix wave: the item question (ruling 7) ---------------------------------------------


def test_the_item_question_only_without_a_number() -> None:
    assert "item" not in build_request(query("3 sp 5 cl"), "m")["questions"]
    assert "item" in build_request(query("which branch sells most ube"), "m")["questions"]


def test_a_period_question_with_a_number_reads_item_0() -> None:
    picks = {"period": "not_stated", "branch": "all", "item_0": "i2"}
    out, _ = args("sales_period", "cl sold in 2 branches", picks)
    assert out["item_id"] == "i2"
    out, _ = args("sales_period", "sold in 2 branches", {**picks, "item_0": "none"})
    assert out["item_id"] is None


# ---- final fix wave: target dates (I4) --------------------------------------------------------


def test_target_tomorrow_is_a_day_target_for_tomorrow() -> None:
    picks = {"target_period": "day", "target_start": "tomorrow", "branch": "not_stated"}
    out, missing = args("set_target", "target tomorrow 3,500", {**picks, "item_0": "none"})
    assert missing is None
    assert (out["period"], out["starts_on"], out["amount"]) == ("day", "2026-10-20", 350000)


def test_target_for_december_is_a_month_target_from_the_first() -> None:
    picks = {"target_period": "month", "target_start": "m12", "branch": "not_stated"}
    out, _ = args(
        "set_target", "target for December is 60,000 for the mall", {**picks, "item_0": "none"}
    )
    assert (out["period"], out["starts_on"], out["amount"]) == ("month", "2026-12-01", 6000000)


def test_target_start_ids_map_to_dates() -> None:
    assert _target_start("today", TODAY, "day") == TODAY
    assert _target_start(None, TODAY, "day") == TODAY
    assert _target_start(None, TODAY, "month") == dt.date(2026, 10, 1)
    assert _target_start("this_month", TODAY, "month") == dt.date(2026, 10, 1)
    assert _target_start("next_month", TODAY, "month") == dt.date(2026, 11, 1)
    assert _target_start("m10", TODAY, "month") == dt.date(2026, 10, 1)  # this month included
    assert _target_start("m01", TODAY, "month") == dt.date(2027, 1, 1)
    assert _target_start("next_month", dt.date(2026, 12, 5), "month") == dt.date(2027, 1, 1)


def test_an_unstated_target_period_follows_the_start() -> None:
    picks = {"target_period": "not_stated", "branch": "not_stated", "item_0": "none"}
    out, _ = args("set_target", "target 3,500", {**picks, "target_start": "tomorrow"})
    assert (out["period"], out["starts_on"]) == ("day", "2026-10-20")
    out, _ = args("set_target", "target 60,000", {**picks, "target_start": "m12"})
    assert (out["period"], out["starts_on"]) == ("month", "2026-12-01")


# ---- final fix wave: build_query (I3, I5, M2) -------------------------------------------------


def test_build_query_offers_every_branch_and_carries_the_message_ids(
    session: Session, ferinos: tuple[Branch, dict[str, Person]]
) -> None:
    _, people = ferinos
    ana = people["Ana"]
    deps = deps_for(session, ana)
    why = t("sales.why", ana.language)
    q = build_query(deps, "maraming tao", why, message_id="m1", previous_id="m0")
    assert set(q.branches.values()) == {"Mall kiosk", "Street stall"}
    assert q.why_asked and q.message_id == "m1"
    answers = {"theme": {"choice": "event", "confidence": 0.9}}
    out, _ = _args("why_answer", Reader(answers, q))
    assert out["asked_message_id"] == "m0"
    other = build_query(deps, "maraming tao", "Hello", message_id="m1", previous_id="m0")
    assert not other.why_asked
    count = build_query(deps, "3 sp", "", message_id="m2")
    sp = {"item_0": {"choice": next(iter(count.items)), "confidence": 0.9}}
    assert _args("report_sales", Reader(sp, count))[0]["source_message_id"] == "m2"


def _parsed(message: str, action: str) -> Any:
    answers = {
        "action": {"choice": action, "confidence": 0.95, "probabilities": {action: 0.95}},
        "item_0": {"choice": "i2", "confidence": 0.9},
        "item_1": {"choice": "i1", "confidence": 0.9},
        "period": {"choice": "not_stated", "confidence": 0.9},
        "branch": {"choice": "not_stated", "confidence": 0.9},
    }
    return _parse(answers, query(message))


def test_a_correction_by_rule_is_correct_sales_whatever_jevs_pick() -> None:
    d = _parsed("5 classic hindi 6", "report_sales")
    assert d.action == "correct_sales" and d.raw_action == "report_sales"
    assert d.args["item_id"] == "i2" and d.args["quantity"] == 5
    d = _parsed("4 special instead of 3", "sales_period")
    assert d.action == "correct_sales" and d.raw_action == "sales_period"


def test_a_breakdown_word_settles_a_doubtful_period_pick() -> None:
    """'benta kahapon bawat item' fell from 0.62 to 0.49 on sales_period (23 Oct run): code read
    the breakdown words, so the read answers instead of asking; without them it still asks."""
    answers = {
        "action": {
            "choice": "sales_period",
            "confidence": 0.49,
            "probabilities": {"sales_period": 0.49, "report_sales": 0.2},
        },
        "period": {"choice": "not_stated", "confidence": 0.9},
        "branch": {"choice": "not_stated", "confidence": 0.9},
        "item": {"choice": "not_stated", "confidence": 0.9},
    }
    d = _parse(answers, query("benta kahapon bawat item"))
    assert d.action == "sales_period" and d.args["breakdown"] == "item"
    assert _parse(answers, query("benta kahapon")).action == "clarify"
    # live 24 Oct: Jev read "benta" as a count; with no counts typed it is the period read
    as_count = {
        **answers,
        "action": {
            "choice": "report_sales",
            "confidence": 0.52,
            "probabilities": {"report_sales": 0.52},
        },
    }
    d = _parse(as_count, query("benta kahapon bawat item"))
    assert d.action == "sales_period" and d.args["breakdown"] == "item"
    counts = query("3 sp bawat item")
    typed = {**as_count, "item_0": {"choice": next(iter(counts.items)), "confidence": 0.9}}
    assert _parse(typed, counts).action != "sales_period"  # counts typed: never the read


def test_only_counts_on_a_receipts_kiosk_is_the_ring_up_question() -> None:
    """Live 24 Oct: '2 classic 1 special gcash' got Did you mean (a sale or a correction);
    code knows the message is only counts, so a receipts kiosk asks to ring it up."""
    import dataclasses

    answers = {
        "action": {
            "choice": "correct_sales",
            "confidence": 0.41,
            "probabilities": {"correct_sales": 0.41, "record_receipt": 0.38},
        },
        "item_0": {"choice": "i2", "confidence": 0.9},
        "item_1": {"choice": "i1", "confidence": 0.9},
    }
    q = dataclasses.replace(
        query("2 cl 1 sp gcash"), source="receipts", counts_only=True, tender="gcash"
    )
    d = _parse(answers, q)
    assert d.action == "record_receipt" and d.args.get("confirm") is True
    other = dataclasses.replace(q, counts_only=False)
    assert _parse(answers, other).action != "record_receipt"  # not only counts: Jev's pick


def test_without_a_negation_jevs_pick_stands() -> None:
    d = _parsed("3 special 5 classic", "report_sales")
    assert d.action == "report_sales" and len(d.args["items"]) == 2


def _nouls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIA_SALES_QUESTION", "nouls")
    get_settings.cache_clear()


@pytest.mark.parametrize("mode", ["choice", "nouls"])
def test_action_instructions_say_who_texts_and_carry_no_message_text(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("MIA_SALES_QUESTION", mode)
    get_settings.cache_clear()
    request = build_request(query("zorblax 3 sp"), "m")
    asks = [q for k, q in request["questions"].items() if k == "action" or k.startswith("is_")]
    offered = [a for a in offered_on("counts") if a in NOULS]  # a counts kiosk (I2)
    assert asks and len(asks) == (1 if mode == "choice" else len(offered))
    for question in asks:
        assert "zorblax" not in question["instructions"]
        assert "`sender_role`" in question["instructions"]
        assert "Filipino" in question["instructions"]


@pytest.mark.parametrize("mode", ["choice", "nouls"])
def test_action_instructions_name_the_organisation_of_the_request(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("MIA_SALES_QUESTION", mode)
    get_settings.cache_clear()
    q = dataclasses.replace(query("3 sp"), org="Acme Bakes")
    questions = build_request(q, "m")["questions"].items()
    asks = [v for k, v in questions if k == "action" or k.startswith("is_")]
    assert asks
    for question in asks:
        assert "Acme Bakes" in question["instructions"]
        assert "Ferino" not in question["instructions"]


def test_build_query_reads_the_organisation_name(
    session: Session, ferinos: tuple[Branch, dict[str, Person]]
) -> None:
    from mia.core.models import Organisation

    q = build_query(deps_for(session, ferinos[1]["Ana"]), "3 sp", "")
    assert q.org == session.exec(select(Organisation)).one().name


def test_nouls_ask_a_yes_or_no_per_action_and_keep_the_slot_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    choice_keys = set(build_request(query("3 sp"), "m")["questions"])
    _nouls(monkeypatch)
    questions = build_request(query("3 sp"), "m")["questions"]
    asked = {f"is_{a}" for a in offered_on("counts") if a in NOULS}  # a counts kiosk (I2)
    assert set(questions) == (choice_keys - {"action"}) | asked
    assert "clarify" not in NOULS
    noul = questions["is_report_sales"]
    assert noul["type"] == "noul"
    assert noul["criteria"]["true"] == ACTIONS["report_sales"].description


def _noul_parsed(message: str, **yes: float) -> Any:
    answers: dict[str, Any] = {f"is_{a}": {"type": "noul", "noul": 0.02} for a in NOULS}
    answers |= {f"is_{a}": {"type": "noul", "noul": p} for a, p in yes.items()}
    answers |= {
        "item_0": {"choice": "i1", "confidence": 0.9},
        "item": {"choice": "not_stated", "confidence": 0.9},
        "period": {"choice": "not_stated", "confidence": 0.9},
        "branch": {"choice": "not_stated", "confidence": 0.9},
    }
    return _parse(answers, query(message))


def test_nouls_pick_the_one_confident_action() -> None:
    d = _noul_parsed("3 sp", report_sales=0.9, sales_today=0.3)
    assert d.action == "report_sales" and d.confidence == pytest.approx(0.9)
    assert d.args["items"] == [{"item_id": "i1", "quantity": 3}]
    assert d.alternatives[0].action == "sales_today"


def test_nouls_ask_with_both_buttons_when_two_are_confident() -> None:
    d = _noul_parsed("3 sp", report_sales=0.9, sales_today=0.7, sales_period=0.5)
    assert d.action == "clarify" and d.raw_action == "clarify"
    assert [a.action for a in d.alternatives] == ["report_sales", "sales_today"]


def test_nouls_ask_when_none_is_confident() -> None:
    d = _noul_parsed("sales?", sales_today=0.5, sales_period=0.45)
    assert d.action == "clarify" and d.raw_action == "sales_today"
    assert [a.action for a in d.alternatives][:2] == ["sales_today", "sales_period"]


def test_nouls_keep_the_correction_by_rule() -> None:
    d = _noul_parsed("5 sp hindi 6", report_sales=0.9)
    assert d.action == "correct_sales"


def test_a_missing_noul_is_a_decide_error() -> None:
    with pytest.raises(DecideError):
        _parse({"is_report_sales": {"noul": 0.9}}, query("3 sp"))


def test_nouls_ask_when_the_runner_up_yes_is_close() -> None:
    """The review: one yes at 0.95 and a runner-up at 0.59 is not sure enough to write."""
    d = _noul_parsed("3 sp", report_sales=0.95, sales_today=0.59)
    assert d.action == "clarify"
    assert [a.action for a in d.alternatives] == ["report_sales", "sales_today"]


def test_nouls_write_when_the_runner_up_yes_is_below_the_margin() -> None:
    d = _noul_parsed("3 sp", report_sales=0.95, sales_today=0.39)
    assert d.action == "report_sales"


@pytest.mark.parametrize(
    ("message", "breakdown"),
    [
        ("benta last week per item", "item"),
        ("sales by item this month", "item"),
        ("each item yesterday", "item"),
        ("sales per product", "item"),
        ("benta kahapon bawat item", "item"),
        ("kada item last week", "item"),
        ("benta isa-isa", "item"),
        ("sales per kiosk", "kiosk"),
        ("by kiosk last week", "kiosk"),
        ("benta bawat kiosk", "kiosk"),
        ("sales last week", None),
        ("superitem per items", None),
    ],
)
def test_code_reads_the_breakdown_words(message: str, breakdown: str | None) -> None:
    assert breakdown_of(message) == breakdown


def test_a_period_question_carries_the_breakdown_and_a_kiosk_one_reads_every_branch() -> None:
    picks = {"period": "sun", "branch": "not_stated"}
    out, _ = args("sales_period", "benta last week per item", picks)
    assert out["breakdown"] == "item" and out["branch_id"] is None
    assert out["start"] == out["end"] == "2026-10-18"  # the period still read as before
    out, _ = args("sales_period", "benta last week per kiosk", picks)
    assert out["breakdown"] == "kiosk" and out["branch_id"] == "all"
    out, _ = args("sales_period", "benta last week", picks)
    assert "breakdown" not in out
