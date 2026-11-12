"""Request identity for Row Level Security: current tenant and current user.

RLS policies compare rows with two transaction-local settings:

- ``app.tenant_id``: the business the request acts on. Set only from a
  verified ``TenantContext`` (membership checked, ADR-005), or by the few
  flows that create the tenant relationship themselves (signup, accepting an
  invitation) after validating their token.
- ``app.user_id``: the authenticated user. Lets a user see their own user row,
  sessions, tokens and memberships across all their businesses.

If a setting is not set, policies see NULL and match nothing (fail closed).

``set_config(..., true)`` scopes values to the current transaction, so a
pooled connection never carries one request's identity into another. Values
are bound parameters, never interpolated into SQL.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

TENANT_SETTING = "app.tenant_id"
USER_SETTING = "app.user_id"

_SET_CONFIG = text("SELECT set_config(:name, :value, true)")


def _params(name: str, value: uuid.UUID) -> dict[str, str]:
    if not isinstance(value, uuid.UUID):
        raise TypeError(f"{name} must be a uuid.UUID")
    return {"name": name, "value": str(value)}


async def set_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(_SET_CONFIG, _params(TENANT_SETTING, tenant_id))


def set_tenant_sync(session: Session, tenant_id: uuid.UUID) -> None:
    session.execute(_SET_CONFIG, _params(TENANT_SETTING, tenant_id))


async def set_current_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(_SET_CONFIG, _params(USER_SETTING, user_id))


def set_current_user_sync(session: Session, user_id: uuid.UUID) -> None:
    session.execute(_SET_CONFIG, _params(USER_SETTING, user_id))
