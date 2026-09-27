"""JobSource, Job, and JobMatch ORM models."""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.application import Application
    from backend.models.company import Company
    from backend.models.person import JobPerson
    from backend.models.resume import ResumeProfile
    from backend.models.verification import VerificationEvent


class JobSource(Base, UUIDPrimaryKeyMixin):
    """Origin source of job postings (ATS platform, career portal, etc.)."""

    __tablename__ = "job_sources"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="job_source",
    )


class Job(Base, UUIDPrimaryKeyMixin):
    """Normalized job opening entity with stable internal UUID."""

    __tablename__ = "jobs"

    # Foreign Keys
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Core Job Descriptors
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    work_mode: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # ATS & Source Tracking Identifiers
    external_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    requisition_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    posting_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # URLs
    job_url: Mapped[str] = mapped_column(Text, nullable=False)
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)

    # Timestamps & Status
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False, index=True)

    # Deduplication & Normalization Fields
    normalized_company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_location: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    __table_args__ = (
        Index("ix_jobs_normalized_tuple", "normalized_company", "normalized_title", "normalized_location"),
        Index("ix_jobs_company_external_id", "company_id", "external_job_id"),
        Index("ix_jobs_requisition_company", "requisition_id", "company_id"),
    )

    # Relationships
    company: Mapped["Company | None"] = relationship("Company", back_populates="jobs")
    job_source: Mapped["JobSource | None"] = relationship("JobSource", back_populates="jobs")
    matches: Mapped[list["JobMatch"]] = relationship(
        "JobMatch",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    verification_events: Mapped[list["VerificationEvent"]] = relationship(
        "VerificationEvent",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    job_people: Mapped[list["JobPerson"]] = relationship(
        "JobPerson",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list["Application"]] = relationship(
        "Application",
        back_populates="job",
        cascade="all, delete-orphan",
    )

    @staticmethod
    def calculate_dedup_hash(
        normalized_company: str,
        normalized_title: str,
        normalized_location: str,
        requisition_id: str | None = None,
    ) -> str:
        """Calculate deterministic SHA-256 fingerprint for deduplication."""
        fingerprint = f"{normalized_company.lower().strip()}|{normalized_title.lower().strip()}|{normalized_location.lower().strip()}"
        if requisition_id:
            fingerprint += f"|{requisition_id.strip()}"
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


class JobMatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Match evaluation between a specific resume profile and a job opening."""

    __tablename__ = "job_matches"

    resume_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    fit_level: Mapped[str] = mapped_column(String(50), nullable=False)  # high, medium, low
    matched_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    missing_requirements: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("resume_profile_id", "job_id", name="uq_profile_job_match"),
    )

    resume_profile: Mapped["ResumeProfile"] = relationship("ResumeProfile", back_populates="matches")
    job: Mapped["Job"] = relationship("Job", back_populates="matches")
