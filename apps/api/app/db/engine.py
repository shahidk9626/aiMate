"""Engine and session factories.

- API: async engine (psycopg 3 async) — ``create_async_db_engine``.
- Celery workers: sync engine (psycopg 3 sync) — ``create_sync_db_engine``.

Both connect as the restricted app role (ADR-003, ADR-006). Creating an engine
does not open a connection; the pool connects lazily on first use.
"""

from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def _engine_kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "connect_args": {
            "connect_timeout": settings.db_connect_timeout_seconds,
            "application_name": settings.app_name,
        },
    }


def create_async_db_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url(), **_engine_kwargs(settings))


def create_sync_db_engine(settings: Settings) -> Engine:
    return create_engine(settings.database_url(), **_engine_kwargs(settings))


def async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: objects stay readable after commit in async code
    # (no implicit lazy reload, which async sessions cannot do).
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def sync_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, autoflush=False)
