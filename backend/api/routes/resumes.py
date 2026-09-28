import asyncio
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.config import get_settings
from backend.db.database import get_session
from backend.db.models import Resume, SheetLink
from backend.services import resume_service as rs, sheets_service, job_hunter

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _out(r: Resume) -> dict:
    return {"id": r.id, "filename": r.filename, "file_hash": r.file_hash,
            "created_at": r.created_at, "target_roles": r.profile.get("target_roles", []),
            "seniority": r.profile.get("seniority"), "skills": r.profile.get("skills", [])}


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...), allow_duplicate: bool = False,
                 db: AsyncSession = Depends(get_session)):
    if not (file.filename or "").lower().endswith((".pdf", ".docx")):
        raise HTTPException(400, "Only PDF and DOCX files are supported")
    data = await file.read()
    if len(data) > get_settings().MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, "File too large")
    h = rs.sha256(data)
    try:
        text = rs.extract_text(file.filename, data)
    except Exception:
        raise HTTPException(422, "Could not read the file")

    dup = (await db.execute(select(Resume).where(Resume.file_hash == h))).scalars().first()
    if dup and not allow_duplicate:
        # Gracefully refresh profile and re-trigger hunt instead of failing with 409
        dup.filename = file.filename
        dup.raw_text = text
        dup.profile = rs.build_profile(text)
        await db.commit()
        await db.refresh(dup)
        asyncio.create_task(job_hunter.hunt_jobs_for_resume(dup.id))
        return _out(dup)

    r = Resume(filename=file.filename, file_hash=h, raw_text=text, profile=rs.build_profile(text))
    db.add(r)
    await db.commit()
    await db.refresh(r)
    # Trigger autonomous background job hunt for entry-level roles
    asyncio.create_task(job_hunter.hunt_jobs_for_resume(r.id))
    return _out(r)


@router.get("")
async def list_resumes(db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(Resume).order_by(Resume.created_at.desc()))).scalars().all()
    return [_out(r) for r in rows]


async def _get(db, rid) -> Resume:
    r = await db.get(Resume, rid)
    if not r:
        raise HTTPException(404, "Resume not found")
    return r


@router.get("/{resume_id}")
async def get_resume(resume_id: str, db: AsyncSession = Depends(get_session)):
    return _out(await _get(db, resume_id))


@router.get("/{resume_id}/profile")
async def get_profile(resume_id: str, db: AsyncSession = Depends(get_session)):
    return (await _get(db, resume_id)).profile


@router.get("/{resume_id}/sheets")
async def get_sheet(resume_id: str, db: AsyncSession = Depends(get_session)):
    await _get(db, resume_id)
    sheet = (await db.execute(select(SheetLink).where(SheetLink.resume_id == resume_id))).scalars().first()
    if not sheet:
        raise HTTPException(404, "No Google Sheet created for this resume yet")
    return {
        "id": sheet.id,
        "resume_id": sheet.resume_id,
        "spreadsheet_id": sheet.spreadsheet_id,
        "spreadsheet_url": sheet.spreadsheet_url,
        "sync_status": sheet.sync_status,
        "last_synced_at": sheet.last_synced_at,
    }


@router.post("/{resume_id}/sheets")
async def create_or_sync_sheet(resume_id: str, db: AsyncSession = Depends(get_session)):
    resume = await _get(db, resume_id)
    sheet = (await db.execute(select(SheetLink).where(SheetLink.resume_id == resume_id))).scalars().first()
    if sheet:
        return {
            "id": sheet.id,
            "resume_id": sheet.resume_id,
            "spreadsheet_id": sheet.spreadsheet_id,
            "spreadsheet_url": sheet.spreadsheet_url,
            "sync_status": sheet.sync_status,
            "last_synced_at": sheet.last_synced_at,
            "already_existed": True,
        }

    try:
        data = sheets_service.create_or_get_spreadsheet(resume.id, resume.filename)
    except Exception as e:
        raise HTTPException(502, f"Failed to create Google Sheet: {e}")

    sheet = SheetLink(
        resume_id=resume.id,
        spreadsheet_id=data["spreadsheet_id"],
        spreadsheet_url=data["spreadsheet_url"],
        sync_status="SYNCED",
    )
    db.add(sheet)
    await db.commit()
    await db.refresh(sheet)
    return {
        "id": sheet.id,
        "resume_id": sheet.resume_id,
        "spreadsheet_id": sheet.spreadsheet_id,
        "spreadsheet_url": sheet.spreadsheet_url,
        "sync_status": sheet.sync_status,
        "last_synced_at": sheet.last_synced_at,
        "already_existed": False,
    }


class ConnectSheetReq(BaseModel):
    spreadsheet_url: str


@router.post("/{resume_id}/connect-sheet")
async def connect_sheet(resume_id: str, req: ConnectSheetReq, db: AsyncSession = Depends(get_session)):
    resume = await _get(db, resume_id)
    url = req.spreadsheet_url.strip()
    if not url.startswith("http"):
        raise HTTPException(400, "Please provide a valid Google Sheet URL starting with https://")

    # Update config and environment so sheets_service uses it
    from backend.core.config import get_settings
    get_settings().GOOGLE_SHEET_URL = url

    try:
        data = sheets_service.create_or_get_spreadsheet(resume.id, resume.filename, sheet_url=url)
    except Exception as e:
        raise HTTPException(400, f"{e}")

    # Check if SheetLink exists
    sheet = (await db.execute(select(SheetLink).where(SheetLink.resume_id == resume_id))).scalars().first()
    if not sheet:
        sheet = SheetLink(
            resume_id=resume.id,
            spreadsheet_id=data["spreadsheet_id"],
            spreadsheet_url=data["spreadsheet_url"],
            sync_status="SYNCED",
        )
        db.add(sheet)
    else:
        sheet.spreadsheet_id = data["spreadsheet_id"]
        sheet.spreadsheet_url = data["spreadsheet_url"]
        sheet.sync_status = "SYNCED"

    await db.commit()
    await db.refresh(sheet)

    # Immediately trigger an entry-level job hunt and sync to sheet in background
    asyncio.create_task(job_hunter.hunt_jobs_for_resume(resume.id))

    return {
        "id": sheet.id,
        "spreadsheet_id": sheet.spreadsheet_id,
        "spreadsheet_url": sheet.spreadsheet_url,
        "sync_status": sheet.sync_status,
        "message": "Google Sheet connected successfully! Autonomous job hunt started."
    }


@router.post("/{resume_id}/hunt")
async def trigger_hunt(resume_id: str, db: AsyncSession = Depends(get_session)):
    await _get(db, resume_id)
    res = await job_hunter.hunt_jobs_for_resume(resume_id)
    return res

