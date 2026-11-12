"""Versioned product API. Module routers are included here as they are built."""

from fastapi import APIRouter

from app.modules.identity.router import router as identity_router

API_V1_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_V1_PREFIX)
api_router.include_router(identity_router)
