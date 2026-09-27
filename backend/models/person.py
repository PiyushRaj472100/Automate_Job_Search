"""Person and JobPerson ORM models."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.company import Company
    from backend.models.job import Job


class Person(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Public recruiter, talent acquisition, or hiring team member."""

    __tablename__ = "people"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    company: Mapped["Company | None"] = relationship("Company", back_populates="people")
    job_links: Mapped[list["JobPerson"]] = relationship(
        "JobPerson",
        back_populates="person",
        cascade="all, delete-orphan",
    )


class JobPerson(Base, UUIDPrimaryKeyMixin):
    """Association linking verified recruiters/contacts to specific job openings."""

    __tablename__ = "job_people"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("people.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(
        String(100),
        default="recruiter",
        nullable=False,
    )  # recruiter, hiring_manager, referrer
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    relevance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("job_id", "person_id", name="uq_job_person"),
    )

    job: Mapped["Job"] = relationship("Job", back_populates="job_people")
    person: Mapped["Person"] = relationship("Person", back_populates="job_links")
