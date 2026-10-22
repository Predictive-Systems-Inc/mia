"""The dev test clock in db.utcnow: shifts the node's now in dev mode only."""

import datetime as dt

import pytest

from mia.core import db
from mia.settings import get_settings
from mia.templates.retail.hours import business_date

MANILA = dt.timezone(dt.timedelta(hours=8))

# conftest's autouse fixture resets the offset around every test


def test_the_offset_applies_in_dev_and_the_business_date_follows() -> None:
    at = dt.datetime(2026, 10, 28, 9, 0, tzinfo=MANILA)
    db.set_dev_clock(at)
    assert abs(db.utcnow() - at) < dt.timedelta(seconds=5)
    assert db.dev_clock() is not None
    day = business_date(db.utcnow(), "Asia/Manila", dt.time(9), dt.time(21))
    assert day == dt.date(2026, 10, 28)
    db.set_dev_clock(at.replace(day=29, hour=0, minute=30))  # after a 23:30 closing: yesterday
    assert business_date(db.utcnow(), "Asia/Manila", dt.time(9), dt.time(23, 30)) == at.date()


def test_reset_returns_to_real_time() -> None:
    db.set_dev_clock(dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
    db.set_dev_clock(None)
    assert db.dev_clock() is None
    assert abs(db.utcnow() - dt.datetime.now(dt.UTC)) < dt.timedelta(seconds=5)


def test_a_naive_time_is_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        db.set_dev_clock(dt.datetime(2026, 10, 28, 9, 0))  # noqa: DTZ001 (the case under test)


def test_required_mode_ignores_the_offset_and_refuses_to_set_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db.set_dev_clock(dt.datetime(2020, 1, 1, tzinfo=dt.UTC))  # set in dev, then the mode changes
    monkeypatch.setenv("MIA_AUTH_MODE", "required")
    get_settings.cache_clear()
    assert abs(db.utcnow() - dt.datetime.now(dt.UTC)) < dt.timedelta(seconds=5)
    assert db.dev_clock() is None
    with pytest.raises(PermissionError):
        db.set_dev_clock(dt.datetime(2030, 1, 1, tzinfo=dt.UTC))
    with pytest.raises(PermissionError):
        db.set_dev_clock(None)
