import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mia.core import orgconfig


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
