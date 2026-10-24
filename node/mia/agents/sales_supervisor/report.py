"""Report questions (teach-Mia spec section 4c): a fixed report form, its validator, the period
resolver and the executor that sums the figures by code (rule 7). A model may fill the form;
it never sees or writes a figure. The executor is unchecked: the report tool checks rbac first.
"""

import datetime as dt
from collections.abc import Callable
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator
from sqlmodel import Session

from mia.agents.sales_supervisor.actions import WEEKDAYS, _period, _periods
from mia.core import sales
from mia.core.models import TENDERS, Branch, Tender
from mia.templates.retail.models import RetailItem

Measure = Literal["pieces", "amount"]
GroupBy = Literal["none", "item", "day", "weekday", "kiosk", "tender", "clerk"]
Compare = Literal["none", "previous_period", "same_period_last_year"]
PERIOD_IDS = tuple(_periods("en"))  # the decider's period ids (weekdays as mon to sun)
ALL = "all"  # kiosks: every shop of the organisation


class ReportForm(BaseModel):
    """One report question as a closed form: what to sum, over which dates, grouped how. No
    field holds a figure, and an unknown field fails validation."""

    model_config = ConfigDict(extra="forbid")

    measure: Measure
    group_by: GroupBy = "none"
    period: str | None = None
    start: dt.date | None = None
    end: dt.date | None = None
    items: list[str] = []
    kiosks: list[str] = []
    tenders: list[Tender] = []
    compare_to: Compare = "none"

    @model_validator(mode="after")
    def _one_period(self) -> Self:
        dated = self.start is not None and self.end is not None
        partial = (self.start is None) != (self.end is None)
        if partial or (self.period is not None) == dated:
            raise ValueError("give a period id or both dates")
        return self


