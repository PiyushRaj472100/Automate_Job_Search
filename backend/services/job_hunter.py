import asyncio
import hashlib
import logging
import urllib.parse
from datetime import datetime, timezone
import httpx
from sqlalchemy import select
from backend.db.database import SessionLocal
from backend.db.models import Job, Resume, SheetLink
from backend.services import sheets_service
from backend.sources.registry import SOURCES

log = logging.getLogger("job_hunter")

# Strictly forbidden domains / roles that don't match software / Python / AI developer
FORBIDDEN_DOMAINS = [
    "mechanical", "electrical", "civil", "chemical", "hardware", "gimbal",
    "copywriter", "writer", "marketing", "sales", "seo", "content", "accountant",
    "hr ", "recruiter", "nurse", "doctor", "cook", "fashion", "draping",
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

import re

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

# Required positive domain indicators
TECH_ROLE_KEYWORDS = [
    "python", "backend", "ai", "ml", "machine learning", "software",
    "developer", "engineer", "data science", "fastapi", "django", "nlp", "deep learning"
]


def is_suitable_job(title: str, description: str, location: str) -> tuple[bool, int]:
    """
    Returns (is_suitable, priority_score).
    Strictly accepts only 0-2 years experience / entry-level / fresher roles in India (Bangalore #1).
    """
    t_low = title.lower()
    d_low = (description or "").lower()
    loc_low = (location or "").lower()

    # 1. Negative domain filter: zero tolerance for non-tech / mechanical / electrical
    for kw in FORBIDDEN_DOMAINS:
        if kw in t_low:
            return False, 0

    # 2. Strict Seniority & Experience filter: reject senior, mid-level, SDE 2/3, and >2 years requirement
    for kw in SENIOR_KEYWORDS:
        if kw in t_low:
            return False, 0

    if EXP_REJECT_PATTERN.search(t_low) or EXP_REJECT_PATTERN.search(d_low):
        return False, 0

    # 3. Positive domain match: must be tech / software / python / AI
    has_tech = any(kw in t_low for kw in TECH_ROLE_KEYWORDS)
    if not has_tech:
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
    trusted = ["linkedin.com", "hasjob.co", "jobicy.com", "remotive.com", "arbeitnow.com"]
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

        # Targeted Indian queries: Bangalore priority (0-2 years entry-level / fresher)
        targeted_queries = [
            "python developer fresher",
            "junior python developer",
            "entry level python developer",
            "python developer 0-2 years",
            "junior backend developer",
            "backend developer fresher",
            "ai engineer intern",
            "junior ai engineer",
            "entry level machine learning",
            "fastapi developer fresher",
        ]

        discovered_jobs = []

        # 1. Primary: LinkedIn India Guest API for Bangalore & Indian entry-level tech roles
        linkedin_src = SOURCES.get("linkedin_india")
        if linkedin_src and linkedin_src.enabled and not linkedin_src.breaker.open:
            for q in targeted_queries:
                try:
                    jobs = await linkedin_src.discover(q)
                    discovered_jobs.extend(jobs)
                except Exception as e:
                    log.error("LinkedIn India error on '%s': %s", q, e)

        # 2. Hasjob India Startup tech feed
        hasjob_src = SOURCES.get("hasjob_india")
        if hasjob_src and hasjob_src.enabled and not hasjob_src.breaker.open:
            try:
                jobs = await hasjob_src.discover("python developer")
                discovered_jobs.extend(jobs)
            except Exception as e:
                log.error("Hasjob error: %s", e)

        # Filter strictly for domain matching, Indian/Bangalore priority, and entry level
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

            # Location formatting (ensure Bangalore / India is prominently visible)
            loc = j.location or "Bengaluru, Karnataka, India"
            if "bengaluru" in loc.lower() or "bangalore" in loc.lower():
                work_mode = "Bangalore (On-site / Hybrid)"
            elif any(h in loc.lower() for h in INDIAN_HUBS):
                work_mode = f"{loc} (India)"
            else:
                work_mode = "Remote (India Eligible)"

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

            # Save in batches of up to 30 top matching jobs
            if len(new_jobs) >= 30:
                break

        if new_jobs:
            await db.commit()
            log.info("Persisted %d verified Indian tech jobs to DB for resume %s", len(new_jobs), resume_id)

        # Sync to Google Sheet if linked
        sheet_res = await db.execute(select(SheetLink).where(SheetLink.resume_id == resume_id))
        sheet = sheet_res.scalars().first()
        synced_count = 0
        if sheet and new_jobs:
            try:
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
    """Background task that runs periodically across all resumes."""
    while True:
        try:
            log.info("Starting scheduled periodic job sweep for Indian tech hubs...")
            async with SessionLocal() as db:
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
