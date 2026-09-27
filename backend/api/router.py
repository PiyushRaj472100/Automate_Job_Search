"""Main API router combining all sub-routers."""

from fastapi import APIRouter

from backend.api.routes import health, resumes

api_router = APIRouter()

# Include routes under /api/v1
api_router.include_router(health.router)
api_router.include_router(resumes.router)
