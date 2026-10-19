"""The customer service on the Ferino's seed, pinned to TODAY so no test reads the wall clock
(the seeded pickup is today at 15:00, the picked-up order yesterday)."""

import datetime as dt

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.customer_service import MANIFEST, public, tools
from mia.agents.customer_service.models import Complaint, Customer, CustomerMessage, Order
from mia.agents.customer_service.public import CustomerDeps
from mia.agents.customer_service.tools import (
    AreaInput,
    ComplainInput,
    ComplaintRef,
    EmptyInput,
    LineIn,
    OrderRef,
    PlaceOrderInput,
    PricesInput,
)
from mia.chat.blocks import ApprovalCardBlock
from mia.core import approvals, orgconfig, store
from mia.core.approvals import ApprovalError
from mia.core.ids import new_id
from mia.core.models import Actor, Approval, Branch, Event, Message, Person, Principal
from mia.core.orgconfig import DeliveryArea
from mia.core.rbac import PermissionDenied
from mia.i18n import t
from mia.templates.retail.models import RetailItem
from tests.conftest import MNL, TODAY, Shop

BINDING = {b.tool_id: b for b in tools.BINDINGS}
PLACE = tools.PLACE_ORDER
CANCEL = f"{MANIFEST.id}.cancel_order"


def test_seed_customer_service_data(cs: Shop, session: Session) -> None:
    assert sorted(c.language for c in session.exec(select(Customer))) == ["en", "fil"]
    assert sorted(o.status for o in session.exec(select(Order))) == ["confirmed", "picked_up"]
    assert [c.status for c in session.exec(select(Complaint))] == ["open"] and [
        a.fee for a in orgconfig.load().delivery_areas
    ] == [5000, 8000, 6000]


def test_the_seeded_pickup_is_today_at_three_and_milas_window_is_closed(
    cs: Shop, session: Session
) -> None:
    mila = session.exec(select(Customer).where(Customer.name == "Mila Reyes")).one()
    order = session.exec(select(Order).where(Order.customer_id == mila.id)).one()
    assert order.pickup_at.astimezone(MNL) == dt.datetime.combine(TODAY, dt.time(15), MNL)
    assert order.lines[0]["quantity"] == 10 and order.total == 10 * order.lines[0]["unit_price"]
    assert mila.last_inbound_at is not None
    assert cs.pin(10) - mila.last_inbound_at >= dt.timedelta(hours=24)


def test_customer_identity_and_text_stay_off_the_seed_events(cs: Shop, session: Session) -> None:
    hidden = {
        "customer_service_customers": {"name", "address"},
        "customer_service_complaints": {"text"},
    }
    rows = session.exec(select(Event)).all()
    for table, fields in hidden.items():
        created = [e for e in rows if e.action == f"{table}.created"]
        assert created
        assert all(e.after and e.after[f] == "<redacted>" for e in created for f in fields)
    assert not [e for e in rows if "Mila" in str(e.after) or "+63917" in str(e.after)]


# ---- tools and the order approval (Task 4) --------------------------------------------------


def utcnow() -> dt.datetime:
    """The pinned clock (cs moves approvals.utcnow), for a fresh step-up."""
    return approvals.utcnow()


def customer_by_lang(session: Session, lang: str) -> Customer:
    return session.exec(select(Customer).where(Customer.language == lang)).one()


def customer_deps(cs: Shop, session: Session, lang: str = "fil") -> CustomerDeps:
    """The agent acting for a seeded customer: fil is Mila Reyes, en is Mark Lim."""
    customer = customer_by_lang(session, lang)
    return CustomerDeps(
        session=session,
        actor=public.customer_actor(customer),
        branch=cs.kiosk,
        organisation_id=cs.kiosk.organisation_id,
        today=TODAY,
        lang=customer.language,
        manifest=MANIFEST,
        customer=customer,
    )


def deps_for(session: Session, person: Person) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=TODAY,
        lang=person.language,
        manifest=MANIFEST,
    )


def agent_actor(cs: Shop) -> Actor:
    role = MANIFEST.roles.agent_role
    return Actor(principal=Principal(type="agent", id=role, roles=[role]), branch_id=cs.kiosk.id)


def ana(cs: Shop) -> Actor:
    return Actor.person(cs.people["Ana"])  # a Mall kiosk clerk


def classic(session: Session) -> RetailItem:
    return session.exec(select(RetailItem).where(RetailItem.name == "Classic")).one()


def order_input(
    session: Session, quantity: int = 10, hour: int = 16, **kw: object
) -> PlaceOrderInput:
    pickup = dt.datetime.combine(TODAY, dt.time(hour), MNL)
    line = LineIn(item_id=classic(session).id, quantity=quantity)
    return PlaceOrderInput.model_validate(
        {"order_id": new_id(), "lines": [line], "fulfilment": "pickup", "pickup_at": pickup} | kw
    )


