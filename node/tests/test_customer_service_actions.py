"""The customer service's actions per side, Jev request and argument mapping (no model)."""

import json
from typing import Any

from sqlmodel import Session, select

from mia.agents.customer_service.actions import (
    CUSTOMER,
    STAFF,
    Query,
    Side,
    build_query,
    build_request,
)
from mia.agents.customer_service.decider import parse
from mia.agents.customer_service.models import Complaint, Customer
from mia.core import store
from mia.core.models import Actor, CustomerOrder
from mia.templates.retail.models import RetailItem
from tests.conftest import TODAY, Shop
from tests.jev_fake import answers_for


def build(session: Session, cs: Shop, message: str, side: Side = "customer") -> Query:
    return build_query(session, cs.kiosk, side, message, "", TODAY, "fil")


def item_id(session: Session, name: str) -> str:
    return session.exec(select(RetailItem).where(RetailItem.name == name)).one().id


def classic_id(session: Session) -> str:
    return item_id(session, "Classic")


def decide(q: Query, action: str, **slots: Any) -> Any:
    return parse(answers_for(build_request(q, "m"), action, **slots), q)


def test_an_order_message_gives_lines_and_a_pickup_time(cs: Shop, session: Session) -> None:
    q = build(session, cs, "pa-order 10 bibingka, pickup bukas 8am")
    d = decide(q, "place_order", time="t0", day="d0", fulfilment="pickup")
    assert d.args["lines"] == [{"item_id": classic_id(session), "quantity": 10}]
    assert d.args["time"] == "08:00"
    assert (d.action, d.args["day"], d.args["fulfilment"]) == (
        "place_order",
        "2026-10-21",
        "pickup",
    )


def test_an_order_with_two_items_and_a_delivery_area(cs: Shop, session: Session) -> None:
    q = build(session, cs, "2 puto bumbong at 1 ube, deliver sa Marikina bukas 3pm")
    d = decide(q, "place_order", time="t0", day="d0", fulfilment="delivery")
    pb, ube = item_id(session, "Puto bumbong"), item_id(session, "Ube")
    assert d.args["lines"] == [{"item_id": pb, "quantity": 2}, {"item_id": ube, "quantity": 1}]
    assert (d.args["area"], d.args["time"]) == ("Marikina", "15:00")


def test_an_order_with_an_unknown_item_or_no_time_is_asked(cs: Shop, session: Session) -> None:
    d = decide(build(session, cs, "order 10 kutsinta bukas 8am"), "place_order", time="t0")
    assert (d.action, d.missing) == ("clarify", "items")
    d = decide(build(session, cs, "pa-order 10 bibingka bukas"), "place_order", day="d0")
    assert (d.action, d.missing) == ("clarify", "pickup_time")


def test_a_negation_drops_the_old_quantity(cs: Shop, session: Session) -> None:
    q = build(session, cs, "hindi 10, 12 bibingka po 9am")
    assert q.corrected
    d = decide(q, "place_order", time="t0")
    assert d.args["lines"] == [{"item_id": classic_id(session), "quantity": 12}]


def test_prices_name_the_items_by_code(cs: Shop, session: Session) -> None:
    d = decide(build(session, cs, "magkano ang bibingka at puto bumbong"), "prices")
    assert d.args == {"item_ids": [classic_id(session), item_id(session, "Puto bumbong")]}
    assert decide(build(session, cs, "menu po"), "prices").args == {"item_ids": []}
    assert decide(build(session, cs, "magkano ang bibingka?"), "prices").args == {"item_ids": []}


def test_a_delivery_area_question_reads_the_configured_areas(cs: Shop, session: Session) -> None:
    d = decide(build(session, cs, "nagdedeliver ba kayo sa marikina"), "delivery_area")
    assert d.args == {"area": "Marikina"}
    assert decide(build(session, cs, "sa Cebu?"), "delivery_area").args == {"area": None}


def test_a_language_switch_picks_a_supported_language(cs: Shop, session: Session) -> None:
    q = build(session, cs, "English please")
    assert decide(q, "language_switch", language="en").args == {"language": "en"}
    assert decide(q, "language_switch").missing == "language"


def test_a_customer_request_offers_no_staff_action(cs: Shop, session: Session) -> None:
    body = build_request(build(session, cs, "orders today"), "m")
    options = body["questions"]["action"]["criteria"]
    assert set(options) == CUSTOMER and not {a for a in options if a.startswith("staff_")}
    assert "order" not in body["questions"]


