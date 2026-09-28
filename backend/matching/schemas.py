"""Pydantic schemas and domain models for resume/job matching."""

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MatchLevel(StrEnum):
    """Primary qualitative match classification."""

    STRONG = "STRONG"
    RELEVANT = "RELEVANT"
    POSSIBLE = "POSSIBLE"
    REJECTED = "REJECTED"


class EvaluationBreakdown(BaseModel):
    """Detailed multi-dimensional criteria evaluation."""

    role_relevance: str = Field(..., description="Assessment of title and role trajectory fit")
    required_skills: list[str] = Field(default_factory=list, description="Core technical competencies needed by the job")
    preferred_skills: list[str] = Field(default_factory=list, description="Bonus or preferred skills")
    skills_you_have: list[str] = Field(
        default_factory=list,
        description="Explicit intersection between verified resume skills and job requirements",
    )
    missing_improve: list[str] = Field(
        default_factory=list,
        description="Legitimate skills to acquire or improve before applying (zero fabrication)",
    )
    project_relevance: str = Field(..., description="How the candidate's portfolio/academic projects apply to this role")
    experience_assessment: str = Field(..., description="Years of experience and seniority evaluation")
    education_assessment: str = Field(..., description="Degree, major, and graduation year suitability")
    location_work_mode: str = Field(..., description="Geographic and remote/hybrid alignment")
    concerns: list[str] = Field(default_factory=list, description="Transparent risks, missing qualifications, or gaps")


class JobMatchEvaluation(BaseModel):
    """Complete, qualitative job match result for a single candidate profile."""

    job_id: uuid.UUID | str | None = None
    resume_profile_id: uuid.UUID | str | None = None
    match_level: MatchLevel = Field(..., description="STRONG, RELEVANT, POSSIBLE, or REJECTED")
    why_it_matches: str = Field(..., description="Detailed, transparent rationale explaining why the candidate fits")
    skills_you_have: list[str] = Field(
        default_factory=list,
        description="Confirmed technical skills candidate possesses that match this job",
    )
    missing_improve: list[str] = Field(
        default_factory=list,
        description="Specific actionable topics or tools for the candidate to study",
    )
    experience_assessment: str = Field(..., description="Detailed evaluation of entry-level / experience constraints")
    concerns: list[str] = Field(default_factory=list, description="Potential obstacles or warnings")
    breakdown: EvaluationBreakdown
    is_suitable_fresher: bool = Field(default=True, description="True if role is open to freshers/0-2 years")
    is_senior_role: bool = Field(default=False, description="True if role demands senior/lead/staff experience")
    raw_telemetry: dict[str, Any] = Field(default_factory=dict, description="Metadata for debugging and logging")
