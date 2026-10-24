"""D50, data standard 1.10 (ADR 024): a supervisor works across their assigned kiosks. The
service's refusals, the one branch scope (home plus active assignments) in the sales reads,
the report, the bookkeeper's balances, the alerts and the approvals, and the branch manager's
assign_kiosk chat action (owner and admin only)."""

import dataclasses
import datetime as dt
from typing import Any

import pytest
from alembic import command
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.bookkeeper import tools as bk_tools
from mia.agents.inventory_manager import tools as inv_tools
from mia.agents.sales_supervisor import MANIFEST as SS
from mia.agents.sales_supervisor import report as report_form
from mia.agents.sales_supervisor import tools as ss_tools
from mia.agents.sales_supervisor import turn as ss_turn
from mia.agents.shift_supervisor import alerts
from mia.cli import _alembic_config
from mia.core import approvals, assignments, db, sales, store
from mia.core import people as people_service
from mia.core.assignments import AssignmentError
from mia.core.db import get_engine
from mia.core.models import (
    STANDARD_VERSION,
    Actor,
    Branch,
    BranchAssignment,
    Event,
    Organisation,
    Person,
    SalesReceipt,
)
from mia.core.rbac import PermissionDenied
from mia.i18n import t
from tests.conftest import RS_TODAY
from tests.test_bookkeeper_tools import deps_for as bk_deps
from tests.test_bookkeeper_tools import told
from tests.test_branch_manager_people import _answers, _turn, jev_on  # noqa: F401 (a fixture)
from tests.test_sales_receipts import _scenario, _void
from tests.test_sales_tools import deps_for as _ss_deps

Ferinos = tuple[Branch, dict[str, Person]]
SS_BINDINGS = {b.tool_id: b for b in ss_tools.BINDINGS}


def _street(session: Session) -> Branch:
    return session.exec(select(Branch).where(Branch.name == "Street stall")).one()


def _commissary(session: Session) -> Branch:
    return session.exec(select(Branch).where(Branch.name == "Commissary")).one()


def ss_deps(session: Session, person: Person) -> AgentDeps:
    return dataclasses.replace(_ss_deps(session, person), today=RS_TODAY)


def _today(session: Session, who: Person, branch_id: str | None) -> dict[str, Any]:
    args = ss_tools.TodayInput(branch_id=branch_id)
    return call_tool(ss_deps(session, who), SS_BINDINGS[f"{SS.id}.today"], args, "c")


def _report(session: Session, who: Person, kiosks: list[str]) -> dict[str, Any]:
    form = report_form.ReportForm(
        measure="amount",
        group_by="kiosk",
        start=RS_TODAY - dt.timedelta(days=7),
        end=RS_TODAY - dt.timedelta(days=1),
        kiosks=kiosks,
    )
    args = ss_tools.ReportInput(form=form)
    return call_tool(ss_deps(session, who), SS_BINDINGS[f"{SS.id}.report"], args, "c")


def _denied(out: dict[str, Any]) -> bool:
    return out.get("status") == "denied"


# ---- the table and the service -----------------------------------------------------------


def test_the_standard_is_1_10_and_assignments_are_core() -> None:
    assert STANDARD_VERSION == "1.10"
    assert BranchAssignment.__tablename__ == "branch_assignments"
    assert BranchAssignment.__module__ == "mia.core.models"


def test_the_migration_creates_the_table_and_its_open_rule() -> None:
    command.upgrade(_alembic_config(), "head")
    with get_engine().connect() as conn:
        found = inspect(conn)
        assert "branch_assignments" in found.get_table_names()
        ix = {i["name"]: i for i in found.get_indexes("branch_assignments")}
    open_ix = ix["ux_branch_assignments_open"]
    assert (open_ix["unique"], open_ix["column_names"]) == (1, ["person_id", "branch_id"])


