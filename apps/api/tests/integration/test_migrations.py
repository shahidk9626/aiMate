from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool

from app.core.config import Settings
from app.db.base import Base
from tests.integration.conftest import alembic_config, owner_connect


def _current_revision(settings: Settings) -> str | None:
    with owner_connect(settings) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row else None


def test_database_is_at_head(integration_settings: Settings) -> None:
    head = ScriptDirectory.from_config(alembic_config(integration_settings)).get_current_head()

    assert _current_revision(integration_settings) == head


def test_migrations_downgrade_to_base_and_upgrade_again(integration_settings: Settings) -> None:
    config = alembic_config(integration_settings)

    command.downgrade(config, "base")
    assert _current_revision(integration_settings) is None

    command.upgrade(config, "head")
    assert _current_revision(integration_settings) == "0001"


def test_citext_extension_installed(integration_settings: Settings) -> None:
    with owner_connect(integration_settings) as conn:
        row = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'citext'").fetchone()

    assert row is not None


def test_models_and_migrations_are_in_sync(integration_settings: Settings) -> None:
    """Fails if a model changed without a matching migration."""
    engine = create_engine(integration_settings.migration_database_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()

    assert diff == []
