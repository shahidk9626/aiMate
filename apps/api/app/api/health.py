"""Health probes.

Mounted at the root (not under /api/v1) because they are infrastructure
endpoints for Docker, the load balancer and uptime monitors, not part of the
versioned product API.

- ``/healthz``: liveness. The process is up and serving. Never touches
  dependencies, so a database outage does not get healthy API containers
  restarted in a loop.
- ``/readyz``: readiness. 200 only when PostgreSQL and Redis both answer
  within the timeout; otherwise 503 so the load balancer stops routing here.
  Failure reasons are logged, never returned (no hostnames or errors leak).
"""

import asyncio
from collections.abc import Awaitable
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger("app.health")

CheckStatus = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessChecks(BaseModel):
    database: CheckStatus
    redis: CheckStatus


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: ReadinessChecks


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


async def _check_database(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis(client: Redis) -> None:
    await client.ping()


async def _probe(name: str, check: Awaitable[None], limit_seconds: float) -> CheckStatus:
    try:
        async with asyncio.timeout(limit_seconds):
            await check
    except Exception as exc:
        logger.warning("readiness_check_failed", check=name, error_type=type(exc).__name__)
        return "unavailable"
    return "ok"


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse}},
)
async def readyz(request: Request, response: Response) -> ReadinessResponse:
    state = request.app.state
    timeout: float = state.settings.readiness_timeout_seconds
    database, redis = await asyncio.gather(
        _probe("database", _check_database(state.db_engine), timeout),
        _probe("redis", _check_redis(state.redis), timeout),
    )
    ready = database == "ok" and redis == "ok"
    if not ready:
        response.status_code = 503
    return ReadinessResponse(
        status="ok" if ready else "unavailable",
        checks=ReadinessChecks(database=database, redis=redis),
    )
