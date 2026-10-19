"""The customer service on the Ferino's seed, pinned to TODAY so no test reads the wall clock
(the seeded pickup is today at 15:00, the picked-up order yesterday)."""

import datetime as dt

from sqlmodel import Session, select

from mia.agents.customer_service.models import Complaint, Customer, Order
from mia.core import orgconfig
from mia.core.models import Event
from tests.conftest import MNL, TODAY, Shop


def test_seed_customer_service_data(cs: Shop, session: Session) -> None:
    assert sorted(c.language for c in session.exec(select(Customer))) == ["en", "fil"]
    assert sorted(o.status for o in session.exec(select(Order))) == ["confirmed", "picked_up"]
    assert [c.status for c in session.exec(select(Complaint))] == ["open"] and [
        a.fee for a in orgconfig.load().delivery_areas
    ] == [5000, 8000, 6000]


def test_the_seeded_pickup_is_today_at_three_and_milas_window_is_closed(
    cs: Shop, session: Session
) -> None:
    mila = session.exec(select(Customer).where(Customer.name == "Mila Reyes")).one()
    order = session.exec(select(Order).where(Order.customer_id == mila.id)).one()
    assert order.pickup_at.astimezone(MNL) == dt.datetime.combine(TODAY, dt.time(15), MNL)
    assert order.lines[0]["quantity"] == 10 and order.total == 10 * order.lines[0]["unit_price"]
    assert mila.last_inbound_at is not None
    assert cs.pin(10) - mila.last_inbound_at >= dt.timedelta(hours=24)


def test_customer_identity_and_text_stay_off_the_seed_events(cs: Shop, session: Session) -> None:
    hidden = {
        "customer_service_customers": {"name", "address"},
        "customer_service_complaints": {"text"},
    }
    rows = session.exec(select(Event)).all()
    for table, fields in hidden.items():
        created = [e for e in rows if e.action == f"{table}.created"]
        assert created
        assert all(e.after and e.after[f] == "<redacted>" for e in created for f in fields)
    assert not [e for e in rows if "Mila" in str(e.after) or "+63917" in str(e.after)]
