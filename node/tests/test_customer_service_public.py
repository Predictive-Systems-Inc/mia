"""The customer service's public side: the message throttle per channel:address key."""

import datetime as dt

from sqlmodel import Session

from mia.core import auth


def test_customer_message_limit_is_30_per_hour(session: Session) -> None:
    now, key = dt.datetime(2026, 10, 20, 2, tzinfo=dt.UTC), "a1b2@-"
    for i in range(30):
        assert not auth.throttled(session, "customer_message", key, now)
        auth.record_attempt(session, "customer_message", key, False, now + dt.timedelta(seconds=i))
    assert auth.throttled(session, "customer_message", key, now + dt.timedelta(minutes=1))
    assert not auth.throttled(session, "customer_message", "other@-", now)
    assert not auth.throttled(session, "customer_message", key, now + dt.timedelta(hours=2))


def test_a_limit_from_settings_replaces_the_default(session: Session) -> None:
    now, key = dt.datetime(2026, 10, 20, 2, tzinfo=dt.UTC), "c3d4@-"
    auth.record_attempt(session, "customer_message", key, False, now)
    tight = auth.Limit(1, auth.H1, auth.H1)
    assert auth.throttled(session, "customer_message", key, now, limit=tight)
    assert not auth.throttled(session, "customer_message", key, now)
