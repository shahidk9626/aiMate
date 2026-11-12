"""Application factory.

Run locally from apps/api:
    uv run uvicorn app.main:app --reload --no-access-log
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.router import API_V1_PREFIX, api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import RateLimiter
from app.core.redis import create_redis_client
from app.core.request_context import REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.security_middleware import (
    BodySizeLimitMiddleware,
    CatchAllErrorsMiddleware,
    CSRFMiddleware,
    SecurityHeadersMiddleware,
)
from app.db.engine import async_session_factory, create_async_db_engine

logger = get_logger("app.lifecycle")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    # web_origin is logged so a port/host mismatch with the browser is obvious.
    logger.info("startup", env=settings.app_env.value, web_origin=settings.web_origin)
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
    app.state.rate_limiter = RateLimiter(app.state.redis)

    register_exception_handlers(app)
    # Middleware: each add_middleware wraps the previous ones, so the LAST added
    # is the OUTERMOST. Resulting order, outermost first:
    #   CORS → request id → security headers → catch-all errors → body limit → CSRF → app
    app.add_middleware(CSRFMiddleware, trusted_origin=settings.web_origin)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(CatchAllErrorsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    # Exactly one trusted origin; credentials allowed because the dashboard
    # authenticates with an HttpOnly session cookie (ADR-023).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Content-Type",
            "X-Requested-With",
            "X-Tenant-ID",
            "Idempotency-Key",
            REQUEST_ID_HEADER,
        ],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
