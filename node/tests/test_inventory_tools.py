import datetime as dt
from collections.abc import Callable
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.inventory_manager import MANIFEST, tools
from mia.agents.inventory_manager.tools import (
    DraftOrderInput,
    EventIn,
    LineIn,
    LowStockInput,
    PlanTomorrowInput,
    ReceiveDeliveryInput,
    RecordEventsInput,
)
from mia.core import approvals, events, store
from mia.core.models import (
    Actor,
    Approval,
    Branch,
    Event,
    Message,
    Person,
    StockEvent,
    SupplierOrder,
)
from mia.core.rbac import PermissionDenied
from mia.templates.retail.models import RetailBranchHours, RetailIngredient, RetailItem
from mia.templates.retail.seed import ITEMS

Ferinos = tuple[Branch, dict[str, Person]]
MNL = ZoneInfo("Asia/Manila")
BINDING = {b.tool_id: b for b in tools.BINDINGS}


@pytest.fixture(autouse=True)
def afternoon(manila_at: Callable[[int, int], dt.datetime]) -> dt.datetime:
    """Before closing, so the business date is the local date unless a test says so."""
    return manila_at(15, 0)


def today() -> dt.date:
    return dt.datetime.now(MNL).date()


def deps_for(session: Session, person: Person) -> AgentDeps:
    branch = session.get(Branch, person.branch_id)
    assert branch is not None
    return AgentDeps(
        session=session,
        actor=Actor.person(person).as_agent(MANIFEST.roles.agent_role),
        person=person,
        branch=branch,
        organisation_id=branch.organisation_id,
        today=today(),
        lang=person.language or "en",
        manifest=MANIFEST,
    )


def item(session: Session, name: str) -> str:
    return session.exec(select(RetailItem).where(RetailItem.name == name)).one().id


def ingredient(session: Session, name: str) -> str:
    return session.exec(select(RetailIngredient).where(RetailIngredient.name == name)).one().id


def stall(session: Session) -> Branch:
    return session.exec(select(Branch).where(Branch.name == "Street stall")).one()


def order_eggs(session: Session, person: Person, call_id: str = "o1") -> dict[str, object]:
    args = DraftOrderInput(
        supplier="Aling Nena",
        lines=[LineIn(ingredient_id=ingredient(session, "Eggs"), quantity=10)],
    )
    return call_tool(deps_for(session, person), BINDING[tools.DRAFT_ORDER], args, call_id)


