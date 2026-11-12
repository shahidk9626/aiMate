"""The runtime role must be unable to escape tenant isolation or change schema."""

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.config import Settings
from app.db.bootstrap import bootstrap_app_role
from app.db.engine import create_sync_db_engine
from tests.integration.conftest import owner_connect


def test_role_attributes_are_restricted(integration_settings: Settings) -> None:
    with owner_connect(integration_settings) as conn:
        row = conn.execute(
            "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication, "
            "rolcanlogin FROM pg_roles WHERE rolname = %s",
            (integration_settings.app_db_user,),
        ).fetchone()

    assert row == (False, False, False, False, False, True)


def test_app_connects_as_restricted_role(integration_settings: Settings) -> None:
    engine = create_sync_db_engine(integration_settings)
    with engine.connect() as conn:
        user = conn.execute(text("SELECT current_user")).scalar_one()
    engine.dispose()

    assert user == integration_settings.app_db_user


def test_app_role_cannot_create_tables(integration_settings: Settings) -> None:
    engine = create_sync_db_engine(integration_settings)
    with engine.connect() as conn, pytest.raises(ProgrammingError) as exc_info:
        conn.execute(text("CREATE TABLE should_fail (id int)"))
    engine.dispose()

    assert isinstance(exc_info.value.orig, psycopg.errors.InsufficientPrivilege)


def test_app_role_cannot_read_migration_state(integration_settings: Settings) -> None:
    engine = create_sync_db_engine(integration_settings)
    with engine.connect() as conn, pytest.raises(ProgrammingError) as exc_info:
        conn.execute(text("SELECT * FROM alembic_version"))
    engine.dispose()

    assert isinstance(exc_info.value.orig, psycopg.errors.InsufficientPrivilege)


def test_bootstrap_is_idempotent(integration_settings: Settings) -> None:
    bootstrap_app_role(integration_settings)
    bootstrap_app_role(integration_settings)

    test_app_connects_as_restricted_role(integration_settings)
