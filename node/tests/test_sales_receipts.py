"""Sales receipts in the chat (plan 2026-10-22-sales-receipts-chat): a clerk's check-in opens her
sales session on a receipts kiosk and the bookkeeper's closing count closes it. The shared
helpers here (receipts_kiosk, drawer, ring, money) are imported by the later tasks' tests."""

import datetime as dt
from collections.abc import Callable

import pytest
from sqlmodel import Session, select

from mia.agents.base import ToolBinding, call_tool
from mia.agents.bookkeeper import replies as bk_replies
from mia.agents.bookkeeper import tools as bk_tools
from mia.agents.bookkeeper.models import CashCount
from mia.agents.bookkeeper.tools import CashCountInput, ExpenseInput
from mia.agents.shift_supervisor import replies as shift_replies
from mia.agents.shift_supervisor import tools as shift_tools
from mia.agents.shift_supervisor.rules import fmt_date
from mia.agents.shift_supervisor.tools import AssignCoverInput, CheckInInput, RespondToCoverInput
from mia.chat.blocks import TextBlock
from mia.core import orgconfig, sales
from mia.core.models import Actor, Person, SalesReceipt, SalesSession
from mia.core.money import format_money
from mia.core.rbac import PermissionDenied, Rbac, Resource, get_rbac
from mia.core.sales import LineIn, PaymentIn
from mia.i18n import t
from mia.templates.retail.items import price_on
from tests.conftest import BK_TODAY, RS_TODAY, Pin
from tests.test_bookkeeper_chat import _answers, _turn, jev_on  # noqa: F401 (a fixture)
from tests.test_bookkeeper_tools import deps_for as bk_deps
from tests.test_data_standard_1_7 import MONDAY, TUESDAY, Ferinos, at, visit_of
from tests.test_data_standard_1_9 import MNL, item
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
        at(RS_TODAY, hh),
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


def test_the_count_closes_the_earliest_open_drawer_and_names_the_others(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch, rs_pin: Pin
) -> None:
    receipts_kiosk(monkeypatch)
    ana, liza = drawer(session, rs, "Ana", 9), drawer(session, rs, "Liza", 13)
    rs_pin(at(RS_TODAY, 17, 5))
    out = bk_tools.record_cash_count(
        bk_deps(session, rs[1]["Marites"]), CashCountInput(counted=100_000), "c"
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
    bk_tools.record_cash_count(deps, CashCountInput(counted=112_500), "c")
    rs_pin(at(RS_TODAY, 21, 5))
    bk_tools.record_cash_count(deps, CashCountInput(counted=105_000), "c")
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
    first = bk_tools.record_cash_count(deps, CashCountInput(counted=110_500), "c")
    rs_pin(at(RS_TODAY, 21, 5))
    second = bk_tools.record_cash_count(deps, CashCountInput(counted=102_000), "c")
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


@pytest.mark.usefixtures("jev_on")
def test_a_correction_on_a_receipts_day_writes_nothing(
    session: Session, bk_en: Ferinos, monkeypatch: pytest.MonkeyPatch, bk_pin: Pin
) -> None:
    settings = orgconfig.load().model_copy(deep=True)
    settings.sales.receipts_from = {"Mall kiosk": BK_TODAY}
    monkeypatch.setattr(orgconfig, "load", lambda org=None: settings)
    kiosk, people = bk_en
    for who, hh in (("Ana", 9), ("Liza", 13)):
        p = people[who]
        sales.open_for_shift(
            session,
            Actor.person(p),
            kiosk,
            p.id,
            None,
            dt.datetime.combine(BK_TODAY, dt.time(hh), MNL),
        )
    session.commit()
    bk_pin(at(BK_TODAY, 21, 20))
    _answers(monkeypatch, "cash_count", amount="p0")
    _turn(session, people["Marites"], "cash count 1000")
    counts = len(session.exec(select(CashCount)).all())
    text = _turn(session, people["Marites"], "hindi 1000, 1100").text()
    assert text == t("bk.correction.ask", "en")
    assert len(session.exec(select(CashCount)).all()) == counts
    liza = select(SalesSession).where(SalesSession.person_id == people["Liza"].id)
    assert session.exec(liza).one().state == "open"


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
