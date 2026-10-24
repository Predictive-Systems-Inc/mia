"""Report questions, Task 1 (plan 2026-10-24-report-questions, teach-Mia 4c, D49): the report
form, its validator and the executor run by code over day_sales, with period_report's rbac and
a clerk's own kiosk only."""

import dataclasses
import datetime as dt
from collections.abc import Callable

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from mia.agents.base import AgentDeps, call_tool
from mia.agents.sales_supervisor import replies, tools
from mia.agents.sales_supervisor.report import (
    Line,
    ReportError,
    ReportForm,
    Result,
    compared,
    resolve,
)
from mia.agents.sales_supervisor.tools import PeriodReportInput, ReportInput
from mia.chat.blocks import TextBlock
from mia.core import sales
from mia.core.models import TENDERS, Branch, Person
from mia.core.money import format_money
from mia.core.rbac import PermissionDenied
from mia.i18n import t
from tests.conftest import RS_TODAY
from tests.test_sales_receipts import drawer, receipts_kiosk, ring
from tests.test_sales_tools import deps_for

Ferinos = tuple[Branch, dict[str, Person]]
BINDING = next(b for b in tools.BINDINGS if b.tool_id.endswith(".report"))


def ss_deps(session: Session, person: Person) -> AgentDeps:
    return dataclasses.replace(deps_for(session, person), today=RS_TODAY)


def stall(session: Session) -> Branch:
    return session.exec(select(Branch).where(Branch.name == "Street stall")).one()


def _code(call: Callable[[], object]) -> str:
    with pytest.raises(ReportError) as exc:
        call()
    return exc.value.code


def _run(session: Session, person: Person, form: ReportForm) -> Result:
    return tools.report(ss_deps(session, person), ReportInput(form=form), "c").result


def test_bad_forms_are_refused() -> None:
    bad = [
        ReportForm(measure="pieces", start=dt.date(2025, 1, 1), end=RS_TODAY),  # range
        ReportForm(measure="amount", start=RS_TODAY, end=RS_TODAY - dt.timedelta(days=1)),
        ReportForm(measure="amount", start=RS_TODAY, end=RS_TODAY + dt.timedelta(days=1)),
        ReportForm(measure="pieces", period="last_week", group_by="tender"),  # combo
        ReportForm(measure="amount", period="last_week", group_by="item", tenders=["gcash"]),
        ReportForm(measure="amount", period="next_year"),  # period
    ]
    codes = [_code(lambda f=f: resolve(f, RS_TODAY, "en")) for f in bad]
    assert codes == ["range", "order", "future", "combo", "combo", "period"]
    with pytest.raises(ValidationError):
        ReportForm.model_validate({"measure": "amount", "period": "last_week", "total": 5})
    with pytest.raises(ValidationError):  # neither a period nor both dates
        ReportForm.model_validate({"measure": "amount", "start": "2026-10-01"})
    long = ReportForm(measure="amount", start=dt.date(2026, 3, 1), end=RS_TODAY)
    assert _code(lambda: resolve(long.model_copy(update={"compare_to": "previous_period"}),
                                 RS_TODAY, "en")) == "range"  # fmt: skip
    assert resolve(long, RS_TODAY, "en") == (dt.date(2026, 3, 1), RS_TODAY)


def test_named_periods_resolve_and_end_today() -> None:
    week = ReportForm(measure="amount", period="last_week")
    assert resolve(week, RS_TODAY, "en") == (dt.date(2026, 10, 19), dt.date(2026, 10, 25))
    this_week = ReportForm(measure="amount", period="this_week")
    assert resolve(this_week, RS_TODAY, "en") == (dt.date(2026, 10, 26), RS_TODAY)


def test_compared_ranges() -> None:
    assert compared(dt.date(2026, 10, 19), dt.date(2026, 10, 25), "previous_period") == (
        dt.date(2026, 10, 12),
        dt.date(2026, 10, 18),
    )
    assert compared(dt.date(2028, 2, 29), dt.date(2028, 2, 29), "same_period_last_year") == (
        dt.date(2027, 2, 28),
        dt.date(2027, 2, 28),
    )
    assert compared(RS_TODAY, RS_TODAY, "none") is None


def test_report_sums_equal_period_report(session: Session, rs: Ferinos) -> None:
    people = rs[1]
    out = _run(session, people["Marites"], ReportForm(measure="amount", period="last_week",
                                                      group_by="item"))  # fmt: skip
    args = PeriodReportInput(
        start=dt.date(2026, 10, 19), end=dt.date(2026, 10, 25), breakdown="item"
    )
    rep = tools.period_report(ss_deps(session, people["Marites"]), args, "c")
    assert [(x.name, x.quantity, x.amount) for x in out.lines] == [
        (b.name, b.quantity, b.amount) for b in rep.breakdown
    ]
    assert out.total == rep.total and out.currency == rep.currency and rep.total > 0
    assert (out.start, out.end) == (args.start, args.end)
    pieces = _run(session, people["Marites"], ReportForm(measure="pieces", period="last_week"))
    assert pieces.lines == [] and pieces.total == sum(b.quantity for b in rep.breakdown)


