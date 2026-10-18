import datetime as dt
from typing import Any

from mia.agents.decider import Reader
from mia.agents.sales_supervisor.actions import Query, pre_parse
from mia.agents.sales_supervisor.decider import _args

TODAY = dt.date(2026, 10, 19)  # a Monday


def test_number_then_words_and_words_then_number() -> None:
    groups, _ = pre_parse("3 special 5 classic")
    assert [(g.quantity, g.words) for g in groups] == [(3, "special"), (5, "classic")]
    groups, _ = pre_parse("special 3 classic 5")
    assert [(g.quantity, g.words) for g in groups] == [(3, "special"), (5, "classic")]


def test_short_codes_and_filler_words() -> None:
    groups, _ = pre_parse("sp 3 cl 5 po")
    assert [(g.quantity, g.words) for g in groups] == [(3, "sp"), (5, "cl")]
    groups, _ = pre_parse("nakabenta ng 12 ube")
    assert [(g.quantity, g.words) for g in groups] == [(12, "nakabenta ube")]


def test_total_is_split_from_the_groups() -> None:
    groups, total = pre_parse("3 special 5 classic total 1,450")
    assert total == 1450 and len(groups) == 2
    groups, total = pre_parse("kabuuan 1450")
    assert total == 1450 and groups == []


def test_no_numbers_gives_no_groups() -> None:
    assert pre_parse("how are we doing today") == ([], None)


ITEMS = {"i1": "Special (sp)", "i2": "Classic (cl)"}


def query(message: str, why_asked: bool = False) -> Query:
    groups, total = pre_parse(message)
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
    )


def args(action: str, message: str, picks: dict[str, str], why_asked: bool = False) -> Any:
    answers = {k: {"choice": v, "confidence": 0.9} for k, v in picks.items()}
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
    assert out["total"] == 1450


def test_group_picked_none_is_missing() -> None:
    _, missing = args("report_sales", "3 xyz", {"item_0": "none"})
    assert missing == "item_0"


def test_why_answer_outside_the_why_flow_is_missing() -> None:
    assert args("why_answer", "good weather", {})[1] == "why"
    out, missing = args("why_answer", "good weather", {}, why_asked=True)
    assert missing is None and out["text"] == "good weather"


def test_set_target_amount_from_total_and_periods() -> None:
    out, missing = args(
        "set_target", "target total 5000", {"target_period": "month", "branch": "not_stated"}
    )
    assert missing is None
    assert (out["period"], out["starts_on"], out["amount"], out["branch_id"]) == (
        "month",
        "2026-10-01",
        5000,
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
