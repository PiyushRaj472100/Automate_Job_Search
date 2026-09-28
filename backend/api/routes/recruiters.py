from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.database import get_session
from backend.db.models import Job, Resume

router = APIRouter(prefix="/recruiters", tags=["recruiters"])


@router.get("")
async def list_recruiters(db: AsyncSession = Depends(get_session)):
    # Find distinct companies from discovered jobs
    comp_query = select(Job.company, Job.title, Job.job_url, Job.location).distinct(Job.company).limit(50)
    rows = (await db.execute(comp_query)).all()

    recruiters_list = []
    for r in rows:
        comp = r.company or ""
        if not comp:
            continue
        comp_enc = comp.replace(" ", "%20")
        title_enc = (r.title or "").replace(" ", "%20")

        # 3 targeted search avenues on LinkedIn tailored for Bangalore / India
        search_links = [
            {
                "title": f"Bangalore Tech Recruiters ({comp})",
                "url": f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20technical%20recruiter%20Bengaluru",
                "role_type": "Recruiter / HR"
            },
            {
                "title": f"Bangalore Engineering Managers ({comp})",
                "url": f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20%22engineering%20manager%22%20Bengaluru",
                "role_type": "Engineering Manager"
            },
            {
                "title": f"Software Engineers for Referral ({comp})",
                "url": f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20%22software%20engineer%22%20Bengaluru",
                "role_type": "Peer / Referral"
            },
        ]

        # Cold outreach template
        template = (
            f"Hi [Name],\n\n"
            f"I came across the {r.title} opening at {comp} and am very excited about your team's work. "
            f"With hands-on experience in modern software engineering and Python development, I believe I'd be a great match for this role.\n\n"
            f"I would greatly appreciate any insights or advice on the hiring process, or a referral if you feel my background aligns.\n\n"
            f"Best regards,\n[Your Name]"
        )

        recruiters_list.append({
            "company": comp,
            "job_title": r.title,
            "job_url": r.job_url,
            "location": r.location or "Not specified",
            "search_links": search_links,
            "outreach_template": template,
        })

    return recruiters_list
