"""Create or update the restricted runtime database role.

Run once per environment, and again whenever APP_DB_PASSWORD changes:

    uv run python -m app.db.bootstrap

Connects as the owner role (POSTGRES_USER/POSTGRES_PASSWORD). Idempotent.
The role is created with LOGIN and explicitly without SUPERUSER, CREATEDB,
CREATEROLE, REPLICATION or BYPASSRLS. Table privileges are granted by the
Alembic baseline migration, not here.

The password is sent as an escaped literal (DDL cannot take bound
parameters). Do not enable ``log_statement = 'all'`` on the server while
running this, or the password would appear in the PostgreSQL log.
"""

import psycopg
from psycopg import sql

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger("app.db.bootstrap")

_ROLE_ATTRIBUTES = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"


def _owner_conninfo(settings: Settings) -> str:
    url = settings.migration_database_url()
    return psycopg.conninfo.make_conninfo(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=settings.db_connect_timeout_seconds,
    )


def bootstrap_app_role(settings: Settings) -> None:
    if settings.app_db_password is None or not settings.app_db_password.get_secret_value():
        raise RuntimeError("APP_DB_PASSWORD is required to bootstrap the app role")

    role = sql.Identifier(settings.app_db_user)
    password = sql.Literal(settings.app_db_password.get_secret_value())
    attributes = sql.SQL(_ROLE_ATTRIBUTES)

    with psycopg.connect(_owner_conninfo(settings), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (settings.app_db_user,)
        ).fetchone()
        verb = sql.SQL("ALTER ROLE") if exists else sql.SQL("CREATE ROLE")
        conn.execute(sql.SQL("{} {} WITH {} PASSWORD {}").format(verb, role, attributes, password))
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(settings.postgres_db), role
            )
        )
    logger.info(
        "app_role_bootstrapped",
        role=settings.app_db_user,
        action="updated" if exists else "created",
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    bootstrap_app_role(settings)


if __name__ == "__main__":
    main()
