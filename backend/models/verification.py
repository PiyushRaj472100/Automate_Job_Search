"""VerificationEvent ORM model for historical URL/status verifications."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
    from backend.models.job import Job


class VerificationEvent(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail of a verification attempt on a job listing."""

    __tablename__ = "verification_events"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verification_method: Mapped[str] = mapped_column(
        String(100),
        default="http_head",
        nullable=False,
    )  # http_head, http_get, page_content_check
    status_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_response_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="verification_events")
