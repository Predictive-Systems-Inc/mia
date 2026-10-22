"""Sales receipts in the chat (plan 2026-10-22-sales-receipts-chat): a clerk's check-in opens her
sales session on a receipts kiosk and the bookkeeper's closing count closes it. The shared
helpers here (receipts_kiosk, drawer, ring, money) are imported by the later tasks' tests."""

import dataclasses
import datetime as dt
import functools
import sys
from collections.abc import Callable
from typing import Any

import pytest
from sqlmodel import Session, col, select

from mia.agents.base import AgentDeps, ToolBinding, call_tool
from mia.agents.bookkeeper import replies as bk_replies
from mia.agents.bookkeeper import tools as bk_tools
from mia.agents.bookkeeper.models import CashCount
from mia.agents.bookkeeper.tools import CashCountInput, ExpenseInput
from mia.agents.sales_supervisor import MANIFEST as SS
from mia.agents.sales_supervisor import actions as actions_mod
from mia.agents.sales_supervisor import due as ss_due
from mia.agents.sales_supervisor import replies as ss_replies
from mia.agents.sales_supervisor import tools as ss_tools
from mia.agents.sales_supervisor.actions import build_query
from mia.agents.sales_supervisor.tools import (
    CountIn,
    RecordReceiptInput,
    RefundReceiptInput,
    VoidReceiptInput,
)
from mia.agents.shift_supervisor import replies as shift_replies
from mia.agents.shift_supervisor import tools as shift_tools
from mia.agents.shift_supervisor.rules import fmt_date
from mia.agents.shift_supervisor.tools import AssignCoverInput, CheckInInput, RespondToCoverInput
from mia.chat.blocks import TextBlock
from mia.core import approvals, db, events, orgconfig, sales, scheduling, store
from mia.core.approvals import ApprovalError
from mia.core.models import (
    TENDERS,
    Actor,
    Approval,
    Event,
    Person,
    SalesCount,
    SalesPayment,
    SalesReceipt,
    SalesReceiptLine,
    SalesSession,
    Visit,
)
from mia.core.money import format_money
from mia.core.people import add_person
from mia.core.rbac import PermissionDenied, Rbac, Resource, get_rbac
from mia.core.sales import LineIn, PaymentIn
from mia.i18n import t
from mia.settings import get_settings
from mia.templates.retail import items as retail_items
from mia.templates.retail.items import price_on
from tests.conftest import BK_TODAY, RS_TODAY, Pin
from tests.test_bookkeeper_chat import _answers, _turn, jev_on  # noqa: F401 (a fixture)
from tests.test_bookkeeper_tools import deps_for as bk_deps
from tests.test_bookkeeper_tools import told
from tests.test_data_standard_1_7 import MONDAY, TUESDAY, Ferinos, at, visit_of
from tests.test_data_standard_1_9 import MNL, approve, item
from tests.test_sales_chat import _answers as ss_answers
from tests.test_sales_chat import _buttons
from tests.test_sales_tools import deps_for as _ss_deps
from tests.test_shift_retail_tools import decide as shift_decide
from tests.test_shift_retail_tools import deps_for as shift_deps

MALL_FLOAT = 100_000  # PHP 1,000.00


def receipts_kiosk(monkeypatch: pytest.MonkeyPatch, opening_float: int | None = MALL_FLOAT) -> None:
    """The Mall kiosk on receipts from RS_TODAY, with its float when given (orgconfig.load patched)."""
    settings = orgconfig.load().model_copy(deep=True)
    settings.sales.receipts_from = {"Mall kiosk": RS_TODAY}
    if opening_float is not None:
        settings.sales.opening_float = {"Mall kiosk": opening_float}
    monkeypatch.setattr(orgconfig, "load", lambda org=None: settings)


def drawer(session: Session, rs: Ferinos, who: str = "Ana", hh: int = 9) -> SalesSession:
    """sales.open_for_shift at at(RS_TODAY, hh) as who (no visit)."""
    kiosk, person = rs[0], rs[1][who]
    return sales.open_for_shift(
        session, Actor.person(person), kiosk, person.id, None, at(RS_TODAY, hh)
    )


def ring(
    session: Session,
    rs: Ferinos,
    s: SalesSession,
    no: str,
    lines: list[tuple[str, int]],
    tender: str,
    hh: int = 10,
    mm: int = 0,
) -> SalesReceipt:
    """sales.record_receipt of the lines (item name, quantity) at the dated prices, paid in full
    by one tender, source chat."""
    rows = [(item(session, name), q) for name, q in lines]
    total = sum(q * price_on(session, i, rs[0].id, RS_TODAY) for i, q in rows)
    clerk = session.get(Person, s.person_id)
    assert clerk is not None
    return sales.record_receipt(
        session,
        Actor.person(clerk),
        s,
        no,
        at(RS_TODAY, hh, mm),
        [LineIn(item_id=i.id, quantity=q) for i, q in rows],
        [PaymentIn(tender=tender, amount=total)],  # type: ignore[arg-type]
        source="chat",
    )


def money(amount: int) -> str:
    return format_money(amount, "PHP", "fil")


def shift_binding(name: str) -> ToolBinding:
    return next(b for b in shift_tools.BINDINGS if b.tool_id.endswith(f".{name}"))


def _deny_on(name: str) -> Callable[..., None]:
    """Rbac.require that raises PermissionDenied for the named data resource only."""
    real = Rbac.require

    def require(actor: Actor, resource: Resource, action: str, **kw: object) -> None:
        if resource.name == name:
            raise PermissionDenied(actor.principal.id, f"{resource.obj}:{action}")
        real(get_rbac(), actor, resource, action, **kw)  # type: ignore[arg-type]

    return require


# ---- the check-in opens the drawer ----------------------------------------------------------


def test_a_counts_kiosk_check_in_opens_no_session(
    session: Session, rs: Ferinos, rs_pin: Pin
) -> None:
    rs_pin(at(RS_TODAY, 9))
    out = shift_tools.check_in(shift_deps(session, rs[1]["Ana"]), CheckInInput(), "c")
    assert out.status == "ok" and out.opening_float is None
    assert session.exec(select(SalesSession)).all() == []


