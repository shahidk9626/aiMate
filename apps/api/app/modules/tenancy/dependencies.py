"""Tenant context: the verified answer to "which business is this request for?" (ADR-005).

``CurrentTenant`` (an Annotated dependency) is the ONLY way user requests get a
tenant id:

1. read ``X-Tenant-ID`` (400 if missing or not a UUID);
2. load the caller's ACTIVE membership in that business. Visible through the
   memberships RLS policy ``user_id = app.user_id``, so this works before
   the tenant is set;
3. no membership → 404 TENANT_NOT_FOUND, identical for "exists but not
   yours" and "does not exist", plus a security log and audit entry;
4. business suspended or cancelled → 403 TENANT_INACTIVE;
5. set ``app.tenant_id`` for the request's transaction (RLS) and return
   ``TenantContext`` with the caller's role.

Services check permissions with ``ctx.require(Role.ADMIN)`` etc.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError, NotFoundError
from app.core.logging import get_logger
from app.db.session import DbSession
from app.db.tenant import set_tenant
from app.modules.audit import service as audit
from app.modules.identity.dependencies import Client, CurrentAuth
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.models import Membership, MembershipStatus, Tenant, TenantStatus

TENANT_HEADER = "X-Tenant-ID"

logger = get_logger("app.security")


class TenantHeaderError(AppError):
    status_code = 400
    code = "TENANT_REQUIRED"
    message = f"Send the business id in the {TENANT_HEADER} header."


class TenantNotFoundError(NotFoundError):
    code = "TENANT_NOT_FOUND"
    message = "Business not found."


class TenantInactiveError(AppError):
    status_code = 403
    code = "TENANT_INACTIVE"
    message = "This business is suspended or cancelled."


def _parse_tenant_header(request: Request) -> uuid.UUID:
    raw = request.headers.get(TENANT_HEADER)
    if not raw:
        raise TenantHeaderError()
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise TenantHeaderError(
            f"{TENANT_HEADER} must be a business id (UUID).", code="INVALID_TENANT_ID"
        ) from exc


async def get_tenant_context(
    request: Request, db: DbSession, auth: CurrentAuth, client: Client
) -> TenantContext:
    tenant_id = _parse_tenant_header(request)
    row = (
        await db.execute(
            select(Membership.role, Tenant.status)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == auth.user.id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
    ).first()

    if row is None:
        logger.warning("tenant_access_denied", user_id=str(auth.user.id), tenant_id=str(tenant_id))
        factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
        await audit.record_independently(
            factory,
            "security.tenant_access_denied",
            actor_user_id=auth.user.id,
            details={"requested_tenant_id": str(tenant_id)},
            ip=client.ip,
        )
        raise TenantNotFoundError()

    role, status = row
    if status in (TenantStatus.SUSPENDED, TenantStatus.CANCELLED):
        raise TenantInactiveError()

    await set_tenant(db, tenant_id)
    return TenantContext(tenant_id=tenant_id, user_id=auth.user.id, role=role)


CurrentTenant = Annotated[TenantContext, Depends(get_tenant_context)]
