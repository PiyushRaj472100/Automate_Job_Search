"""Application ORM model representing manual user job applications."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.job import Job
    from backend.models.resume import Resume, ResumeProfile


class Application(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-managed manual job application record."""

    __tablename__ = "applications"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="to_apply",
        nullable=False,
        index=True,
    )  # to_apply, applied, interviewing, offer, rejected, withdrawn
    applied_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("resume_id", "job_id", name="uq_resume_job_application"),
    )

    resume: Mapped["Resume"] = relationship("Resume", back_populates="applications")
    resume_profile: Mapped["ResumeProfile | None"] = relationship("ResumeProfile", back_populates="applications")
    job: Mapped["Job"] = relationship("Job", back_populates="applications")
