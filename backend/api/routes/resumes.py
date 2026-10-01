import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.db.session import get_sync_session

logger = logging.getLogger("job_intelligence.resumes")
from backend.ingestion.extractor import ResumeExtractionError
from backend.ingestion.parser import (
    CorruptFileError,
    EmptyResumeError,
    UnsupportedFileFormatError,
)
from backend.ingestion.schemas import (
    ResumeDetailResponse,
    ResumeSummaryResponse,
)
from backend.ingestion.service import ResumeIngestionService

router = APIRouter(prefix="/resumes", tags=["Resumes"])
ingestion_service = ResumeIngestionService()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a resume (PDF or DOCX)",
    description="Extracts raw text, performs structured Gemini extraction, and creates a persistent resume profile in PostgreSQL.",
)
async def upload_resume(
    file: Annotated[UploadFile, File(description="Resume file in PDF or DOCX format")],
    profile_name: Annotated[str | None, Form(description="Optional custom profile title")] = None,
    db: Annotated[Session, Depends(get_sync_session)] = None,  # type: ignore
) -> dict[str, Any]:
    """Upload a resume file and trigger the ingestion pipeline."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename.",
        )

    content = await file.read()
    try:
        resume, profile, extracted_data, is_duplicate = ingestion_service.process_and_persist_resume(
            db=db,
            file_name=file.filename,
            content=content,
            profile_name=profile_name,
        )
        return {
            "message": "Resume successfully ingested and structured." if not is_duplicate else "Resume already exists. New profile version created.",
            "resume_id": str(resume.id),
            "profile_id": str(profile.id),
            "file_name": resume.file_name,
            "file_hash": resume.file_hash,
            "is_duplicate": is_duplicate,
            "profile_name": profile.profile_name,
            "target_role": profile.target_role,
            "seniority": extracted_data.seniority,
            "skills_extracted_count": len(extracted_data.all_unique_skills()),
        }
    except UnsupportedFileFormatError as e:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e)) from e
    except (EmptyResumeError, CorruptFileError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ResumeExtractionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Structured extraction error: {e}") from e


@router.get(
    "",
    response_model=list[ResumeSummaryResponse],
    summary="List all uploaded resumes",
    description="Retrieve all stored resumes with their profile count and upload timestamps.",
)
def list_resumes(db: Annotated[Session, Depends(get_sync_session)]) -> list[ResumeSummaryResponse]:
    """List all stored resume records."""
    try:
        return ingestion_service.get_all_resumes(db)
    except Exception as e:
        logger.warning("Database unavailable when listing resumes: %s", e)
        return []


@router.get(
    "/{resume_id}",
    response_model=ResumeDetailResponse,
    summary="Get resume details by ID",
    description="Retrieve full metadata, raw text preview, and linked profiles for a resume.",
)
def get_resume(resume_id: uuid.UUID, db: Annotated[Session, Depends(get_sync_session)]) -> ResumeDetailResponse:
    """Fetch single resume details."""
    detail = ingestion_service.get_resume_by_id(db, resume_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resume with ID '{resume_id}' not found.",
        )
    return detail


@router.get(
    "/{resume_id}/profile",
    summary="Get structured profile for a resume",
    description="Retrieve active profile, categorized skills, and full structured data extraction.",
)
def get_resume_profile(resume_id: uuid.UUID, db: Annotated[Session, Depends(get_sync_session)]) -> dict[str, Any]:
    """Fetch structured profile for a resume."""
    profile_data = ingestion_service.get_resume_profile_by_id(db, resume_id)
    if not profile_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active profile found for resume ID '{resume_id}'.",
        )
    return profile_data
