from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, case
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.database import get_session
from backend.db.models import Application, Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobUpdateReq(BaseModel):
    status: str | None = None
    application_status: str | None = None


def _format_time_ago(dt: datetime | None) -> str:
    if not dt:
        return "Recent"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    total_seconds = int(diff.total_seconds())

    if total_seconds < 60:
        return "Just now"
    elif total_seconds < 3600:
        mins = total_seconds // 60
        return f"{mins}m ago"
    elif total_seconds < 86400:
        hrs = total_seconds // 3600
        return f"{hrs}h ago"
    else:
        days = total_seconds // 86400
        return f"{days}d ago"


def _format_job(j: Job) -> dict:
    comp = j.company or ""
    comp_encoded = comp.replace(" ", "%20")
    loc = j.location or "Not specified"
    is_blr = "bangalore" in loc.lower() or "bengaluru" in loc.lower()

    # Recruiter post time display: prioritize exact post string (e.g. 2h ago, 45m ago) or formatted post date
    time_display = _format_time_ago(j.first_seen_at or j.created_at)
    if j.posted_at and any(k in j.posted_at.lower() for k in ["ago", "just now", "today", "yesterday"]):
        time_display = j.posted_at

    return {
        "id": j.id,
        "resume_id": j.resume_id,
        "title": j.title,
        "company": j.company,
        "location": loc,
        "work_mode": j.work_mode or "Remote",
        "is_bangalore": is_blr,
        "job_url": j.job_url,
        "application_url": j.application_url,
        "description": j.description,
        "source": j.source,
        "status": j.status,
        "application_status": j.application_status,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "recruiter_posted_at": j.first_seen_at.isoformat() if j.first_seen_at else (j.created_at.isoformat() if j.created_at else None),
        "time_ago": time_display,
        "linkedin_recruiter_url": f"https://www.linkedin.com/search/results/people/?keywords={comp_encoded}%20technical%20recruiter%20Bengaluru" if comp else None,
        "linkedin_manager_url": f"https://www.linkedin.com/search/results/people/?keywords={comp_encoded}%20%22engineering%20manager%22%20Bengaluru" if comp else None,
        "linkedin_referral_url": f"https://www.linkedin.com/search/results/people/?keywords={comp_encoded}%20%22software%20engineer%22%20Bengaluru" if comp else None,
    }


@router.get("")
async def list_jobs(
    q: str | None = None,
    work_mode: str | None = None,
    city: str | None = None,
    source: str | None = None,
    sort_by: str = Query("latest", regex="^(latest|bangalore)$"),
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    # Auto-exclude jobs older than 4 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=4)
    query = select(Job).where(
        (Job.first_seen_at >= cutoff) | ((Job.first_seen_at.is_(None)) & (Job.created_at >= cutoff))
    )

    if q:
        query = query.where(Job.title.ilike(f"%{q}%") | Job.company.ilike(f"%{q}%"))
    if work_mode:
        query = query.where(Job.work_mode.ilike(f"%{work_mode}%"))
    if city:
        if city.lower() in ["bangalore", "bengaluru"]:
            query = query.where(Job.location.ilike("%bangalore%") | Job.location.ilike("%bengaluru%"))
        elif city.lower() == "remote":
            query = query.where(Job.work_mode.ilike("%remote%") | Job.location.ilike("%remote%"))
        else:
            query = query.where(Job.location.ilike(f"%{city}%"))
    if source:
        query = query.where(Job.source == source)

    # Sorting
    if sort_by == "bangalore":
        # Bangalore first, then latest recruiter posting
        blr_priority = case(
            (Job.location.ilike("%bangalore%"), 1),
            (Job.location.ilike("%bengaluru%"), 1),
            else_=2
        )
        query = query.order_by(blr_priority, Job.first_seen_at.desc().nullslast(), Job.created_at.desc())
    else:
        # Default: latest recruiter posting first (e.g. 1 hour ago before 1 day ago)
        query = query.order_by(Job.first_seen_at.desc().nullslast(), Job.created_at.desc())

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