def place(cs: Shop, session: Session, quantity: int = 10, **kw: object) -> dict[str, object]:
    args = order_input(session, quantity, **kw)
    return call_tool(customer_deps(cs, session), BINDING[PLACE], args, new_id())


def waiting(cs: Shop, session: Session) -> Approval:
    """An order placed through call_tool as Mila, recorded waiting; its approval."""
    deps, args = customer_deps(cs, session), order_input(session)
    out = call_tool(deps, BINDING[PLACE], args, new_id())
    assert out["status"] == "approval_required"
    tools.record_waiting(deps, args, str(out["approval_id"]))
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None
    return approval


def _session(row: object) -> Session:
    session = Session.object_session(row)
    assert session is not None
    return session


def customer_of(a: Approval) -> Customer:
    row = _session(a).get(Customer, a.requester_on_behalf_of)
    assert row is not None
    return row


def order_of(a: Approval) -> Order:
    return _session(a).exec(select(Order).where(Order.approval_id == a.id)).one()


def seeded_order(session: Session, lang: str) -> Order:
    customer = customer_by_lang(session, lang)
    return session.exec(
        select(Order).where(Order.customer_id == customer.id).order_by(col(Order.id))
    ).first() or pytest.fail("no seeded order")


def last_out(session: Session) -> CustomerMessage:
    return session.exec(
        select(CustomerMessage)
        .where(CustomerMessage.direction == "out")
        .order_by(col(CustomerMessage.id).desc())
    ).first() or pytest.fail("no out message")


# negative tests first


def test_the_agent_requester_cannot_decide(cs: Shop, session: Session) -> None:
    with pytest.raises(ApprovalError):
        approvals.decide(
            session, waiting(cs, session).id, agent_actor(cs), "approved", stepped_up_at=utcnow()
        )


def test_a_customer_cannot_approve_an_order(cs: Shop, session: Session) -> None:
    a = waiting(cs, session)
    with pytest.raises(ApprovalError):
        approvals.decide(
            session,
            a.id,
            public.customer_actor(customer_of(a)),
            "approved",
            stepped_up_at=utcnow(),
        )


def test_a_forged_evidence_order_id_is_refused(cs: Shop, session: Session) -> None:
    a = waiting(cs, session)
    a.evidence = {
        **a.evidence,
        "input": {**a.evidence["input"], "order_id": seeded_order(session, "en").id},
    }
    with pytest.raises(LookupError):
        approvals.decide(session, a.id, ana(cs), "approved", stepped_up_at=utcnow())


def test_approve_refuses_an_order_no_longer_waiting(cs: Shop, session: Session) -> None:
    a = waiting(cs, session)
    call_tool(customer_deps(cs, session), BINDING[CANCEL], EmptyInput(), new_id())
    with pytest.raises(ApprovalError, match="withdrawn"):  # cancel_order closed the approval
        approvals.decide(session, a.id, ana(cs), "approved", stepped_up_at=utcnow())
    with pytest.raises(LookupError):  # and the handler re-reads the row on its own
        tools.apply_order_approval(session, a, ana(cs))


def test_cancel_order_withdraws_the_pending_approval(cs: Shop, session: Session) -> None:
    a = waiting(cs, session)
    out = call_tool(customer_deps(cs, session), BINDING[CANCEL], EmptyInput(), new_id())
    assert out["status"] == "cancelled" and a.status == "withdrawn"
    assert session.exec(select(Event).where(Event.action == "approval.withdrawn")).one()


def test_a_pickup_already_past_or_a_known_order_id_is_refused(cs: Shop, session: Session) -> None:
    assert place(cs, session, hour=9)["message"] == "past"  # open since 09:00, the clock is 10:00
    assert place(cs, session, order_id=seeded_order(session, "en").id)["message"] == "order"
    assert not session.exec(select(Approval)).all()


def test_a_late_approval_of_a_passed_pickup_is_refused_and_the_customer_told(
    cs: Shop, session: Session
) -> None:
    a = waiting(cs, session)  # pickup today at 16:00
    cs.pin(17)
    with pytest.raises(LookupError):
        approvals.decide(session, a.id, ana(cs), "approved", stepped_up_at=utcnow())
    assert (order_of(a).status, a.status, a.reason) == ("rejected", "expired", "past")
    assert last_out(session).text == t("cs.order_rejected.other", "fil", time="16:00")


def test_staff_tools_refuse_the_customer_role(cs: Shop, session: Session) -> None:
    deps = customer_deps(cs, session)
    out = call_tool(deps, BINDING[f"{MANIFEST.id}.orders_today"], EmptyInput(), new_id())
    assert out["status"] == "denied"