def test_report_sums_on_a_receipts_day(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    ring(session, rs, s, "1", [("Special", 2)], "cash")
    ring(session, rs, s, "2", [("Ube", 1), ("Classic", 3)], "gcash", hh=11)
    form = ReportForm(measure="amount", period="today", group_by="tender")
    out = _run(session, rs[1]["Rosa"], form)
    by_tender = sales.day_sales(session, rs[0].id, RS_TODAY).by_tender
    assert [(x.name, x.amount) for x in out.lines] == [
        (k, by_tender[k]) for k in TENDERS if k in by_tender
    ]
    assert out.total == sum(by_tender.values())
    gcash = _run(session, rs[1]["Rosa"], form.model_copy(update={"tenders": ["gcash"]}))
    assert [(x.name, x.amount) for x in gcash.lines] == [("gcash", by_tender["gcash"])]


def test_kiosk_grouping_needs_read_all(session: Session, rs: Ferinos) -> None:
    people = rs[1]
    form = ReportForm(measure="amount", period="last_week", group_by="kiosk")
    with pytest.raises(PermissionDenied):
        _run(session, people["Marites"], form)
    out = _run(session, people["Rosa"], form)
    assert {x.name for x in out.lines} == {"Mall kiosk", "Street stall"}
    assert sum(x.amount for x in out.lines) == out.total
    assert out.lines[0].amount >= out.lines[1].amount  # largest first


def test_clerk_grouping_needs_read(session: Session, rs: Ferinos) -> None:
    people = rs[1]
    form = ReportForm(measure="pieces", period="last_week", group_by="clerk")
    out = _run(session, people["Rosa"], form)
    assert out.lines and {x.name for x in out.lines} <= {p.name for p in people.values()}
    with pytest.raises(PermissionDenied):  # a clerk holds read_own on sales_counts only
        _run(session, people["Ana"], form)


def test_a_clerk_reads_her_own_kiosk_only(session: Session, rs: Ferinos) -> None:
    """D49: a clerk asks report questions about her own kiosk; never another kiosk, every
    kiosk or another clerk's figures."""
    people, street = rs[1], stall(session)
    pao = ss_deps(session, people["Pao"])
    form = ReportForm(measure="amount", period="last_week", group_by="item")
    out = call_tool(pao, BINDING, ReportInput(form=form), "c1")
    args = PeriodReportInput(
        start=dt.date(2026, 10, 19), end=dt.date(2026, 10, 25), branch_id=street.id,
        breakdown="item",
    )  # fmt: skip
    rep = tools.period_report(ss_deps(session, people["Rosa"]), args, "c")
    assert out["result"]["total"] == rep.total > 0
    assert [x["amount"] for x in out["result"]["lines"]] == [b.amount for b in rep.breakdown]
    for refused in (
        form.model_copy(update={"kiosks": [rs[0].id]}),  # the Mall kiosk
        form.model_copy(update={"kiosks": ["all"]}),
        form.model_copy(update={"group_by": "kiosk"}),
        form.model_copy(update={"group_by": "clerk"}),
    ):
        assert call_tool(pao, BINDING, ReportInput(form=refused), "c2")["status"] == "denied"


def test_an_unknown_item_or_bad_range_is_invalid(session: Session, rs: Ferinos) -> None:
    rosa = ss_deps(session, rs[1]["Rosa"])
    unknown = ReportForm(measure="amount", period="last_week", items=["nope"])
    long = ReportForm(measure="amount", start=dt.date(2025, 1, 1), end=RS_TODAY)
    assert call_tool(rosa, BINDING, ReportInput(form=unknown), "c")["message"] == "form"
    assert call_tool(rosa, BINDING, ReportInput(form=long), "c")["message"] == "range"


def _result(lines: list[Line], **kw: object) -> Result:
    base: dict[str, object] = {
        "head_measure": "amount",
        "group_by": "item",
        "start": dt.date(2026, 10, 19),
        "end": dt.date(2026, 10, 25),
        "lines": lines,
        "total": sum(x.amount for x in lines),
        "total_before": None,
        "currency": "PHP",
    }
    return Result.model_validate({**base, **kw})


def test_report_text_shows_ten_then_more() -> None:
    lines = [Line(name=f"Item {n}", quantity=n, amount=100 * n) for n in range(12, 0, -1)]
    (block,) = replies.report_text(_result(lines), "en")
    assert isinstance(block, TextBlock)
    rows = block.text.split("\n")
    by = t("sales.report.by", "en", group=t("sales.report.group.item", "en"))
    assert rows[0] == t(
        "sales.report.head", "en", measure=t("sales.report.measure.amount", "en"),
        start="2026-10-19", end="2026-10-25", by=by, total=format_money(7800, "PHP", "en"),
    )  # fmt: skip
    assert rows[1] == t("sales.report.row", "en", name="Item 12",
                        value=format_money(1200, "PHP", "en"))  # fmt: skip
    assert len(rows) == 12 and rows[-1] == t("sales.period.more", "en", n="2")


def test_compare_lines_carry_the_percent() -> None:
    line = Line(name="Ube", quantity=3, amount=1200, before=1000)
    (block,) = replies.report_text(_result([line], total_before=1000), "en")
    assert isinstance(block, TextBlock)
    money = format_money(1000, "PHP", "en")
    assert "(20% vs " + money + ")" in block.text.split("\n")[1]
    assert block.text.split("\n")[-1] == t(
        "sales.report.total_vs", "en", total=format_money(1200, "PHP", "en"), percent="20",
        before=money,
    )  # fmt: skip