def test_ana_records_a_sell_out_and_a_count(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    special, ube = item(session, "Special"), item(session, "Ube")
    args = RecordEventsInput(
        events=[
            EventIn(kind="sold_out", item_id=special, at="14:00"),
            EventIn(kind="count", item_id=ube, quantity=5),
        ],
        source_message_id="m1",
    )
    out = tools.record_events(deps_for(session, people["Ana"]), args, "c1")
    sold, count = out.recorded
    assert out.business_date == today()
    assert (sold.name, sold.at.astimezone(MNL).time()) == ("Special", dt.time(14, 0))
    assert (count.name, count.quantity, count.business_date) == ("Ube", 5, today())
    row = session.get(StockEvent, sold.event_id)
    assert row is not None and row.reported_by == people["Ana"].id
    assert row.source_message_id == "m1"
    actions = {e.action for e in session.exec(select(Event).where(Event.tool_call_id == "c1"))}
    assert {"stock.sold_out", "stock.counted"} <= actions


def test_an_event_about_nothing_known_is_refused(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = RecordEventsInput(events=[EventIn(kind="count", item_id="nope", quantity=1)])
    with pytest.raises(LookupError):
        tools.record_events(deps_for(session, people["Ana"]), args, "c1")


def test_a_receipt_and_a_bad_time_are_no_report(session: Session, ferinos: Ferinos) -> None:
    eggs = ingredient(session, "Eggs")
    with pytest.raises(ValidationError):  # only receive_delivery writes stock.received
        EventIn(kind="received", ingredient_id=eggs, quantity=10)  # type: ignore[arg-type]
    for bad in ("25:00", "12:99", "7:5"):
        with pytest.raises(ValidationError):
            EventIn(kind="sold_out", item_id=item(session, "Ube"), at=bad)


def test_a_sell_out_stores_no_quantity(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    args = RecordEventsInput(
        events=[EventIn(kind="sold_out", item_id=item(session, "Ube"), quantity=2)]
    )
    (out,) = tools.record_events(deps_for(session, people["Ana"]), args, "c1").recorded
    row = session.get(StockEvent, out.event_id)
    assert row is not None and row.quantity is None and out.quantity is None


def test_a_supervisors_delivery_counts_once(session: Session, ferinos: Ferinos) -> None:
    kiosk, people = ferinos
    eggs = ingredient(session, "Eggs")
    count = RecordEventsInput(events=[EventIn(kind="count", ingredient_id=eggs, quantity=6)])
    tools.record_events(deps_for(session, people["Ana"]), count, "c1")
    delivery = ReceiveDeliveryInput(lines=[LineIn(ingredient_id=eggs, quantity=10)])
    tools.receive_delivery(deps_for(session, people["Marites"]), delivery, "c2")
    rows = tools._stock_rows(session, kiosk.id, ["count", "received"])
    assert tools._on_hand(rows)[eggs] == 16


def test_a_late_sell_out_belongs_to_the_closing_day(
    session: Session, ferinos: Ferinos, manila_at: Callable[[int, int], dt.datetime]
) -> None:
    kiosk, people = ferinos
    for row in session.exec(
        select(RetailBranchHours).where(RetailBranchHours.branch_id == kiosk.id)
    ):
        store.update(session, row, {"closes": "23:00"}, Actor.system(kiosk.id))
    manila_at(0, 30)
    args = RecordEventsInput(
        events=[
            EventIn(kind="sold_out", item_id=item(session, "Special")),
            EventIn(kind="sold_out", item_id=item(session, "Ube"), at="23:40"),
        ]
    )
    out = tools.record_events(deps_for(session, people["Ana"]), args, "c1")
    yesterday = today() - dt.timedelta(days=1)
    assert out.business_date == yesterday
    assert [e.business_date for e in out.recorded] == [yesterday, yesterday]
    assert out.recorded[1].at.astimezone(MNL).date() == yesterday


def test_a_clerk_reads_only_their_branch_stock(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    sugar = ingredient(session, "Sugar")
    tools.record_events(
        deps_for(session, people["Pao"]),
        RecordEventsInput(events=[EventIn(kind="low", ingredient_id=sugar)]),
        "c1",
    )
    ana = deps_for(session, people["Ana"])
    names = [i.name for i in tools.low_stock(ana, LowStockInput(), "c2").ingredients]
    assert "LPG" in names and "Sugar" not in names and "Eggs" not in names
    with pytest.raises(PermissionDenied):
        tools.low_stock(ana, LowStockInput(branch_id=stall(session).id), "c3")
    with pytest.raises(PermissionDenied):
        tools.plan_tomorrow(ana, PlanTomorrowInput(branch_id=stall(session).id), "c4")
    rosa = deps_for(session, people["Rosa"])
    stall_low = tools.low_stock(rosa, LowStockInput(branch_id=stall(session).id), "c5")
    assert "Sugar" in [i.name for i in stall_low.ingredients]


def test_a_delivery_after_a_count_is_on_hand(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    lpg = ingredient(session, "LPG")
    marites = deps_for(session, people["Marites"])
    args = ReceiveDeliveryInput(lines=[LineIn(ingredient_id=lpg, quantity=2)])
    assert tools.receive_delivery(marites, args, "c1").received_order_ids == []
    names = [i.name for i in tools.low_stock(marites, LowStockInput(), "c2").ingredients]
    assert "LPG" not in names


def test_the_bake_plan_has_a_line_per_item(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = tools.plan_tomorrow(deps_for(session, people["Ana"]), PlanTomorrowInput(), "c1")
    assert len(out.lines) == 8 and out.note_heuristic
    assert [line.item for line in out.lines] == [name for name, *_ in ITEMS]  # menu order
    assert {line.plan for line in out.lines} <= {"more", "same", "fewer"}


def test_a_clerk_cannot_place_an_order(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = order_eggs(session, people["Ana"])
    assert out["status"] == "denied"
    assert session.exec(select(Approval)).all() == []
    with pytest.raises(PermissionDenied):
        tools.receive_delivery(
            deps_for(session, people["Ana"]),
            ReceiveDeliveryInput(
                lines=[LineIn(ingredient_id=ingredient(session, "Eggs"), quantity=1)]
            ),
            "c1",
        )


def test_an_order_waits_for_the_owners_approval(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = order_eggs(session, people["Marites"])
    assert out["status"] == "approval_required"
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None and approval.status == "pending"
    assert approval.type == tools.DRAFT_ORDER and approval.approver_roles == ["owner", "admin"]
    assert approval.channel == "app_only"
    stmt = select(SupplierOrder).where(SupplierOrder.approval_id == approval.id)
    assert session.exec(stmt).all() == []
    with pytest.raises(LookupError):  # the body never runs without the approval
        tools.draft_order(
            deps_for(session, people["Marites"]),
            DraftOrderInput(supplier="Aling Nena", lines=[LineIn(ingredient_id="x", quantity=1)]),
            "o2",
        )


def test_an_owners_own_order_needs_the_pin_step_up(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos  # a supplier order is money (app_only): D37 reaches it with a step-up
    out = order_eggs(session, people["Rosa"])
    rosa = Actor.person(people["Rosa"])
    with pytest.raises(approvals.ApprovalError, match="made or triggered"):
        approvals.decide(session, str(out["approval_id"]), rosa, "approved")
    stale = approvals.utcnow() - approvals.STEP_UP_TTL - dt.timedelta(seconds=1)
    with pytest.raises(approvals.ApprovalError, match="made or triggered"):
        approvals.decide(session, str(out["approval_id"]), rosa, "approved", stepped_up_at=stale)
    approval = session.get(Approval, str(out["approval_id"]))
    assert approval is not None and approval.status == "pending"


def test_a_requester_cannot_approve_their_own_order(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos  # a supervisor; the owner decides their own with step-up (D37)
    out = order_eggs(session, people["Marites"])
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(
            session,
            str(out["approval_id"]),
            Actor.person(people["Marites"]),
            "approved",
            stepped_up_at=approvals.utcnow(),
        )


def test_an_approved_order_is_written_and_the_requester_told(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    marites = people["Marites"]
    out = order_eggs(session, marites)
    approvals.decide(
        session,
        str(out["approval_id"]),
        Actor.person(people["Rosa"]),
        "approved",
        stepped_up_at=approvals.utcnow(),
    )
    stmt = select(SupplierOrder).where(SupplierOrder.approval_id == out["approval_id"])
    order = session.exec(stmt).one()
    assert (order.status, order.supplier, order.requested_by) == (
        "approved",
        "Aling Nena",
        marites.id,
    )
    assert order.total == 10 * 25000 and order.lines[0]["unit"] == "tray"
    assert session.exec(
        select(Event)
        .where(Event.action == "inventory.order_approved")
        .where(Event.entity_id == order.id)
    ).one()
    told = session.exec(select(Message).where(Message.agent_id == MANIFEST.id)).all()
    (note,) = [m for m in told if m.role == "notification"]
    assert note.sender_id == "system"  # Actor.system, not the requester as the agent
    deps = deps_for(session, marites)
    deps.approved = {str(out["approval_id"])}
    again = tools.draft_order(
        deps, DraftOrderInput(supplier="x", lines=[LineIn(ingredient_id="y", quantity=1)]), "o3"
    )
    assert again.order_id == order.id  # one order per approval


def test_receive_closes_the_order_line(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = order_eggs(session, people["Marites"])
    approvals.decide(
        session,
        str(out["approval_id"]),
        Actor.person(people["Rosa"]),
        "approved",
        stepped_up_at=approvals.utcnow(),
    )
    order = session.exec(
        select(SupplierOrder).where(SupplierOrder.approval_id == out["approval_id"])
    ).one()
    eggs = ingredient(session, "Eggs")
    marites = deps_for(session, people["Marites"])
    part = ReceiveDeliveryInput(lines=[LineIn(ingredient_id=eggs, quantity=4)], order_id=order.id)
    assert tools.receive_delivery(marites, part, "r1").received_order_ids == []
    rest = ReceiveDeliveryInput(lines=[LineIn(ingredient_id=eggs, quantity=6)], order_id=order.id)
    done = tools.receive_delivery(marites, rest, "r2")
    assert done.received_order_ids == [order.id]
    session.refresh(order)
    assert order.status == "received" and order.lines[0]["received"] == 10
    rows = session.exec(select(StockEvent).where(StockEvent.order_id == order.id)).all()
    assert sorted(r.quantity or 0 for r in rows) == [4, 6]
    with pytest.raises(LookupError):  # a received order is no longer open
        tools.receive_delivery(marites, rest, "r3")


def test_a_supervisor_cannot_decide_an_order(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = order_eggs(session, people["Rosa"])
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(
            session,
            str(out["approval_id"]),
            Actor.person(people["Marites"]),
            "approved",
            stepped_up_at=approvals.utcnow(),
        )
    stmt = select(SupplierOrder).where(SupplierOrder.approval_id == out["approval_id"])
    assert session.exec(stmt).all() == []


def test_the_order_comes_from_the_requesters_own_call(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    coconut = DraftOrderInput(
        supplier="Aling Nena",
        lines=[LineIn(ingredient_id=ingredient(session, "Coconut"), quantity=99)],
    )
    call_tool(deps_for(session, people["Jun"]), BINDING[tools.DRAFT_ORDER], coconut, "same-id")
    out = order_eggs(session, people["Marites"], "same-id")
    approvals.decide(
        session,
        str(out["approval_id"]),
        Actor.person(people["Rosa"]),
        "approved",
        stepped_up_at=approvals.utcnow(),
    )
    stmt = select(SupplierOrder).where(SupplierOrder.approval_id == out["approval_id"])
    order = session.exec(stmt).one()
    assert order.lines[0]["ingredient_id"] == ingredient(session, "Eggs")
    assert order.lines[0]["quantity"] == 10


def test_a_rejected_order_tells_the_requester_from_the_system(
    session: Session, ferinos: Ferinos
) -> None:
    _, people = ferinos
    out = order_eggs(session, people["Marites"])
    approvals.decide(
        session,
        str(out["approval_id"]),
        Actor.person(people["Rosa"]),
        "rejected",
        stepped_up_at=approvals.utcnow(),
    )
    assert (
        session.exec(
            select(SupplierOrder).where(SupplierOrder.approval_id == out["approval_id"])
        ).all()
        == []
    )
    told = session.exec(select(Message).where(Message.agent_id == MANIFEST.id)).all()
    (note,) = [m for m in told if m.role == "notification"]
    assert note.sender_id == "system"


def test_the_approved_order_is_the_one_the_owner_saw(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    marites = people["Marites"]
    out = order_eggs(session, marites, "seen")
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None
    bigger = DraftOrderInput(
        supplier="Aling Nena",
        lines=[LineIn(ingredient_id=ingredient(session, "Eggs"), quantity=500)],
    )
    deps = deps_for(session, marites)
    events.emit(
        session,
        "tool.called",
        ("tool", tools.DRAFT_ORDER),
        {"input": bigger.model_dump(mode="json")},
        {"output": {}},
        deps.actor,
        tool_call_id="seen",
    )
    approvals.decide(
        session, approval.id, Actor.person(people["Rosa"]), "approved",
        stepped_up_at=approvals.utcnow(),
    )  # fmt: skip
    stmt = select(SupplierOrder).where(SupplierOrder.approval_id == approval.id)
    order = session.exec(stmt).one()
    assert order.lines[0]["quantity"] == 10 == approval.evidence["input"]["lines"][0]["quantity"]


def test_an_approval_without_input_is_refused(session: Session, ferinos: Ferinos) -> None:
    _, people = ferinos
    out = order_eggs(session, people["Marites"])
    approval = session.get(Approval, out["approval_id"])
    assert approval is not None
    store.update(
        session, approval, {"evidence": {"tool_call_id": "o1"}}, Actor.system(approval.branch_id)
    )
    session.commit()
    with pytest.raises(LookupError):
        approvals.decide(
            session, approval.id, Actor.person(people["Rosa"]), "approved",
            stepped_up_at=approvals.utcnow(),
        )  # fmt: skip
    session.rollback()
    session.refresh(approval)
    assert approval.status == "pending"
    stmt = select(SupplierOrder).where(SupplierOrder.approval_id == approval.id)
    assert session.exec(stmt).all() == []
