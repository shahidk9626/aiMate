"""Identity: users, login sessions, single-use email tokens.

These tables are global (not owned by a tenant) but still protected by RLS
keyed on the current user (ADR-023): a user sees their own rows, plus the
user rows of teammates in the current tenant. Lookups by email or token hash,
before the user is known, go through SECURITY DEFINER functions that return
ids only (migration 0002).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(UUIDPrimaryKeyMixin, Base):
    """A login session (ADR-023). Only the SHA-256 hash of the token is stored."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Absolute expiry; the idle timeout is enforced from last_seen_at.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip: Mapped[str | None] = mapped_column(INET)


class EmailTokenPurpose(StrEnum):
    PASSWORD_RESET = "password_reset"  # noqa: S105 - enum value, not a secret
    EMAIL_VERIFICATION = "email_verification"


class EmailToken(UUIDPrimaryKeyMixin, Base):
    """Single-use token sent by email. Only the SHA-256 hash is stored."""

    __tablename__ = "email_tokens"
    __table_args__ = (Index(None, "user_id", "purpose"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[EmailTokenPurpose] = mapped_column(str_enum(EmailTokenPurpose, "purpose"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
