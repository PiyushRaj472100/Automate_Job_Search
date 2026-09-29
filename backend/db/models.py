import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, DateTime, ForeignKey, JSON, UniqueConstraint, func,
    Integer, Float, Boolean, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db.database import Base


def _id() -> str:
    return uuid.uuid4().hex


class Resume(Base):
    __tablename__ = "resumes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_hunted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hunt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResumeProfile(Base):
    __tablename__ = "resume_profiles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, index=True)
    target_roles: Mapped[list] = mapped_column(JSON, default=list)
    seniority_level: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    preferred_locations: Mapped[list] = mapped_column(JSON, default=list)
    work_modes: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)


class ResumeSkill(Base):
    __tablename__ = "resume_skills"
    __table_args__ = (UniqueConstraint("resume_id", "skill_id", name="uq_resume_skills_resume_skill"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    proficiency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    years_of_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    careers_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobSource(Base):
    __tablename__ = "job_sources"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adapter_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    policy: Mapped[str] = mapped_column(String(64), default="public_api")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=30)
    circuit_breaker_state: Mapped[str] = mapped_column(String(32), default="CLOSED")
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("resume_id", "dedup_key", name="uq_jobs_resume_dedup_key"),
        Index("ix_jobs_title_company", "title", "company"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    dedup_key: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    normalized_title: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_mode: Mapped[str] = mapped_column(String(128), default="UNKNOWN")
    experience_level: Mapped[str] = mapped_column(String(64), default="UNKNOWN")
    min_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="ACTIVE")
    verification_status: Mapped[str] = mapped_column(String(64), default="NOT_VERIFIED")
    application_status: Mapped[str] = mapped_column(String(64), default="NEW")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobIdentifier(Base):
    __tablename__ = "job_identifiers"
    __table_args__ = (
        UniqueConstraint("job_id", "identifier_type", "identifier_value", name="uq_job_identifiers"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    identifier_type: Mapped[str] = mapped_column(String(64), index=True)
    identifier_value: Mapped[str] = mapped_column(String(255), index=True)


class JobSnapshot(Base):
    __tablename__ = "job_snapshots"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobVerificationEvent(Base):
    __tablename__ = "job_verification_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("resume_id", "job_id", name="uq_job_matches_resume_job"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    match_level: Mapped[str] = mapped_column(String(32))  # STRONG / RELEVANT / POSSIBLE
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    why_it_matches: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobMissingSkill(Base):
    __tablename__ = "job_missing_skills"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_match_id: Mapped[str] = mapped_column(ForeignKey("job_matches.id", ondelete="CASCADE"), index=True)
    skill_name: Mapped[str] = mapped_column(String(100), index=True)
    importance: Mapped[str] = mapped_column(String(32), default="NICE_TO_HAVE")


class Person(Base):
    __tablename__ = "people"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[str] = mapped_column(String(32), default="LOW")
    verification_status: Mapped[str] = mapped_column(String(64), default="Not reliably identified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobPerson(Base):
    __tablename__ = "job_people"
    __table_args__ = (
        UniqueConstraint("job_id", "person_id", name="uq_job_people_job_person"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), default="recruiter")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("resume_id", "job_id", name="uq_applications_resume_job"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="NEW")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    old_status: Mapped[str] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32))
    changed_by: Mapped[str] = mapped_column(String(64), default="user")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SearchRun(Base):
    __tablename__ = "search_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), default="manual")
    total_discovered: Mapped[int] = mapped_column(Integer, default=0)
    total_verified: Mapped[int] = mapped_column(Integer, default=0)
    total_matched: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SearchQuery(Base):
    __tablename__ = "search_queries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    search_run_id: Mapped[str] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"), index=True)
    query_text: Mapped[str] = mapped_column(String(255))
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    search_run_id: Mapped[str | None] = mapped_column(ForeignKey("search_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="SUCCESS")
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    trigger_type: Mapped[str] = mapped_column(String(32), default="manual")
    total_checked: Mapped[int] = mapped_column(Integer, default=0)
    total_active: Mapped[int] = mapped_column(Integer, default=0)
    total_closed: Mapped[int] = mapped_column(Integer, default=0)
    total_failed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SheetLink(Base):
    __tablename__ = "sheets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, index=True)
    spreadsheet_id: Mapped[str] = mapped_column(String(128))
    spreadsheet_url: Mapped[str] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), default="NEVER_SYNCED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SheetSyncEvent(Base):
    __tablename__ = "sheet_sync_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    sheet_id: Mapped[str] = mapped_column(ForeignKey("sheets.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32))  # SUCCESS / FAILED
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemEvent(Base):
    __tablename__ = "system_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="INFO")
    component: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ErrorEvent(Base):
    __tablename__ = "error_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    error_code: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReferralSearch(Base):
    __tablename__ = "referral_searches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    company: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(255), default="Bengaluru, India")
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_skills: Mapped[list] = mapped_column(JSON, default=list)
    search_links: Mapped[list] = mapped_column(JSON, default=list)
    email_formats: Mapped[list] = mapped_column(JSON, default=list)
    outreach_template: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