def test_the_seed_assigns_both_supervisors_to_the_other_kiosk(
    session: Session, rs: Ferinos
) -> None:
    mall, people = rs
    street = _street(session)
    both = {mall.id, street.id}
    assert assignments.branches_of(session, people["Jun"], RS_TODAY) == both
    assert assignments.branches_of(session, people["Marites"], RS_TODAY) == both
    assert assignments.branches_of(session, people["Ana"], RS_TODAY) == {mall.id}
    assert assignments.branches_of(session, people["Nonoy"], RS_TODAY) == {_commissary(session).id}


def test_the_owner_assigns_and_unassigns_with_events(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    rosa, nonoy = Actor.person(people["Rosa"]), people["Nonoy"]
    row = assignments.assign(session, rosa, nonoy, mall, RS_TODAY)
    assert mall.id in assignments.branches_of(session, nonoy, RS_TODAY)
    ended = assignments.unassign(session, rosa, nonoy, mall, RS_TODAY)
    assert (ended.id, ended.to_date) == (row.id, RS_TODAY)
    assert mall.id not in assignments.branches_of(session, nonoy, RS_TODAY)
    actions = [e.action for e in session.exec(select(Event).where(Event.entity_id == row.id))]
    assert actions == ["assignment.created", "assignment.ended"]


@pytest.mark.parametrize(
    ("who", "where", "code"),
    [
        ("Ana", "mall", "not_supervisor"),  # a clerk keeps one kiosk
        ("Rosa", "street", "not_supervisor"),  # the owner already sees every kiosk
        ("Jun", "street", "home_branch"),
        ("Jun", "mall", "already_assigned"),
    ],
)
def test_the_service_refuses(
    session: Session, rs: Ferinos, who: str, where: str, code: str
) -> None:
    mall, people = rs
    branch = mall if where == "mall" else _street(session)
    before = len(session.exec(select(BranchAssignment)).all())
    with pytest.raises(AssignmentError) as exc:
        assignments.assign(session, Actor.person(people["Rosa"]), people[who], branch, RS_TODAY)
    assert exc.value.code == code
    assert len(session.exec(select(BranchAssignment)).all()) == before


def test_a_branch_of_another_organisation_is_refused(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    system = Actor.system(mall.id)
    org = store.insert(session, Organisation(name="Other", country="PH"), system)
    there = store.insert(session, Branch(organisation_id=org.id, name="Elsewhere"), system)
    with pytest.raises(AssignmentError) as exc:
        assignments.assign(session, Actor.person(people["Rosa"]), people["Nonoy"], there, RS_TODAY)
    assert exc.value.code == "other_organisation"


def test_only_the_owner_or_an_admin_assigns(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    for who in ("Marites", "Ana"):
        with pytest.raises(PermissionDenied):
            assignments.assign(session, Actor.person(people[who]), people["Nonoy"], mall, RS_TODAY)
        with pytest.raises(PermissionDenied):
            assignments.unassign(session, Actor.person(people[who]), people["Jun"], mall, RS_TODAY)


def test_unassign_without_an_open_assignment_is_refused(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    with pytest.raises(AssignmentError) as exc:
        assignments.unassign(session, Actor.person(people["Rosa"]), people["Nonoy"], mall, RS_TODAY)
    assert exc.value.code == "not_assigned"


def test_two_open_assignments_are_refused_by_the_index(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    row = BranchAssignment(branch_id=mall.id, person_id=people["Jun"].id, from_date=RS_TODAY)
    with pytest.raises(IntegrityError):
        store.insert(session, row, Actor.system(mall.id))


# ---- reads: sales, reports, balances -----------------------------------------------------


def test_jun_reads_the_mall_kiosks_sales_and_a_report_over_both(
    session: Session, rs: Ferinos
) -> None:
    mall, people = rs
    street, jun = _street(session), people["Jun"]
    out = _today(session, jun, mall.id)
    assert [b["branch"] for b in out["branches"]] == ["Mall kiosk"]
    report = _report(session, jun, [mall.id, street.id])
    assert {line["name"] for line in report["result"]["lines"]} == {"Mall kiosk", "Street stall"}
    every = _report(session, jun, [report_form.ALL])  # "all" is his kiosks, never others
    assert {line["name"] for line in every["result"]["lines"]} == {"Mall kiosk", "Street stall"}


def test_marites_reads_the_street_stalls_sales(session: Session, rs: Ferinos) -> None:
    _, people = rs
    out = _today(session, people["Marites"], _street(session).id)
    assert [b["branch"] for b in out["branches"]] == ["Street stall"]


def test_a_clerk_still_reads_only_her_kiosk(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    assert _denied(_today(session, people["Pao"], mall.id))
    assert _denied(_report(session, people["Pao"], [mall.id]))


def test_a_supervisor_not_assigned_cannot_read_the_kiosk(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    assert _denied(_today(session, people["Nonoy"], mall.id))
    assert _denied(_report(session, people["Nonoy"], [mall.id]))


def test_an_ended_assignment_gives_no_access(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    rosa, jun, nonoy = Actor.person(people["Rosa"]), people["Jun"], people["Nonoy"]
    assignments.unassign(session, rosa, jun, mall, RS_TODAY - dt.timedelta(days=2))
    assert _denied(_today(session, jun, mall.id))
    assignments.assign(session, rosa, nonoy, mall, RS_TODAY - dt.timedelta(days=10))
    assignments.unassign(session, rosa, nonoy, mall, RS_TODAY - dt.timedelta(days=1))
    assert assignments.branches_of(session, nonoy, RS_TODAY) == {_commissary(session).id}
    assert _denied(_today(session, nonoy, mall.id))


def test_an_assigned_supervisor_reads_the_kiosks_balances_not_its_books(
    session: Session, rs: Ferinos
) -> None:
    mall, people = rs
    deps = dataclasses.replace(bk_deps(session, people["Jun"]), today=RS_TODAY)
    binding = {b.tool_id: b for b in bk_tools.BINDINGS}
    out = call_tool(
        deps, binding["bookkeeper.balances"], bk_tools.BalancesInput(branch_id=mall.id), "c"
    )
    assert out["branch_id"] == mall.id
    nonoy = dataclasses.replace(bk_deps(session, people["Nonoy"]), today=RS_TODAY)
    out = call_tool(
        nonoy, binding["bookkeeper.balances"], bk_tools.BalancesInput(branch_id=mall.id), "c"
    )
    assert _denied(out)


def test_the_report_models_kiosks_for_jun_hold_both(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    street = _street(session)
    deps = ss_deps(session, people["Jun"])
    assert ss_turn._report_context(deps).kiosks == {street.id: street.name, mall.id: mall.name}
    options = ss_turn._clarify_options(
        session, deps, "which_kiosk", {"measure": "amount", "period": "yesterday"}
    )
    assert {"Mall kiosk", "Street stall"} <= set(options)
    pao = ss_deps(session, people["Pao"])
    assert ss_turn._report_context(pao).kiosks == {street.id: street.name}


# ---- alerts and approvals ----------------------------------------------------------------


def test_the_mall_kiosks_alerts_reach_jun(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    names = {p.name for p in alerts.supervisors(session, mall.id)}
    assert names == {people["Marites"].name, people["Jun"].name}
    assert people["Nonoy"].name not in names


def test_jun_gets_the_mall_kiosks_void_card_and_may_decide_it(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, (_, _, r3) = _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "3", "mali")
    jun = rs[1]["Jun"]
    assert len(told(session, jun)) == 1
    from mia.core.scheduling import inbox

    assert [a.id for a in inbox(session, Actor.person(jun))] == [out["approval_id"]]
    approvals.decide(
        session, out["approval_id"], Actor.person(jun), "approved", stepped_up_at=db.utcnow()
    )
    session.refresh(r3)
    assert (r3.status, r3.voided_by) == ("voided", jun.id)


def test_an_unassigned_supervisor_may_not_decide_the_mall_kiosks_void(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "3", "mali")
    nonoy = rs[1]["Nonoy"]
    assert told(session, nonoy) == []
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(
            session, out["approval_id"], Actor.person(nonoy), "approved", stepped_up_at=db.utcnow()
        )
    voided = session.exec(select(SalesReceipt).where(SalesReceipt.status == "voided")).all()
    assert voided == []


def test_receipts_of_an_assigned_kiosk_are_readable_in_core(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    mall, people = rs
    _scenario(session, rs, monkeypatch)
    assert len(sales.receipts(session, Actor.person(people["Jun"]), mall.id, RS_TODAY)) == 3
    with pytest.raises(PermissionDenied):
        sales.receipts(session, Actor.person(people["Nonoy"]), mall.id, RS_TODAY)


# ---- the chat ----------------------------------------------------------------------------


@pytest.mark.usefixtures("jev_on")
def test_the_owner_assigns_and_removes_a_supervisor_in_the_chat(
    session: Session, bm: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    mall, people = bm
    rosa, nonoy = people["Rosa"], people["Nonoy"]
    today = assignments.local_day(mall)
    _answers(monkeypatch, "assign_kiosk", [], supervisor=nonoy.id, branch=mall.id)
    reply = _turn(session, rosa, "assign Nonoy to the Mall kiosk")
    assert reply == t("bm.assign.done", rosa.language, name=nonoy.name, branch=mall.name)
    assert mall.id in assignments.branches_of(session, nonoy, today)
    _answers(monkeypatch, "assign_kiosk", [], supervisor=nonoy.id, branch=mall.id, remove=1.0)
    reply = _turn(session, rosa, "alisin si Nonoy sa Mall kiosk")
    assert reply == t("bm.assign.removed", rosa.language, name=nonoy.name, branch=mall.name)
    assert mall.id not in assignments.branches_of(session, nonoy, today)


@pytest.mark.usefixtures("jev_on")
def test_a_refused_assignment_is_worded_in_the_chat(
    session: Session, bm: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    mall, people = bm
    rosa, jun = people["Rosa"], people["Jun"]
    _answers(monkeypatch, "assign_kiosk", [], supervisor=jun.id, branch=mall.id)
    reply = _turn(session, rosa, "assign Jun to the Mall kiosk")
    assert reply == t("bm.assign.already_assigned", rosa.language, name=jun.name, branch=mall.name)


@pytest.mark.usefixtures("jev_on")
def test_a_supervisor_may_not_assign_in_the_chat(
    session: Session, bm: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    mall, people = bm
    marites, nonoy = people["Marites"], people["Nonoy"]
    _answers(monkeypatch, "assign_kiosk", [], supervisor=nonoy.id, branch=mall.id)
    assert _turn(session, marites, "assign Nonoy to the Mall kiosk") == t(
        "bm.not_allowed", marites.language
    )
    assert mall.id not in assignments.branches_of(session, nonoy, assignments.local_day(mall))


# ---- round 1 (the security review) -------------------------------------------------------


def _covering(session: Session, who: Person, at: Branch) -> AgentDeps:
    """ss_deps moved to another kiosk, as at_visit does for a cover."""
    return dataclasses.replace(ss_deps(session, who), branch=at)


def test_a_clerk_on_a_cover_keeps_one_kiosk(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    deps = _covering(session, people["Pao"], mall)  # Pao's home is the Street stall
    assert deps.kiosks() == {mall.id}
    args = ss_tools.TodayInput(branch_id=report_form.ALL)
    assert _denied(call_tool(deps, SS_BINDINGS[f"{SS.id}.today"], args, "c"))
    assert ss_turn._readable(session, deps) == ([mall], False)


def test_only_a_kiosk_is_assignable(session: Session, rs: Ferinos) -> None:
    _, people = rs
    with pytest.raises(AssignmentError) as exc:
        assignments.assign(
            session, Actor.person(people["Rosa"]), people["Jun"], _commissary(session), RS_TODAY
        )
    assert exc.value.code == "not_a_kiosk"


@pytest.mark.usefixtures("jev_on")
def test_the_commissary_is_refused_in_the_chat(
    session: Session, bm: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, people = bm
    rosa, jun, kitchen = people["Rosa"], people["Jun"], _commissary(session)
    _answers(monkeypatch, "assign_kiosk", [], supervisor=jun.id, branch=kitchen.id)
    reply = _turn(session, rosa, "assign Jun to the Commissary")
    assert reply == t("bm.assign.not_a_kiosk", rosa.language, name=jun.name, branch=kitchen.name)
    assert kitchen.id not in assignments.branches_of(session, jun, assignments.local_day(kitchen))


def test_owners_keep_the_fallback_alerts_beside_an_assigned_supervisor(
    session: Session, rs: Ferinos
) -> None:
    _, people = rs
    street = _street(session)
    rosa = Actor.person(people["Rosa"])
    dina = people_service.add_person(
        session, rosa, branch_id=street.id, name="Dina", roles=["admin"], language="en"
    )
    people_service.set_roles(session, rosa, people["Jun"], ["staff"])  # no supervisor of its own
    names = {p.name for p in alerts.supervisors(session, street.id)}
    assert names == {dina.name, people["Marites"].name}


def test_deactivation_ends_the_assignments_for_good(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    jun = people["Jun"]
    people_service.deactivate(session, Actor.person(people["Rosa"]), jun)
    assert assignments.open_assignment(session, jun.id, mall.id) is None
    ended = session.exec(select(Event).where(Event.action == "assignment.ended")).all()
    assert [e.after["person_id"] for e in ended if e.after] == [jun.id]
    assert jun.name not in {p.name for p in alerts.supervisors(session, mall.id)}
    store.update(session, jun, {"status": "active"}, Actor.system(mall.id))  # reactivated
    assert assignments.branches_of(session, jun, RS_TODAY) == {jun.branch_id}
    assert _denied(_today(session, jun, mall.id))


def test_losing_the_supervisor_role_ends_the_assignments(session: Session, rs: Ferinos) -> None:
    _, people = rs
    marites, rosa = people["Marites"], Actor.person(people["Rosa"])
    people_service.set_roles(session, rosa, marites, ["clerk"])
    people_service.set_roles(session, rosa, marites, ["supervisor"])  # promoted again
    assert assignments.branches_of(session, marites, RS_TODAY) == {marites.branch_id}


@pytest.mark.usefixtures("jev_on")
def test_the_chat_assignment_event_carries_the_tool_call(
    session: Session, bm: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    mall, people = bm
    _answers(monkeypatch, "assign_kiosk", [], supervisor=people["Nonoy"].id, branch=mall.id)
    _turn(session, people["Rosa"], "assign Nonoy to the Mall kiosk")
    (created,) = session.exec(
        select(Event)
        .where(Event.action == "assignment.created")
        .where(Event.on_behalf_of == people["Rosa"].id)
    ).all()
    assert created.tool_call_id is not None


@pytest.mark.parametrize(
    "kind", [sales.REFUND, "bookkeeper.record_large_expense", "branch_manager.change_price"]
)
def test_an_assigned_supervisor_never_decides_owner_money(
    session: Session, rs: Ferinos, kind: str
) -> None:
    mall, people = rs
    a = approvals.request(
        session, kind, ("sales_receipts", "x"), kind, Actor.person(people["Marites"]),
        ["owner", "admin"], risk="money",
    )  # fmt: skip
    assert a.branch_id == mall.id
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(
            session, a.id, Actor.person(people["Jun"]), "approved", stepped_up_at=db.utcnow()
        )


def test_an_assigned_supervisor_never_writes_at_the_kiosk(session: Session, rs: Ferinos) -> None:
    mall, people = rs
    jun = people["Jun"]
    args = ss_tools.SetTargetInput(period="day", starts_on=RS_TODAY, amount=100, branch_id=mall.id)
    assert _denied(call_tool(ss_deps(session, jun), SS_BINDINGS[f"{SS.id}.set_target"], args, "c"))
    deps = dataclasses.replace(ss_deps(session, jun), manifest=inv_tools.MANIFEST)
    with pytest.raises(PermissionDenied):
        inv_tools._branch(deps, mall.id, inv_tools.ORDERS, "write", "c")
