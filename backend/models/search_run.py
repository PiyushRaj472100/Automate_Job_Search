"""SearchRun ORM model tracking discovery runs and orchestrations."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.resume import ResumeProfile


class SearchRun(Base, UUIDPrimaryKeyMixin):
    """Historical record of an automated or manual job discovery search run."""

    __tablename__ = "search_runs"

    resume_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_type: Mapped[str] = mapped_column(
        String(100),
        default="discovery",
        nullable=False,
    )  # discovery, liveness_check, morning_report, manual
    source: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )  # Specific source name e.g. "arbeitnow", or "all"
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        default="running",
        nullable=False,
        index=True,
    )  # running, completed, failed
    jobs_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_verified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_matched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    resume_profile: Mapped["ResumeProfile | None"] = relationship(
        "ResumeProfile",
        back_populates="search_runs",
    )
