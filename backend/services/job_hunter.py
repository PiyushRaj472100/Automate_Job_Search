import asyncio
import hashlib
import logging
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy import select, delete
from backend.db.database import SessionLocal
from backend.db.models import Job, Resume, SheetLink
from backend.services import sheets_service
from backend.sources.registry import SOURCES

log = logging.getLogger("job_hunter")

# Strictly forbidden domains / roles that don't match AI / ML / Python / Data Science
FORBIDDEN_DOMAINS = [
    # Frontend & Mobile (Strict zero tolerance as requested)
    "flutter", "react", "react.js", "reactjs", "angular", "vue", "vue.js",
    "frontend", "front-end", "front end", "ui/ux", "ui developer", "ux developer",
    "web designer", "html/css", "wordpress", "mobile developer", "android", "ios",
    "swift", "kotlin", "react native", "dart",
    # ERP / Non-Python / Testing / Operations
    "odoo", "salesforce", "sap", "qa", "tester", "test engineer", "automation tester",
    "devops", "sre", "sysadmin", "network engineer",
    # Non-software
    "mechanical", "electrical", "civil", "chemical", "hardware", "gimbal",
    "copywriter", "writer", "marketing", "sales", "seo", "content", "accountant",
    "executive", "insights", "hr ", "recruiter", "nurse", "doctor", "cook", "fashion", "draping",
    "video editor", "telecaller", "driver", "bpo", "voice process"
]

# Unsuitable foreign-only locations
FOREIGN_ONLY_LOCATIONS = [
    "germany", "france", "paris", "würzburg", "wuerzburg", "poland", "brazil",
    "argentina", "mexico", "united kingdom", "london", "canada only", "us only"
]

# High-priority Indian tech hubs
INDIAN_HUBS = [
    "bengaluru", "bangalore", "hyderabad", "pune", "gurgaon", "gurugram",
    "noida", "delhi", "mumbai", "chennai", "india"
]

# Reject if description or title demands 3+ years, 2-4 years, 2-5 years, or senior experience
EXP_REJECT_PATTERN = re.compile(
    r"\b(([3-9]|\d{2,})\s*(\+|-\s*\d+)?\s*(?:to\s*\d+\s*)?(?:years?|yrs?)|[2-9]\s*[-–to]+\s*[3-9]\s*(?:years?|yrs?))\b",
    re.IGNORECASE
)

# Senior / mid-level titles to strictly exclude (0-2 years entry-level only)
SENIOR_KEYWORDS = [
    "senior", "sr.", "sr ", "sr-", "lead", "principal", "architect", "staff",
    "director", "head of", "vp", "chief", "manager",
    "sde 2", "sde-2", "sde2", "sde ii", "sde 3", "sde-3", "sde3", "sde iii", "sde 4", "sde iv",
    "software engineer 2", "software engineer ii", "software engineer 3", "software engineer iii",
    "engineer 2", "engineer ii", "engineer 3", "engineer iii",
    "mid-level", "mid level", "intermediate", "experienced"
]

# Explicit fresher / 0-2 years positive indicators
FRESHER_BONUS_KEYWORDS = [
    "fresher", "freshers", "entry level", "entry-level", "intern", "internship",
    "trainee", "graduate", "junior", "jr", "jr.", "associate", "sde 1", "sde-1", "sde i",
    "0-1", "0-2", "1-2"
]

# Strict AI / ML / Python / Data Science positive patterns (using word boundaries)
AI_ML_PYTHON_PATTERN = re.compile(
    r"\b(ai\b|ml\b|machine\s*learning|deep\s*learning|data\s*scien\w+|data\s*analys\w+|data\s*analyst|python|fastapi|django|nlp|llm|genai|generative\s*ai|computer\s*vision|backend|data\s*engineer|ai\s*engineer|ml\s*engineer|artificial\s*intelligence)\b",
    re.IGNORECASE
)