class ReportError(ValueError):
    """A form code refuses; the code is period, order, future, range or combo."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def compared(start: dt.date, end: dt.date, compare: Compare) -> tuple[dt.date, dt.date] | None:
    """The range a form compares with: the same length just before, or the same dates a year
    earlier (29 February becomes 28 February); None without a compare."""
    if compare == "previous_period":
        n = end - start + dt.timedelta(days=1)
        return start - n, start - dt.timedelta(days=1)
    if compare == "same_period_last_year":

        def back(d: dt.date) -> dt.date:
            return d.replace(year=d.year - 1, day=28 if (d.month, d.day) == (2, 29) else d.day)

        return back(start), back(end)
    return None


def resolve(form: ReportForm, today: dt.date, lang: str) -> tuple[dt.date, dt.date]:
    """The form's (start, end) dates: a named period (actions._period, its end cut at today), or
    the explicit dates. Raises ReportError for an unknown period id (or neither or both), an end
    before the start, an end after today, more than sales.MAX_SALES_DAYS days read (the compared
    range included), or a tender grouping or filter with pieces or with item or clerk grouping
    (DaySales.by_tender is per branch and day only)."""
    tender = form.group_by == "tender" or bool(form.tenders)
    if tender and (form.measure == "pieces" or form.group_by in ("item", "clerk")):
        raise ReportError("combo")
    if form.period is not None and form.start is None and form.end is None:
        found = _period(form.period, today, lang) if form.period in PERIOD_IDS else None
        if found is None:
            raise ReportError("period")
        start, end = found[0], min(found[1], today)
    elif form.period is None and form.start is not None and form.end is not None:
        start, end = form.start, form.end
    else:
        raise ReportError("period")
    if end < start:
        raise ReportError("order")
    if end > today:
        raise ReportError("future")
    days = (end - start).days + 1
    if days * (1 if form.compare_to == "none" else 2) > sales.MAX_SALES_DAYS:
        raise ReportError("range")
    return start, end


class Line(BaseModel):
    """One group of a report: its key worded for the reply (an item or kiosk name, an ISO date,
    a weekday id mon to sun, a tender id, a clerk's name), its sums and the compared value of
    the form's measure."""

    name: str
    quantity: int
    amount: int
    before: int | None = None


class Result(BaseModel):
    head_measure: Measure
    group_by: GroupBy
    start: dt.date
    end: dt.date
    lines: list[Line]
    total: int  # of the measure: pieces, or minor units of currency
    total_before: int | None
    currency: str


Sums = dict[str, tuple[int, int]]  # group key -> (quantity, amount)


def _add(sums: Sums, key: str, quantity: int, amount: int) -> None:
    q, a = sums.get(key, (0, 0))
    sums[key] = (q + quantity, a + amount)


def _sums(
    session: Session, branches: list[Branch], form: ReportForm, start: dt.date, end: dt.date
) -> tuple[Sums, tuple[int, int]]:
    """(quantity, amount) per group key and the grand total over start to end, each date from
    its one source: DaySales.by_tender for a tender grouping or filter, else sale_rows."""
    sums: Sums = {}
    total = (0, 0)
    names = {b.id: b.name for b in branches}
    if form.group_by == "tender" or form.tenders:
        for branch in branches:
            for day, found in sales.days_sales(session, branch.id, start, end).items():
                for tender, amount in found.by_tender.items():
                    if form.tenders and tender not in form.tenders:
                        continue
                    key = {
                        "tender": tender,
                        "day": day.isoformat(),
                        "weekday": WEEKDAYS[day.weekday()],
                        "kiosk": branch.name,
                    }.get(form.group_by, "")
                    _add(sums, key, 0, amount)
                    total = (0, total[1] + amount)
        return sums, total
    rows = sales.sale_rows(session, [b.id for b in branches], start, end)
    for r in rows:
        if form.items and r.item_id not in form.items:
            continue
        key = {
            "item": r.item_id,
            "day": r.business_date.isoformat(),
            "weekday": WEEKDAYS[r.business_date.weekday()],
            "kiosk": names[r.branch_id],
            "clerk": r.reported_by,
        }.get(form.group_by, "")
        _add(sums, key, r.quantity, r.amount)
        total = (total[0] + r.quantity, total[1] + r.amount)
    return sums, total


def run(
    session: Session,
    branches: list[Branch],
    form: ReportForm,
    start: dt.date,
    end: dt.date,
    names: dict[str, RetailItem],
    clerks: dict[str, str],
) -> Result:
    """The form's figures over start to end and, with a compare, over compared(...): one Line
    per group (none for group_by none) ordered by menu order (item, no compare), date (day),
    Monday first (weekday), TENDERS order (tender), else largest first; a group seen only in
    the compared range shows 0 now. Unchecked: the caller checks rbac and validates the form
    (resolve)."""
    pick = 0 if form.measure == "pieces" else 1
    now, total = _sums(session, branches, form, start, end)
    back = compared(start, end, form.compare_to)
    before: Sums = {}
    total_before = None
    if back is not None:
        before, old = _sums(session, branches, form, *back)
        total_before = old[pick]
    keys = [] if form.group_by == "none" else list(dict.fromkeys([*now, *before]))
    order: dict[str, Callable[[str], Any]] = {
        "day": lambda k: k,
        "weekday": WEEKDAYS.index,
        "tender": TENDERS.index,
    }
    if form.group_by == "item" and back is None:
        order["item"] = lambda k: names[k].sort_order

    def largest(k: str) -> int:
        return -now.get(k, (0, 0))[pick]

    keys.sort(key=order.get(form.group_by, largest))

    def worded(k: str) -> str:
        if form.group_by == "item":
            return names[k].name if k in names else k
        return clerks.get(k, k) if form.group_by == "clerk" else k

    lines = [
        Line(
            name=worded(k),
            quantity=now.get(k, (0, 0))[0],
            amount=now.get(k, (0, 0))[1],
            before=before.get(k, (0, 0))[pick] if back is not None else None,
        )
        for k in keys
    ]
    # ponytail: one currency per organisation in v1 (the menu's); a mixed one needs per-currency sums
    currency = next(iter(names.values())).currency if names else "PHP"
    return Result(
        head_measure=form.measure,
        group_by=form.group_by,
        start=start,
        end=end,
        lines=lines,
        total=total[pick],
        total_before=total_before,
        currency=currency,
    )
