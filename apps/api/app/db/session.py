"""FastAPI database session dependency.

One session and one transaction per request: committed when the handler
returns, rolled back if it raises. Tenant-scoped handlers call
``set_tenant`` inside this transaction (Stage 2 wires that into the
``TenantContext`` dependency so individual handlers cannot forget).
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    async with factory() as session, session.begin():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
