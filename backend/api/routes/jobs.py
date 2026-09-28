from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.database import get_session
from backend.db.models import Application, Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobUpdateReq(BaseModel):
    status: str | None = None
    application_status: str | None = None


def _format_job(j: Job) -> dict:
    comp = j.company or ""
    comp_encoded = comp.replace(" ", "%20")
    return {
        "id": j.id,
        "resume_id": j.resume_id,
        "title": j.title,
        "company": j.company,
        "location": j.location or "Not specified",
        "work_mode": j.work_mode or "Remote",
        "job_url": j.job_url,
        "application_url": j.application_url,
        "description": j.description,
        "source": j.source,
        "status": j.status,
        "application_status": j.application_status,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "linkedin_recruiter_url": f"https://www.linkedin.com/search/results/people/?keywords={comp_encoded}%20technical%20recruiter%20Bengaluru" if comp else None,
        "linkedin_manager_url": f"https://www.linkedin.com/search/results/people/?keywords={comp_encoded}%20%22engineering%20manager%22%20Bengaluru" if comp else None,
        "linkedin_referral_url": f"https://www.linkedin.com/search/results/people/?keywords={comp_encoded}%20%22software%20engineer%22%20Bengaluru" if comp else None,
    }


@router.get("")
async def list_jobs(
    q: str | None = None,
    work_mode: str | None = None,
    source: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    query = select(Job).order_by(Job.created_at.desc())

    if q:
        query = query.where(Job.title.ilike(f"%{q}%") | Job.company.ilike(f"%{q}%"))
    if work_mode:
        query = query.where(Job.work_mode.ilike(f"%{work_mode}%"))
    if source:
        query = query.where(Job.source == source)

    query = query.limit(limit).offset(offset)
    rows = (await db.execute(query)).scalars().all()
    return [_format_job(j) for j in rows]


@router.get("/{job_id}")
async def get_job(job_id: str, db: AsyncSession = Depends(get_session)):
    j = await db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return _format_job(j)


@router.patch("/{job_id}")
async def update_job(job_id: str, req: JobUpdateReq, db: AsyncSession = Depends(get_session)):
    j = await db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")

    if req.status is not None:
        j.status = req.status
    if req.application_status is not None:
        j.application_status = req.application_status

    await db.commit()
    await db.refresh(j)
    return _format_job(j)


@router.post("/{job_id}/apply")
async def track_application(job_id: str, db: AsyncSession = Depends(get_session)):
    j = await db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")

    # Check if already tracked
    app_res = await db.execute(
        select(Application).where(Application.job_id == job_id, Application.resume_id == j.resume_id)
    )
    existing = app_res.scalars().first()
    if existing:
        return {"message": "Job already tracked in applications", "application_id": existing.id}

    app = Application(
        resume_id=j.resume_id,
        job_id=j.id,
        status="APPLIED",
        notes=f"Applied via {j.source} ({j.job_url})"
    )
    j.application_status = "APPLIED"
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return {"message": "Application tracked successfully", "application_id": app.id}


@router.delete("/{job_id}")
async def delete_job(job_id: str, db: AsyncSession = Depends(get_session)):
    j = await db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    await db.delete(j)
    await db.commit()
    return {"message": "Job deleted"}
