"""The branch manager's tools: typed inputs and outputs, permission checked data access, writes
only through mia.core.store. No bindings yet; each new tool is a manifest entry plus a binding
here."""

import datetime as dt

from sqlmodel import Session

from mia.agents.base import ToolBinding
from mia.agents.branch_manager.experiments import Day
from mia.agents.sales_supervisor.tools import _live_counts

BINDINGS: list[ToolBinding] = []


def daily(
    session: Session, branch_id: str, item_id: str, start: dt.date, end: dt.date
) -> dict[dt.date, Day]:
    """The item's live counts at the branch summed per business date from start to end
    (inclusive), as (units, amount); a date without counts is absent. Reads only, unchecked:
    callers check (or are the system tick)."""
    out: dict[dt.date, Day] = {}
    for row in _live_counts(session, [branch_id], start, end, item_id):
        units, amount = out.get(row.business_date, (0, 0))
        out[row.business_date] = (units + row.quantity, amount + row.amount)
    return out
