"""The commissary's oven capacity for a date (rule 7): ovens times the production window, less
the planned batches times their oven minutes. ponytail: one pool of oven minutes, no packing per
oven; the upgrade is a schedule per oven.

free() is the interface customer_service's _order_precheck may later call for a pre-order
(raising LookupError("capacity") itself; Carried over). It reads settings, recipes and plans
without a permission check: the caller checks (a tool) or is the system."""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import Session, col, select

from mia.agents.production_planner.models import Plan, Recipe
from mia.core import orgconfig

DAY_MINUTES = 24 * 60


def minutes_free(
    ovens: int, start: dt.time, end: dt.time, planned: Iterable[tuple[int, int]]
) -> int:
    """ovens times the minutes from start to end (a window past midnight wraps), less the
    sum of batches times oven_minutes of `planned` (batches, oven_minutes); never below 0."""
    window = (end.hour * 60 + end.minute - start.hour * 60 - start.minute) % DAY_MINUTES
    return max(0, ovens * window - sum(b * m for b, m in planned))


def batches_free(minutes: int, oven_minutes: int) -> int:
    """Whole batches of oven_minutes that fit in minutes."""
    return minutes // oven_minutes


@dataclass(frozen=True)
class Capacity:
    """Free oven minutes of a date, and free pieces per item with an active recipe."""

    minutes_free: int
    per_item: dict[str, int]


def free(session: Session, commissary_id: str, day: dt.date) -> Capacity:
    """The commissary's free capacity on day: the settings' ovens and hours, less the batches of
    that date's plan (none without a plan); per item its free batches times its batch yield."""
    s = orgconfig.load().production_planner
    recipes = {
        r.item_id: r
        for r in session.exec(
            select(Recipe)
            .where(Recipe.branch_id == commissary_id)
            .where(col(Recipe.active).is_(True))
        )
    }
    plan = session.exec(
        select(Plan).where(Plan.branch_id == commissary_id).where(Plan.production_date == day)
    ).first()
    lines = plan.lines if plan else []
    planned = [
        (x["batches"], recipes[x["item_id"]].oven_minutes) for x in lines if x["item_id"] in recipes
    ]
    minutes = minutes_free(s.ovens, s.hours.start, s.hours.end, planned)
    return Capacity(
        minutes,
        {i: batches_free(minutes, r.oven_minutes) * r.batch_yield for i, r in recipes.items()},
    )
