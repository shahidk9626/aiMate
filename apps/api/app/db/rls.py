"""SQL for Row Level Security (ADR-006, ADR-023).

Used by Alembic migrations and by the RLS tests, so the policies that are
tested are exactly the policies that ship.

- ENABLE + FORCE: policies apply to the table owner too (superusers still
  bypass RLS, which is why the app never connects as one).
- ``current_setting(..., true)`` returns NULL when unset, so comparisons are
  NULL and nothing matches: fail closed.
- ``NULLIF(..., '')``: a setting that was set earlier in the session and then
  reset reads back as an empty string; treat it as unset rather than erroring
  on the uuid cast.

Standard tenant tables use ``enable_tenant_rls_sql``. Tables with special
rules (users, memberships, tenants, audit_logs, sessions, tokens) call
``force_rls_sql`` and define their policies in the migration with
``CURRENT_TENANT`` / ``CURRENT_USER``.
"""

import re

from app.db.tenant import TENANT_SETTING, USER_SETTING

POLICY_NAME = "tenant_isolation"
CURRENT_TENANT = f"NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"
CURRENT_USER = f"NULLIF(current_setting('{USER_SETTING}', true), '')::uuid"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _check(table: str) -> str:
    if not _IDENTIFIER.fullmatch(table):
        raise ValueError(f"invalid table name: {table!r}")
    return table


def force_rls_sql(table: str) -> list[str]:
    t = _check(table)
    return [
        f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY",
    ]


def enable_tenant_rls_sql(table: str) -> list[str]:
    t = _check(table)
    return [
        *force_rls_sql(t),
        f"CREATE POLICY {POLICY_NAME} ON {t} "
        f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})",
    ]


def disable_tenant_rls_sql(table: str) -> list[str]:
    t = _check(table)
    return [
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {t}",
        f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY",
    ]
