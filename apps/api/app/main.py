"""Application factory.

Run locally from apps/api:
    uv run uvicorn app.main:app --reload --no-access-log
"""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import API_V1_PREFIX, api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware


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
    )
    app.state.settings = settings

    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
