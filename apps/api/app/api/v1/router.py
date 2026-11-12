"""Versioned product API. Module routers are included here as they are built."""

from fastapi import APIRouter

API_V1_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_V1_PREFIX)
