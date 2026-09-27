"""Main API router combining all sub-routers."""

from fastapi import APIRouter

from backend.api.routes import health

api_router = APIRouter()

# Include health routes under /api/v1 as well
api_router.include_router(health.router)
