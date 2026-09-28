"""API routes for managing Google Sheets dashboards linked to resume profiles."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.session import get_sync_session
from backend.models.resume import Resume
from backend.sheets.client import GoogleSheetsAuthError
from backend.sheets.service import GoogleSheetsService

router = APIRouter(prefix="/resumes/{resume_id}/sheets", tags=["Google Sheets"])
sheets_service = GoogleSheetsService()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create or initialize Google Spreadsheet for a resume",
    description="Provisions a dedicated 5-tab Google Sheet (Dashboard, Jobs, Recruiters, Applications, System Status) and links it in PostgreSQL.",
)
def create_spreadsheet_for_resume(
    resume_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_session)],
) -> dict[str, Any]:
    """Create or get the dedicated Google Sheet for a resume profile."""
    resume = db.execute(select(Resume).where(Resume.id == resume_id)).scalars().first()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resume with ID '{resume_id}' not found.",
        )

    try:
        spreadsheet_id, spreadsheet_url = sheets_service.create_or_get_spreadsheet_for_resume(db, resume_id)
        return {
            "message": "Google Spreadsheet linked successfully.",
            "resume_id": str(resume_id),
            "file_name": resume.file_name,
            "spreadsheet_id": spreadsheet_id,
            "spreadsheet_url": spreadsheet_url,
            "worksheets": ["Dashboard", "Jobs", "Recruiters", "Applications", "System Status"],
        }
    except GoogleSheetsAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Google Sheets authentication error: {e}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Google Spreadsheet: {e}",
        ) from e


@router.get(
    "",
    summary="Get spreadsheet status and URL for a resume",
    description="Retrieve linked Google Spreadsheet ID and URL for this resume from PostgreSQL.",
)
def get_spreadsheet_status(
    resume_id: uuid.UUID,
    db: Annotated[Session, Depends(get_sync_session)],
) -> dict[str, Any]:
    """Fetch spreadsheet linkage details for a resume."""
    resume = db.execute(select(Resume).where(Resume.id == resume_id)).scalars().first()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resume with ID '{resume_id}' not found.",
        )

    return {
        "resume_id": str(resume_id),
        "file_name": resume.file_name,
        "spreadsheet_id": resume.spreadsheet_id,
        "spreadsheet_url": resume.spreadsheet_url,
        "is_linked": resume.spreadsheet_id is not None,
    }
