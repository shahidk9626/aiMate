"""Tenancy services. Stage 2 step 2.3: creating a business at signup.

Business/team management (profile, members, invitations) arrives in step 2.4.
"""

import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tenancy.models import Membership, MembershipStatus, Role, Tenant

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def make_slug(name: str) -> str:
    """URL-friendly, unique-by-construction slug: 'Acme Dental!' -> 'acme-dental-3f9a1c'."""
    base = _NON_SLUG.sub("-", name.lower()).strip("-")[:40].strip("-") or "business"
    return f"{base}-{secrets.token_hex(3)}"


async def create_tenant_with_owner(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    name: str,
    timezone: str,
) -> Tenant:
    """Caller must have set app.tenant_id = tenant_id for this transaction (RLS)."""
    tenant = Tenant(id=tenant_id, name=name, slug=make_slug(name), timezone=timezone)
    db.add(tenant)
    await db.flush()
    db.add(Membership(tenant_id=tenant_id, user_id=owner_user_id, role=Role.OWNER))
    await db.flush()
    return tenant


async def active_memberships(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[Tenant, Role]]:
    """The user's businesses. Visible across tenants via the memberships RLS policy."""
    rows = await db.execute(
        select(Tenant, Membership.role)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(Tenant.name, Tenant.id)
    )
    return [(tenant, role) for tenant, role in rows.all()]
