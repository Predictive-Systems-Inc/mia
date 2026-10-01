"""Engine and session handling. SQLite runs in WAL mode with a 5 second busy timeout."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, String, TypeDecorator, event
from sqlalchemy.engine.interfaces import Dialect
from sqlmodel import Session, create_engine

from mia.settings import get_settings

_engines: dict[str, Engine] = {}


class TZDateTime(TypeDecorator[datetime]):
    """Stores timezone-aware datetimes as ISO 8601 strings with offset. Naive values are refused."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; times must carry a time zone")
        return value.isoformat()

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        return None if value is None else datetime.fromisoformat(value)


def utcnow() -> datetime:
    """Current time, timezone-aware (UTC)."""
    return datetime.now(UTC)


def _set_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def get_engine(url: str | None = None) -> Engine:
    """Return a cached engine for the url (default: settings.MIA_DB_PATH), creating its folder."""
    url = url or get_settings().db_url
    if url not in _engines:
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _set_pragmas)
        _engines[url] = engine
    return _engines[url]


def reset_engines() -> None:
    """Dispose all cached engines (used by tests and the CLI)."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """A session that commits on success and rolls back on error."""
    with Session(engine or get_engine(), expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
