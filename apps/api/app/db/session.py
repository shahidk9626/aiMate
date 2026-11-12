"""FastAPI database session dependency.

One session and one transaction per request: committed when the handler
returns, rolled back if it raises. Tenant-scoped handlers receive the tenant
through the ``TenantContext`` dependency, which sets it on this transaction.

``scope="function"`` is essential: it makes FastAPI run the commit *before*
the response is sent. With the default scope the commit runs after the
response, so a failed commit (e.g. a unique-constraint race) would still have
answered "201 Created" and set cookies for data that was never saved.
Verified in Stage 2 step 2.3; covered by tests/integration/test_auth_api.py.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    async with factory() as session, session.begin():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
