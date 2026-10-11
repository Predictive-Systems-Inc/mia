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
    assert reader.fieldnames == billing.COLUMNS
    assert sum(1 for _ in reader) >= 1


def test_cli_export_writes_the_file_and_an_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], session: Session, branch: Branch
) -> None:
    year, month = _month(branch)
    out = tmp_path / "billing.csv"
    assert main(["billing", "export", "--month", f"{year}-{month:02d}", "--out", str(out)]) == 0
    assert "row(s)" in capsys.readouterr().out and out.read_text().startswith(
        "client_id,client,location_id,location"
    )
    session.expire_all()
    ev = session.exec(select(Event).where(Event.action == "billing.exported")).one()
    assert ev.after == {
        "month": f"{year}-{month:02d}",
        "rows": len(billing.summary(session, branch.id, year, month)),
    }
    with pytest.raises(SystemExit):
        main(["billing", "export", "--month", "2026-13"])


def test_rows_key_on_ids_and_csv_quotes_names(session: Session, branch: Branch) -> None:
    """Two sites with one name under two clients stay two rows; a comma in a name survives."""
    from mia.core import store
    from mia.core.models import Actor, Client, Location

    year, month = _month(branch)
    actor = Actor.system(branch.id)
    rows_before = billing.summary(session, branch.id, year, month)
    first = rows_before[0]
    loc = session.exec(select(Location).where(Location.name == first.location)).first()
    assert loc is not None
    other_client = store.insert(
        session, Client(branch_id=branch.id, name='Acme "A, B"', type="business"), actor
    )
    twin = store.insert(
        session,
        Location(branch_id=branch.id, client_id=other_client.id, name=loc.name, address="x"),
        actor,
    )
    done = session.exec(
        select(Visit)
        .where(Visit.location_id == loc.id)
        .where(Visit.status == "completed")
        .where(
            Visit.date >= dt.date(year, month, 1)
        )  # this month, not the seed's last-month visits
    ).first()
    assert done is not None
    store.update(session, done, {"location_id": twin.id}, actor)
    rows = billing.summary(session, branch.id, year, month)
    names = [(r.client, r.location) for r in rows]
    assert names.count((first.client, first.location)) == 1 and ('Acme "A, B"', loc.name) in names
    assert all(r.client_id and r.location_id for r in rows)
    out = io.StringIO()
    billing.write_csv(rows, out)
    parsed = list(csv.DictReader(io.StringIO(out.getvalue())))
    assert any(p["client"] == 'Acme "A, B"' for p in parsed)
    assert parsed[0].keys() >= {"client_id", "location_id"}
