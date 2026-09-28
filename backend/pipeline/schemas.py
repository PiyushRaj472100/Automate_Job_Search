"""Domain schemas and configuration models for the End-to-End Job Intelligence Pipeline."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.matching.schemas import MatchLevel
from backend.recruiter.schemas import ProfileVerificationResult, RecruiterStatus
from backend.sheets.constants import ApplicationStatus
from backend.verification.schemas import VerificationStatus


class PipelineConfig(BaseModel):
    """Configuration options for a single end-to-end pipeline run."""

    min_match_level: MatchLevel = MatchLevel.RELEVANT
    require_verified_job: bool = True
    max_jobs_to_process: int = 50
    sync_to_sheets: bool = True
    check_network: bool = False
    custom_sources: list[str] | None = None
    candidate_recruiter_pool: list[dict[str, Any]] | None = None


class PipelineStageMetrics(BaseModel):
    """Execution telemetry tracking job counts across all pipeline stages."""

    jobs_discovered: int = 0
    duplicates_removed: int = 0
    jobs_rejected: int = 0
    jobs_verified: int = 0
    matches_evaluated: int = 0
    strong_matches: int = 0
    relevant_matches: int = 0
    recruiter_profiles_found: int = 0
    sheet_rows_created: int = 0


class PipelineJobOutput(BaseModel):
    """A qualified, verified job ready for the primary morning view and Google Sheet."""

    job_id: uuid.UUID
    title: str
    company: str
    location: str
    work_mode: str
    experience: str
    job_url: str
    application_url: str | None = None
    source: str
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_verified: datetime = Field(default_factory=lambda: datetime.now(UTC))
    verification_status: VerificationStatus
    source_quality: str = "high"
    match_level: MatchLevel
    why_it_matches: str
    required_skills: list[str] = Field(default_factory=list)
    skills_you_have: list[str] = Field(default_factory=list)
    missing_improve: list[str] = Field(default_factory=list)
    experience_assessment: str
    concerns: list[str] = Field(default_factory=list)
    recruiter_1: str = ""
    recruiter_2: str = ""
    recruiter_3: str = ""
    verified_recruiters: list[ProfileVerificationResult] = Field(default_factory=list)
    recruiter_status: RecruiterStatus = RecruiterStatus.NOT_FOUND
    application_status: ApplicationStatus = ApplicationStatus.NEW
    sheet_row_index: int | None = None

    def to_sheet_row_dict(self, resume_label: str) -> dict[str, Any]:
        """Convert to dictionary matching the exact 27 JOBS_HEADERS columns."""
        return {
            "Date Found": self.first_seen.strftime("%Y-%m-%d"),
            "Job Title": self.title,
            "Company": self.company,
            "Experience": self.experience,
            "Location": self.location,
            "Work Mode": self.work_mode,
            "Job Link": self.job_url,
            "Direct Application Link": self.application_url or self.job_url,
            "Source": self.source,
            "Job ID": str(self.job_id),
            "First Seen": self.first_seen.isoformat(),
            "Last Verified": self.last_verified.isoformat(),
            "Verification Status": self.verification_status.value,
            "Source Quality": self.source_quality,
            "Match Level": self.match_level.value,
            "Why It Matches": self.why_it_matches,
            "Required Skills": ", ".join(self.required_skills),
            "Skills You Have": ", ".join(self.skills_you_have),
            "Missing / Improve": "; ".join(self.missing_improve),
            "Resume": resume_label,
            "Recruiter 1": self.recruiter_1,
            "Recruiter 2": self.recruiter_2,
            "Recruiter 3": self.recruiter_3,
            "Application Status": self.application_status.value,
            "Applied Date": "",
            "Follow-up Date": "",
            "Notes": f"Experience note: {self.experience_assessment}",
        }


class PipelineRunSummary(BaseModel):
    """Complete results, telemetry, and output from an end-to-end pipeline run."""

    resume_id: uuid.UUID
    resume_profile_id: uuid.UUID
    search_run_id: uuid.UUID | None = None
    status: str = "completed"
    candidate_name: str
    target_role: str
    spreadsheet_id: str | None = None
    spreadsheet_url: str | None = None
    metrics: PipelineStageMetrics = Field(default_factory=PipelineStageMetrics)
    primary_morning_jobs: list[PipelineJobOutput] = Field(default_factory=list)
    failed_sources: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
