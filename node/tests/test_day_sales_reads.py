"""The branch manager, the production planner and the period report read sales.day_sales: on a
receipts day at the Mall kiosk they see the receipts (a counts day is pinned by their own tests,
unedited). Helpers from test_sales_receipts.py."""

import dataclasses
import datetime as dt

import pytest
from sqlmodel import Session

from mia.agents.branch_manager import due as bm_due
from mia.agents.branch_manager import tools as bm_tools
from mia.agents.branch_manager.tools import WeeklyInput
from mia.agents.production_planner import tools as pp_tools
from mia.agents.sales_supervisor import MANIFEST as SS
from mia.agents.sales_supervisor import due as ss_due
from mia.agents.sales_supervisor import tools as ss_tools
from mia.agents.sales_supervisor.tools import PeriodReportInput
from mia.core import sales
from mia.core.rbac import PermissionDenied
from mia.templates.retail.items import price_on
from tests.conftest import RS_TODAY
from tests.test_branch_manager_tools import deps_for as bm_deps
from tests.test_data_standard_1_7 import Ferinos
from tests.test_data_standard_1_9 import item
from tests.test_production_planner_tools import comm, deny
from tests.test_sales_receipts import drawer, receipts_kiosk, ring, ss_deps


def _day(session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch) -> tuple[int, int]:
    """Ana's receipts day: 3 Ube and 2 Classic cash, then 1 Ube by GCash. Returns the Ube
    amount and the day's total."""
    receipts_kiosk(monkeypatch)
    s = drawer(session, rs)
    ring(session, rs, s, "1", [("Ube", 3), ("Classic", 2)], "cash")
    ring(session, rs, s, "2", [("Ube", 1)], "gcash", hh=11)
    session.commit()
    ube, classic = (
        price_on(session, item(session, n), rs[0].id, RS_TODAY) for n in ("Ube", "Classic")
    )
    return 4 * ube, 4 * ube + 2 * classic


def test_the_branch_manager_reads_a_receipts_day(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    ube_amount, total = _day(session, rs, monkeypatch)
    kiosk, ana = rs[0], rs[1]["Ana"]
    ube = item(session, "Ube").id
    assert bm_tools.daily(session, kiosk.id, ube, RS_TODAY, RS_TODAY) == {RS_TODAY: (4, ube_amount)}
    assert bm_due._amounts(session, kiosk.id, ana.id, RS_TODAY)[RS_TODAY] == total
    assert ss_due._reporters(session, kiosk.id, RS_TODAY) == {ana.id}  # the morning, nudges
    owner = dataclasses.replace(bm_deps(session, rs[1]["Rosa"]), today=RS_TODAY + dt.timedelta(1))
    monday = RS_TODAY - dt.timedelta(days=RS_TODAY.weekday())
    week = bm_tools.weekly_summary(owner, WeeklyInput(branch_id=kiosk.id, week_start=monday), "c")
    before = sales.live_counts(session, [kiosk.id], monday, RS_TODAY - dt.timedelta(days=1))
    assert [w.amount for w in week.branches] == [sum(c.amount for c in before) + total]


def test_the_planner_forecast_reads_a_receipts_day(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    _day(session, rs, monkeypatch)
    data = pp_tools.kiosk_data(session, comm(session), rs[0], RS_TODAY + dt.timedelta(days=1))
    ube, classic = item(session, "Ube").id, item(session, "Classic").id
    assert {k: data.daily[RS_TODAY].get(k) for k in (ube, classic)} == {ube: 4, classic: 2}


def test_the_period_report_reads_a_receipts_day(
    session: Session, rs: Ferinos, monkeypatch: pytest.MonkeyPatch
) -> None:
    ube_amount, total = _day(session, rs, monkeypatch)
    deps = ss_deps(session, rs[1]["Ana"])
    out = ss_tools.period_report(deps, PeriodReportInput(start=RS_TODAY, end=RS_TODAY), "c")
    assert (out.total, out.best_day) == (total, RS_TODAY)
    assert [(r.item, r.quantity, r.amount) for r in out.rows if r.item == "Ube"] == [
        ("Ube", 4, ube_amount)
    ]
    deny(monkeypatch, SS.roles.agent_role, ss_tools.RECEIPT_TABLES[1], "read")
    with pytest.raises(PermissionDenied):
        ss_tools.period_report(deps, PeriodReportInput(start=RS_TODAY, end=RS_TODAY), "c")