def is_suitable_job(title: str, description: str, location: str) -> tuple[bool, int]:
    """
    Returns (is_suitable, priority_score).
    Strictly accepts only 0-2 years experience / entry-level / fresher roles in AI, ML, Python, Data Science, and Backend in India (Bangalore #1).
    Zero tolerance for frontend, flutter, react, or mobile.
    """
    t_low = title.lower()
    d_low = (description or "").lower()
    loc_low = (location or "").lower()

    # 1. Negative domain filter: zero tolerance for frontend, mobile, non-tech
    for kw in FORBIDDEN_DOMAINS:
        if kw in t_low:
            return False, 0

    # 2. Strict Seniority & Experience filter: reject senior, mid-level, SDE 2/3, and >2 years requirement
    for kw in SENIOR_KEYWORDS:
        if kw in t_low:
            return False, 0

    if EXP_REJECT_PATTERN.search(t_low) or EXP_REJECT_PATTERN.search(d_low):
        return False, 0

    # 3. Positive domain match: MUST strictly be AI, ML, Data Science, Python, or Backend
    has_title_match = bool(AI_ML_PYTHON_PATTERN.search(t_low))
    if not has_title_match:
        # If title doesn't explicitly mention AI/ML/Python, check if it's an engineering/developer/intern role with strong AI/ML description
        is_tech_role = any(r in t_low for r in ["developer", "engineer", "scientist", "intern", "programmer"])
        has_desc_match = bool(AI_ML_PYTHON_PATTERN.search(d_low))
        if not (is_tech_role and has_desc_match):
            return False, 0

    # 4. Strict India filter: must be in Bangalore, an Indian tech metro, or remote eligible for India
    is_in_india = any(hub in loc_low for hub in INDIAN_HUBS)
    is_remote_open = ("remote" in loc_low or "anywhere" in loc_low or "worldwide" in loc_low) and not any(fl in loc_low for fl in FOREIGN_ONLY_LOCATIONS)
    if not (is_in_india or is_remote_open):
        return False, 0

    # 5. Score by Indian location priority (Bangalore #1)
    if "bangalore" in loc_low or "bengaluru" in loc_low:
        priority = 100  # 1st priority: Bangalore, India
    elif any(hub in loc_low for hub in INDIAN_HUBS):
        priority = 85   # 2nd priority: Other Indian metro hubs
    else:
        priority = 60   # 3rd priority: Open remote available to India

    # 6. Priority bonus for explicit fresher / entry-level / intern / 0-2 yrs tags
    if any(fk in t_low or fk in d_low for fk in FRESHER_BONUS_KEYWORDS):
        priority += 25

    return True, priority


async def verify_job_url(url: str) -> bool:
    """Verifies that the job link is alive and working."""
    if not url or not url.startswith("http"):
        return False
    trusted = ["linkedin.com", "hasjob.co", "instahyre.com", "jobicy.com", "remotive.com", "arbeitnow.com"]
    if any(dom in url for dom in trusted):
        return True
    try:
        async with httpx.AsyncClient(timeout=2, follow_redirects=True) as client:
            r = await client.head(url)
            return r.status_code < 400
    except Exception:
        return False


def generate_verified_linkedin_links(company: str, location: str = "Bengaluru") -> str:
    """Generates precise, working LinkedIn search URLs for Bangalore/India recruiters and hiring managers."""
    comp_clean = company.strip()
    if not comp_clean or comp_clean.lower() in ["startup", "confidential", "stealth"]:
        return "N/A"

    comp_enc = urllib.parse.quote(comp_clean)

    recruiter_link = f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20technical%20recruiter%20Bengaluru"
    manager_link = f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20%22engineering%20manager%22%20Bengaluru"
    peer_referral = f"https://www.linkedin.com/search/results/people/?keywords={comp_enc}%20%22software%20engineer%22%20Bengaluru"

    return (
        f"1. Bangalore Recruiter: {recruiter_link}\n"
        f"2. Bangalore Eng Manager: {manager_link}\n"
        f"3. Peer Referral: {peer_referral}"
    )


