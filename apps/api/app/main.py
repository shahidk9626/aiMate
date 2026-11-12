"""Application factory.

Run locally from apps/api:
    uv run uvicorn app.main:app --reload --no-access-log
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import API_V1_PREFIX, api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.redis import create_redis_client
from app.core.request_context import RequestContextMiddleware
from app.db.engine import async_session_factory, create_async_db_engine

logger = get_logger("app.lifecycle")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("startup", env=app.state.settings.app_env.value)
    try:
        yield
    finally:
        # Release pooled connections so shutdown is clean and fast.
        await app.state.db_engine.dispose()
        await app.state.redis.aclose()
        logger.info("shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    docs = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        openapi_url=f"{API_V1_PREFIX}/openapi.json" if docs else None,
        docs_url=f"{API_V1_PREFIX}/docs" if docs else None,
        redoc_url=None,
        lifespan=_lifespan,
    )

    # Created eagerly but connect lazily: no I/O happens here.
    app.state.settings = settings
    app.state.db_engine = create_async_db_engine(settings)
    app.state.db_session_factory = async_session_factory(app.state.db_engine)
    app.state.redis = create_redis_client(settings)

    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
