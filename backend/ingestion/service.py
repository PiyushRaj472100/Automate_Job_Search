"""Resume ingestion service orchestrating parsing, extraction, and persistence."""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.ingestion.extractor import GeminiResumeExtractor
from backend.ingestion.parser import parse_resume_bytes
from backend.ingestion.schemas import (
    ResumeDetailResponse,
    ResumeProfileDetailResponse,
    ResumeSummaryResponse,
    StructuredResumeExtraction,
)
from backend.models.resume import Resume, ResumeProfile, ResumeSkill, Skill

logger = logging.getLogger("job_intelligence.ingestion_service")


class ResumeIngestionService:
    """Service handling resume upload, text extraction, structured parsing, and database persistence."""

    def __init__(self, extractor: GeminiResumeExtractor | None = None) -> None:
        self.extractor = extractor or GeminiResumeExtractor()

    def process_and_persist_resume(
        self,
        db: Session,
        file_name: str,
        content: bytes,
        profile_name: str | None = None,
    ) -> tuple[Resume, ResumeProfile, StructuredResumeExtraction, bool]:
        """Ingest a resume file, extract structured data, and persist to PostgreSQL.

        Args:
            db: Database session
            file_name: Original file name
            content: Raw binary file content
            profile_name: Optional custom profile label

        Returns:
            Tuple of (Resume, ResumeProfile, StructuredResumeExtraction, is_duplicate)
        """
        # 1. Parse and clean resume text
        parse_result = parse_resume_bytes(file_name, content)

        # 2. Check for existing resume with identical SHA-256 hash
        existing_resume = (
            db.execute(select(Resume).where(Resume.file_hash == parse_result.file_hash))
            .scalars()
            .first()
        )

        is_duplicate = existing_resume is not None

        if is_duplicate and existing_resume:
            logger.info("Found existing resume record with hash %s (ID: %s)", parse_result.file_hash, existing_resume.id)
            resume = existing_resume
        else:
            # 3. Create persistent Resume record
            resume = Resume(
                file_name=parse_result.file_name,
                file_hash=parse_result.file_hash,
                raw_text=parse_result.cleaned_text,
            )
            db.add(resume)
            db.flush()
            logger.info("Created new persistent Resume record (ID: %s)", resume.id)

        # 4. Perform structured extraction via Gemini
        extracted_data = self.extractor.extract(parse_result.cleaned_text)

        # 5. Derive profile title
        resolved_profile_name = profile_name
        if not resolved_profile_name:
            if extracted_data.likely_target_roles:
                resolved_profile_name = f"{extracted_data.likely_target_roles[0]} Profile"
            elif extracted_data.degree:
                resolved_profile_name = f"{extracted_data.degree} ({extracted_data.seniority})"
            else:
                resolved_profile_name = f"Profile for {file_name}"

        # If duplicate, append version count
        if is_duplicate:
            existing_count = len(resume.profiles)
            resolved_profile_name = f"{resolved_profile_name} (v{existing_count + 1})"

        primary_target_role = (
            extracted_data.likely_target_roles[0]
            if extracted_data.likely_target_roles
            else "Software Engineer (0-2 YOE)"
        )

        # 6. Create ResumeProfile
        profile = ResumeProfile(
            resume_id=resume.id,
            profile_name=resolved_profile_name,
            target_role=primary_target_role,
            target_locations=[],
            work_modes=["remote", "hybrid", "on_site"],
            max_experience_years=2,
            is_active=True,
            structured_data=extracted_data.model_dump(),
        )
        db.add(profile)
        db.flush()

        # 7. Normalize skills and link to resume profile
        all_skills = extracted_data.all_unique_skills()
        for skill_name in all_skills:
            normalized_name = skill_name.strip().lower()
            if not normalized_name:
                continue

            # Find or create skill in taxonomy
            skill = db.execute(select(Skill).where(Skill.name == normalized_name)).scalars().first()
            if not skill:
                skill = Skill(name=normalized_name)
                db.add(skill)
                db.flush()

            # Create link
            resume_skill = ResumeSkill(
                resume_profile_id=profile.id,
                skill_id=skill.id,
            )
            db.add(resume_skill)

        db.flush()
        return resume, profile, extracted_data, is_duplicate

    @staticmethod
    def get_all_resumes(db: Session) -> list[ResumeSummaryResponse]:
        """Fetch all resumes with summary metrics."""
        resumes = (
            db.execute(select(Resume).options(joinedload(Resume.profiles)).order_by(Resume.created_at.desc()))
            .unique()
            .scalars()
            .all()
        )
        return [
            ResumeSummaryResponse(
                id=r.id,
                file_name=r.file_name,
                file_hash=r.file_hash,
                created_at=r.created_at,
                profiles_count=len(r.profiles),
            )
            for r in resumes
        ]

    @staticmethod
    def get_resume_by_id(db: Session, resume_id: uuid.UUID) -> ResumeDetailResponse | None:
        """Fetch detailed resume record with profiles."""
        resume = (
            db.execute(
                select(Resume)
                .options(
                    joinedload(Resume.profiles).joinedload(ResumeProfile.skills).joinedload(ResumeSkill.skill)
                )
                .where(Resume.id == resume_id)
            )
            .unique()
            .scalars()
            .first()
        )
        if not resume:
            return None

        preview = resume.raw_text[:500] + "..." if resume.raw_text and len(resume.raw_text) > 500 else resume.raw_text

        profiles_detail: list[ResumeProfileDetailResponse] = []
        for p in resume.profiles:
            skills_list = [rs.skill.name for rs in p.skills]
            profiles_detail.append(
                ResumeProfileDetailResponse(
                    id=p.id,
                    resume_id=p.resume_id,
                    profile_name=p.profile_name,
                    target_role=p.target_role,
                    target_locations=p.target_locations or [],
                    work_modes=p.work_modes or [],
                    max_experience_years=p.max_experience_years,
                    is_active=p.is_active,
                    skills=skills_list,
                    structured_data=p.structured_data,
                    created_at=p.created_at,
                )
            )

        return ResumeDetailResponse(
            id=resume.id,
            file_name=resume.file_name,
            file_hash=resume.file_hash,
            created_at=resume.created_at,
            updated_at=resume.updated_at,
            profiles=profiles_detail,
            raw_text_preview=preview,
        )

    @staticmethod
    def get_resume_profile_by_id(db: Session, resume_id: uuid.UUID) -> dict[str, Any] | None:
        """Fetch active profile and structured data for a resume."""
        profile = (
            db.execute(
                select(ResumeProfile)
                .options(joinedload(ResumeProfile.skills).joinedload(ResumeSkill.skill))
                .where(ResumeProfile.resume_id == resume_id, ResumeProfile.is_active.is_(True))
                .order_by(ResumeProfile.created_at.desc())
            )
            .unique()
            .scalars()
            .first()
        )
        if not profile:
            return None

        skills_list = [rs.skill.name for rs in profile.skills]
        return {
            "profile_id": str(profile.id),
            "resume_id": str(profile.resume_id),
            "profile_name": profile.profile_name,
            "target_role": profile.target_role,
            "target_locations": profile.target_locations,
            "work_modes": profile.work_modes,
            "max_experience_years": profile.max_experience_years,
            "skills": skills_list,
            "structured_data": profile.structured_data,
            "created_at": profile.created_at.isoformat(),
        }
