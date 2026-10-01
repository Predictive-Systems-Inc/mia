"""Alembic environment: SQLite with batch mode, metadata from mia.schema."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from mia.schema import metadata
from mia.settings import get_settings

config = context.config
if config.get_main_option("sqlalchemy.url", "").endswith("data/mia.db"):
    config.set_main_option("sqlalchemy.url", get_settings().db_url)


def run_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
