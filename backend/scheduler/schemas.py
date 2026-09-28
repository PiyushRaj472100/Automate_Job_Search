"""Schemas and configuration models for scheduled continuous operation."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.matching.schemas import MatchLevel
from backend.pipeline.schemas import PipelineJobOutput


class ScheduleConfig(BaseModel):
    """Configuration for continuous automated job intelligence pipeline."""

    discovery_interval_hours: float = Field(
        default=6.0,
        description="Hours between automated incremental discovery cycles",
    )
    morning_report_time: str = Field(
        default="08:00",
        description="Daily 24-hr time (HH:MM) to run final morning verification and update Google Sheet",
    )
    max_retries_per_source: int = Field(
        default=3,
        description="Maximum retry attempts on transient source failure",
    )
    retry_backoff_base_seconds: float = Field(
        default=1.0,
        description="Base backoff delay in seconds for exponential backoff (delay = base * 2^attempt)",
    )
    source_rate_limits: dict[str, int] = Field(
        default_factory=lambda: {
            "arbeitnow": 30,
            "remotive": 20,
            "greenhouse": 40,
            "default": 20,
        },
        description="Per-source rate limits (requests per minute)",
    )
    incremental: bool = Field(
        default=True,
        description="Whether to perform incremental discovery using high-water mark timestamps",
    )
    min_match_level: MatchLevel = Field(
        default=MatchLevel.RELEVANT,
        description="Minimum match level to qualify for primary morning view",
    )
    sync_to_sheets: bool = Field(
        default=True,
        description="Synchronize morning verified results to Google Sheets",
    )


class CycleExecutionRecord(BaseModel):
    """Telemetry and tracking record for an individual source discovery cycle."""

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_name: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: str = "running"  # running, completed, failed
    jobs_discovered: int = 0
    jobs_accepted: int = 0
    jobs_rejected: int = 0
    errors: list[str] = Field(default_factory=list)
    retries_attempted: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MorningPassSummary(BaseModel):
    """Telemetry and output summary for the final morning verification pass."""

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: str = "completed"
    candidates_rechecked: int = 0
    still_verified: int = 0
    closed_or_expired: int = 0
    sheet_rows_updated: int = 0
    errors: list[str] = Field(default_factory=list)
    primary_morning_jobs: list[PipelineJobOutput] = Field(default_factory=list)
