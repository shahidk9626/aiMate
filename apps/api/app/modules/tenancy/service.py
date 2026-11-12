"""Tenancy services: creating a business at signup (step 2.3); business profile
and team management (step 2.4). Invitations arrive in step 2.5.
"""

import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.audit import service as audit
from app.modules.identity.models import User
from app.modules.tenancy.context import ROLE_RANK, TenantContext
from app.modules.tenancy.models import Membership, MembershipStatus, Role, Tenant
from app.modules.tenancy.schemas import (
    MemberOut,
    TenantOut,
    UpdateMemberRequest,
    UpdateTenantRequest,
)

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


# --- business profile and team (step 2.4) ---------------------------------------------
#
# Every function below receives a verified TenantContext; app.tenant_id is set
# for the transaction, so RLS confines all queries to that business.
#
# Role matrix (STAGE_2_DESIGN.md §5.4, as implemented):
#   view profile / team ................ any member
#   edit profile ....................... admin, owner
#   change anyone's role ............... owner
#   remove an agent .................... admin, owner
#   remove an admin or owner ........... owner
#   leave (remove yourself) ............ anyone
#   leave the business without an owner  nobody (409 LAST_OWNER)


class MemberNotFoundError(NotFoundError):
    code = "MEMBER_NOT_FOUND"
    message = "Team member not found."


class LastOwnerError(ConflictError):
    code = "LAST_OWNER"
    message = "A business must keep at least one owner. Make someone else an owner first."


async def get_tenant(db: AsyncSession, ctx: TenantContext) -> TenantOut:
    tenant = await db.get(Tenant, ctx.tenant_id)
    if tenant is None:  # pragma: no cover - the context guarantees it exists
        raise NotFoundError()
    return TenantOut.model_validate(tenant, from_attributes=True)


async def update_tenant(
    db: AsyncSession, ctx: TenantContext, data: UpdateTenantRequest, client_ip: str | None
) -> TenantOut:
    ctx.require(Role.ADMIN)
    tenant = await db.get(Tenant, ctx.tenant_id)
    if tenant is None:  # pragma: no cover
        raise NotFoundError()
    changed = sorted(data.model_fields_set)
    for field in changed:
        setattr(tenant, field, getattr(data, field))
    await db.flush()
    await db.refresh(tenant)
    await audit.record(
        db,
        "tenant.updated",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        resource_type="tenant",
        resource_id=ctx.tenant_id,
        details={"fields": changed},
        ip=client_ip,
    )
    return TenantOut.model_validate(tenant, from_attributes=True)


def _member_out(membership: Membership, user: User) -> MemberOut:
    return MemberOut(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=membership.role,
        status=membership.status,
        joined_at=membership.created_at,
    )


async def list_members(db: AsyncSession, ctx: TenantContext) -> list[MemberOut]:
    rows = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        # RLS already limits memberships to this tenant; the filter states intent.
        .where(Membership.tenant_id == ctx.tenant_id)
    )
    members = [_member_out(m, u) for m, u in rows.all()]
    return sorted(members, key=lambda m: (-ROLE_RANK[m.role], m.full_name.casefold()))


async def _load_member(
    db: AsyncSession, ctx: TenantContext, user_id: uuid.UUID
) -> tuple[Membership, User]:
    row = (
        await db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == ctx.tenant_id, Membership.user_id == user_id)
            .with_for_update(of=Membership)
        )
    ).first()
    if row is None:
        raise MemberNotFoundError()
    membership, user = row
    return membership, user


async def _ensure_another_owner_remains(
    db: AsyncSession, ctx: TenantContext, leaving: Membership
) -> None:
    """Called when ``leaving`` stops being an active owner.

    Locks all owner memberships of the business first, so two owners demoting
    each other concurrently cannot both succeed.
    """
    owners = (
        await db.scalars(
            select(Membership)
            .where(
                Membership.tenant_id == ctx.tenant_id,
                Membership.role == Role.OWNER,
                Membership.status == MembershipStatus.ACTIVE,
            )
            .with_for_update()
        )
    ).all()
    if not any(owner.id != leaving.id for owner in owners):
        raise LastOwnerError()


async def change_member_role(
    db: AsyncSession,
    ctx: TenantContext,
    user_id: uuid.UUID,
    data: UpdateMemberRequest,
    client_ip: str | None,
) -> MemberOut:
    ctx.require(Role.OWNER)
    membership, user = await _load_member(db, ctx, user_id)
    previous = membership.role
    if previous == data.role:
        return _member_out(membership, user)
    if previous == Role.OWNER:
        await _ensure_another_owner_remains(db, ctx, membership)

    membership.role = data.role
    await db.flush()
    await db.refresh(membership)
    await audit.record(
        db,
        "member.role_changed",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        resource_type="user",
        resource_id=user_id,
        details={"from": previous.value, "to": data.role.value},
        ip=client_ip,
    )
    return _member_out(membership, user)


async def remove_member(
    db: AsyncSession, ctx: TenantContext, user_id: uuid.UUID, client_ip: str | None
) -> None:
    membership, _ = await _load_member(db, ctx, user_id)
    leaving_self = user_id == ctx.user_id
    if not leaving_self:
        # Admins may remove agents; only owners may remove admins and owners.
        ctx.require(Role.OWNER if membership.role != Role.AGENT else Role.ADMIN)
    if membership.role == Role.OWNER:
        await _ensure_another_owner_remains(db, ctx, membership)

    await db.delete(membership)
    await db.flush()
    await audit.record(
        db,
        "member.left" if leaving_self else "member.removed",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        resource_type="user",
        resource_id=user_id,
        details={"role": membership.role.value},
        ip=client_ip,
    )
