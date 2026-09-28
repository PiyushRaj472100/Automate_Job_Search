"""End-to-End Pipeline Verification Script (Phase 8).

Runs one complete pipeline execution against one candidate resume.
Integrates all 9 phases:
Resume Ingestion -> Resume Profile -> Job Discovery -> Normalization ->
Deduplication -> Eligibility & Matching -> Missing/Improve -> Conservative Job Verification ->
Recruiter Discovery & Verification -> PostgreSQL Persistence -> Google Sheets Sync.

Demonstrates:
* jobs discovered
* duplicates removed
* jobs rejected
* jobs verified
* matches
* missing/improve
* recruiter profiles
* Sheet rows created
"""

import io
import logging
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Ensure workspace root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.session import SyncSessionLocal
from backend.discovery.adapters.arbeitnow import ArbeitnowAdapter
from backend.discovery.registry import JobDiscoveryCollector
from backend.matching.schemas import MatchLevel
from backend.pipeline.orchestrator import JobIntelligencePipeline
from backend.pipeline.schemas import PipelineConfig
from backend.verification.inspector import PageInspector
from backend.verification.service import JobVerificationService

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def build_candidate_resume_pdf() -> bytes:
    """Generate a valid candidate resume PDF in memory."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(72, 750, "Rohan Verma")
    c.drawString(72, 735, "Email: rohan.verma@example.com | Bengaluru, India | LinkedIn: linkedin.com/in/rohan-verma")
    c.drawString(72, 710, "Target Roles: Junior Backend Engineer, Python Developer, Associate Software Engineer")
    c.drawString(72, 690, "Education:")
    c.drawString(90, 675, "B.Tech in Computer Science and Engineering, 2024")
    c.drawString(72, 650, "Technical Skills:")
    c.drawString(90, 635, "Programming: Python, SQL")
    c.drawString(90, 620, "Frameworks & Tools: FastAPI, PostgreSQL, Docker, Git, Redis")
    c.drawString(72, 595, "Experience & Projects:")
    c.drawString(90, 580, "Backend Engineering Intern (6 months): Developed async REST APIs using FastAPI & PostgreSQL.")
    c.drawString(90, 565, "Microservices Orchestration: Containerized distributed tasks with Docker and Redis queues.")
    c.save()
    return buffer.getvalue()


def run_pipeline_verification():
    print("=" * 80)
    print("END-TO-END JOB INTELLIGENCE PIPELINE VERIFICATION")
    print("=" * 80)

    # 1. Build Candidate Resume
    resume_pdf_bytes = build_candidate_resume_pdf()
    print("[1] Generated candidate resume: Rohan Verma (B.Tech CS 2024, Python/FastAPI/PostgreSQL/Docker)")

    # 2. Setup Discovery Collector with real accessible source (Arbeitnow)
    collector = JobDiscoveryCollector()
    collector.register(ArbeitnowAdapter())

    # 3. Setup Realistic Job Feed with varied edge cases
    # Includes:
    # - Strong match (Junior Python/FastAPI entry-level)
    # - Exact duplicate with UTM tracking parameters
    # - Relevant match (Software Engineer I Python)
    # - Senior role (Senior Backend Architect - must be rejected by fresh/seniority filter)
    # - Unrelated domain (Registered Nurse ICU - must be rejected by role relevance)
    # - Dead link job (HTTP 404 - must fail verification and be excluded)
    test_jobs_feed = [
        {
            "title": "Junior Backend Engineer",
            "company": "Nexus Labs",
            "location": "Remote",
            "job_url": "https://nexuslabs.com/careers/junior-backend",
            "description": "Seeking junior engineer with Python, FastAPI, PostgreSQL, and Docker experience (0-2 years). Contact: Sarah Connor",
            "source": "company_site",
        },
        {
            "title": "Junior Backend Engineer",
            "company": "Nexus Labs",
            "location": "Remote",
            "job_url": "https://nexuslabs.com/careers/junior-backend?utm_source=linkedin&utm_campaign=hiring_2026",
            "description": "Seeking junior engineer with Python, FastAPI, PostgreSQL, and Docker experience (0-2 years).",
            "source": "linkedin",
        },
        {
            "title": "Software Engineer I - Python",
            "company": "Fintech Stream",
            "location": "Remote",
            "job_url": "https://fintechstream.com/jobs/swe-1",
            "description": "Core platform team opening for Python developers. 1+ years experience preferred. Familiarity with AWS and Redis is a plus.",
            "source": "company_site",
        },
        {
            "title": "Senior Principal Cloud Architect",
            "company": "Enterprise Global",
            "location": "Remote",
            "job_url": "https://enterpriseglobal.com/careers/arch-500",
            "description": "Looking for Principal Cloud Architect with 12+ years of experience leading multi-cloud migrations and director-level roadmaps.",
            "source": "company_site",
        },
        {
            "title": "Registered Nurse - ICU",
            "company": "Metro Health Hospital",
            "location": "Bengaluru",
            "job_url": "https://metrohealth.org/nursing/icu-101",
            "description": "Seeking certified ICU registered nurse with BLS/ACLS certification and patient care experience.",
            "source": "company_site",
        },
        {
            "title": "Python Developer - Entry Level",
            "company": "Ghost Postings Inc",
            "location": "Remote",
            "job_url": "https://ghostpostings.org/jobs/expired-404",
            "description": "Python junior developer role.",
            "source": "public_feed",
        },
    ]

    # Recruiter talent pool for discovery
    recruiter_pool = [
        {
            "name": "Sarah Connor",
            "title": "Lead Technical Recruiter",
            "company": "Nexus Labs",
            "linkedin_url": "https://www.linkedin.com/in/sarah-connor-recruiter",
            "email": "sarah.c@nexuslabs.com",
        },
        {
            "name": "Alex Rivera",
            "title": "Talent Acquisition Partner",
            "company": "Fintech Stream",
            "linkedin_url": "https://www.linkedin.com/in/alex-rivera-ta",
        },
        {
            "name": "Unrelated Staff",
            "title": "Accountant",
            "company": "Nexus Labs",
            "linkedin_url": "https://www.linkedin.com/in/unrelated-accountant",
        },
    ]

    # 4. Setup Page Inspector with conservative simulation
    mock_inspector = PageInspector()

    def mock_fetch(url: str):
        if "expired-404" in url or "ghostpostings" in url:
            return (404, url, "<html><title>404 Not Found</title><body>Position no longer active.</body></html>", {})
        html = (
            "<html><head><title>Job Details</title></head><body>"
            "<h1>Junior Backend Engineer</h1><h2>Nexus Labs</h2>"
            "<h1>Software Engineer I - Python</h1><h2>Fintech Stream</h2>"
            "<p>We are actively hiring for our engineering teams. Review requirements and submit application.</p>"
            "<a href='https://jobs.lever.co/apply'>Apply for this job</a>"
            "</body></html>"
        )
        return (200, url, html, {})

    mock_inspector.fetch_page = mock_fetch
    verification_service = JobVerificationService(inspector=mock_inspector)

    pipeline = JobIntelligencePipeline(
        discovery_collector=collector,
        verification_service=verification_service,
    )

    config = PipelineConfig(
        min_match_level=MatchLevel.RELEVANT,
        require_verified_job=True,
        candidate_recruiter_pool=recruiter_pool,
        sync_to_sheets=True,
    )

    print("[2] Executing Unified End-to-End Pipeline...")
    with SyncSessionLocal() as db_session:
        summary = pipeline.run_pipeline(
            db_session=db_session,
            resume_source=("rohan_verma_resume.pdf", resume_pdf_bytes),
            config=config,
            custom_jobs_feed=test_jobs_feed,
        )

    # 5. Display Pipeline Output Metrics
    print("\n" + "=" * 80)
    print("PIPELINE EXECUTION METRICS")
    print("=" * 80)
    print(f"* jobs discovered:          {summary.metrics.jobs_discovered}")
    print(f"* duplicates removed:        {summary.metrics.duplicates_removed}")
    print(f"* jobs rejected:             {summary.metrics.jobs_rejected}")
    print(f"* jobs verified:             {summary.metrics.jobs_verified}")
    print(f"* matches (qualified):       {len(summary.primary_morning_jobs)}")
    print(f"* recruiter profiles found:  {summary.metrics.recruiter_profiles_found}")
    print(f"* Sheet rows created:        {summary.metrics.sheet_rows_created}")

    print("\n" + "=" * 80)
    print("PRIMARY MORNING VIEW (QUALIFIED & VERIFIED JOBS)")
    print("=" * 80)

    for idx, job in enumerate(summary.primary_morning_jobs, 1):
        row_data = job.to_sheet_row_dict(resume_label="Rohan Verma")
        print(f"\n--- [Job #{idx}] {job.title} @ {job.company} ---")
        print(f"  Status:             {job.verification_status.value} (Verified URL usable)")
        print(f"  Match Level:        {job.match_level.value}")
        print(f"  Why It Matches:     {job.why_it_matches}")
        print(f"  Skills You Have:    {', '.join(job.skills_you_have)}")
        print(f"  Missing / Improve:  {', '.join(job.missing_improve) if job.missing_improve else 'None (Complete Coverage)'}")
        print(f"  Recruiter 1:        {job.recruiter_1 or 'None verified'}")
        print(f"  Recruiter 2:        {job.recruiter_2 or 'None'}")
        print(f"  Sheet Row Index:    Row {job.sheet_row_index} in Google Sheets ({len(row_data)} columns formatted)")
        print(f"  Application Link:   {job.application_url or job.job_url}")

    print("\n" + "=" * 80)
    print("PIPELINE AUDIT SUMMARY")
    print("=" * 80)
    print(f"Resume Record ID:    {summary.resume_id}")
    print(f"Profile ID:          {summary.resume_profile_id}")
    print(f"Search Run ID:       {summary.search_run_id}")
    print(f"Pipeline Status:     {summary.status.upper()}")
    print("=" * 80)


if __name__ == "__main__":
    run_pipeline_verification()
