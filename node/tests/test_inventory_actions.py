"""The inventory manager's actions, Jev request and argument mapping (pure, no model)."""

import dataclasses
import datetime as dt
from typing import Any

import pytest
from sqlmodel import Session

from mia.agents.decider import Reader, pseudonymised
from mia.agents.inventory_manager.actions import Query, build_query, build_request, offer_texts
from mia.agents.inventory_manager.decider import _args
from mia.core.egress import Pseudonymiser
from mia.core.models import Branch, Person
from mia.i18n import t
from tests.jev_fake import answers_for
from tests.test_sales_tools import deps_for

TODAY = dt.date(2026, 10, 19)


def build(session: Session, ferinos: tuple[Branch, dict[str, Person]], message: str, **kw: Any):
    _, people = ferinos
    return build_query(deps_for(session, people["Ana"]), message, kw.pop("previous", ""))


def args(
    q: Query, action: str, confidence: float = 0.95, **slots: str
) -> tuple[dict[str, Any], str | None]:
    answers = answers_for(build_request(q, "m"), action, confidence, **slots)
    return _args(action, Reader(answers, q))


def named(q: Query, name: str) -> str:
    return next(i for i, label in q.items.items() if label.startswith(f"{name} ("))


def test_sold_out_at_a_time(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "sold out of special at 2pm")
    assert q.times == {"t0": "14:00"} and q.groups == []
    special = named(q, "Special")
    out, missing = args(q, "report_stock", kind="sold_out", item=special, time="t0")
    assert missing is None
    assert out["events"] == [
        {
            "kind": "sold_out",
            "item_id": special,
            "ingredient_id": None,
            "quantity": None,
            "unit": None,
            "reason": None,
            "at": "14:00",
        }
    ]


def test_a_bare_count_is_a_count(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "only 5 ube left")
    ube = named(q, "Ube")
    out, missing = args(q, "report_stock", item_0=ube)  # kind not_stated
    assert missing is None
    assert (out["events"][0]["kind"], out["events"][0]["quantity"]) == ("count", 5)
    assert out["events"][0]["at"] is None  # the time question's default is now


def test_waste_without_a_reason_is_missing_reason(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "threw away 8 classic")
    classic = named(q, "Classic")
    _, missing = args(q, "report_stock", kind="waste", item_0=classic)
    assert missing == "reason"
    out, missing = args(q, "report_stock", kind="waste", reason="burnt", item_0=classic)
    assert missing is None and out["events"][0]["reason"] == "burnt"


def test_running_low_names_an_ingredient(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "running low on rice flour")
    flour = named(q, "Rice flour")
    out, missing = args(q, "report_stock", kind="low", item=flour)
    event = out["events"][0]
    assert missing is None and q.kinds[flour] == "ingredient"
    assert (event["kind"], event["ingredient_id"], event["item_id"]) == ("low", flour, None)
    assert (event["quantity"], event["unit"]) == (None, "kg")


def test_a_group_picked_none_is_missing(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "5 zorblax")
    assert args(q, "report_stock", item_0="none")[1] == "item_0"


def test_place_order_with_a_stated_supplier(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "order 10 trays of eggs from Aling Nena")
    eggs = named(q, "Eggs")
    out, missing = args(q, "place_order", item_0=eggs, supplier="Aling Nena")
    assert missing is None
    assert out == {
        "supplier": "Aling Nena",
        "lines": [{"ingredient_id": eggs, "quantity": 10, "unit": "tray"}],
    }


def test_place_order_takes_the_one_fitting_supplier_else_asks(
    session: Session, ferinos: Any
) -> None:
    q = build(session, ferinos, "order 10 eggs")
    out, missing = args(q, "place_order", item_0=named(q, "Eggs"))
    assert missing is None and out["supplier"] == "Aling Nena"
    mixed = build(session, ferinos, "order 10 eggs 4 sugar")
    assert len(mixed.groups) == 2
    picks = {"item_0": named(mixed, "Eggs"), "item_1": named(mixed, "Sugar")}
    assert args(mixed, "place_order", **picks)[1] == "supplier"
    assert args(mixed, "place_order", supplier="Metro Supply", **picks)[1] is None


def test_receive_lines_skip_items(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "received 10 eggs")
    out, missing = args(q, "receive", item_0=named(q, "Eggs"))
    assert missing is None and out["lines"][0]["quantity"] == 10
    assert args(q, "receive", item_0=named(q, "Ube"))[1] == "lines"


def test_answer_offer_only_after_the_offer(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "yes please")
    assert "answer" not in build_request(q, "m")["questions"]
    assert args(q, "answer_offer")[1] == "offer"
    asked = build(
        session, ferinos, "yes please", previous=t("stock.offer_order", "fil", ingredient="Eggs")
    )
    assert asked.offer_asked and asked.previous_mia_message in offer_texts("fil", ["Eggs"])
    assert args(asked, "answer_offer", answer="yes") == ({"yes": True}, None)
    assert args(asked, "answer_offer", answer="no") == ({"yes": False}, None)
    assert args(asked, "answer_offer")[1] == "answer"


def test_plain_actions_and_reply_only(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "what to bake tomorrow")
    assert args(q, "bake_plan") == ({}, None) and args(q, "whats_low") == ({}, None)
    assert args(q, "reply_only", conversation="thanks")[0] == {"kind": "thanks"}


def test_the_item_question_only_without_a_number(session: Session, ferinos: Any) -> None:
    assert "item" not in build_request(build(session, ferinos, "5 ube"), "m")["questions"]
    assert "item" in build_request(build(session, ferinos, "ube is sold out"), "m")["questions"]


def test_item_instructions_carry_no_message_text(session: Session, ferinos: Any) -> None:
    q = build(session, ferinos, "3 zorblax 5 quuxberry at 2pm")
    request = build_request(q, "m")
    for question in request["questions"].values():
        for g in q.groups:
            assert g.raw not in question["instructions"]
        assert "zorblax" not in question["instructions"]
    assert request["questions"]["item_1"]["instructions"].count("index 1") == 1


def test_times_and_groups_are_pseudonymised_in_the_state() -> None:
    q = Query(message="m", previous_mia_message="", role="clerk", today=TODAY)
    body = build_request(dataclasses.replace(q, times={"t0": "14:00"}), "m")
    body["state"]["groups"] = ["5 ube for Maria"]
    state = pseudonymised(body, Pseudonymiser({"Maria": "Person_1"}))["state"]
    assert state["groups"] == ["5 ube for Person_1"] and state["times"] == ["14:00"]


def test_query_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Query("m", "", "clerk", TODAY).message = "x"  # type: ignore[misc]
