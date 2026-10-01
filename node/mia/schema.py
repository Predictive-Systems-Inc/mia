"""Imports every table module so SQLModel.metadata is complete (for Alembic and tests)."""

from sqlalchemy import Engine
from sqlmodel import SQLModel

import mia.agents.dispatcher.models
import mia.core.events
import mia.core.models
import mia.templates.cleaning.models  # noqa: F401

metadata = SQLModel.metadata


def create_all(engine: Engine) -> None:
    """Create every table and trigger. Used by tests; real nodes run Alembic migrations."""
    metadata.create_all(engine)
