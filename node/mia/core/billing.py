"""The billing summary export (spec: "Billing summary export (CSV) done in code"): completed
work per client and site for a month. Prices, extras and approvals wait for service
agreements (D21), so the rows carry work done, not amounts.
"""

import csv
import datetime as dt
from dataclasses import dataclass, field
from typing import TextIO

from sqlmodel import Session, col, select

from mia.core.models import Client, Location, Visit

COLUMNS = [
    "client_id",
    "client",
    "location_id",
    "location",
    "completed_visits",
    "planned_minutes",
    "actual_minutes",
    "visit_ids",
]


@dataclass(order=True)
class BillingRow:
    client: str
    location: str
    client_id: str = field(compare=False, default="")
    location_id: str = field(compare=False, default="")
    completed_visits: int = 0
    planned_minutes: int = 0
    actual_minutes: int = 0
    visit_ids: list[str] = field(default_factory=list, compare=False)


def _minutes(start: dt.datetime, end: dt.datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def summary(session: Session, branch_id: str, year: int, month: int) -> list[BillingRow]:
    """One row per client and site (by id, since names repeat and change) with the completed
    visits of the month, sorted by the names. Actual minutes come from check-in to check-out,
    planned minutes otherwise."""
    first = dt.date(year, month, 1)
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    rows: dict[tuple[str, str], BillingRow] = {}
    visits = session.exec(
        select(Visit)
        .where(Visit.branch_id == branch_id)
        .where(Visit.status == "completed")
        .where(col(Visit.date) >= first)
        .where(col(Visit.date) <= last)
        .order_by(col(Visit.id))
    ).all()
    for v in visits:
        loc = session.get(Location, v.location_id)
        client = session.get(Client, loc.client_id) if loc else None
        key = (client.id if client else "?", loc.id if loc else "?")
        row = rows.setdefault(
            key,
            BillingRow(
                client=client.name if client else "?",
                location=loc.name if loc else "?",
                client_id=key[0],
                location_id=key[1],
            ),
        )
        planned = _minutes(v.planned_start, v.planned_end)
        actual = planned
        if v.actual_start and v.actual_end:
            actual = _minutes(v.actual_start, v.actual_end)
        row.completed_visits += 1
        row.planned_minutes += planned
        row.actual_minutes += actual
        row.visit_ids.append(v.id)
    return sorted(rows.values())


def write_csv(rows: list[BillingRow], out: TextIO) -> None:
    """The rows as CSV with the COLUMNS header; visit ids joined by spaces."""
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for r in rows:
        writer.writerow(
            [
                r.client_id,
                r.client,
                r.location_id,
                r.location,
                r.completed_visits,
                r.planned_minutes,
                r.actual_minutes,
                " ".join(r.visit_ids),
            ]
        )
