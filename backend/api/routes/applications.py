from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.database import get_session
from backend.db.models import Application, Job

router = APIRouter(prefix="/applications", tags=["applications"])


class ApplicationCreateReq(BaseModel):
    resume_id: str
    job_id: str
    status: str = "APPLIED"
    notes: str | None = None


class ApplicationUpdateReq(BaseModel):
    status: str | None = None
    notes: str | None = None


def _format_app(a: Application, j: Job | None) -> dict:
    return {
        "id": a.id,
        "resume_id": a.resume_id,
        "job_id": a.job_id,
        "status": a.status,
        "notes": a.notes,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "job": {
            "title": j.title if j else "Unknown Role",
            "company": j.company if j else "Unknown Company",
            "location": j.location if j else "",
            "work_mode": j.work_mode if j else "Remote",
            "job_url": j.job_url if j else "",
            "source": j.source if j else "",
        } if j else None,
    }


@router.get("")
async def list_applications(status: str | None = None, db: AsyncSession = Depends(get_session)):
    query = select(Application, Job).outerjoin(Job, Application.job_id == Job.id).order_by(Application.created_at.desc())
    if status:
        query = query.where(Application.status == status.upper())

    res = await db.execute(query)
    rows = res.all()
    return [_format_app(a, j) for a, j in rows]


@router.post("", status_code=201)
async def create_application(req: ApplicationCreateReq, db: AsyncSession = Depends(get_session)):
    app = Application(
        resume_id=req.resume_id,
        job_id=req.job_id,
        status=req.status.upper(),
        notes=req.notes,
        applied_at=datetime.now(timezone.utc)
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    j = await db.get(Job, req.job_id)
    return _format_app(app, j)


@router.patch("/{app_id}")
async def update_application(app_id: str, req: ApplicationUpdateReq, db: AsyncSession = Depends(get_session)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")

    if req.status is not None:
        app.status = req.status.upper()
    if req.notes is not None:
        app.notes = req.notes

    await db.commit()
    await db.refresh(app)
    j = await db.get(Job, app.job_id)
    return _format_app(app, j)


@router.delete("/{app_id}")
async def delete_application(app_id: str, db: AsyncSession = Depends(get_session)):
    app = await db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    await db.delete(app)
    await db.commit()
    return {"message": "Application deleted"}
