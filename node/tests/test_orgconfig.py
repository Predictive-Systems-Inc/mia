import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mia.core import orgconfig


def test_production_planner_settings_load() -> None:
    s = orgconfig.load("ferinos").production_planner
    got = (s.commissary, s.serves, s.ovens, s.hours.start, s.hours.end, s.plan_at, s.dispatch_at)
    assert got == (
        "Commissary",
        ["Mall kiosk", "Street stall"],
        2,
        dt.time(3),
        dt.time(9),
        dt.time(14),
        dt.time(8, 30),
    )
    assert orgconfig.OrgSettings().production_planner.commissary == ""  # off by default


def test_payroll_defaults_and_no_holidays() -> None:
    s = orgconfig.OrgSettings()
    assert s.payroll.cutoffs == "semi_monthly" and s.payroll.pay_lag_days == 5
    assert s.holidays == []


def test_a_holiday_validates() -> None:
    s = orgconfig.OrgSettings.model_validate(
        {"holidays": [{"date": "2026-12-25", "kind": "regular", "name": "Christmas"}]}
    )
    assert s.holidays[0].date == dt.date(2026, 12, 25)


@pytest.mark.parametrize(
    "bad",
    [
        {"date": "not-a-date", "kind": "regular", "name": "x"},
        {"date": "2026-12-25", "kind": "bank", "name": "x"},
    ],
)
def test_a_bad_holiday_is_refused(bad: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        orgconfig.OrgSettings.model_validate({"holidays": [bad]})


def test_holidays_file_and_inline_list_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = tmp_path / "org" / "acme"
    org.mkdir(parents=True)
    (org / "settings.yaml").write_text(
        "holidays: [{date: '2026-01-01', kind: regular, name: New Year}]\n"
    )
    (org / "holidays.yaml").write_text("- {date: '2026-02-17', kind: special, name: CNY}\n")
    stub = SimpleNamespace(config_dir=tmp_path, MIA_ORG="acme")
    monkeypatch.setattr(orgconfig, "get_settings", lambda: stub)
    orgconfig.load.cache_clear()
    try:
        names = [h.name for h in orgconfig.load("acme").holidays]
    finally:
        orgconfig.load.cache_clear()
    assert names == ["New Year", "CNY"]


def test_branch_manager_settings_load() -> None:
    assert orgconfig.load("ferinos").branch_manager == orgconfig.BranchManagerSettings(
        experiment_days=14, nudge_after_misses=3
    )
    assert "branch_manager" in orgconfig.load("ferinos").agents


def test_shift_supervisor_settings_load() -> None:
    assert orgconfig.load("ferinos").shift_supervisor == orgconfig.ShiftSupervisorSettings(
        weekly_roster_weekday=6, weekly_roster_time=dt.time(17, 0)
    )
    assert orgconfig.OrgSettings().shift_supervisor.weekly_roster_weekday == 6


def test_bookkeeper_settings_load() -> None:
    assert orgconfig.load("ferinos").bookkeeper == orgconfig.BookkeeperSettings(
        threshold=10_000,
        expense_limit=500_000,
        fees={"gcash": 2, "maya": 2},
        commissions={"grab": 25, "foodpanda": 28},
        tax_regime="vat",
        petty_floor=50_000,
        undeposited_limit=2_000_000,
    )
    assert "bookkeeper" in orgconfig.load("ferinos").agents


def test_sales_settings_load_the_opening_float() -> None:
    assert orgconfig.SalesSettings().opening_float == {}
    assert orgconfig.load("ferinos").sales.opening_float == {}


def test_delivery_areas_in_two_currencies_fail_to_load() -> None:
    areas = [{"name": "A", "fee": 1, "currency": "PHP"}, {"name": "B", "fee": 1, "currency": "USD"}]
    with pytest.raises(ValidationError, match="one currency"):
        orgconfig.OrgSettings.model_validate({"delivery_areas": areas})
    same = [a | {"currency": "PHP"} for a in areas]
    assert len(orgconfig.OrgSettings.model_validate({"delivery_areas": same}).delivery_areas) == 2