def test_a_staff_request_offers_no_customer_action(cs: Shop, session: Session) -> None:
    body = build_request(build(session, cs, "magkano ang ube", side="staff"), "m")
    assert set(body["questions"]["action"]["criteria"]) == STAFF
    assert not {"fulfilment", "day", "time", "language"} & set(body["questions"])


def test_an_action_of_the_other_side_becomes_clarify(cs: Shop, session: Session) -> None:
    q = build(session, cs, "orders today")
    d = decide(q, "staff_orders_today", probabilities={"staff_orders_today": 0.9, "hours": 0.1})
    assert (d.action, d.raw_action) == ("clarify", "staff_orders_today")
    assert all(a.action in CUSTOMER for a in d.alternatives)
    staff = build(session, cs, "magkano ang ube", side="staff")
    assert decide(staff, "prices").action == "clarify"


def test_staff_mark_ready_finds_the_named_customers_order(cs: Shop, session: Session) -> None:
    mila = session.exec(select(Customer).where(Customer.name == "Mila Reyes")).one()
    order = session.exec(select(CustomerOrder).where(CustomerOrder.customer_id == mila.id)).one()
    q = build(session, cs, "ready na yung kay Mila", side="staff")
    assert list(q.orders) == [order.id] and "Mila" not in json.dumps(q.orders)
    d = decide(q, "staff_mark_ready")
    assert (d.action, d.args) == ("staff_mark_ready", {"order_id": order.id})


def test_customer_request_puts_the_message_in_state_only(cs: Shop, session: Session) -> None:
    body = build_request(build(session, cs, "magkano ang ube"), "m")
    assert body["state"]["message"] == "magkano ang ube"
    nonce = build_request(build(session, cs, "magkano ang ube qzv"), "m")
    assert "qzv" not in json.dumps(nonce["questions"])


def test_item_instructions_carry_no_message_text(cs: Shop, session: Session) -> None:
    body = build_request(build(session, cs, "zqx 10 ube"), "m")
    assert "zqx" not in json.dumps({k: v["instructions"] for k, v in body["questions"].items()})


def test_the_query_holds_no_customer_name_or_address(cs: Shop, session: Session) -> None:
    fields = set(Query.__dataclass_fields__)
    assert not {"name", "address", "customer", "customer_name", "phone"} & fields


def test_a_named_customer_with_no_order_today_gives_no_candidate(
    cs: Shop, session: Session
) -> None:
    ana = Customer(
        branch_id=cs.kiosk.id,
        channel="whatsapp",
        address="+639170000155",
        name="Ana Cruz",
        language="fil",
        first_seen_at=cs.pin(10),
    )
    store.insert(session, ana, Actor.system(cs.kiosk.id))  # a customer with no order today
    q = build(session, cs, "ready na yung kay Ana", side="staff")  # Mila's order is today's only
    assert q.orders == {}
    d = decide(q, "staff_mark_ready")
    assert (d.action, d.missing, d.args) == ("clarify", "order", {"order_id": None})


def test_no_name_offers_every_order_of_today(cs: Shop, session: Session) -> None:
    q = build(session, cs, "ready na yung order", side="staff")
    assert len(q.orders) == 1


def test_a_box_of_4_is_one_item_with_its_own_quantity(cs: Shop, session: Session) -> None:
    q = build(session, cs, "pa-order 1 Box of 4 bibingka, pickup 3pm")
    d = decide(q, "place_order", time="t0")
    assert d.args["lines"] == [{"item_id": item_id(session, "Box of 4"), "quantity": 1}]


def test_four_bibingka_alone_is_four_classic(cs: Shop, session: Session) -> None:
    d = decide(build(session, cs, "pa-order 4 bibingka, pickup 3pm"), "place_order", time="t0")
    assert d.args["lines"] == [{"item_id": classic_id(session), "quantity": 4}]


def test_a_marker_before_a_word_that_is_no_customer_keeps_the_orders(
    cs: Shop, session: Session
) -> None:
    q = build(session, cs, "kay wala, ready na ba", side="staff")  # Cebuano "because none"
    assert len(q.orders) == 1
    assert decide(q, "staff_mark_ready").args == {"order_id": next(iter(q.orders))}


def test_staff_resolve_complaint_offers_the_open_complaints_by_when_logged(
    cs: Shop, session: Session
) -> None:
    complaint = session.exec(select(Complaint)).one()
    q = build(session, cs, "ayos na yung reklamo", side="staff")
    assert list(q.complaints) == [complaint.id] and complaint.text not in json.dumps(q.complaints)
    d = decide(q, "staff_resolve_complaint")
    assert (d.action, d.args) == ("staff_resolve_complaint", {"complaint_id": complaint.id})
    assert build(session, cs, "ayos na", side="customer").complaints == {}
