"""Declarative base and shared column mixins.

Naming conventions give every constraint and index a deterministic name, so
Alembic autogenerate produces stable migrations and errors name the
constraint that failed.

Tenant-owned tables use ``TenantMixin`` (adds ``tenant_id``) and
``tenant_table_args`` (adds ``UNIQUE(tenant_id, id)`` so children can use
composite foreign keys, ADR-007). Their migration must also enable RLS with
``app.db.rls.enable_tenant_rls_sql`` (a test checks every tenant table).
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, MetaData, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.db.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantMixin:
    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805 - SQLAlchemy declared_attr convention
        return mapped_column(
            ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
        )


def tenant_table_args(*extra: Any) -> tuple[Any, ...]:
    """``__table_args__`` for tenant tables: UNIQUE(tenant_id, id) plus extras."""
    return (UniqueConstraint("tenant_id", "id"), *extra)


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR + CHECK constraint for a StrEnum (ADR-009); stores the values."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        # Room to add longer values later without altering the column.
        length=max(32, *(len(member.value) for member in enum_cls)),
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
