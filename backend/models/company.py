"""Company entity model."""

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.models.job import Job
    from backend.models.person import Person


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Company entity representing hiring organizations."""

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    career_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    people: Mapped[list["Person"]] = relationship(
        "Person",
        back_populates="company",
        cascade="all, delete-orphan",
    )
