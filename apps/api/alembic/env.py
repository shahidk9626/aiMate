"""Alembic environment.

Migrations always run synchronously as the database owner role. Settings
come from ``config.attributes["settings"]`` when provided (tests) or from the
environment otherwise.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.db.models  # noqa: F401  (registers all models on Base.metadata)
from app.core.config import Settings, get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings: Settings = config.attributes.get("settings") or get_settings()
# Expose to migration scripts (they need e.g. the app role name for grants).
config.attributes["settings"] = settings

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing (``alembic upgrade head --sql``)."""
    context.configure(
        url=settings.migration_database_url().render_as_string(hide_password=True),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(settings.migration_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # One transaction per migration file, so a failure leaves the
            # database at the last fully applied revision.
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
