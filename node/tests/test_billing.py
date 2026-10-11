"""The billing summary: completed work per client and site for a month, as rows and CSV."""

import csv
import datetime as dt
import io
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, select

from mia.cli import main
from mia.core import billing
from mia.core.models import Branch, Event, Visit


def _month(branch: Branch) -> tuple[int, int]:
    today = dt.datetime.now(ZoneInfo(branch.timezone)).date()
    return today.year, today.month


def test_summary_counts_completed_visits_per_client_and_site(
    session: Session, branch: Branch
) -> None:
    year, month = _month(branch)
    rows = billing.summary(session, branch.id, year, month)
    assert rows and all(r.completed_visits > 0 for r in rows)
    done = [
        v
        for v in session.exec(select(Visit).where(Visit.status == "completed"))
        if (v.date.year, v.date.month) == (year, month)
    ]
    assert sum(r.completed_visits for r in rows) == len(done)
    assert all(r.planned_minutes > 0 and r.actual_minutes > 0 for r in rows)
    assert rows == sorted(rows, key=lambda r: (r.client, r.location))
    assert billing.summary(session, branch.id, 2020, 1) == []


def test_csv_columns(session: Session, branch: Branch) -> None:
    year, month = _month(branch)
    out = io.StringIO()
    billing.write_csv(billing.summary(session, branch.id, year, month), out)
    reader = csv.DictReader(io.StringIO(out.getvalue()))
    assert reader.fieldnames == [
        "client",
        "location",
        "completed_visits",
        "planned_minutes",
        "actual_minutes",
        "visit_ids",
    ]
    assert sum(1 for _ in reader) >= 1


def test_cli_export_writes_the_file_and_an_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], session: Session, branch: Branch
) -> None:
    year, month = _month(branch)
    out = tmp_path / "billing.csv"
    assert main(["billing", "export", "--month", f"{year}-{month:02d}", "--out", str(out)]) == 0
    assert "row(s)" in capsys.readouterr().out and out.read_text().startswith("client,location")
    session.expire_all()
    ev = session.exec(select(Event).where(Event.action == "billing.exported")).one()
    assert ev.after == {
        "month": f"{year}-{month:02d}",
        "rows": len(billing.summary(session, branch.id, year, month)),
    }
    with pytest.raises(SystemExit):
        main(["billing", "export", "--month", "2026-13"])
