"""Tenant context for Row Level Security.

Every tenant-scoped transaction must call ``set_tenant`` (async) or
``set_tenant_sync`` (workers) before touching tenant-owned tables. RLS
policies compare each row's ``tenant_id`` with this transaction-local
setting. If it is not set, policies see NULL and return no rows (fail closed).

The tenant id passed here must come from a verified ``TenantContext``
(membership checked, ADR-005) or from a resolved channel record — never from
client input directly.

``set_config(..., true)`` scopes the value to the current transaction, so a
pooled connection never carries one tenant's context into another request.
The id is a bound parameter, never interpolated into SQL.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

TENANT_SETTING = "app.tenant_id"

_SET_TENANT = text("SELECT set_config(:name, :tenant_id, true)")


def _params(tenant_id: uuid.UUID) -> dict[str, str]:
    if not isinstance(tenant_id, uuid.UUID):
        raise TypeError("tenant_id must be a uuid.UUID")
    return {"name": TENANT_SETTING, "tenant_id": str(tenant_id)}


async def set_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(_SET_TENANT, _params(tenant_id))


def set_tenant_sync(session: Session, tenant_id: uuid.UUID) -> None:
    session.execute(_SET_TENANT, _params(tenant_id))
