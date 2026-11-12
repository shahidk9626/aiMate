"""Health probes.

Mounted at the root (not under /api/v1) because they are infrastructure
endpoints for Docker, the load balancer and uptime monitors, not part of the
versioned product API.

- ``/healthz``: liveness. The process is up and serving. Never touches
  dependencies, so a database outage does not get healthy API containers
  restarted in a loop.
- ``/readyz``: readiness (database + Redis). Added in Stage 1, step 3.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")
