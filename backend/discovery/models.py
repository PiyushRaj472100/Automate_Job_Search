"""Data structures, domain schemas, and policy models for the job discovery engine."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    """Categorization of job source access mechanisms."""

    OFFICIAL_API = "official_api"
    PUBLIC_FEED = "public_feed"
    COMPANY_CAREER_PAGE = "company_career_page"
    SEARCH_ENGINE = "search_engine"
    PUBLIC_PAGE = "public_page"


class SourcePolicy(BaseModel):
    """Legal, compliance, rate limiting, and technical access specification for a job source."""

    source_name: str
    source_type: SourceType
    base_url: str
    official_api_available: bool = False
    feed_available: bool = False
    public_page_available: bool = False
    robots_restrictions: str = "Permitted for public search and discovery"
    rate_limit_per_minute: int = 30
    authentication_required: bool = False
    permitted_access_method: str = "Direct HTTP REST API / Public Feed"
    notes: str = ""


class SearchQuery(BaseModel):
    """Normalized query parameters emitted by the search query engine."""

    query_text: str = Field(..., description="Full search query phrase (e.g. 'Junior Backend Engineer Python')")
    role_title: str = Field(..., description="Core role title")
    skills: list[str] = Field(default_factory=list, description="Target technical skills")
    experience_level: str = Field(default="entry_level", description="Target experience keyword (fresher, 0-2 years, junior)")
    location: str | None = Field(default=None, description="Target geographic location")
    work_mode: str | None = Field(default=None, description="Preferred work mode (remote, hybrid, on_site)")
    limit: int = Field(default=25, description="Maximum number of items to retrieve")


class RawJobPosting(BaseModel):
    """Unprocessed job posting extracted from a source adapter before database normalization."""

    source_name: str = Field(..., description="Name of the source adapter (e.g. arbeitnow, remotive, greenhouse)")
    external_job_id: str | None = Field(default=None, description="Source-provided unique job identifier")
    requisition_id: str | None = Field(default=None, description="ATS requisition identifier if available")
    title: str = Field(..., description="Job title")
    company_name: str = Field(..., description="Company or hiring organization name")
    location: str = Field(default="Remote", description="Job location or remote status")
    work_mode: str = Field(default="unknown", description="Work mode: remote, hybrid, on_site, unknown")
    description: str = Field(..., description="Full job description or summary text")
    job_url: str = Field(..., description="Public link to the job posting")
    application_url: str | None = Field(default=None, description="Direct URL to submit application")
    posting_date: datetime | None = Field(default=None, description="Publication timestamp if available")
    tags: list[str] = Field(default_factory=list, description="Associated skill/category tags from the source")
    raw_payload: dict[str, Any] = Field(default_factory=dict, description="Original unparsed response payload")


class SourceHealthCheck(BaseModel):
    """Health status probe result for a source adapter."""

    source_name: str
    is_healthy: bool
    status_code: int | None = None
    response_time_ms: float = 0.0
    details: str = "OK"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
