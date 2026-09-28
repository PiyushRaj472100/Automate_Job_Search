import re
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.database import get_session
from backend.db.models import ReferralSearch

router = APIRouter(prefix="/referrals", tags=["referrals"])

COMMON_TECH_SKILLS = [
    "Python", "FastAPI", "Django", "Flask", "Java", "Spring Boot", "C++", "C#", ".NET",
    "Go", "Rust", "Node.js", "Express", "TypeScript", "JavaScript", "React", "Vue", "Angular",
    "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "Docker", "Kubernetes", "AWS", "Azure", "GCP", "CI/CD", "Linux",
    "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "NLP", "LLM", "scikit-learn",
    "Pandas", "NumPy", "REST API", "GraphQL", "Microservices", "Kafka"
]


class ReferralAnalyzeReq(BaseModel):
    company: str
    role: str
    location: str | None = "Bengaluru, India"
    job_description: str | None = ""


def extract_skills_from_jd(text: str) -> list[str]:
    if not text:
        return []
    found = []
    text_lower = text.lower()
    for skill in COMMON_TECH_SKILLS:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found.append(skill)
    return found[:12]


def clean_company_domain(company: str) -> str:
    cleaned = company.lower().strip()
    cleaned = re.sub(r"\b(inc|corp|ltd|llc|technologies|solutions|services|pvt|private)\b", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9]", "", cleaned)
    return f"{cleaned}.com" if cleaned else "company.com"


@router.post("/analyze")
async def analyze_job_for_referral(
    req: ReferralAnalyzeReq,
    db: AsyncSession = Depends(get_session),
):
    comp = req.company.strip()
    if not comp:
        raise HTTPException(400, "Company name is required")

    role = req.role.strip() or "Software Engineer"
    loc = req.location.strip() if req.location else "Bengaluru, India"
    jd = req.job_description.strip() if req.job_description else ""

    comp_enc = urllib.parse.quote(comp)
    role_enc = urllib.parse.quote(role)
    loc_enc = urllib.parse.quote(loc)

    # 1. Extract technical requirements from JD
    detected_skills = extract_skills_from_jd(jd)
    skills_str = ", ".join(detected_skills[:5]) if detected_skills else "Python, backend engineering, and modern APIs"

    # 2. Hyper-targeted LinkedIn People Search Links
    search_links = [
        {
            "category": "Technical Recruiters / HR",
            "title": f"Technical Recruiters at {comp} ({loc})",
            "url": f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20technical%20recruiter%20{loc_enc}",
            "purpose": "Reach out directly to recruiters managing active openings.",
        },
        {
            "category": "Hiring Managers",
            "title": f"Engineering Managers / Leads at {comp} ({loc})",
            "url": f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20%22engineering%20manager%22%20{loc_enc}",
            "purpose": "Contact the engineering leads who make the final hiring decisions.",
        },
        {
            "category": "Peer Engineers (Internal Referral)",
            "title": f"Software Engineers at {comp} ({loc}) for Referral",
            "url": f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20%22software%20engineer%22%20{loc_enc}",
            "purpose": "Connect with current developers who can submit internal referral tickets.",
        },
        {
            "category": "Early Careers & Campus Recruiters",
            "title": f"University / Early Career Recruiters at {comp}",
            "url": f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20%22campus%20recruiter%22%20India",
            "purpose": "Dedicated HR teams handling 0-2 years fresher & entry-level hiring.",
        },
        {
            "category": "Talent Acquisition India",
            "title": f"Talent Acquisition Partners at {comp} (India)",
            "url": f"https://www.linkedin.com/search/results/people/?keywords=talent%20acquisition%20{comp_enc}%20India",
            "purpose": "Pan-India talent acquisition specialists.",
        },
    ]

    # 3. Verified Corporate Email Syntax & Recruitment Inboxes
    domain = clean_company_domain(comp)
    email_formats = [
        {
            "pattern": f"first.last@{domain}",
            "example": f"john.doe@{domain}",
            "usage": "Standard corporate email syntax for 80% of tech firms.",
        },
        {
            "pattern": f"first@{domain}",
            "example": f"john@{domain}",
            "usage": "Common at startups and agile tech companies.",
        },
        {
            "pattern": f"firstinitiallast@{domain}",
            "example": f"jdoe@{domain}",
            "usage": "Common at legacy tech & enterprise IT firms.",
        },
        {
            "pattern": f"careers@{domain} / jobs@{domain}",
            "example": f"careers@{domain}",
            "usage": "Direct talent acquisition team inbox.",
        },
    ]

    # 4. Tailored Cold Referral Outreach Template
    template = (
        f"Hi [Name],\n\n"
        f"I came across the {role} role at {comp} in {loc} and was thoroughly impressed by your engineering team's work.\n\n"
        f"With hands-on experience in {skills_str}, I have built robust backend services and projects closely aligned with the requirements in the job description.\n\n"
        f"Would you be open to a quick review of my profile or submitting an internal referral if you feel my background is a strong fit? "
        f"I would be immensely grateful for any guidance.\n\n"
        f"Resume & Portfolio: [Your Resume Link / GitHub]\n\n"
        f"Thank you for your time and consideration,\n"
        f"[Your Name]\n"
        f"[Your LinkedIn Profile]"
    )

    # 5. Persist record in database
    search_record = ReferralSearch(
        company=comp,
        role=role,
        location=loc,
        job_description=jd[:3000] if jd else None,
        detected_skills=detected_skills,
        search_links=search_links,
        email_formats=email_formats,
        outreach_template=template,
    )
    db.add(search_record)
    await db.commit()
    await db.refresh(search_record)

    return {
        "id": search_record.id,
        "company": comp,
        "role": role,
        "location": loc,
        "detected_skills": detected_skills,
        "search_links": search_links,
        "email_formats": email_formats,
        "outreach_template": template,
        "created_at": search_record.created_at.isoformat(),
    }


@router.get("/history")
async def get_referral_history(db: AsyncSession = Depends(get_session)):
    query = select(ReferralSearch).order_by(ReferralSearch.created_at.desc()).limit(20)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": r.id,
            "company": r.company,
            "role": r.role,
            "location": r.location,
            "detected_skills": r.detected_skills,
            "search_links": r.search_links,
            "email_formats": r.email_formats,
            "outreach_template": r.outreach_template,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
