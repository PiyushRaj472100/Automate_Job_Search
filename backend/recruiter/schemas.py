"""Pydantic schemas and domain models for recruiter and hiring-person discovery."""

import uuid
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RecruiterStatus(StrEnum):
    """Conservative verification statuses for discovered professional profiles."""

    VERIFIED = "VERIFIED"
    PLAUSIBLE = "PLAUSIBLE"
    UNVERIFIED = "UNVERIFIED"
    NOT_FOUND = "NOT_FOUND"


class RecruiterRoleTier(int, Enum):
    """Strict priority ranking for candidate professional roles.

    Ranked 1 to 6 in order of recruitment relevance:
    1. Recruiter
    2. Talent Acquisition
    3. Technical Recruiter
    4. Hiring Manager
    5. Engineering Manager
    6. Relevant recruitment professional
    99. Unrelated employee (rejected)
    """

    RECRUITER = 1
    TALENT_ACQUISITION = 2
    TECHNICAL_RECRUITER = 3
    HIRING_MANAGER = 4
    ENGINEERING_MANAGER = 5
    RECRUITMENT_PROFESSIONAL = 6
    UNRELATED = 99


class RawCandidateProfile(BaseModel):
    """Raw candidate profile data before conservative verification."""

    name: str
    title: str | None = None
    company: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    source: str = "discovery"
    claimed_job_ownership: bool = False
    evidence_text: str | None = None


class ProfileVerificationResult(BaseModel):
    """Verified professional profile with complete provenance and confidence metrics."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    title: str
    company: str
    linkedin_url: str | None = None
    email: str | None = None
    status: RecruiterStatus
    role_tier: RecruiterRoleTier
    confidence: float = Field(ge=0.0, le=1.0)
    is_job_owner: bool = False
    relevance_reason: str
    verification_source: str = "profile_verifier"
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    verification_details: dict[str, Any] = Field(default_factory=dict)

    def to_formatted_display(self) -> str:
        """Render clean string representation for Google Sheets or UI display."""
        parts = [f"{self.name} ({self.title})"]
        if self.linkedin_url:
            parts.append(self.linkedin_url)
        if self.email:
            parts.append(f"<{self.email}>")
        return " - ".join(parts)


class JobRecruiterDiscoveryResult(BaseModel):
    """Result of recruiter discovery for a specific job."""

    job_id: uuid.UUID | None = None
    job_title: str
    company_name: str
    verified_recruiters: list[ProfileVerificationResult] = Field(default_factory=list)
    plausible_recruiters: list[ProfileVerificationResult] = Field(default_factory=list)
    unverified_recruiters: list[ProfileVerificationResult] = Field(default_factory=list)
    overall_status: RecruiterStatus = RecruiterStatus.NOT_FOUND

    # Primary recruiter columns for Google Sheets (Maximum 3, strictly VERIFIED only)
    recruiter_1: str = ""
    recruiter_2: str = ""
    recruiter_3: str = ""
