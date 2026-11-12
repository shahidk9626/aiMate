"""Baseline: extensions, schema hardening and runtime-role privileges.

Revision ID: 0001
Revises:
Create Date: 2026-11-12

No tables yet. Establishes what every later migration relies on:

- ``citext`` for case-insensitive emails and slugs.
- ``public`` schema: nobody but the owner may create objects in it.
- The runtime app role (ADR-006) gets USAGE on the schema and, through
  default privileges, DML (not DDL) on every table and sequence the owner
  creates from now on. Tables therefore need no per-migration GRANT.

The app role itself (LOGIN, password) is created by ``python -m
app.db.bootstrap``. If it does not exist yet, this migration creates it
NOLOGIN so grants succeed; bootstrap later adds LOGIN and the password.
"""

from collections.abc import Sequence

from alembic import context, op

from app.core.config import Settings

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _app_role() -> str:
    settings: Settings = context.config.attributes["settings"]
    # Validated as a plain lowercase identifier by Settings; safe to embed.
    return settings.app_db_user


def upgrade() -> None:
    role = _app_role()

    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )

    # Default in PostgreSQL 15+, stated explicitly so it holds everywhere.
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")

    # Applies to objects created later by the role running migrations.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}"
    )


def downgrade() -> None:
    role = _app_role()
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {role}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {role}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
    # The role and the citext extension are left in place: the role is
    # managed by bootstrap, and dropping an extension could destroy data.
