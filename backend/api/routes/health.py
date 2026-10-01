"""Health check endpoint definition.

Provides both liveness (/health) and readiness (/ready) endpoints.
Readiness checks critical dependencies: database connection, Google Sheets client.
Also includes /metrics for basic pipeline metrics.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from backend.core.config import Settings, get_settings
from backend.db.session import SyncSessionLocal, get_sync_session
from backend.models.search_run import SearchRun
from backend.sheets.client import GoogleSheetsManager

logger = logging.getLogger("job_intelligence.health")

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Schema for health check response."""

    status: str = Field(default="ok", examples=["ok"])
    project: str = Field(..., examples=["Personal Job Intelligence Platform"])
    environment: str = Field(..., examples=["development"])
    version: str = Field(default="0.1.0", examples=["0.1.0"])
    timestamp: datetime = Field(..., description="UTC timestamp of the health check")


class ReadyResponse(BaseModel):
    """Schema for readiness check response."""

    ready: bool = Field(..., description="True if all dependencies are healthy")
    details: dict = Field(..., description="Per‑component status details")
    timestamp: datetime = Field(..., description="UTC timestamp of the readiness check")


class MetricsResponse(BaseModel):
    """Basic pipeline metrics extracted from SearchRun records."""

    last_successful_run: datetime | None = Field(None, description="Timestamp of last successful run")
    last_failed_run: datetime | None = Field(None, description="Timestamp of last failed run")
    total_runs: int = Field(0, description="Total number of runs recorded")
    failed_runs: int = Field(0, description="Number of runs that ended with failure")
    timestamp: datetime = Field(..., description="UTC timestamp of the metrics response")


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


@router.get(
    "/ready",
    response_model=ReadyResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
    description="Verifies that critical external dependencies (DB, Google Sheets) are reachable.",
)
async def get_ready(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Any:
    details = {}
    # DB check (sync for simplicity)
    try:
        with SyncSessionLocal() as session:
            session.execute(select(1))
        details["database"] = "ok"
    except Exception as e:
        details["database"] = f"error: {e}"
    # Google Sheets check
    try:
        manager = GoogleSheetsManager()
        manager.get_client()
        details["google_sheets"] = "ok"
    except Exception as e:
        details["google_sheets"] = f"error: {e}"
    ready = all(v == "ok" for v in details.values())
    if not ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "ready": False,
                "details": details,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    return ReadyResponse(ready=True, details=details, timestamp=datetime.now(UTC))


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Pipeline metrics",
    description="Provides basic metrics about pipeline runs from the system of record.",
)
async def get_metrics() -> MetricsResponse:
    last_success = None
    last_failed = None
    total = 0
    failed = 0
    try:
        with SyncSessionLocal() as session:
            total = session.scalar(select(func.count(SearchRun.id))) or 0
            failed = session.scalar(select(func.count(SearchRun.id)).where(SearchRun.status == "failed")) or 0
            last_success = (
                session.execute(
                    select(SearchRun)
                    .where(SearchRun.status == "completed")
                    .order_by(desc(SearchRun.completed_at))
                    .limit(1)
                )
                .scalar_one_or_none()
            )
            last_failed = (
                session.execute(
                    select(SearchRun)
                    .where(SearchRun.status == "failed")
                    .order_by(desc(SearchRun.completed_at))
                    .limit(1)
                )
                .scalar_one_or_none()
            )
    except Exception as e:
        logger.warning("Could not retrieve pipeline metrics from database: %s", e)

    return MetricsResponse(
        last_successful_run=last_success.completed_at if last_success else None,
        last_failed_run=last_failed.completed_at if last_failed else None,
        total_runs=total,
        failed_runs=failed,
        timestamp=datetime.now(UTC),
    )



