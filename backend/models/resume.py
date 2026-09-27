"""Resume, ResumeProfile, and Skill ORM models."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.application import Application
    from backend.models.job import JobMatch
    from backend.models.search_run import SearchRun


class Resume(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Uploaded or ingested resume document."""

    __tablename__ = "resumes"

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    profiles: Mapped[list["ResumeProfile"]] = relationship(
        "ResumeProfile",
        back_populates="resume",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list["Application"]] = relationship(
        "Application",
        back_populates="resume",
        cascade="all, delete-orphan",
    )


class ResumeProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Independent job-search profile derived from a resume."""

    __tablename__ = "resume_profiles"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_role: Mapped[str] = mapped_column(String(255), nullable=False)
    target_locations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    work_modes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    min_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_experience_years: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    sheet_tab_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    structured_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


    # Relationships
    resume: Mapped["Resume"] = relationship("Resume", back_populates="profiles")
    skills: Mapped[list["ResumeSkill"]] = relationship(
        "ResumeSkill",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
    )
    matches: Mapped[list["JobMatch"]] = relationship(
        "JobMatch",
        back_populates="resume_profile",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list["Application"]] = relationship(
        "Application",
        back_populates="resume_profile",
    )
    search_runs: Mapped[list["SearchRun"]] = relationship(
        "SearchRun",
        back_populates="resume_profile",
    )


class Skill(Base, UUIDPrimaryKeyMixin):
    """Global normalized skill taxonomy entity."""

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)

    resume_skills: Mapped[list["ResumeSkill"]] = relationship(
        "ResumeSkill",
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class ResumeSkill(Base, UUIDPrimaryKeyMixin):
    """Association between resume profiles and extracted skills."""

    __tablename__ = "resume_skills"

    resume_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    years_of_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    proficiency_level: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        UniqueConstraint("resume_profile_id", "skill_id", name="uq_resume_profile_skill"),
    )

    resume_profile: Mapped["ResumeProfile"] = relationship("ResumeProfile", back_populates="skills")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="resume_skills")