def test_a_customer_reading_another_customers_order_is_an_rbac_deny(
    cs: Shop, session: Session
) -> None:
    with pytest.raises(PermissionDenied):
        tools.read_order(
            customer_deps(cs, session, lang="en"), seeded_order(session, "fil").id, "t1"
        )
    assert session.exec(select(Event).where(Event.action == "rbac.deny")).first()


def test_a_clerk_lists_only_their_branch_orders(cs: Shop, session: Session) -> None:
    assert tools.orders_today(deps_for(session, cs.people["Pao"]), EmptyInput(), "t1").orders == []


def test_an_order_over_the_max_quantity_is_refused(cs: Shop, session: Session) -> None:
    out = place(cs, session, quantity=51)
    assert (out["status"], out["message"]) == ("invalid", "too_large")
    assert not session.exec(select(Approval)).all()


def test_a_second_order_while_one_waits_is_refused(cs: Shop, session: Session) -> None:
    """Each waiting order asks every clerk and supervisor, so a customer has one at a time."""
    waiting(cs, session)
    out = place(cs, session, quantity=5)
    assert (out["status"], out["message"]) == ("invalid", "pending")
    assert len(session.exec(select(Approval)).all()) == 1


def test_an_order_in_two_currencies_is_refused(
    cs: Shop, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ube = session.exec(select(RetailItem).where(RetailItem.name == "Ube")).one()
    lines = [LineIn(item_id=classic(session).id, quantity=1), LineIn(item_id=ube.id, quantity=1)]
    store.update(session, ube, {"currency": "USD"}, Actor.system(cs.kiosk.id))
    assert place(cs, session, lines=lines)["message"] == "currency"
    area = DeliveryArea(name="Marikina", fee=5000, currency="USD")
    usd = orgconfig.load().model_copy(update={"delivery_areas": [area]})
    monkeypatch.setattr(orgconfig, "load", lambda org=None: usd)
    out = place(cs, session, fulfilment="delivery", delivery_area="Marikina")
    assert out["message"] == "currency"
    assert not session.exec(select(Approval)).all()


def test_set_language_writes_only_the_acting_customers_row(cs: Shop, session: Session) -> None:
    deps, tool = customer_deps(cs, session), BINDING[f"{MANIFEST.id}.set_language"]
    out = call_tool(deps, tool, tools.LanguageInput(language="en"), new_id())
    mila = session.exec(select(Customer).where(Customer.name == "Mila Reyes")).one()
    assert out["language"] == mila.language == "en"
    assert session.exec(select(Event).where(Event.action == public.LANGUAGE)).one()
    bad = call_tool(deps, tool, tools.LanguageInput(language="xx"), new_id())
    assert (bad["status"], bad["message"]) == ("invalid", "language")


def test_record_waiting_refuses_an_approval_for_another_input(cs: Shop, session: Session) -> None:
    deps = customer_deps(cs, session)
    out = call_tool(deps, BINDING[PLACE], order_input(session), new_id())
    with pytest.raises(LookupError):
        tools.record_waiting(deps, order_input(session, quantity=40), str(out["approval_id"]))
    other = customer_deps(cs, session, lang="en")
    with pytest.raises(LookupError):
        tools.record_waiting(other, order_input(session), str(out["approval_id"]))
    assert not session.exec(select(Order).where(Order.status == "waiting")).all()


def test_an_order_outside_the_hours_or_area_or_menu_is_refused(cs: Shop, session: Session) -> None:
    assert place(cs, session, hour=22)["message"] == "closed"
    assert place(cs, session, fulfilment="delivery", delivery_area="Cebu")["message"] == "area"
    deps, args = customer_deps(cs, session), order_input(session)
    args.lines[0].item_id = new_id()
    assert call_tool(deps, BINDING[PLACE], args, new_id())["message"] == "item"
    assert not session.exec(select(Approval)).all()


def test_a_ready_order_cannot_be_cancelled(cs: Shop, session: Session) -> None:
    tools.mark_ready(
        deps_for(session, cs.people["Ana"]),
        OrderRef(order_id=seeded_order(session, "fil").id),
        "t1",
    )
    out = call_tool(customer_deps(cs, session), BINDING[CANCEL], EmptyInput(), new_id())
    assert (out["status"], out["message"]) == ("invalid", "ready")


def test_a_clerk_of_another_branch_cannot_mark_an_order(cs: Shop, session: Session) -> None:
    ref = OrderRef(order_id=seeded_order(session, "fil").id)
    with pytest.raises(LookupError):
        tools.mark_ready(deps_for(session, cs.people["Pao"]), ref, "t1")


def test_a_clerk_cannot_resolve_a_complaint(cs: Shop, session: Session) -> None:
    complaint = session.exec(select(Complaint)).one()
    out = call_tool(
        deps_for(session, cs.people["Ana"]),
        BINDING[f"{MANIFEST.id}.resolve_complaint"],
        ComplaintRef(complaint_id=complaint.id),
        new_id(),
    )
    assert out["status"] == "denied"


# positive


def test_approve_confirms_and_queues_the_customer_reply(cs: Shop, session: Session) -> None:
    a = waiting(cs, session)
    approvals.decide(session, a.id, ana(cs), "approved", stepped_up_at=utcnow())
    assert order_of(a).status == "confirmed" and last_out(session).status == "queued"
    assert order_of(a).decided_by == cs.people["Ana"].id
    assert session.exec(
        select(Event).where(Event.action == "customer_service.order_confirmed")
    ).one()


def test_approve_on_a_node_that_built_no_agent(
    cs: Shop, session: Session, fresh_rbac: None
) -> None:
    public.ensure_role()  # the public turn loads it before the tools run
    a = waiting(cs, session)
    from mia.core.rbac import get_rbac

    get_rbac.cache_clear()  # the decision comes later, on an enforcer that never loaded it
    approvals.decide(session, a.id, ana(cs), "approved", stepped_up_at=utcnow())
    assert order_of(a).status == "confirmed"


def test_reject_tells_the_customer_the_reason(cs: Shop, session: Session) -> None:
    a = waiting(cs, session)
    approvals.decide(session, a.id, ana(cs), "rejected", "sold_out", stepped_up_at=utcnow())
    assert order_of(a).status == "rejected"
    assert last_out(session).text == t("cs.order_rejected.sold_out", "fil", time="16:00")


def test_a_waiting_order_shows_staff_its_card(cs: Shop, session: Session) -> None:
    a = waiting(cs, session)
    order = order_of(a)
    assert (order.status, order.total) == ("waiting", 10 * classic(session).price)
    told = {m.thread_id for m in session.exec(select(Message))}
    assert len(told) == 3  # Marites (supervisor), Ana and Liza (clerks) of the kiosk
    sent = session.exec(select(Event).where(Event.action == "notification.sent")).all()
    assert sent and all("Mila" not in str(e.after) for e in sent)
    blocks = [b for m in session.exec(select(Message)) for b in m.blocks]
    card = ApprovalCardBlock.model_validate(next(b for b in blocks if b["type"] == "approval_card"))
    assert (card.approval_id, card.summary) == (a.id, "Mila (0101)")


def test_customer_tools_answer_from_the_seed(cs: Shop, session: Session) -> None:
    deps = customer_deps(cs, session)
    assert tools.hours(deps, EmptyInput(), "t1").is_open
    menu = tools.prices(deps, PricesInput(), "t1").items
    assert (
        menu and tools.prices(deps, PricesInput(item_ids=[menu[0].item_id]), "t1").items == menu[:1]
    )
    area = tools.delivery_area(deps, AreaInput(name="marikina"), "t1")
    assert (area.area, area.fee, area.pickup_branch) == ("Marikina", 5000, "Mall kiosk")
    assert tools.order_status(deps, EmptyInput(), "t1").status == "confirmed"
    complaint = tools.complain(deps, ComplainInput(text="Matigas"), "t1")
    assert session.get(Complaint, complaint.complaint_id) is not None


def test_staff_list_mark_ready_and_picked_up(cs: Shop, session: Session) -> None:
    deps = deps_for(session, cs.people["Ana"])
    (order,) = tools.orders_today(deps, EmptyInput(), "t1").orders
    assert (order.customer, order.status) == ("Mila", "confirmed")
    assert tools.mark_ready(deps, OrderRef(order_id=order.order_id), "t2").status == "ready"
    assert last_out(session).status == "queued"
    assert tools.mark_picked_up(deps, OrderRef(order_id=order.order_id), "t3").status == "picked_up"
    supervisor = deps_for(session, cs.people["Marites"])
    complaint = session.exec(select(Complaint)).one()
    out = tools.resolve_complaint(supervisor, ComplaintRef(complaint_id=complaint.id), "t4")
    assert out.status == "resolved"


def test_the_order_tools_are_sensitive_and_the_manifest_matches(cs: Shop, session: Session) -> None:
    assert {b.tool_id for b in tools.BINDINGS} == {t.id for t in MANIFEST.tools}
    sensitive = {t.name for t in MANIFEST.tools if t.sensitive}
    assert sensitive == {"place_order", "complain", "orders_today", "mark_ready", "mark_picked_up"}
    assert orgconfig.load().customer_service.max_order_quantity == 50