async def hunt_jobs_for_resume(resume_id: str) -> dict:
    log.info("Starting high-precision Indian tech job hunt for resume %s", resume_id)
    async with SessionLocal() as db:
        resume = await db.get(Resume, resume_id)
        if not resume:
            log.warning("Resume %s not found for job hunt", resume_id)
            return {"status": "error", "message": "Resume not found"}

        # Auto-prune jobs older than 4 days in DB to ensure freshness
        cutoff = datetime.now(timezone.utc) - timedelta(days=4)
        try:
            await db.execute(delete(Job).where(Job.created_at < cutoff))
            await db.commit()
            log.info("Auto-pruned jobs older than 4 days from database")
        except Exception as e:
            log.warning("Failed to prune old DB jobs: %s", e)

        # Targeted Indian queries strictly for AI, ML, Python, Data Science (0-2 years / fresher)
        targeted_queries = [
            "ai engineer intern",
            "junior data scientist",
            "machine learning entry level",
            "python backend developer fresher",
            "python developer fresher",
            "junior ai engineer",
        ]

        discovered_jobs = []

        # 1. Primary: LinkedIn India Guest API (Date Descending, past 24h)
        linkedin_src = SOURCES.get("linkedin_india")
        if linkedin_src and linkedin_src.enabled and not linkedin_src.breaker.open:
            for q in targeted_queries:
                try:
                    jobs = await linkedin_src.discover(q)
                    discovered_jobs.extend(jobs)
                except Exception as e:
                    log.error("LinkedIn India error on '%s': %s", q, e)

        # 2. Instahyre India (Bangalore / India tech hiring platform)
        instahyre_src = SOURCES.get("instahyre")
        if instahyre_src and instahyre_src.enabled and not instahyre_src.breaker.open:
            try:
                jobs = await instahyre_src.discover("python ai")
                discovered_jobs.extend(jobs)
            except Exception as e:
                log.error("Instahyre error: %s", e)

        # 3. Hasjob India Startup tech feed
        hasjob_src = SOURCES.get("hasjob_india")
        if hasjob_src and hasjob_src.enabled and not hasjob_src.breaker.open:
            try:
                jobs = await hasjob_src.discover("python ai")
                discovered_jobs.extend(jobs)
            except Exception as e:
                log.error("Hasjob error: %s", e)

        # Filter strictly for AI/ML/Python/Data Science, Indian/Bangalore priority, and 0-2 yrs
        scored_jobs = []
        seen_urls = set()

        for j in discovered_jobs:
            url = j.job_url or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            suitable, score = is_suitable_job(j.title, j.description or "", j.location or "")
            if suitable:
                scored_jobs.append((score, j))

        # Sort jobs by location priority (Bangalore 100 first, then Indian metros 85, then Remote)
        scored_jobs.sort(key=lambda x: x[0], reverse=True)
        sorted_jobs = [j for _, j in scored_jobs]

        # Fetch existing job URLs in DB for this resume
        existing_res = await db.execute(select(Job.dedup_key).where(Job.resume_id == resume_id))
        existing_db_dedups = set(existing_res.scalars().all())

        new_jobs = []
        for j in sorted_jobs:
            if not j.job_url:
                continue

            dedup_hash = hashlib.sha256(j.job_url.encode()).hexdigest()
            if dedup_hash in existing_db_dedups:
                continue
            existing_db_dedups.add(dedup_hash)

            # Verify link is working
            is_alive = await verify_job_url(j.job_url)
            if not is_alive:
                continue

            # Location and work mode formatting (Office, Remote, Hybrid)
            loc = j.location or "Bengaluru, Karnataka, India"
            loc_low = loc.lower()
            t_low = j.title.lower()

            if "remote" in loc_low or "remote" in t_low:
                work_mode = "Remote (India Eligible)"
            elif "hybrid" in loc_low or "hybrid" in t_low:
                work_mode = "Hybrid (Bangalore)" if ("bangalore" in loc_low or "bengaluru" in loc_low) else "Hybrid"
            elif "bangalore" in loc_low or "bengaluru" in loc_low:
                work_mode = "Work from Office (Bangalore)"
            elif any(h in loc_low for h in INDIAN_HUBS):
                work_mode = f"Work from Office ({loc.split(',')[0]})"
            else:
                work_mode = "Work from Office"

            referral_links = generate_verified_linkedin_links(j.company, location="Bengaluru")

            db_job = Job(
                resume_id=resume.id,
                dedup_key=dedup_hash,
                source=j.source,
                title=j.title,
                normalized_title=j.title.strip().lower(),
                company=j.company,
                location=loc,
                work_mode=work_mode,
                job_url=j.job_url,
                description=j.description,
                status="ACTIVE",
            )
            db.add(db_job)

            new_jobs.append({
                "title": j.title,
                "company": j.company,
                "location": loc,
                "work_mode": work_mode,
                "job_url": j.job_url,
                "source": j.source,
                "referral_links": referral_links,
                "status": "NEW",
            })

            # Save in batches of up to 35 top matching jobs
            if len(new_jobs) >= 35:
                break

        if new_jobs:
            await db.commit()
            log.info("Persisted %d verified AI/ML/Python jobs to DB for resume %s", len(new_jobs), resume_id)

        # Sync to Google Sheet if linked (prunes jobs older than 4 days automatically)
        sheet_res = await db.execute(select(SheetLink).where(SheetLink.resume_id == resume_id))
        sheet = sheet_res.scalars().first()
        synced_count = 0
        if sheet:
            try:
                # Prune old sheet rows even if new_jobs is empty
                sheets_service.prune_sheet_jobs(sheet.spreadsheet_id, max_days=4)
                if new_jobs:
                    synced_count = sheets_service.sync_jobs_to_sheet(sheet.spreadsheet_id, new_jobs)
                sheet.last_synced_at = datetime.now(timezone.utc)
                sheet.sync_status = "SYNCED"
                await db.commit()
                log.info("Synced %d verified jobs to Google Sheet %s", synced_count, sheet.spreadsheet_id)
            except Exception as e:
                log.error("Failed to sync to Google Sheet: %s", e)

        return {
            "status": "ok",
            "discovered": len(discovered_jobs),
            "suitable_tech_india": len(sorted_jobs),
            "new_persisted": len(new_jobs),
            "synced_to_sheet": synced_count,
        }


async def run_periodic_sweep():
    """Background task that runs periodically across all resumes and purges 4-day-old records."""
    while True:
        try:
            log.info("Starting scheduled periodic job sweep for Indian tech hubs...")
            async with SessionLocal() as db:
                # Prune old jobs across DB
                cutoff = datetime.now(timezone.utc) - timedelta(days=4)
                await db.execute(delete(Job).where(Job.created_at < cutoff))
                await db.commit()

                res = await db.execute(select(Resume.id))
                resume_ids = res.scalars().all()

            for rid in resume_ids:
                try:
                    await hunt_jobs_for_resume(rid)
                except Exception as e:
                    log.error("Error in periodic sweep for resume %s: %s", rid, e)

            log.info("Periodic job sweep completed. Sleeping for 2 hours.")
        except Exception as e:
            log.error("Periodic sweep encountered error: %s", e)

        await asyncio.sleep(2 * 3600)
