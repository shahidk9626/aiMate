"""Tenancy: businesses (tenants), memberships and invitations.

RLS (migration 0002):
- tenants: readable when it is the current tenant or the current user is an
  active member; writable only as the current tenant; never deletable by the app.
- memberships: readable in the current tenant, or the current user's own rows
  across all tenants ("which businesses am I in?"); writable only in the
  current tenant.
- invitations: standard tenant isolation.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum,
    tenant_table_args,
)


class TenantStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    AGENT = "agent"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(CITEXT, unique=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default="UTC", default="UTC")
    locale: Mapped[str] = mapped_column(String(16), server_default="en", default="en")
    status: Mapped[TenantStatus] = mapped_column(
        str_enum(TenantStatus, "status"),
        server_default=TenantStatus.TRIAL.value,
        default=TenantStatus.TRIAL,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), default=dict
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = tenant_table_args(UniqueConstraint("tenant_id", "user_id"))

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))
    status: Mapped[MembershipStatus] = mapped_column(
        str_enum(MembershipStatus, "status"),
        server_default=MembershipStatus.ACTIVE.value,
        default=MembershipStatus.ACTIVE,
    )


class Invitation(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "invitations"
    __table_args__ = tenant_table_args(
        # At most one open invitation per email per business.
        Index(
            "uq_invitations_tenant_id_email_open",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    email: Mapped[str] = mapped_column(CITEXT)
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