def test_head_staff_check_in_opens_no_session(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    rs_pin(at(RS_TODAY, 9))
    shift_tools.check_in(shift_deps(session, rs[1]["Marites"]), CheckInInput(), "c")
    assert session.exec(select(SalesSession)).all() == []


def test_a_denied_session_write_leaves_the_visit_planned(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    rs_pin(at(RS_TODAY, 9))
    deps = shift_deps(session, rs[1]["Ana"])
    monkeypatch.setattr(get_rbac(), "require", _deny_on("sales_sessions"))
    out = call_tool(deps, shift_binding("check_in"), CheckInInput(), "c")
    assert out["status"] == "denied"
    assert visit_of(session, rs[1]["Ana"], RS_TODAY).status == "planned"


def test_a_clerks_check_in_opens_her_session_with_the_branch_float(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    rs_pin(at(RS_TODAY, 9))
    ana = rs[1]["Ana"]
    out = shift_tools.check_in(shift_deps(session, ana), CheckInInput(), "c")
    (s,) = session.exec(select(SalesSession)).all()
    visit = visit_of(session, ana, RS_TODAY)
    assert (s.person_id, s.state, s.opening_float, s.visit_id, s.business_date, s.currency) == (
        ana.id, "open", MALL_FLOAT, visit.id, RS_TODAY, "PHP",
    )  # fmt: skip
    assert (out.opening_float, out.currency) == (MALL_FLOAT, "PHP")


def test_the_float_defaults_to_zero(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch, opening_float=None)
    rs_pin(at(RS_TODAY, 9))
    shift_tools.check_in(shift_deps(session, rs[1]["Ana"]), CheckInInput(), "c")
    assert session.exec(select(SalesSession)).one().opening_float == 0


# ---- the closing count closes it ------------------------------------------------------------


def test_a_closing_count_without_an_open_drawer_is_refused(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    before = len(session.exec(select(CashCount)).all())
    with pytest.raises(LookupError, match="no_session"):
        bk_tools.record_cash_count(
            bk_deps(session, rs[1]["Marites"]), CashCountInput(counted=100_000), "c"
        )
    assert len(session.exec(select(CashCount)).all()) == before


def test_the_closing_count_closes_the_clerks_session(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    ring(session, rs, s, "1", [("Classic", 2), ("Ube", 1)], "cash")
    ring(session, rs, s, "2", [("Classic", 2), ("Special", 1)], "gcash", hh=11)
    rs_pin(at(RS_TODAY, 17, 5))
    marites = rs[1]["Marites"]
    out = bk_tools.record_cash_count(
        bk_deps(session, marites), CashCountInput(counted=112_000), "c"
    )
    session.refresh(s)
    assert (s.state, s.counted, s.expected, s.difference, s.closed_by) == (
        "closed", 112_000, 112_500, -500, marites.id,
    )  # fmt: skip
    assert (
        out.expected, out.difference, out.flagged, out.clerk, out.opening_float, out.cash,
        out.still_open,
    ) == (112_500, -500, False, "Ana", MALL_FLOAT, 12_500, [])  # fmt: skip


def test_drawer_out_is_taken_from_the_count_not_the_session(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    ring(session, rs, s, "1", [("Classic", 2), ("Ube", 1)], "cash")
    rs_pin(at(RS_TODAY, 15))
    marites = rs[1]["Marites"]
    spend = ExpenseInput(category="supplies", amount=2_000, source="cash", business_date=RS_TODAY)
    bk_tools.record_expense(bk_deps(session, marites), spend, "c")
    rs_pin(at(RS_TODAY, 17, 5))
    out = bk_tools.record_cash_count(
        bk_deps(session, marites), CashCountInput(counted=110_500), "c"
    )
    session.refresh(s)
    row = session.get(CashCount, out.id)
    assert row is not None and (row.expected, row.difference) == (110_500, 0)
    assert (s.expected, s.difference) == (112_500, -2_000)


def test_the_count_closes_the_named_drawer_and_names_the_others(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    receipts_kiosk(monkeypatch)
    ana, liza = drawer(session, rs, "Ana", 9), drawer(session, rs, "Liza", 13)
    rs_pin(at(RS_TODAY, 17, 5))
    out = bk_tools.record_cash_count(
        bk_deps(session, rs[1]["Marites"]), CashCountInput(counted=100_000, drawer=ana.id), "c"
    )
    session.refresh(ana)
    session.refresh(liza)
    assert (ana.state, liza.state, out.clerk, out.still_open) == ("closed", "open", "Ana", ["Liza"])


def test_two_drawers_add_their_takings_to_the_undeposited_cash(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    receipts_kiosk(monkeypatch)
    ana, liza = drawer(session, rs, "Ana", 9), drawer(session, rs, "Liza", 13)
    ring(session, rs, ana, "1", [("Classic", 2), ("Ube", 1)], "cash")
    ring(session, rs, liza, "2", [("Classic", 1)], "cash", hh=14)
    rs_pin(at(RS_TODAY, 17, 5))
    deps = bk_deps(session, rs[1]["Marites"])
    bk_tools.record_cash_count(deps, CashCountInput(counted=112_500, drawer=ana.id), "c")
    rs_pin(at(RS_TODAY, 21, 5))
    bk_tools.record_cash_count(deps, CashCountInput(counted=105_000, drawer=liza.id), "c")
    session.refresh(liza)
    assert liza.state == "closed"
    undeposited = bk_tools.balance_days(session, rs[0].id, RS_TODAY)[1]
    before = max(d for d in undeposited if d < RS_TODAY)  # the seed's counts days before
    assert undeposited[RS_TODAY] - undeposited[before] == 17_500  # no deposit or spend today
    assert sales.closed_takings(session, rs[0].id)[RS_TODAY] == 17_500


# ---- the replies ----------------------------------------------------------------------------


def test_the_check_in_reply_names_the_drawer_float(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    rs_pin(at(RS_TODAY, 9))
    out = shift_tools.check_in(shift_deps(session, rs[1]["Ana"]), CheckInInput(), "c")
    blocks = shift_replies.tool_reply("check_in", out.model_dump(mode="json"), "fil")
    assert [b.text for b in blocks if isinstance(b, TextBlock)][-1] == t(
        "retail.check_in.drawer", "fil", float=money(MALL_FLOAT)
    )


def test_the_count_reply_words_the_drawer_and_the_open_ones() -> None:
    out = bk_tools.CashCountOut(
        id="x", business_date=RS_TODAY, counted=112_000, expected=112_500, difference=-500,
        flagged=False, currency="PHP", clerk="Ana", opening_float=MALL_FLOAT, cash=12_500,
        still_open=["Liza"],
    )  # fmt: skip
    drawer_line = t(
        "bk.count.drawer.within", "fil", clerk="Ana", counted=money(112_000),
        expected=money(112_500), float=money(MALL_FLOAT), cash=money(12_500),
        difference=money(500),
    )  # fmt: skip
    still = t("bk.count.still_open", "fil", names="Liza")
    assert bk_replies.count_text(out, "fil") == f"{drawer_line} {still}"


@pytest.mark.usefixtures("jev_on")
def test_a_count_with_no_open_drawer_is_answered_in_the_chat(
    session: Session, bk_en: Ferinos, monkeypatch: pytest.MonkeyPatch, bk_pin: Pin
) -> None:
    settings = orgconfig.load().model_copy(deep=True)
    settings.sales.receipts_from = {"Mall kiosk": BK_TODAY}
    monkeypatch.setattr(orgconfig, "load", lambda org=None: settings)
    bk_pin(at(BK_TODAY, 21, 20))
    _answers(monkeypatch, "cash_count", amount="p0")
    text = _turn(session, bk_en[1]["Marites"], "cash count 1000").text()
    assert text == t("bk.count.no_session", "en", branch="Mall kiosk")


# ---- fix round 1 ----------------------------------------------------------------------------


def test_the_days_drawer_out_is_taken_from_the_first_count_only(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    """One cash spend of 2_000 on a day of two drawers is taken once (the first drawer closed,
    Q126 assumed): Liza's drawer, 2_000 short, shows it."""
    receipts_kiosk(monkeypatch)
    ana, liza = drawer(session, rs, "Ana", 9), drawer(session, rs, "Liza", 13)
    ring(session, rs, ana, "1", [("Classic", 2), ("Ube", 1)], "cash")
    ring(session, rs, liza, "2", [("Classic", 1)], "cash", hh=14)
    rs_pin(at(RS_TODAY, 15))
    deps = bk_deps(session, rs[1]["Marites"])
    spend = ExpenseInput(category="supplies", amount=2_000, source="cash", business_date=RS_TODAY)
    bk_tools.record_expense(deps, spend, "c")
    rs_pin(at(RS_TODAY, 17, 5))
    first = bk_tools.record_cash_count(deps, CashCountInput(counted=110_500, drawer=ana.id), "c")
    rs_pin(at(RS_TODAY, 21, 5))
    second = bk_tools.record_cash_count(deps, CashCountInput(counted=102_000, drawer=liza.id), "c")
    assert (first.clerk, first.expected, first.difference) == ("Ana", 110_500, 0)
    assert (second.clerk, second.expected, second.difference) == ("Liza", 104_000, -2_000)


def test_a_stale_drawer_is_never_reused_and_head_staff_count_it_first(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    yesterday = RS_TODAY - dt.timedelta(days=1)
    ana = rs[1]["Ana"]
    stale = sales.open_for_shift(session, Actor.person(ana), rs[0], ana.id, None, at(yesterday, 9))
    rs_pin(at(RS_TODAY, 9))
    out = shift_tools.check_in(shift_deps(session, ana), CheckInInput(), "c")
    assert out.status == "ok" and visit_of(session, ana, RS_TODAY).status == "in_progress"
    assert (out.opening_float, out.drawer_stale) == (None, yesterday)
    assert session.exec(select(SalesSession)).all() == [stale]  # one open per clerk and branch
    blocks = shift_replies.tool_reply("check_in", out.model_dump(mode="json"), "fil")
    assert [b.text for b in blocks if isinstance(b, TextBlock)][-1] == t(
        "retail.check_in.drawer_stale", "fil", date=fmt_date(yesterday.isoformat(), "fil")
    )
    rs_pin(at(RS_TODAY, 17, 5))
    bk_tools.record_cash_count(bk_deps(session, rs[1]["Marites"]), CashCountInput(counted=0), "c")
    session.refresh(stale)
    today = select(SalesSession).where(SalesSession.business_date == RS_TODAY)
    assert stale.state == "closed" and session.exec(today).all() == []


def test_a_cover_check_in_opens_the_drawer_at_the_visits_kiosk(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pao (Street stall, on counts) covers Ana's Tuesday at the Mall kiosk (D39): the drawer
    opens there with the Mall kiosk's float."""
    receipts_kiosk(monkeypatch)
    orgconfig.load().sales.opening_float["Street stall"] = 50_000
    people = rs[1]
    visit = visit_of(session, people["Ana"], TUESDAY)
    approval = shift_tools.assign_cover(
        shift_deps(session, people["Marites"], MONDAY),
        AssignCoverInput(visit_id=visit.id, candidate_id=people["Pao"].id),
        "a",
    ).approval_id
    assert approval is not None
    shift_decide(session, approval, people["Rosa"], "approved")
    rs_pin(at(MONDAY, 12))
    shift_tools.respond_to_cover(
        shift_deps(session, people["Pao"], MONDAY), RespondToCoverInput(accept=True), "y"
    )
    rs_pin(at(TUESDAY, 8, 50))
    out = shift_tools.check_in(shift_deps(session, people["Pao"], TUESDAY), CheckInInput(), "c")
    (s,) = session.exec(select(SalesSession)).all()
    assert (s.branch_id, s.person_id, s.opening_float, s.visit_id) == (
        rs[0].id, people["Pao"].id, MALL_FLOAT, visit.id,
    )  # fmt: skip
    assert out.opening_float == MALL_FLOAT


# ---- Task 2: the sales supervisor rings up a receipt ----------------------------------------


def ss_deps(session: Session, person: Person) -> AgentDeps:
    """test_sales_tools.deps_for on RS_TODAY."""
    return dataclasses.replace(_ss_deps(session, person), today=RS_TODAY)


def _ube(session: Session, quantity: int, tender: str) -> RecordReceiptInput:
    ube = item(session, "Ube").id
    return RecordReceiptInput(items=[CountIn(item_id=ube, quantity=quantity)], tender=tender)  # type: ignore[arg-type]


def test_the_receipt_tool_refuses_a_counts_kiosk(session: Session, rs: Ferinos) -> None:
    with pytest.raises(LookupError, match="counts_kiosk"):
        ss_tools.record_receipt(ss_deps(session, rs[1]["Ana"]), _ube(session, 3, "cash"), "c")


def test_a_receipt_needs_the_clerks_open_session(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    out = ss_tools.record_receipt(ss_deps(session, rs[1]["Ana"]), _ube(session, 3, "cash"), "c")
    assert out.status == "no_session"
    assert session.exec(select(SalesReceipt)).all() == []
    assert session.exec(select(SalesSession)).all() == []


def test_a_stale_drawer_is_no_session_for_a_receipt(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    ana = rs[1]["Ana"]
    yesterday = RS_TODAY - dt.timedelta(days=1)
    stale = sales.open_for_shift(session, Actor.person(ana), rs[0], ana.id, None, at(yesterday, 9))
    out = ss_tools.record_receipt(ss_deps(session, ana), _ube(session, 3, "cash"), "c")
    assert out.status == "no_session" and session.exec(select(SalesReceipt)).all() == []
    assert session.exec(select(SalesSession)).all() == [stale]


def test_a_typed_total_that_disagrees_writes_nothing(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    drawer(session, rs)
    args = RecordReceiptInput(
        items=[
            CountIn(item_id=item(session, "Classic").id, quantity=2),
            CountIn(item_id=item(session, "Special").id, quantity=1),
        ],
        tender="cash",
        typed_total=15_000,
    )
    out = ss_tools.record_receipt(ss_deps(session, rs[1]["Ana"]), args, "c")
    assert (out.status, out.total, out.typed_total) == ("total_differs", 12_950, 15_000)
    assert session.exec(select(SalesReceipt)).all() == []


def test_a_receipt_is_written_at_the_dated_prices(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    drawer(session, rs)
    deps = ss_deps(session, rs[1]["Ana"])
    assert retail_items.price_on(session, item(session, "Special"), rs[0].id, RS_TODAY) == 4950
    one = ss_tools.record_receipt(
        deps,
        RecordReceiptInput(
            items=[
                CountIn(item_id=item(session, "Classic").id, quantity=2),
                CountIn(item_id=item(session, "Ube").id, quantity=1),
            ],
            tender="cash",
            typed_total=12_500,
            source_message_id="m1",
        ),
        "c1",
    )
    two = ss_tools.record_receipt(
        deps,
        RecordReceiptInput(
            items=[CountIn(item_id=item(session, "Special").id, quantity=1)], tender="gcash"
        ),
        "c2",
    )
    lines = [(x.item, x.quantity, x.line_total) for x in one.lines]
    assert (one.status, one.receipt_no, one.total, lines) == (
        "recorded", "1", 12_500, [("Classic", 2, 8000), ("Ube", 1, 4500)],
    )  # fmt: skip
    assert (two.receipt_no, two.total) == ("2", 4950)
    r = session.exec(select(SalesReceipt).where(SalesReceipt.receipt_no == "1")).one()
    assert (r.source, r.source_message_id, r.clerk_id) == ("chat", "m1", rs[1]["Ana"].id)
    paid = session.exec(select(SalesPayment).where(SalesPayment.receipt_id == r.id))
    assert [(p.tender, p.amount) for p in paid] == [("cash", 12_500)]


def test_the_next_receipt_number_skips_a_tills_own_numbers(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    ring(session, rs, s, "7", [("Ube", 1)], "cash")
    ring(session, rs, s, "POS-99", [("Ube", 1)], "cash")
    assert ss_tools._next_receipt_no(session, rs[0].id) == "8"


# chat, fake Jev, Filipino (rs), the sales supervisor the only agent


@pytest.fixture(params=["choice", "nouls"])
def ss_jev(monkeypatch: pytest.MonkeyPatch, rs_shop: Any, request: pytest.FixtureRequest) -> None:
    """Jev mode with the sales supervisor as the org's only agent (Ferino's settings kept),
    under each action question (MIA_SALES_QUESTION)."""
    only = orgconfig.load().model_copy(update={"agents": [SS.id]})
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    monkeypatch.setenv("MIA_SALES_QUESTION", request.param)
    get_settings.cache_clear()


def _receipts(session: Session) -> list[SalesReceipt]:
    return list(session.exec(select(SalesReceipt)).all())


def _open_drawer(session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch) -> None:
    receipts_kiosk(monkeypatch)
    drawer(session, rs)
    session.commit()


def _paid(session: Session, r: SalesReceipt) -> list[tuple[str, int]]:
    rows = session.exec(select(SalesPayment).where(SalesPayment.receipt_id == r.id))
    return [(p.tender, p.amount) for p in rows]


@pytest.mark.usefixtures("ss_jev")
def test_a_receipt_without_a_tender_asks_with_the_tender_buttons(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_drawer(session, rs, monkeypatch)
    cl, ube = item(session, "Classic").id, item(session, "Ube").id
    ss_answers(monkeypatch, "record_receipt", item_0=cl, item_1=ube, conversation="other")
    asked = _turn(session, rs[1]["Ana"], "2 cl 1 ube")
    assert asked.blocks[0].text == t("sales.receipt.ask_tender", "fil")  # type: ignore[union-attr]
    assert _buttons(asked) == [t(f"bk.tender.{x}", "fil") for x in TENDERS]
    assert _receipts(session) == []
    _turn(session, rs[1]["Ana"], t("bk.tender.gcash", "fil"), asked.thread_id)
    (r,) = _receipts(session)
    assert (r.receipt_no, r.total, _paid(session, r)) == ("1", 12_500, [("gcash", 12_500)])


@pytest.mark.usefixtures("ss_jev")
def test_two_tenders_ask_for_one(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_drawer(session, rs, monkeypatch)
    cl, ube = item(session, "Classic").id, item(session, "Ube").id
    ss_answers(monkeypatch, "record_receipt", item_0=cl, item_1=ube, conversation="other")
    asked = _turn(session, rs[1]["Ana"], "2 cl cash 1 ube gcash")
    assert _buttons(asked) == [t(f"bk.tender.{x}", "fil") for x in TENDERS]
    assert _receipts(session) == []


@pytest.mark.usefixtures("ss_jev")
def test_a_disagreeing_total_asks_before_writing(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_drawer(session, rs, monkeypatch)
    cl, sp = item(session, "Classic").id, item(session, "Special").id
    ss_answers(monkeypatch, "record_receipt", item_0=cl, item_1=sp, conversation="other")
    asked = _turn(session, rs[1]["Ana"], "resibo 2 cl 1 sp cash 150")
    question = t("sales.receipt.total_differs", "fil", computed=money(12_950), typed=money(15_000))
    assert asked.blocks[0].text == question  # type: ignore[union-attr]
    assert _receipts(session) == []
    use = t("sales.receipt.use_computed", "fil", total=money(12_950))
    assert _buttons(asked) == [use, t("clarify.something_else", "fil")]
    _turn(session, rs[1]["Ana"], use, asked.thread_id)
    (r,) = _receipts(session)
    assert (r.receipt_no, r.total, _paid(session, r)) == ("1", 12_950, [("cash", 12_950)])


@pytest.mark.usefixtures("ss_jev")
def test_a_receipt_reply_names_number_lines_and_total(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_drawer(session, rs, monkeypatch)
    cl, ube = item(session, "Classic").id, item(session, "Ube").id
    ss_answers(monkeypatch, "record_receipt", item_0=cl, item_1=ube, conversation="other")
    reply = _turn(session, rs[1]["Ana"], "resibo 2 cl 1 ube cash 125")
    assert reply.text() == t(
        "sales.receipt.recorded",
        "fil",
        no="1",
        lines="2 Classic, 1 Ube",
        total=money(12_500),
        tender=t("bk.tender.cash", "fil"),
    )


@pytest.mark.usefixtures("ss_jev")
def test_a_count_on_a_receipts_kiosk_is_rung_as_a_receipt(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_drawer(session, rs, monkeypatch)
    ss_answers(monkeypatch, "report_sales", item_0=item(session, "Ube").id, conversation="other")
    _turn(session, rs[1]["Ana"], "r 3 ube cash")
    (r,) = _receipts(session)
    assert (r.receipt_no, r.total) == ("1", 13_500)
    today = select(SalesCount).where(SalesCount.business_date == RS_TODAY)
    assert session.exec(today).all() == []


@pytest.mark.usefixtures("ss_jev")
def test_a_receipt_on_a_counts_kiosk_is_a_count_and_says_so_once(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    ana = rs[1]["Ana"]
    ube, cl = item(session, "Ube").id, item(session, "Classic").id
    ss_answers(monkeypatch, "report_sales", item_0=ube, conversation="other")  # no receipt action
    first = _turn(session, ana, "r 3 ube cash")
    ss_answers(monkeypatch, "report_sales", item_0=cl, conversation="other")
    second = _turn(session, ana, "r 1 cl cash")
    noted = t("sales.receipt.as_count", "fil")
    assert first.text().startswith(noted) and not second.text().startswith(noted)
    mine = select(SalesCount).where(
        SalesCount.business_date == RS_TODAY, SalesCount.reported_by == ana.id
    )
    assert sorted((c.item_id, c.quantity, c.tender) for c in session.exec(mine)) == sorted(
        [(ube, 3, "cash"), (cl, 1, "cash")]
    )
    assert _receipts(session) == []


@pytest.mark.usefixtures("ss_jev")
def test_no_open_session_asks_to_check_in(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    ss_answers(monkeypatch, "record_receipt", item_0=item(session, "Ube").id, conversation="other")
    reply = _turn(session, rs[1]["Ana"], "r 3 ube cash")
    assert reply.text() == t("sales.receipt.no_session", "fil")
    assert session.exec(select(SalesSession)).all() == [] and _receipts(session) == []


# ---- Task 2 fix round 1 ---------------------------------------------------------------------


def _groups(session: Session, rs: Ferinos, text: str) -> tuple[list[tuple[int | None, str]], Any]:
    q = build_query(ss_deps(session, rs[1]["Ana"]), text, "")
    return [(g.quantity, g.words) for g in q.groups], q.total


@pytest.mark.parametrize("kiosk", ["counts", "receipts"])
def test_a_typed_total_never_eats_a_count(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, kiosk: str
) -> None:
    if kiosk == "receipts":
        receipts_kiosk(monkeypatch)
    assert _groups(session, rs, "classic 5 ube gcash 4") == ([(5, "classic"), (4, "ube")], None)
    assert _groups(session, rs, "resibo 2 cl 1 ube cash 125") == ([(2, "cl"), (1, "ube")], 125)


def test_a_void_word_strips_a_number_only_on_a_receipts_kiosk(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _groups(session, rs, "cancel 3 ube") == ([(3, "ube")], None)
    assert build_query(ss_deps(session, rs[1]["Ana"]), "cancel 3 ube", "").receipt_no is None
    receipts_kiosk(monkeypatch)
    assert build_query(ss_deps(session, rs[1]["Ana"]), "void resibo 3", "").receipt_no == "3"


def test_the_receipt_tool_checks_the_session_read(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    drawer(session, rs)
    monkeypatch.setattr(get_rbac(), "require", _deny_on("sales_sessions"))
    with pytest.raises(PermissionDenied):
        ss_tools.record_receipt(ss_deps(session, rs[1]["Ana"]), _ube(session, 3, "cash"), "c")
    assert _receipts(session) == []


def test_two_chat_receipts_after_a_tills_number_run_from_one_under_the_lock(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    ring(session, rs, s, "POS-9", [("Ube", 1)], "cash")
    locked: list[bool] = []
    real_lock, real_next = events.write_lock, ss_tools._next_receipt_no

    def lock(db: Session) -> None:
        locked.append(True)
        real_lock(db)

    def next_no(db: Session, branch_id: str) -> str:
        assert locked and db.in_transaction()  # computed under the write lock
        return real_next(db, branch_id)

    monkeypatch.setattr(events, "write_lock", lock)
    monkeypatch.setattr(ss_tools, "_next_receipt_no", next_no)
    deps = ss_deps(session, rs[1]["Ana"])
    numbers = [ss_tools.record_receipt(deps, _ube(session, 1, "cash"), c).receipt_no for c in "ab"]
    assert numbers == ["1", "2"]


def test_a_taken_receipt_number_is_refused_not_written(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    ring(session, rs, drawer(session, rs), "1", [("Ube", 1)], "cash")
    monkeypatch.setattr(ss_tools, "_next_receipt_no", lambda db, branch_id: "1")
    with pytest.raises(LookupError, match="receipt_no"):
        ss_tools.record_receipt(ss_deps(session, rs[1]["Ana"]), _ube(session, 1, "cash"), "c")
    assert len(_receipts(session)) == 1


def test_a_till_number_with_a_superscript_digit_is_skipped(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    ring(session, rs, drawer(session, rs), "\u00b2", [("Ube", 1)], "cash")
    assert ss_tools._next_receipt_no(session, rs[0].id) == "1"


def test_both_yeses_ring_the_sale_on_a_receipts_kiosk(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_shop: Any
) -> None:
    _nouls(monkeypatch)
    _open_drawer(session, rs, monkeypatch)
    both = {"record_receipt": 0.9, "report_sales": 0.9}
    ube = item(session, "Ube").id
    ss_answers(monkeypatch, "record_receipt", probabilities=both, item_0=ube, conversation="other")
    _turn(session, rs[1]["Ana"], "r 3 ube cash")
    (r,) = _receipts(session)
    assert (r.receipt_no, r.total) == ("1", 13_500)


def _nouls(monkeypatch: pytest.MonkeyPatch) -> None:
    only = orgconfig.load().model_copy(update={"agents": [SS.id]})
    monkeypatch.setattr(orgconfig, "load", functools.cache(lambda org=None: only))
    monkeypatch.setenv("MIA_TYPESAFE_KEY", "k")
    monkeypatch.setenv("MIA_DECIDER", "jev")
    monkeypatch.setenv("MIA_SALES_QUESTION", "nouls")
    get_settings.cache_clear()


@pytest.mark.usefixtures("ss_jev")
def test_an_unsure_receipt_without_a_tender_asks_did_you_mean(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_drawer(session, rs, monkeypatch)
    cl, ube = item(session, "Classic").id, item(session, "Ube").id
    unsure = {"record_receipt": 0.3, "sales_today": 0.25}
    ss_answers(
        monkeypatch, "record_receipt", confidence=0.3, probabilities=unsure,
        item_0=cl, item_1=ube, conversation="other",
    )  # fmt: skip
    asked = _turn(session, rs[1]["Ana"], "2 cl 1 ube")
    assert t("bk.tender.gcash", "fil") not in asked.text()
    assert _receipts(session) == []


@pytest.mark.usefixtures("ss_jev")
@pytest.mark.parametrize(
    ("kiosk", "other"), [("counts", "record_receipt"), ("receipts", "report_sales")]
)
def test_did_you_mean_never_offers_the_other_kiosks_action(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, kiosk: str, other: str
) -> None:
    if kiosk == "receipts":
        _open_drawer(session, rs, monkeypatch)
    unsure = {"sales_today": 0.5, other: 0.45}
    ube = item(session, "Ube").id
    ss_answers(
        monkeypatch, "sales_today", confidence=0.5, probabilities=unsure,
        item_0=ube, conversation="other",
    )  # fmt: skip
    buttons = _buttons(_turn(session, rs[1]["Ana"], "kumusta 3 ube"))
    assert t("intent.sales_supervisor.sales_today", "fil") in buttons
    assert t(f"intent.sales_supervisor.{other}", "fil") not in buttons


@pytest.mark.usefixtures("ss_jev")
def test_the_counts_kiosk_notice_is_per_clerk_and_business_date(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    ss_answers(monkeypatch, "report_sales", item_0=item(session, "Ube").id, conversation="other")
    noted = t("sales.receipt.as_count", "fil")
    assert _turn(session, rs[1]["Ana"], "r 3 ube cash").text().startswith(noted)
    assert _turn(session, rs[1]["Liza"], "r 2 ube cash").text().startswith(noted)
    rs_pin(at(RS_TODAY + dt.timedelta(days=1), 10))
    assert _turn(session, rs[1]["Ana"], "r 1 ube cash").text().startswith(noted)


# ---- Task 2 fix round 2 ---------------------------------------------------------------------


@pytest.mark.parametrize("kiosk", ["counts", "receipts"])
def test_an_unknown_item_keeps_the_full_parse(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, kiosk: str
) -> None:
    if kiosk == "receipts":
        receipts_kiosk(monkeypatch)
    assert _groups(session, rs, "classic 5 halo gcash 4") == ([(5, "classic"), (4, "halo")], None)
    assert _groups(session, rs, "ube 3 halo cash 2") == ([(3, "ube"), (2, "halo")], None)
    assert _groups(session, rs, "resibo 2 cl 1 ube cash 125") == ([(2, "cl"), (1, "ube")], 125)
    # a typed total is read on a receipts kiosk, or after a receipt word (counts parse as before)
    typed = ([(3, "sp")], 150) if kiosk == "receipts" else ([(3, "sp"), (150, "")], None)
    assert _groups(session, rs, "3 sp cash 150") == typed


@pytest.mark.usefixtures("ss_jev")
@pytest.mark.parametrize(
    ("text", "known", "words"), [("classic 5 halo gcash 4", "Classic", "halo"),
                                 ("ube 3 halo cash 2", "Ube", "halo")]
)  # fmt: skip
def test_an_unknown_item_after_a_tender_asks_which_item(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, text: str, known: str,
    words: str,
) -> None:  # fmt: skip
    ss_answers(
        monkeypatch, "report_sales", item_0=item(session, known).id, item_1="none",
        conversation="other",
    )  # fmt: skip
    before = len(session.exec(select(SalesCount)).all())
    asked = _turn(session, rs[1]["Ana"], text)
    assert t("sales.which_item", "fil", words=words) in asked.text()
    assert len(session.exec(select(SalesCount)).all()) == before


# ---- Task 3: void and refund through the approval card ---------------------------------------


def ss_binding(name: str) -> ToolBinding:
    return next(b for b in ss_tools.BINDINGS if b.tool_id == f"{SS.id}.{name}")


def _scenario(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> tuple[SalesSession, list[SalesReceipt]]:
    """Ana's drawer at 9:00 on a receipts kiosk with #1 = 2 Classic 1 Ube cash 12_500,
    #2 = 2 Classic 1 Special gcash 12_950, #3 = 3 Ube cash 13_500 (committed)."""
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    rows = [
        ring(session, rs, s, "1", [("Classic", 2), ("Ube", 1)], "cash"),
        ring(session, rs, s, "2", [("Classic", 2), ("Special", 1)], "gcash"),
        ring(session, rs, s, "3", [("Ube", 3)], "cash"),
    ]
    session.commit()
    return s, rows


def _cards(session: Session, kind: str) -> list[Approval]:
    return list(session.exec(select(Approval).where(Approval.type == kind)).all())


def _void(session: Session, who: Person, no: str, reason: str = "") -> dict[str, Any]:
    args = VoidReceiptInput(receipt_no=no, reason=reason)
    return call_tool(ss_deps(session, who), ss_binding("void_receipt"), args, "c")


def _refund(
    session: Session, who: Person, no: str, items: list[tuple[str, int]], reason: str = ""
) -> dict[str, Any]:
    counts = [CountIn(item_id=item(session, n).id, quantity=q) for n, q in items]
    args = RefundReceiptInput(receipt_no=no, items=counts, reason=reason)
    return call_tool(ss_deps(session, who), ss_binding("refund_receipt"), args, "c")


def _decide(session: Session, approval_id: str, who: Person) -> None:
    approvals.decide(session, approval_id, Actor.person(who), "approved", stepped_up_at=db.utcnow())


def test_a_void_of_an_unknown_receipt_raises_no_card(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "99")
    assert (out["status"], out["message"]) == ("invalid", "receipt")
    assert _cards(session, sales.VOID) == []


def test_a_clerk_cannot_void_another_clerks_receipt(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ring(session, rs, drawer(session, rs, "Liza", 13), "4", [("Ube", 1)], "cash", 14)
    out = _void(session, rs[1]["Ana"], "4")
    assert (out["status"], out["message"]) == ("invalid", "receipt")
    assert _cards(session, sales.VOID) == []


def test_head_staff_may_void_any_receipt_of_the_branch(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Marites"], "3")
    assert out["status"] == "approval_required"


def test_a_void_on_a_counts_kiosk_raises_no_card(session: Session, rs: Ferinos) -> None:
    out = _void(session, rs[1]["Ana"], "1")
    assert (out["status"], out["message"]) == ("invalid", "counts_kiosk")
    assert _cards(session, sales.VOID) == []


def test_a_void_of_a_refunded_sale_raises_no_card(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, (r1, _, _) = _scenario(session, rs, monkeypatch)
    ok = approve(session, rs, sales.REFUND, r1.id, "admin", "Rosa")
    ube_line = session.exec(
        select(SalesReceiptLine).where(
            SalesReceiptLine.receipt_id == r1.id,
            SalesReceiptLine.item_id == item(session, "Ube").id,
        )
    ).one()
    sales.record_receipt(
        session, Actor.person(rs[1]["Ana"]), s, "R-1", at(RS_TODAY, 11),
        [LineIn(item_id=ube_line.item_id, quantity=-1, refunded_line_id=ube_line.id)],
        [PaymentIn(tender="cash", amount=-4500)], refund_of=r1.id, approval_id=ok,
    )  # fmt: skip
    out = _void(session, rs[1]["Ana"], "1")
    assert (out["status"], out["message"]) == ("invalid", "refunded")
    assert _cards(session, sales.VOID) == []


def test_a_refund_over_the_sale_raises_no_card(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "1", [("Ube", 2)])
    assert (out["status"], out["message"]) == ("invalid", "quantity")
    assert _cards(session, sales.REFUND) == []


def test_a_refund_of_an_item_not_on_the_sale_raises_no_card(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "3", [("Classic", 1)])
    assert (out["status"], out["message"]) == ("invalid", "refunded_line")
    assert _cards(session, sales.REFUND) == []


def test_a_binding_request_replaces_the_generic_approval(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, (_, _, r3) = _scenario(session, rs, monkeypatch)
    _void(session, rs[1]["Ana"], "3")
    (a,) = _cards(session, sales.VOID)
    assert (a.subject_type, a.subject_id) == ("sales_receipts", r3.id)
    assert _cards(session, f"{SS.id}.void_receipt") == []


def test_a_void_raises_head_staffs_card_with_the_summary(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, (_, _, r3) = _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "3", "mali")
    a = session.get(Approval, out["approval_id"])
    assert a is not None
    assert (out["status"], a.type, a.subject_id, a.channel, a.evidence["risk"],
            a.evidence["amount"], a.approver_roles) == (
        "approval_required", "sales.void", r3.id, "app_only", "money", 13_500,
        ["supervisor", "admin", "owner"],
    )  # fmt: skip
    card = t(
        "sales.void.card", "fil", who="Ana", no="3", lines="3 Ube", total=money(13_500),
        tender=t("bk.tender.cash", "fil"), reason="mali",
    )  # fmt: skip
    assert told(session, rs[1]["Marites"]) == [card]
    assert told(session, rs[1]["Ana"]) == []  # nothing written to her receipt yet
    assert session.get(SalesReceipt, r3.id).status == "paid"  # type: ignore[union-attr]


def test_the_clerk_cannot_decide_her_own_void(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, (_, _, r3) = _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "3", "mali")
    with pytest.raises(ApprovalError):
        _decide(session, out["approval_id"], rs[1]["Ana"])
    assert session.get(SalesReceipt, r3.id).status == "paid"  # type: ignore[union-attr]


def test_an_approved_void_voids_the_receipt(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, (_, _, r3) = _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "3", "mali")
    marites = rs[1]["Marites"]
    _decide(session, out["approval_id"], marites)
    session.refresh(r3)
    assert (r3.status, r3.voided_by, r3.approval_id, r3.void_reason) == (
        "voided", marites.id, out["approval_id"], "mali",
    )  # fmt: skip
    assert told(session, rs[1]["Ana"])[-1] == t("sales.void.done", "fil", no="3")
    assert sales.expected_cash(session, s) == 112_500


def test_a_void_approval_runs_once(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "3", "mali")
    _decide(session, out["approval_id"], rs[1]["Marites"])
    a = session.get(Approval, out["approval_id"])
    with pytest.raises(LookupError, match="status"):
        ss_tools.apply_void_approval(session, a, Actor.person(rs[1]["Marites"]))  # type: ignore[arg-type]


def test_a_void_approved_after_the_close_is_refused(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, (_, _, r3) = _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "3", "mali")
    marites = rs[1]["Marites"]
    sales.close_session(session, Actor.person(marites), s, 126_000, marites.id, at(RS_TODAY, 18))
    session.commit()
    with pytest.raises(LookupError, match="session_closed"):
        _decide(session, out["approval_id"], marites)
    session.rollback()
    approvals.close_refused(session, out["approval_id"], Actor.person(marites), "session_closed")
    session.commit()
    session.refresh(r3)
    assert r3.status == "paid"
    assert told(session, rs[1]["Ana"])[-1] == t("sales.void.closed", "fil", no="3")


def test_a_rejected_void_tells_the_clerk(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, (_, _, r3) = _scenario(session, rs, monkeypatch)
    out = _void(session, rs[1]["Ana"], "3", "mali")
    approvals.decide(
        session, out["approval_id"], Actor.person(rs[1]["Marites"]), "rejected",
        stepped_up_at=db.utcnow(),
    )  # fmt: skip
    assert told(session, rs[1]["Ana"])[-1] == t("sales.void.rejected", "fil", no="3")
    assert session.get(SalesReceipt, r3.id).status == "paid"  # type: ignore[union-attr]


def test_a_refund_card_carries_the_amount_of_the_requested_lines(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, (r1, _, _) = _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "1", [("Ube", 1)], "sira")
    a = session.get(Approval, out["approval_id"])
    assert a is not None
    assert (a.type, a.subject_id, a.evidence["amount"], a.approver_roles) == (
        "sales.refund", r1.id, 4_500, ["admin", "owner"],
    )  # fmt: skip
    card = t(
        "sales.refund.card", "fil", who="Ana", amount=money(4_500), no="1", lines="1 Ube",
        reason="sira",
    )  # fmt: skip
    assert told(session, rs[1]["Rosa"]) == [card]
    assert len(_receipts(session)) == 3


def test_a_supervisor_cannot_decide_a_refund(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "1", [("Ube", 1)])
    with pytest.raises(ApprovalError):
        _decide(session, out["approval_id"], rs[1]["Marites"])
    assert len(_receipts(session)) == 3


def test_an_approved_refund_pays_back_in_the_sales_tender(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, (r1, _, _) = _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "1", [("Ube", 1)])
    _decide(session, out["approval_id"], rs[1]["Rosa"])
    r4 = session.exec(select(SalesReceipt).where(SalesReceipt.receipt_no == "4")).one()
    assert (r4.kind, r4.refund_of, r4.total, r4.session_id, r4.approval_id) == (
        "refund", r1.id, -4_500, s.id, out["approval_id"],
    )  # fmt: skip
    assert _paid(session, r4) == [("cash", -4_500)]
    assert sales.expected_cash(session, s) == 100_000 + 12_500 + 13_500 - 4_500 == 121_500
    done = t(
        "sales.refund.done", "fil", refund_no="4", amount=money(4_500), no="1",
        tender=t("bk.tender.cash", "fil"),
    )  # fmt: skip
    assert told(session, rs[1]["Ana"])[-1] == done


def test_a_refund_of_no_items_returns_the_whole_sale(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "2", [])
    a = session.get(Approval, out["approval_id"])
    assert a is not None and a.evidence["amount"] == 12_950
    _decide(session, a.id, rs[1]["Rosa"])
    r4 = session.exec(select(SalesReceipt).where(SalesReceipt.receipt_no == "4")).one()
    assert (r4.total, _paid(session, r4)) == (-12_950, [("gcash", -12_950)])


def test_a_refund_approval_is_used_once(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "1", [("Ube", 1)])
    _decide(session, out["approval_id"], rs[1]["Rosa"])
    a = session.get(Approval, out["approval_id"])
    with pytest.raises(LookupError):
        ss_tools.apply_refund_approval(session, a, Actor.person(rs[1]["Rosa"]))  # type: ignore[arg-type]
    refunds = session.exec(select(SalesReceipt).where(SalesReceipt.kind == "refund")).all()
    assert len(refunds) == 1


def test_a_refund_with_no_open_drawer_is_not_done(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, _ = _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "1", [("Ube", 1)])
    marites, rosa = rs[1]["Marites"], rs[1]["Rosa"]
    sales.close_session(session, Actor.person(marites), s, 126_000, marites.id, at(RS_TODAY, 18))
    session.commit()
    with pytest.raises(LookupError, match="no_session"):
        _decide(session, out["approval_id"], rosa)
    session.rollback()
    approvals.close_refused(session, out["approval_id"], Actor.person(rosa), "no_session")
    assert told(session, rs[1]["Ana"])[-1] == t("sales.refund.not_done", "fil", no="1")


@pytest.mark.usefixtures("ss_jev")
def test_a_void_in_the_chat_says_it_was_sent_for_approval(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ss_answers(monkeypatch, "void_receipt", conversation="other")
    reply = _turn(session, rs[1]["Ana"], "void 3 mali")
    asked = t("sales.void.asked", "fil", no="3", lines="3 Ube", total=money(13_500))
    assert reply.text() == asked
    (a,) = _cards(session, sales.VOID)
    assert a.evidence["reason"] == "void 3 mali"


@pytest.mark.usefixtures("ss_jev")
def test_a_void_without_a_number_asks_which_receipt(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ss_answers(monkeypatch, "void_receipt", conversation="other")
    assert _turn(session, rs[1]["Ana"], "void").text() == t("sales.receipt.which_no", "fil")
    assert _cards(session, sales.VOID) == []


@pytest.mark.usefixtures("ss_jev")
def test_a_refund_in_the_chat_says_it_was_sent_to_the_owner(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ss_answers(monkeypatch, "refund_receipt", item_0=item(session, "Ube").id, conversation="other")
    reply = _turn(session, rs[1]["Ana"], "refund 1 ube resibo 1")
    asked = t("sales.refund.asked", "fil", amount=money(4_500), no="1", lines="1 Ube")
    assert reply.text() == asked


@pytest.mark.usefixtures("ss_jev")
def test_a_void_of_an_unknown_number_in_the_chat_says_so(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ss_answers(monkeypatch, "void_receipt", conversation="other")
    assert _turn(session, rs[1]["Ana"], "void 99").text() == t(
        "sales.void.no_receipt", "fil", no="99"
    )


# ---- Task 3 fix round 1 ---------------------------------------------------------------------


def test_a_refund_is_paid_only_from_the_requesters_own_drawer(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, _ = _scenario(session, rs, monkeypatch)
    out = _refund(session, rs[1]["Ana"], "1", [("Ube", 1)])
    marites, rosa = rs[1]["Marites"], rs[1]["Rosa"]
    sales.close_session(session, Actor.person(marites), s, 126_000, marites.id, at(RS_TODAY, 13))
    liza = drawer(session, rs, "Liza", 13)
    session.commit()
    with pytest.raises(LookupError, match="no_session"):
        _decide(session, out["approval_id"], rosa)
    session.rollback()
    approvals.close_refused(session, out["approval_id"], Actor.person(rosa), "no_session")
    session.commit()
    assert session.exec(select(SalesReceipt).where(SalesReceipt.kind == "refund")).all() == []
    assert sales.expected_cash(session, liza) == MALL_FLOAT
    assert told(session, rs[1]["Ana"])[-1] == t("sales.refund.not_done", "fil", no="1")


def test_head_staff_cannot_request_a_refund(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    for who in ("Marites", "Rosa"):
        out = _refund(session, rs[1][who], "1", [("Ube", 1)])
        assert (out["status"], out["message"]) == ("invalid", "needs_drawer")
    assert _cards(session, sales.REFUND) == []


def test_a_refund_refused_at_approval_tells_the_clerk_why(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ana, rosa = rs[1]["Ana"], rs[1]["Rosa"]
    first = _refund(session, ana, "1", [("Ube", 1)], "a")
    second = _refund(session, ana, "1", [("Ube", 1)], "b")
    _decide(session, first["approval_id"], rosa)
    session.commit()
    with pytest.raises(LookupError, match="quantity"):
        _decide(session, second["approval_id"], rosa)
    session.rollback()
    approvals.close_refused(session, second["approval_id"], Actor.person(rosa), "quantity")
    assert told(session, ana)[-1] == t("sales.refund.changed", "fil", no="1")


def test_a_void_refused_at_approval_is_not_called_expired(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ana, marites = rs[1]["Ana"], rs[1]["Marites"]
    first, second = _void(session, ana, "3", "a"), _void(session, ana, "3", "b")
    _decide(session, first["approval_id"], marites)
    session.commit()
    with pytest.raises(LookupError, match="status"):
        _decide(session, second["approval_id"], marites)
    session.rollback()
    approvals.close_refused(session, second["approval_id"], Actor.person(marites), "status")
    assert told(session, ana)[-1] == t("sales.void.not_done", "fil", no="3")


def test_cards_go_only_to_who_can_decide_them(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    jun = rs[1]["Jun"]  # another branch's supervisor, made an admin there
    store.update(session, jun, {"roles": ["admin"]}, Actor.person(rs[1]["Rosa"]))
    _refund(session, rs[1]["Ana"], "1", [("Ube", 1)])
    _void(session, rs[1]["Marites"], "3")  # no other supervisor: the branch's leads
    assert told(session, jun) == []
    assert len(told(session, rs[1]["Rosa"])) == 2


@pytest.mark.usefixtures("ss_jev")
def test_an_item_named_without_a_count_asks_never_refunds_the_whole_sale(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ss_answers(monkeypatch, "refund_receipt", item=item(session, "Ube").id, conversation="other")
    reply = _turn(session, rs[1]["Ana"], "refund ube resibo 1")
    assert reply.text() == t("sales.refund.which_items", "fil", no="1")
    assert _cards(session, sales.REFUND) == []


@pytest.mark.usefixtures("ss_jev")
def test_a_refund_of_a_voided_sale_says_it_cannot_be_refunded(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    _decide(session, _void(session, rs[1]["Ana"], "3")["approval_id"], rs[1]["Marites"])
    session.commit()
    ss_answers(monkeypatch, "refund_receipt", conversation="other")
    reply = _turn(session, rs[1]["Ana"], "refund resibo 3")
    assert reply.text() == t("sales.refund.not_refundable", "fil", no="3")
    assert _cards(session, sales.REFUND) == []


# ---- Task 4: reading receipts; today, the owner's report and tender sales over day_sales ----


def _day(session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch) -> list[SalesReceipt]:
    """Ana's drawer on a receipts kiosk with #1 = 2 Classic 1 Ube cash 12_500 (10:00),
    #2 = 2 Classic 1 Special gcash 12_950 (11:00) and #3 = 3 Ube cash 13_500 (12:05), #3 voided
    by Marites (committed)."""
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    rows = [
        ring(session, rs, s, "1", [("Classic", 2), ("Ube", 1)], "cash", 10),
        ring(session, rs, s, "2", [("Classic", 2), ("Special", 1)], "gcash", 11),
        ring(session, rs, s, "3", [("Ube", 3)], "cash", 12, 5),
    ]
    marites = rs[1]["Marites"]
    ok = approve(session, rs, sales.VOID, rows[2].id, "supervisor", "Marites")
    sales.void_receipt(session, Actor.person(marites), rows[2], ok, "mali")
    session.commit()
    return rows


def test_receipts_on_a_counts_kiosk_say_so(session: Session, rs: Ferinos) -> None:
    with pytest.raises(LookupError, match="counts_kiosk"):
        ss_tools.receipts(ss_deps(session, rs[1]["Marites"]), ss_tools.ReceiptsInput(), "c")


def test_a_clerk_reads_only_her_receipts(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _day(session, rs, monkeypatch)
    ring(session, rs, drawer(session, rs, "Liza", 13), "4", [("Kape", 1)], "cash", 14)
    session.commit()
    mine = ss_tools.receipts(ss_deps(session, rs[1]["Ana"]), ss_tools.ReceiptsInput(), "c")
    assert [r.receipt_no for r in mine.receipts] == ["1", "2", "3"]
    assert mine.by_tender == {"cash": 12_500, "gcash": 12_950}
    head = ss_tools.receipts(ss_deps(session, rs[1]["Marites"]), ss_tools.ReceiptsInput(), "c")
    assert [r.receipt_no for r in head.receipts] == ["1", "2", "3", "4"]
    assert head.by_tender == {"cash": 15_000, "gcash": 12_950}


def test_receipts_today_by_tender(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _day(session, rs, monkeypatch)
    kiosk, marites = rs[0], rs[1]["Marites"]
    out = ss_tools.receipts(ss_deps(session, marites), ss_tools.ReceiptsInput(), "c")
    assert ([r.receipt_no for r in out.receipts], out.by_tender, out.total) == (
        ["1", "2", "3"], {"cash": 12_500, "gcash": 12_950}, 25_450,
    )  # fmt: skip
    assert out.by_tender == sales.day_sales(session, kiosk.id, RS_TODAY).by_tender


@pytest.mark.usefixtures("ss_jev")
def test_the_receipts_reply_counts_the_paid_ones_by_tender(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _day(session, rs, monkeypatch)
    ss_answers(monkeypatch, "read_receipts", conversation="other")
    reply = _turn(session, rs[1]["Marites"], "resibo ngayon")
    tenders = ", ".join(
        t("sales.receipts.tender", "fil", tender=t(f"bk.tender.{x}", "fil"), amount=money(a))
        for x, a in (("cash", 12_500), ("gcash", 12_950))
    )
    assert reply.text() == t(
        "sales.receipts.today", "fil", branch=rs[0].name, count="2", total=money(25_450),
        tenders=tenders,
    )  # fmt: skip


@pytest.mark.usefixtures("ss_jev")
def test_the_last_receipt_says_it_was_voided(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _day(session, rs, monkeypatch)
    ss_answers(monkeypatch, "read_receipts", receipts_which="last", conversation="other")
    reply = _turn(session, rs[1]["Ana"], "huling resibo")
    assert reply.text() == t(
        "sales.receipts.last_voided", "fil", no="3", time="12:05", lines="3 Ube",
        total=money(13_500), tender=t("bk.tender.cash", "fil"),
    )  # fmt: skip


@pytest.mark.usefixtures("ss_jev")
def test_no_receipts_yet_says_so(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    ss_answers(monkeypatch, "read_receipts", conversation="other")
    reply = _turn(session, rs[1]["Ana"], "resibo ngayon")
    assert reply.text() == t("sales.receipts.today_empty", "fil", branch=rs[0].name)


def test_sales_today_reads_receipts_on_a_receipts_kiosk(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _day(session, rs, monkeypatch)
    out = ss_tools.today(ss_deps(session, rs[1]["Marites"]), ss_tools.TodayInput(), "c")
    (day,) = out.branches
    assert [(i.item, i.quantity, i.amount) for i in day.items] == [
        ("Special", 1, 4_950), ("Classic", 4, 16_000), ("Ube", 1, 4_500),
    ]  # fmt: skip
    assert day.total == 25_450


def _kiosk_report(session: Session, rs: Ferinos) -> list[str]:
    return [m for m in told(session, rs[1]["Rosa"]) if rs[0].name in m]


def test_the_owners_report_reads_receipts(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _day(session, rs, monkeypatch)
    ss_due.run_due(session, at(RS_TODAY, 22, 5))
    (line,) = _kiosk_report(session, rs)
    assert money(25_450) in line and "4 Classic" in line


def test_the_closing_reminder_skips_a_receipts_kiosk(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    for tick in (at(RS_TODAY, 20, 35), at(RS_TODAY, 21, 35)):
        ss_due.run_due(session, tick)
    marked = session.exec(
        select(Event).where(
            col(Event.action).in_([ss_due.REMINDER, ss_due.MISSING]), Event.entity_id == rs[0].id
        )
    ).all()
    assert marked == []


def test_the_closing_reminder_still_runs_on_a_counts_kiosk(session: Session, rs: Ferinos) -> None:
    for tick in (at(RS_TODAY, 20, 35), at(RS_TODAY, 21, 35)):
        ss_due.run_due(session, tick)
    marked = session.exec(
        select(Event).where(
            col(Event.action).in_([ss_due.REMINDER, ss_due.MISSING]), Event.entity_id == rs[0].id
        )
    ).all()
    assert marked != []


def test_tender_sales_reads_the_receipts(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _day(session, rs, monkeypatch)
    kiosk = rs[0]
    assert bk_tools.tender_sales(session, kiosk.id, "gcash", RS_TODAY, RS_TODAY) == 12_950
    assert bk_tools.tender_sales(session, kiosk.id, None, RS_TODAY, RS_TODAY) == 25_450


@pytest.mark.usefixtures("ss_jev")
def test_a_refund_naming_an_item_jev_did_not_pick_asks_which_items(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scenario(session, rs, monkeypatch)
    ss_answers(monkeypatch, "refund_receipt", conversation="other")  # item: not stated
    reply = _turn(session, rs[1]["Ana"], "refund ube resibo 1")
    assert reply.text() == t("sales.refund.which_items", "fil", no="1")
    assert _cards(session, sales.REFUND) == []


# ---- Task 5: the receipt tables checked wherever day_sales reads them; the reads' wording ----

BK_CALLS: dict[str, Callable[[AgentDeps], object]] = {
    "record_cash_count": lambda d: bk_tools.record_cash_count(
        d, CashCountInput(counted=100_000), "c"
    ),
    "record_settlement": lambda d: bk_tools.record_settlement(
        d, bk_tools.SettlementInput(provider="gcash", amount=0, start=RS_TODAY, end=RS_TODAY), "c"
    ),
    "record_payout": lambda d: bk_tools.record_payout(
        d, bk_tools.PayoutInput(provider="grab", amount=0, start=RS_TODAY, end=RS_TODAY), "c"
    ),
    "sales_journal": lambda d: bk_tools.sales_journal(
        d, bk_tools.JournalInput(month=RS_TODAY), "c"
    ),
    "tax_quarter": lambda d: bk_tools.tax_quarter(
        d, bk_tools.TaxInput(quarter_start=RS_TODAY), "c"
    ),
    "monthly_profit": lambda d: bk_tools.monthly_profit(
        d, bk_tools.ProfitInput(month=RS_TODAY), "c"
    ),
}
RECEIPT_TABLE_NAMES = ("sales_receipts", "sales_receipt_lines", "sales_payments")


@pytest.mark.parametrize("table", RECEIPT_TABLE_NAMES)
@pytest.mark.parametrize("tool", sorted(BK_CALLS))
def test_the_bookkeeper_tools_over_tender_sales_check_the_receipt_tables(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin,
    tool: str, table: str,
) -> None:  # fmt: skip
    """tender_sales reads day_sales, the receipt tables on a receipts day: each tool over it
    checks all three, so a denied one stops the tool before any write."""
    receipts_kiosk(monkeypatch)
    drawer(session, rs)
    rs_pin(at(RS_TODAY, 17, 5))
    written = select(Event).where(~col(Event.action).startswith("rbac."))
    before = len(session.exec(written).all())
    monkeypatch.setattr(get_rbac(), "require", _deny_on(table))
    with pytest.raises(PermissionDenied):
        BK_CALLS[tool](bk_deps(session, rs[1]["Rosa"]))
    assert len(session.exec(written).all()) == before  # only the checks' own audit rows


@pytest.mark.parametrize("tool", sorted(BK_CALLS))
def test_the_bookkeeper_manifest_declares_the_receipt_reads(tool: str) -> None:
    from mia.agents.bookkeeper import MANIFEST as BK

    (spec,) = [s for s in BK.tools if s.name == tool]
    assert set(RECEIPT_TABLE_NAMES) <= set(spec.reads), spec.reads


@pytest.mark.parametrize("table", RECEIPT_TABLE_NAMES)
def test_sales_today_checks_every_receipt_table(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, table: str
) -> None:
    _day(session, rs, monkeypatch)
    monkeypatch.setattr(get_rbac(), "require", _deny_on(table))
    with pytest.raises(PermissionDenied):
        ss_tools.today(ss_deps(session, rs[1]["Marites"]), ss_tools.TodayInput(), "c")


def _receipts_out(kind: str, status: str, total: int) -> ss_tools.ReceiptsOutput:
    line = ss_tools.ReceiptLineOut(
        item_id="u", item="Ube", quantity=-1 if kind == "refund" else 1, unit_price=4_500,
        line_total=total,
    )  # fmt: skip
    r = ss_tools.ReceiptOut(
        receipt_no="4", kind=kind, status=status, time="15:00", lines=[line], total=total,
        tender="cash", currency="PHP",
    )  # fmt: skip
    paid = {"cash": total} if status == "paid" else {}
    return ss_tools.ReceiptsOutput(
        branch="Mall kiosk", receipts=[r], by_tender=paid, total=total, currency="PHP"
    )


def test_an_all_voided_day_says_no_receipts_yet() -> None:
    blocks = ss_replies.receipts_read(_receipts_out("sale", "voided", 4_500), "today", "fil")
    assert [b.text for b in blocks if isinstance(b, TextBlock)] == [
        t("sales.receipts.today_empty", "fil", branch="Mall kiosk")
    ]


def test_the_last_receipt_says_it_is_a_refund() -> None:
    blocks = ss_replies.receipts_read(_receipts_out("refund", "paid", -4_500), "last", "fil")
    assert [b.text for b in blocks if isinstance(b, TextBlock)] == [
        t(
            "sales.receipts.last_refund", "fil", no="4", time="15:00", lines="1 Ube",
            total=money(4_500), tender=t("bk.tender.cash", "fil"),
        )
    ]  # fmt: skip


# ---- the final wave ---------------------------------------------------------------------------


def _two_drawers_at_bk(session: Session, bk_en: Ferinos, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Mall kiosk on receipts from BK_TODAY with Ana's drawer open at 9:00 and Liza's at
    13:00 (committed)."""
    settings = orgconfig.load().model_copy(deep=True)
    settings.sales.receipts_from = {"Mall kiosk": BK_TODAY}
    monkeypatch.setattr(orgconfig, "load", lambda org=None: settings)
    kiosk, people = bk_en
    for who, hh in (("Ana", 9), ("Liza", 13)):
        p = people[who]
        when = dt.datetime.combine(BK_TODAY, dt.time(hh), MNL)
        sales.open_for_shift(session, Actor.person(p), kiosk, p.id, None, when)
    session.commit()


def _state(session: Session, who: Person) -> str:
    return session.exec(select(SalesSession).where(SalesSession.person_id == who.id)).one().state


@pytest.mark.usefixtures("jev_on")
def test_a_recount_asks_which_drawer_and_never_closes_the_next_clerks(
    session: Session, bk_en: Ferinos, monkeypatch: pytest.MonkeyPatch, bk_pin: Pin
) -> None:
    """C1: the probe's three turns. Two drawers open: the count asks whose; the correction
    says the count is final; the recount asks again and Liza's drawer stays open."""
    _two_drawers_at_bk(session, bk_en, monkeypatch)
    people, other = bk_en[1], t("clarify.something_else", "en")
    bk_pin(at(BK_TODAY, 21, 20))
    _answers(monkeypatch, "cash_count", amount="p0")
    asked = _turn(session, people["Marites"], "cash count 1000")
    assert asked.blocks[0].text == t(  # type: ignore[union-attr]
        "bk.count.which_drawer", "en", counted=bk_replies.money(100_000, "PHP", "en")
    )
    assert _buttons(asked) == ["Ana", "Liza", other]
    assert (_state(session, people["Ana"]), _state(session, people["Liza"])) == ("open", "open")
    _turn(session, people["Marites"], "Ana", asked.thread_id)
    assert (_state(session, people["Ana"]), _state(session, people["Liza"])) == ("closed", "open")
    counts = len(session.exec(select(CashCount)).all())
    text = _turn(session, people["Marites"], "hindi 1000, 1100").text()
    assert text == t("bk.correction.receipts", "en")
    again = _turn(session, people["Marites"], "cash count 1100")
    assert _buttons(again) == ["Liza", other]
    assert _state(session, people["Liza"]) == "open"
    assert len(session.exec(select(CashCount)).all()) == counts


def test_the_count_tool_asks_whose_drawer_when_two_are_open_or_the_date_has_a_count(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    receipts_kiosk(monkeypatch)
    ana, liza = drawer(session, rs, "Ana", 9), drawer(session, rs, "Liza", 13)
    rs_pin(at(RS_TODAY, 17, 5))
    deps = bk_deps(session, rs[1]["Marites"])
    with pytest.raises(LookupError, match="which_drawer"):
        bk_tools.record_cash_count(deps, CashCountInput(counted=100_000), "c")
    bk_tools.record_cash_count(deps, CashCountInput(counted=100_000, drawer=ana.id), "c")
    with pytest.raises(LookupError, match="which_drawer"):  # one open, but the date has a count
        bk_tools.record_cash_count(deps, CashCountInput(counted=100_000), "c")
    session.refresh(liza)
    assert liza.state == "open"


def _cover(
    session: Session, rs: Ferinos, absent: str, cover: str, day: dt.date, head: str
) -> Visit:
    """cover takes absent's visit of day (assigned by head the day before, approved by Rosa,
    accepted); returns the visit."""
    people = rs[1]
    visit = visit_of(session, people[absent], day)
    before = day - dt.timedelta(days=1)
    approval = shift_tools.assign_cover(
        shift_deps(session, people[head], before),
        AssignCoverInput(visit_id=visit.id, candidate_id=people[cover].id),
        "a",
    ).approval_id
    if approval is not None:
        shift_decide(session, approval, people["Rosa"], "approved")
    shift_tools.respond_to_cover(
        shift_deps(session, people[cover], before), RespondToCoverInput(accept=True), "y"
    )
    return visit


@pytest.mark.usefixtures("ss_jev")
def test_a_covering_clerks_receipt_lands_at_the_visits_kiosk(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I1: Pao (Street stall) covers Ana's Tuesday at the Mall kiosk, on receipts."""
    receipts_kiosk(monkeypatch)
    pao = rs[1]["Pao"]
    rs_pin(at(MONDAY, 12))
    _cover(session, rs, "Ana", "Pao", TUESDAY, "Marites")
    rs_pin(at(TUESDAY, 8, 50))
    shift_tools.check_in(shift_deps(session, pao, TUESDAY), CheckInInput(), "c")
    session.commit()
    rs_pin(at(TUESDAY, 10))
    ss_answers(monkeypatch, "record_receipt", item_0=item(session, "Ube").id, conversation="other")
    _turn(session, pao, "r 3 ube cash")
    (r,) = _receipts(session)
    assert (r.branch_id, r.total) == (rs[0].id, 13_500)
    mine = select(SalesCount).where(SalesCount.reported_by == pao.id)
    assert [c for c in session.exec(mine) if c.business_date == TUESDAY] == []


@pytest.mark.usefixtures("ss_jev")
def test_a_covering_clerks_void_goes_to_the_visits_kiosk(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pao (Street stall home) covers the Mall kiosk and voids a Mall receipt: the approval is
    the Mall's, its card goes to Marites (Mall), not Jun (Street); Jun cannot decide it,
    Pao never decides his own, Marites can."""
    receipts_kiosk(monkeypatch)
    people = rs[1]
    pao, jun, marites = people["Pao"], people["Jun"], people["Marites"]
    rs_pin(at(MONDAY, 12))
    _cover(session, rs, "Ana", "Pao", TUESDAY, "Marites")
    rs_pin(at(TUESDAY, 8, 50))
    shift_tools.check_in(shift_deps(session, pao, TUESDAY), CheckInInput(), "c")
    session.commit()
    rs_pin(at(TUESDAY, 10))
    ss_answers(monkeypatch, "record_receipt", item_0=item(session, "Ube").id, conversation="other")
    _turn(session, pao, "r 3 ube cash")
    (r,) = _receipts(session)
    before = {p.id: len(told(session, p)) for p in (jun, marites)}
    deps = ss_tools.at_visit(dataclasses.replace(ss_deps(session, pao), today=TUESDAY))
    args = VoidReceiptInput(receipt_no=r.receipt_no, reason="mali")
    out = call_tool(deps, ss_binding("void_receipt"), args, "c")
    session.commit()
    a = session.get(Approval, out["approval_id"])
    assert a is not None and a.branch_id == rs[0].id == r.branch_id != pao.branch_id
    assert len(told(session, marites)) == before[marites.id] + 1
    assert len(told(session, jun)) == before[jun.id]
    for who in (jun, pao):
        with pytest.raises(ApprovalError):
            _decide(session, a.id, who)
    _decide(session, a.id, marites)
    session.refresh(r)
    assert (r.status, r.voided_by) == ("voided", marites.id)


@pytest.mark.usefixtures("ss_jev")
def test_a_receipts_clerk_covering_a_counts_stall_reports_counts_there(
    session: Session, rs: Ferinos, rs_pin: Pin, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I1, the reverse: Ana (Mall kiosk, on receipts) covers Pao's Monday at the Street stall,
    on counts. Her count lands at the stall; no "check in first"."""
    receipts_kiosk(monkeypatch)
    ana = rs[1]["Ana"]
    visit = visit_of(session, rs[1]["Pao"], MONDAY)
    scheduling._apply(session, Actor.person(rs[1]["Jun"]), visit, ana, False)  # the cover, set
    rs_pin(at(MONDAY, 6, 5))
    shift_tools.check_in(shift_deps(session, ana, MONDAY), CheckInInput(), "c")
    session.commit()
    rs_pin(at(MONDAY, 10))
    ss_answers(monkeypatch, "report_sales", item_0=item(session, "Ube").id, conversation="other")
    reply = _turn(session, ana, "3 ube cash")
    assert reply.text() != t("sales.receipt.no_session", "fil")
    mine = select(SalesCount).where(SalesCount.reported_by == ana.id)
    rows = [c for c in session.exec(mine) if c.business_date == MONDAY]
    assert [(c.branch_id, c.quantity) for c in rows] == [(visit.branch_id, 3)]
    assert _receipts(session) == []


PRE_PLAN_ACTIONS = [
    "report_sales", "correct_sales", "sales_today", "sales_period", "item_codes", "set_target",
    "why_answer", "reply_only", "clarify",
]  # fmt: skip  # item_codes: a read every kiosk offers, added after the plan on purpose
PRE_PLAN_QUESTIONS = {"period", "branch", "target_period", "target_start", "conversation"}
RECEIPT_ACTIONS = ["record_receipt", "void_receipt", "refund_receipt", "read_receipts"]


@pytest.mark.parametrize("kiosk", ["counts", "receipts"])
def test_a_counts_kiosks_request_is_the_pre_plan_one(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, kiosk: str
) -> None:
    """I2: a counts kiosk's Jev request offers the actions and questions it offered before the
    receipts plan; a receipts kiosk adds the receipt actions and receipts_which."""
    if kiosk == "receipts":
        receipts_kiosk(monkeypatch)
    extra = RECEIPT_ACTIONS if kiosk == "receipts" else []
    for mode in ("choice", "nouls"):
        monkeypatch.setenv("MIA_SALES_QUESTION", mode)
        get_settings.cache_clear()
        q = build_query(ss_deps(session, rs[1]["Ana"]), "3 ube", "")
        questions = actions_mod.build_request(q, "m")["questions"]
        if mode == "choice":
            offered = list(questions["action"]["criteria"])
            want = [*PRE_PLAN_ACTIONS[:1], *extra, *PRE_PLAN_ACTIONS[1:]]
        else:
            offered = [k.removeprefix("is_") for k in questions if k.startswith("is_")]
            want = [a for a in [*PRE_PLAN_ACTIONS[:1], *extra, *PRE_PLAN_ACTIONS[1:]]]
            want = [a for a in want if a in actions_mod.NOULS]
        assert offered == want
        rest = {k for k in questions if k != "action" and not k.startswith(("is_", "item"))}
        assert rest == PRE_PLAN_QUESTIONS | ({"receipts_which"} if extra else set())
    get_settings.cache_clear()


@pytest.mark.usefixtures("ss_jev")
@pytest.mark.parametrize(
    ("text", "picks"),
    [
        ("cash 3 ube", {"item_0": "Ube"}),
        ("cl 20 ube 15 sp 8 cash", {"item_0": "Classic", "item_1": "Ube", "item_2": "Special"}),
    ],
)
def test_a_count_on_a_receipts_kiosk_asks_before_ringing_one_receipt(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, text: str,
    picks: dict[str, str],
) -> None:  # fmt: skip
    """I3: a count with a tender and no receipt word on a receipts kiosk asks with the computed
    receipt on a confirm button; the tap rings it."""
    _open_drawer(session, rs, monkeypatch)
    ids = {k: item(session, v).id for k, v in picks.items()}
    ss_answers(monkeypatch, "report_sales", conversation="other", **ids)
    asked = _turn(session, rs[1]["Ana"], text)
    assert _receipts(session) == []
    total = sum(
        g * price_on(session, item(session, n), rs[0].id, RS_TODAY)
        for g, n in zip([int(w) for w in text.split() if w.isdigit()], picks.values(), strict=True)
    )
    shown = ", ".join(f"{g} {n}" for g, n in zip(
        [int(w) for w in text.split() if w.isdigit()], picks.values(), strict=True
    ))  # fmt: skip
    assert asked.blocks[0].text == t(  # type: ignore[union-attr]
        "sales.receipt.confirm_one", "fil", lines=shown, total=money(total)
    )
    use = t("sales.receipt.use_computed", "fil", total=money(total))
    assert _buttons(asked) == [use, t("clarify.something_else", "fil")]
    _turn(session, rs[1]["Ana"], use, asked.thread_id)
    (r,) = _receipts(session)
    assert r.total == total


@pytest.mark.usefixtures("ss_jev")
def test_a_count_with_a_receipt_word_still_rings_without_asking(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_drawer(session, rs, monkeypatch)
    ss_answers(monkeypatch, "report_sales", item_0=item(session, "Ube").id, conversation="other")
    _turn(session, rs[1]["Ana"], "resibo 3 ube cash")
    (r,) = _receipts(session)
    assert r.total == 13_500


def test_the_sales_journal_reads_a_receipts_day(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 5 must-fix 1: the BIR sales book shows a receipts day by tender (#3 voided)."""
    _day(session, rs, monkeypatch)
    out = bk_tools.sales_journal(
        bk_deps(session, rs[1]["Rosa"]), bk_tools.JournalInput(month=RS_TODAY), "c"
    )
    assert out.days[RS_TODAY] == {"cash": 12_500, "gcash": 12_950}


def test_the_cost_of_goods_reads_a_receipts_day(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 5 must-fix 2: units sold come from the receipts (Classic 2400, Special 2800)."""
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    ring(session, rs, s, "1", [("Classic", 2)], "cash")
    ring(session, rs, s, "2", [("Special", 1)], "gcash", hh=11)
    goods, _ = bk_tools._at_cost(session, rs[0].id, RS_TODAY, RS_TODAY)
    assert goods == 2 * 2400 + 2800


def test_today_counts_the_sales_not_the_refunds() -> None:
    """A day of one sale and one refund says one receipt, the total net."""
    sale = _receipts_out("sale", "paid", 13_500)
    refund = _receipts_out("refund", "paid", -4_500)
    out = sale.model_copy(
        update={
            "receipts": sale.receipts + refund.receipts,
            "total": 9_000,
            "by_tender": {"cash": 9_000},
        }
    )
    tenders = t(
        "sales.receipts.tender", "fil", tender=t("bk.tender.cash", "fil"), amount=money(9_000)
    )
    assert [
        b.text for b in ss_replies.receipts_read(out, "today", "fil") if isinstance(b, TextBlock)
    ] == [
        t(
            "sales.receipts.today",
            "fil",
            branch="Mall kiosk",
            count="1",
            total=money(9_000),
            tenders=tenders,
        )
    ]


# ---- the final wave, round 2 ------------------------------------------------------------------


@pytest.mark.usefixtures("jev_on")
def test_two_clerks_with_one_first_name_get_a_button_each(
    session: Session, bk_en: Ferinos, monkeypatch: pytest.MonkeyPatch, bk_pin: Pin
) -> None:
    """Ana (9:00) and a second Ana (13:00) each get a button with the drawer's open time; the
    first closes the earlier drawer only."""
    settings = orgconfig.load().model_copy(deep=True)
    settings.sales.receipts_from = {"Mall kiosk": BK_TODAY}
    monkeypatch.setattr(orgconfig, "load", lambda org=None: settings)
    kiosk, people = bk_en
    rosa = Actor.person(people["Rosa"])
    other_ana = add_person(
        session, rosa, branch_id=kiosk.id, name="Ana Reyes", roles=["clerk"], language="en"
    )
    for p, hh in ((people["Ana"], 9), (other_ana, 13)):
        when = dt.datetime.combine(BK_TODAY, dt.time(hh), MNL)
        sales.open_for_shift(session, Actor.person(p), kiosk, p.id, None, when)
    session.commit()
    bk_pin(at(BK_TODAY, 21, 20))
    _answers(monkeypatch, "cash_count", amount="p0")
    asked = _turn(session, people["Marites"], "cash count 1000")
    assert _buttons(asked) == ["Ana 09:00", "Ana 13:00", t("clarify.something_else", "en")]
    _turn(session, people["Marites"], "Ana 09:00", asked.thread_id)
    assert (_state(session, people["Ana"]), _state(session, other_ana)) == ("closed", "open")


def test_the_drawer_reads_run_under_the_write_lock(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    """Rule 11: which drawers are open and whether the date has a count decide the close and
    the drawer_out taken, so both are read after events.write_lock."""
    receipts_kiosk(monkeypatch)
    drawer(session, rs)
    rs_pin(at(RS_TODAY, 17, 5))
    locked: list[bool] = []
    real_lock, real_open = events.write_lock, sales.open_sessions

    def lock(db: Session) -> None:
        # taken by _close_drawer itself (an audit row's emit locks too, but only by chance)
        locked.append(sys._getframe(1).f_code.co_name == "_close_drawer")
        real_lock(db)

    def open_sessions(db: Session, branch_id: str) -> list[SalesSession]:
        assert any(locked) and db.in_transaction()  # read under the write lock
        return real_open(db, branch_id)

    monkeypatch.setattr(events, "write_lock", lock)
    monkeypatch.setattr(sales, "open_sessions", open_sessions)
    out = bk_tools.record_cash_count(
        bk_deps(session, rs[1]["Marites"]), CashCountInput(counted=100_000), "c"
    )
    assert out.clerk == "Ana"
