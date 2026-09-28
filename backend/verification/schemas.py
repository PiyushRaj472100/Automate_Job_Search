"""Verification engine status schemas, signals, and outcome models."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VerificationStatus(StrEnum):
    """Conservative verification states for candidate jobs."""

    VERIFIED = "VERIFIED"  # Confirmed accessible, content matches, active application path proven
    ACTIVE = "ACTIVE"  # Confirmed active/reachable, content matches, standard application mechanism
    NEEDS_RECHECK = "NEEDS_RECHECK"  # Transient network glitch or ambiguous state requiring re-evaluation
    CLOSED = "CLOSED"  # 404, 410, or explicit expired / position filled indicators
    UNAVAILABLE = "UNAVAILABLE"  # Inaccessible, server 5xx, or access denied
    REJECTED = "REJECTED"  # Mismatched title/company or invalid landing page


class ExtractedPageSignals(BaseModel):
    """Detailed structural and semantic cues extracted from the job posting page."""

    title_matched: bool = False
    company_matched: bool = False
    location_matched: bool = False
    has_substantive_content: bool = False
    has_active_application: bool = False
    is_expired_notice: bool = False
    is_login_wall: bool = False
    is_access_denied: bool = False
    is_soft_404: bool = False
    http_status: int | None = None
    final_url: str | None = None
    page_text_length: int = 0
    detected_title: str | None = None
    detected_company: str | None = None
    application_links_found: list[str] = Field(default_factory=list)
    cues_detected: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    """Immutable audit record of a comprehensive verification evaluation."""

    job_id: uuid.UUID | str | None = None
    status: VerificationStatus
    is_usable: bool = Field(..., description="True if eligible for morning application list (VERIFIED or ACTIVE)")
    url: str
    final_url: str | None = None
    http_status: int | None = None
    application_url: str | None = None
    application_url_status: int | None = None
    application_usable: bool = False
    extracted_signals: ExtractedPageSignals
    failure_reason: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_headers: dict[str, Any] = Field(default_factory=dict)
