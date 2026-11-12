"""SQL for tenant Row Level Security (ADR-006).

Used by Alembic migrations for every tenant-owned table and by the RLS tests,
so the policy that is tested is exactly the policy that ships.

- ENABLE + FORCE: the policy applies to the table owner too (superusers
  still bypass RLS, which is why the app never connects as one).
- ``current_setting(..., true)`` returns NULL when unset, so the comparison is
  NULL and no row is visible or writable: fail closed.
- ``NULLIF(..., '')``: a setting that was set earlier in the session and then
  reset reads back as an empty string; treat it as unset rather than erroring
  on a uuid cast.
"""

import re

from app.db.tenant import TENANT_SETTING

POLICY_NAME = "tenant_isolation"
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _check(table: str) -> str:
    if not _IDENTIFIER.fullmatch(table):
        raise ValueError(f"invalid table name: {table!r}")
    return table


def enable_tenant_rls_sql(table: str) -> list[str]:
    t = _check(table)
    current = f"NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"
    return [
        f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {POLICY_NAME} ON {t} "
        f"USING (tenant_id = {current}) WITH CHECK (tenant_id = {current})",
    ]


def disable_tenant_rls_sql(table: str) -> list[str]:
    t = _check(table)
    return [
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {t}",
        f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY",
    ]
