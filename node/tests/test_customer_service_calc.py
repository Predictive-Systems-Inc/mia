"""The customer service's pure arithmetic and matching (calc.py): totals, pickup times, hours,
areas, items and the last four digits."""

import datetime as dt

from sqlmodel import Session

from mia.agents.customer_service import calc
from mia.core.orgconfig import DeliveryArea
from mia.templates.retail import hours
from mia.templates.retail.hours import business_date_at
from tests.conftest import MNL, Shop

AREAS = [
    DeliveryArea(name="Marikina", fee=5000, currency="PHP"),
    DeliveryArea(name="Quezon City", fee=8000, currency="PHP"),
    DeliveryArea(name="Pasig", fee=6000, currency="PHP"),
]


def at(day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=MNL)


def test_order_total_adds_lines_and_the_delivery_fee() -> None:
    assert calc.order_total([(10, 4000), (2, 3500)], fee=5000) == 52000
    assert calc.order_total([]) == 0


def test_pickup_tomorrow_8am_is_on_the_branch_calendar(cs: Shop, session: Session) -> None:
    late = dt.datetime(2026, 10, 20, 16, 30, tzinfo=dt.UTC)  # 00:30 on the 21st in Manila
    day = business_date_at(cs.kiosk, hours.load(session, cs.kiosk.id), late) + dt.timedelta(days=1)
    assert calc.pickup_at(day, dt.time(8), "Asia/Manila").isoformat() == "2026-10-22T08:00:00+08:00"


def test_an_area_matches_without_case_or_accents() -> None:
    match = calc.match_area("sa MARIKÍNA po", AREAS)
    assert match is not None and match.name == "Marikina"
    assert calc.match_area("Cebu", AREAS) is None
    assert calc.match_area("taga quezon city kami", AREAS) == AREAS[1]
    assert calc.match_area("Pasigan", AREAS) is None  # whole words only


def test_within_hours_runs_from_opening_up_to_closing(cs: Shop, session: Session) -> None:
    rows = hours.load(session, cs.kiosk.id)  # the kiosk: 09:00 to 21:00 every day
    assert calc.within_hours(cs.kiosk, rows, at(21, 9))
    assert calc.within_hours(cs.kiosk, rows, at(21, 20, 59))
    assert not calc.within_hours(cs.kiosk, rows, at(21, 21))
    assert not calc.within_hours(cs.kiosk, rows, at(21, 8))


def test_open_state_at_half_past_eight_and_after_closing(cs: Shop, session: Session) -> None:
    rows = hours.load(session, cs.kiosk.id)
    evening = calc.open_state(cs.kiosk, rows, at(20, 20, 30))
    assert evening == calc.OpenState(True, at(20, 21), at(21, 9))
    night = calc.open_state(cs.kiosk, rows, at(20, 22))
    assert night == calc.OpenState(False, None, at(21, 9))
    morning = calc.open_state(cs.kiosk, rows, at(20, 7))
    assert morning == calc.OpenState(False, None, at(20, 9))


def test_items_match_by_name_or_code_as_whole_words() -> None:
    items = {"c": ("Classic", "cl", "bibingka"), "u": ("Ube", "ube"), "p": ("Puto bumbong", "pb")}
    assert calc.match_items("magkano ang bibingka at puto bumbong?", items) == ["c", "p"]
    assert calc.match_items("ubos na ba", items) == []


def test_last_four_reads_the_digits() -> None:
    assert calc.last_four("+63 917 555 1234") == "1234"
    assert calc.last_four("sim-ab") == "m-ab"
