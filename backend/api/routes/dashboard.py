from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.database import get_session
from backend.db.models import Application, Job, Resume, SheetLink
from backend.sources.registry import SOURCES

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_session)):
    resumes_count = (await db.execute(select(func.count(Resume.id)))).scalar_one()
    jobs_count = (await db.execute(select(func.count(Job.id)))).scalar_one()
    apps_count = (await db.execute(select(func.count(Application.id)))).scalar_one()
    interviews_count = (await db.execute(
        select(func.count(Application.id)).where(Application.status == "INTERVIEWING")
    )).scalar_one()
    sheets_count = (await db.execute(select(func.count(SheetLink.id)))).scalar_one()

    # Recent 6 jobs
    recent_jobs_query = await db.execute(select(Job).order_by(Job.created_at.desc()).limit(6))
    recent_jobs = [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location or "Not specified",
            "work_mode": j.work_mode or "remote",
            "source": j.source,
            "job_url": j.job_url,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in recent_jobs_query.scalars().all()
    ]

    # Active sources
    active_sources = [
        {"name": name, "enabled": src.enabled, "policy": src.policy}
        for name, src in SOURCES.items()
    ]

    return {
        "resumes_count": resumes_count,
        "jobs_count": jobs_count,
        "applications_count": apps_count,
        "interviews_count": interviews_count,
        "connected_sheets": sheets_count,
        "recent_jobs": recent_jobs,
        "sources": active_sources,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
