"""Health check endpoint definition."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from backend.core.config import Settings, get_settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Schema for health check response."""

    status: str = Field(default="ok", examples=["ok"])
    project: str = Field(..., examples=["Personal Job Intelligence Platform"])
    environment: str = Field(..., examples=["development"])
    version: str = Field(default="0.1.0", examples=["0.1.0"])
    timestamp: datetime = Field(..., description="UTC timestamp of the health check")


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check probe",
    description="Returns the health status and current runtime metadata of the service.",
)
async def get_health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Retrieve service health status."""
    return HealthResponse(
        status="ok",
        project=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        version="0.1.0",
        timestamp=datetime.now(UTC),
    )
