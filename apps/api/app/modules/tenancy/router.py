"""HTTP routes for the current business and its team (docs/API_CONTRACTS.md, Stage 2).

Every route depends on ``CurrentTenant``: X-Tenant-ID is verified against the
caller's membership before any handler runs. Permission checks are in the
service layer.
"""

import uuid

from fastapi import APIRouter, Request, Response, status

from app.core.responses import Envelope, envelope
from app.db.session import DbSession
from app.modules.identity.dependencies import Client
from app.modules.tenancy import service
from app.modules.tenancy.dependencies import CurrentTenant
from app.modules.tenancy.schemas import (
    MemberOut,
    TenantOut,
    UpdateMemberRequest,
    UpdateTenantRequest,
)

router = APIRouter(prefix="/tenant", tags=["business"])


@router.get("", response_model=Envelope[TenantOut], summary="The current business")
async def get_tenant(request: Request, db: DbSession, ctx: CurrentTenant) -> Envelope[TenantOut]:
    return envelope(request, await service.get_tenant(db, ctx))


@router.patch("", response_model=Envelope[TenantOut], summary="Update the business (admin+)")
async def update_tenant(
    request: Request, data: UpdateTenantRequest, db: DbSession, ctx: CurrentTenant, client: Client
) -> Envelope[TenantOut]:
    return envelope(request, await service.update_tenant(db, ctx, data, client.ip))


@router.get("/members", response_model=Envelope[list[MemberOut]], summary="The team")
async def list_members(
    request: Request, db: DbSession, ctx: CurrentTenant
) -> Envelope[list[MemberOut]]:
    return envelope(request, await service.list_members(db, ctx))


@router.patch(
    "/members/{user_id}", response_model=Envelope[MemberOut], summary="Change a role (owner)"
)
async def change_member_role(
    request: Request,
    user_id: uuid.UUID,
    data: UpdateMemberRequest,
    db: DbSession,
    ctx: CurrentTenant,
    client: Client,
) -> Envelope[MemberOut]:
    return envelope(request, await service.change_member_role(db, ctx, user_id, data, client.ip))


@router.delete(
    "/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member, or leave (your own user id)",
)
async def remove_member(
    user_id: uuid.UUID, db: DbSession, ctx: CurrentTenant, client: Client
) -> Response:
    await service.remove_member(db, ctx, user_id, client.ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
