"""Writing audit entries.

``record`` writes inside the caller's transaction: the entry is committed or
rolled back together with the action it describes.

``record_independently`` commits in its own short transaction. Use it only
for events that must survive a failing request, such as a failed login: the
request raises (and rolls back), but the attempt must still be on record.

Never put passwords, tokens, email addresses or message content in
``details``; ids and short codes only.
"""

import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.ids import uuid7
from app.modules.audit.models import AuditLog


async def record(
    db: AsyncSession,
    action: str,
    *,
    tenant_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    # Core insert without RETURNING: tenant-less rows are not readable back under RLS.
    await db.execute(
        insert(AuditLog).values(
            id=uuid7(),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip=ip,
        )
    )


async def record_independently(
    factory: async_sessionmaker[AsyncSession],
    action: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Tenant-less entry committed in its own transaction."""
    async with factory() as db, db.begin():
        await record(db, action, actor_user_id=actor_user_id, details=details, ip=ip)
