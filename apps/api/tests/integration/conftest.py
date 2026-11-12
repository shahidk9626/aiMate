"""Integration fixtures: a real, disposable PostgreSQL database.

Uses the local compose PostgreSQL/Redis (credentials from the root .env), but
never the development database: a fresh ``leadflow_test`` database and a
separate ``leadflow_app_test`` role are created for the session and dropped
afterwards. Every test in this package is marked ``integration`` and the
whole package is skipped with a clear reason when PostgreSQL is unreachable.

Run only unit tests:        uv run pytest -m "not integration"
Run only integration tests: uv run pytest -m integration
"""

import secrets
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from pydantic import SecretStr

from app.core.config import Environment, Settings
from app.db.bootstrap import bootstrap_app_role

TEST_DATABASE = "leadflow_test"
TEST_APP_ROLE = "leadflow_app_test"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.integration)


def owner_connect(settings: Settings, database: str | None = None) -> psycopg.Connection:
    url = settings.migration_database_url(database)
    return psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=3,
        autocommit=True,
    )


def alembic_config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["settings"] = settings
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def integration_settings() -> Iterator[Settings]:
    base = Settings()
    if base.postgres_password is None:
        pytest.skip("POSTGRES_PASSWORD not set; start infra/docker-compose.yml with a root .env")
    settings = Settings(
        _env_file=None,
        app_env=Environment.TEST,
        log_json=True,
        postgres_host=base.postgres_host,
        postgres_port=base.postgres_port,
        postgres_db=TEST_DATABASE,
        postgres_user=base.postgres_user,
        postgres_password=base.postgres_password,
        app_db_user=TEST_APP_ROLE,
        app_db_password=SecretStr(secrets.token_urlsafe(24)),
        redis_host=base.redis_host,
        redis_port=base.redis_port,
        redis_db=15,  # keep test keys away from development data in db 0
        redis_password=base.redis_password,
    )

    try:
        admin = owner_connect(settings, "postgres")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable for integration tests: {type(exc).__name__}")

    with admin:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DATABASE))
        )
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DATABASE)))

    bootstrap_app_role(settings)
    command.upgrade(alembic_config(settings), "head")

    yield settings

    with owner_connect(settings, "postgres") as admin:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DATABASE))
        )
        admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(TEST_APP_ROLE)))
        admin.execute(
            sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(settings.db_lookup_role))
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
