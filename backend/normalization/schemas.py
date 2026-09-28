"""Canonical job models and duplicate resolution schemas."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WorkMode(StrEnum):
    """Normalized work mode categories."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ON_SITE = "on_site"
    UNKNOWN = "unknown"


class DuplicateMatchReason(StrEnum):
    """Categorized signals that determined duplicate identity."""

    REQUISITION_ID = "requisition_id_match"
    CANONICAL_URL = "canonical_url_match"
    APPLICATION_URL = "application_url_match"
    COMPANY_AND_JOB_ID = "company_job_id_match"
    COMPOSITE_EXACT = "composite_company_title_location_match"
    SEMANTIC_SIMILARITY = "semantic_multi_signal_match"


class CanonicalJob(BaseModel):
    """Unified canonical job posting across all discovery sources."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Stable internal unique identifier")
    title: str = Field(..., description="Normalized job title")
    company: str = Field(..., description="Normalized company name")
    location: str = Field(..., description="Normalized geographic location or Remote")
    work_mode: WorkMode = Field(default=WorkMode.UNKNOWN, description="Normalized work mode")
    description: str = Field(..., description="Cleaned job description text")

    # Identifiers
    job_id: str | None = Field(default=None, description="Source or external job identifier")
    requisition_id: str | None = Field(default=None, description="Official ATS requisition code (e.g. REQ-1042)")

    # URLs
    job_url: str = Field(..., description="Primary public job URL")
    application_url: str | None = Field(default=None, description="Direct application submission URL")
    canonical_url: str = Field(..., description="Canonicalized and tracking-stripped URL")
    alternate_urls: list[str] = Field(default_factory=list, description="All associated URLs across sources")

    # Dates
    posting_date: datetime | None = Field(default=None, description="Original posting timestamp if known")
    updated_date: datetime | None = Field(default=None, description="Last updated timestamp from source")
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC), description="First discovery time")
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Most recent discovery time")

    # Metadata & Categorization
    skills: list[str] = Field(default_factory=list, description="Extracted and normalized technical skills")
    sources: list[str] = Field(default_factory=list, description="All source names where this job was found")
    primary_source: str = Field(..., description="Original or authoritative source")

    # Normalization & Deduplication internals
    normalized_company: str = Field(..., description="Standardized company string for index matching")
    normalized_title: str = Field(..., description="Standardized title string for index matching")
    normalized_location: str = Field(..., description="Standardized location string for index matching")
    dedup_hash: str = Field(..., description="Deterministic SHA-256 fingerprint")

    # Deduplication history
    duplicate_count: int = Field(default=1, description="Number of duplicate occurrences aggregated")
    match_reasons: list[DuplicateMatchReason] = Field(
        default_factory=list,
        description="Reasons why merged duplicates were linked",
    )
    raw_payloads: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Original raw payloads preserved for debugging",
    )


class DuplicateMatchResult(BaseModel):
    """Result of duplicate comparison between two jobs."""

    is_duplicate: bool
    confidence_score: float = Field(ge=0.0, le=1.0)
    match_reason: DuplicateMatchReason | None = None
    signals: dict[str, Any] = Field(default_factory=dict)
    rejection_reason: str | None = None
