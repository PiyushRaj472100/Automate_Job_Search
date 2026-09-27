"""Strict Pydantic schemas for structured resume extraction and API responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EducationItem(BaseModel):
    """Structured education entry."""

    degree: str | None = Field(default=None, description="Degree obtained or pursued (e.g. B.Tech Computer Science)")
    institution: str | None = Field(default=None, description="University or college name")
    graduation_year: int | None = Field(default=None, description="Graduation year (e.g. 2024)")
    field_of_study: str | None = Field(default=None, description="Major or field of study")


class ExperienceItem(BaseModel):
    """Structured employment experience entry."""

    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    location: str | None = Field(default=None, description="Location or remote status")
    start_date: str | None = Field(default=None, description="Start date string (e.g. June 2023)")
    end_date: str | None = Field(default=None, description="End date or 'Present'")
    is_current: bool = Field(default=False, description="Whether this is the candidate's current role")
    bullets: list[str] = Field(default_factory=list, description="Key bullet points/achievements")


class InternshipItem(BaseModel):
    """Structured internship entry."""

    title: str = Field(..., description="Internship title")
    organization: str = Field(..., description="Company or organization")
    duration: str | None = Field(default=None, description="Dates or duration")
    bullets: list[str] = Field(default_factory=list, description="Key responsibilities")


class ProjectItem(BaseModel):
    """Structured portfolio or academic project entry."""

    title: str = Field(..., description="Project title")
    description: str | None = Field(default=None, description="Description of the project")
    technologies: list[str] = Field(default_factory=list, description="Explicit technologies used in this project")


class CategorizedSkills(BaseModel):
    """Fine-grained, verified skill categories extracted explicitly from the resume."""

    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    libraries: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)
    ai_ml: list[str] = Field(default_factory=list)
    genai_llm: list[str] = Field(default_factory=list)
    backend: list[str] = Field(default_factory=list)
    frontend: list[str] = Field(default_factory=list)
    devops: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    apis: list[str] = Field(default_factory=list)


class StructuredResumeExtraction(BaseModel):
    """Strict schema for AI resume extraction. Zero hallucination enforced."""

    # Top-Level Education Summary
    education: list[EducationItem] = Field(default_factory=list)
    degree: str | None = Field(default=None, description="Highest degree pursued or completed")
    graduation_year: int | None = Field(default=None, description="Primary graduation year")

    # Experience & Internships
    experience: list[ExperienceItem] = Field(default_factory=list)
    internships: list[InternshipItem] = Field(default_factory=list)

    # Categorized Technical Skills
    skills: CategorizedSkills = Field(default_factory=CategorizedSkills)

    # Certifications
    certifications: list[str] = Field(default_factory=list)

    # Projects
    projects: list[ProjectItem] = Field(default_factory=list)
    project_technologies: list[str] = Field(default_factory=list)

    # Domains & Target Profiles
    domains: list[str] = Field(
        default_factory=list,
        description="Industry or technical domains explicitly reflected (e.g. Fintech, Healthcare, E-Commerce)",
    )
    likely_target_roles: list[str] = Field(
        default_factory=list,
        description="Likely entry-level roles suited for this background (e.g. Junior Backend Engineer)",
    )
    seniority: str = Field(
        default="Entry-Level (0-2 years)",
        description="Candidate seniority based on stated experience (e.g. Fresher / Entry-Level 0-2 YOE)",
    )

    def all_unique_skills(self) -> list[str]:
        """Aggregate all extracted skills across subcategories without duplicates."""
        collected: set[str] = set()
        s = self.skills
        for skill_group in [
            s.programming_languages,
            s.frameworks,
            s.libraries,
            s.databases,
            s.cloud,
            s.ai_ml,
            s.genai_llm,
            s.backend,
            s.frontend,
            s.devops,
            s.tools,
            s.apis,
            self.project_technologies,
        ]:
            for item in skill_group:
                cleaned = item.strip()
                if cleaned:
                    collected.add(cleaned.lower())
        return sorted(collected)


# API Response Schemas
class ResumeSummaryResponse(BaseModel):
    """Summary of a stored resume."""

    id: uuid.UUID
    file_name: str
    file_hash: str | None
    created_at: datetime
    profiles_count: int


class ResumeProfileDetailResponse(BaseModel):
    """Detailed profile data returned by API."""

    id: uuid.UUID
    resume_id: uuid.UUID
    profile_name: str
    target_role: str
    target_locations: list[str]
    work_modes: list[str]
    max_experience_years: int
    is_active: bool
    skills: list[str]
    structured_data: dict | None
    created_at: datetime


class ResumeDetailResponse(BaseModel):
    """Complete resume detail including raw text preview and linked profiles."""

    id: uuid.UUID
    file_name: str
    file_hash: str | None
    created_at: datetime
    updated_at: datetime
    profiles: list[ResumeProfileDetailResponse]
    raw_text_preview: str | None
