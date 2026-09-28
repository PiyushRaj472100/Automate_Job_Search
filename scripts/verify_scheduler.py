"""Phase 10: Scheduled Continuous Operation Verification Script.

Demonstrates:
1. Scheduled continuous operation with rate limiting and exponential backoff retry.
2. Fault isolation: Failing sources fail gracefully with backoff and record failure without halting other sources.
3. Queue-buffered processing: Raw postings buffer in FIFO JobQueueManager before batch normalization & deduplication.
4. Search runs audit: Tracks start time, end time, source, status, discovered, accepted, rejected, errors.
5. Final Morning Pass: Conservative re-verification of candidates before morning report;
   dead/expired listings marked CLOSED, verified jobs update Google Sheets.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from backend.db.session import sync_engine
from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import RawJobPosting, SourcePolicy, SourceType
from backend.discovery.registry import JobDiscoveryCollector
from backend.matching.schemas import MatchLevel
from backend.models.job import Job
from backend.models.resume import Resume, ResumeProfile
from backend.models.search_run import SearchRun
from backend.scheduler.rate_limiter import SourceRateLimiter
from backend.scheduler.schemas import ScheduleConfig
from backend.scheduler.service import ContinuousScheduler
from backend.verification.inspector import PageInspector
from backend.verification.service import JobVerificationService

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s")
logger = logging.getLogger("verify_scheduler")


class ReliableSourceAdapter(JobSourceAdapter):
    def __init__(self, name: str = "reliable_source") -> None:
        policy = SourcePolicy(
            source_name=name,
            source_type=SourceType.OFFICIAL_API,
            base_url=f"https://{name}.com",
            requires_authentication=False,
            rate_limit_per_minute=30,
        )
        super().__init__(policy)

    def search(self, query) -> list[RawJobPosting]:
        return [
            RawJobPosting(
                source_name=self.name,
                source_type=self.policy.source_type,
                external_job_id="ALPHA-101",
                title="Junior Python Developer",
                company_name="Alpha Tech",
                location="Remote",
                job_url="https://alphatech.com/jobs/junior-python",
                description="Junior Python and FastAPI developer with 0-2 years experience. Work with PostgreSQL and Docker.",
            ),
            RawJobPosting(
                source_name=self.name,
                source_type=self.policy.source_type,
                external_job_id="BETA-202",
                title="Software Engineer - Backend",
                company_name="Beta Cloud",
                location="Remote",
                job_url="https://betacloud.com/jobs/backend-closed",
                description="Backend engineer role using Python and FastAPI. 1-2 years experience.",
            ),
        ]

    def fetch_job(self, external_job_id):
        return None

    def health_check(self):
        return MagicMock(is_healthy=True)


class FlakyFailingSourceAdapter(JobSourceAdapter):
    def __init__(self, name: str = "flaky_feed") -> None:
        policy = SourcePolicy(
            source_name=name,
            source_type=SourceType.PUBLIC_FEED,
            base_url=f"https://{name}.com",
            requires_authentication=False,
            rate_limit_per_minute=10,
        )
        super().__init__(policy)
        self.call_count = 0

    def search(self, query) -> list[RawJobPosting]:
        self.call_count += 1
        raise ConnectionResetError(f"Remote server closed connection unexpectedly (attempt {self.call_count})")

    def fetch_job(self, external_job_id):
        return None

    def health_check(self):
        return MagicMock(is_healthy=False)


def main() -> None:
    logger.info("=================================================================")
    logger.info("PHASE 10: SCHEDULED CONTINUOUS OPERATION VERIFICATION")
    logger.info("=================================================================")

    with Session(sync_engine) as session:
        # Step 0: Ensure Test Resume and Profile
        resume = session.query(Resume).filter(Resume.file_name == "phase10_test_candidate.pdf").first()
        if not resume:
            resume = Resume(
                file_name="phase10_test_candidate.pdf",
                file_path="/resumes/phase10_test_candidate.pdf",
                file_hash="hash_phase10_demo",
                raw_text="Candidate with Python, FastAPI, Docker, PostgreSQL skills. Entry level software engineer.",
                spreadsheet_id="test_sheet_phase10",
                spreadsheet_url="https://docs.google.com/spreadsheets/d/test_sheet_phase10",
            )
            session.add(resume)
            session.flush()

        profile = (
            session.query(ResumeProfile)
            .filter(ResumeProfile.resume_id == resume.id, ResumeProfile.profile_name == "Phase 10 Profile")
            .first()
        )
        if not profile:
            profile = ResumeProfile(
                resume_id=resume.id,
                profile_name="Phase 10 Profile",
                target_role="Junior Backend Engineer",
                target_locations=["Remote"],
                work_modes=["remote"],
                max_experience_years=2,
                structured_data={
                    "full_name": "Demo Candidate",
                    "education": "B.Tech Computer Science",
                    "experience_years": 1,
                    "programming_languages": ["Python"],
                    "frameworks": ["FastAPI"],
                    "backend": ["PostgreSQL"],
                    "tools": ["Docker", "Git"],
                    "likely_target_roles": ["Junior Backend Engineer", "Software Engineer"],
                },
            )
            session.add(profile)
            session.flush()

        session.query(Job).filter(Job.company_name.in_(["Alpha Tech", "Beta Cloud"])).update({"status": "active"})
        session.commit()

        # Step 1: Initialize Rate Limiter & Continuous Scheduler
        config = ScheduleConfig(
            max_retries_per_source=2,
            retry_backoff_base_seconds=0.01,
            source_rate_limits={"reliable_source": 30, "flaky_feed": 10, "default": 20},
            min_match_level=MatchLevel.RELEVANT,
            sync_to_sheets=True,
        )

        collector = JobDiscoveryCollector()
        collector.register(ReliableSourceAdapter("reliable_source"))
        collector.register(FlakyFailingSourceAdapter("flaky_feed"))

        # Setup inspector for discovery: both jobs active initially
        initial_inspector = PageInspector()
        initial_inspector.fetch_page = MagicMock(
            return_value=(
                200,
                "https://example.com/job",
                "<html><h1>Junior Python Developer</h1><h1>Software Engineer - Backend</h1><h2>Alpha Tech</h2><h2>Beta Cloud</h2><p>We are actively hiring junior software engineers. Review role details, qualifications, and submit application.</p><a href='/apply'>Apply</a></html>",
                {},
            )
        )
        ver_service = JobVerificationService(inspector=initial_inspector)

        scheduler = ContinuousScheduler(
            config=config,
            discovery_collector=collector,
            verification_service=ver_service,
        )
        # Mock Google Sheets API to simulate real sheet row append
        mock_sheet_rows = []

        def mock_append_row(spreadsheet_id, job_data):
            mock_sheet_rows.append(job_data)
            return len(mock_sheet_rows) + 1

        scheduler.sheets_service.append_job_row = MagicMock(side_effect=mock_append_row)

        logger.info("\n--- 1. Testing Rate Limiting & Retry with Exponential Backoff ---")
        rate_limiter = SourceRateLimiter(rate_limits={"test_src": 5})
        attempts = 0

        def flaky_action():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError(f"Transient network glitch attempt {attempts}")
            return "SUCCESS_ON_ATTEMPT_3"

        res, attempts_used = rate_limiter.execute_with_retry(
            source_name="test_src",
            func=flaky_action,
            max_retries=3,
            backoff_base_seconds=0.01,
        )
        logger.info("Rate limiter executed action with exponential backoff: %s (attempts used: %d)", res, attempts_used)
        assert res == "SUCCESS_ON_ATTEMPT_3"

        logger.info("\n--- 2. Running Discovery Cycle (Fault Isolation & Queue Buffering) ---")
        cycle_records = scheduler.run_discovery_cycle(
            db_session=session,
            resume_profile_id=profile.id,
            sources=["reliable_source", "flaky_feed"],
        )

        logger.info("Discovery Cycle executed across %d sources:", len(cycle_records))
        for rec in cycle_records:
            logger.info(
                "  Source: %-15s | Status: %-10s | Discovered: %d | Accepted: %d | Rejected: %d | Retries: %d",
                rec.source_name,
                rec.status,
                rec.jobs_discovered,
                rec.jobs_accepted,
                rec.jobs_rejected,
                rec.retries_attempted,
            )

        # Fault isolation check
        reliable_rec = next(r for r in cycle_records if r.source_name == "reliable_source")
        flaky_rec = next(r for r in cycle_records if r.source_name == "flaky_feed")
        assert reliable_rec.status == "completed", "Reliable source must complete"
        assert flaky_rec.status == "failed", "Flaky source must fail gracefully"
        assert len(flaky_rec.errors) > 0, "Errors must be recorded for failed source"
        logger.info("Fault Isolation VERIFIED: Failed source 'flaky_feed' did NOT stop 'reliable_source'.")

        # Step 3: Verify audit trail in search_runs
        runs = (
            session.query(SearchRun)
            .filter(SearchRun.resume_profile_id == profile.id, SearchRun.run_type == "discovery")
            .order_by(SearchRun.started_at.desc())
            .limit(2)
            .all()
        )
        logger.info("\n--- 3. Search Runs Audit Records ---")
        for run in runs:
            logger.info(
                "  SearchRun ID: %s | Source: %-15s | Status: %-10s | Discovered: %d | Accepted: %d | Rejected: %d",
                str(run.id)[:8],
                run.source,
                run.status,
                run.jobs_discovered,
                run.jobs_matched,
                run.metadata_json.get("jobs_rejected", 0) if run.metadata_json else 0,
            )

        # Step 4: Final Morning Verification Pass
        # Simulate overnight changes: Beta Cloud job has closed (404), Alpha Tech remains active (200)
        logger.info("\n--- 4. Running Final Morning Pass (Rechecking Candidates & Syncing Sheets) ---")
        morning_inspector = PageInspector()

        def morning_fetch(url):
            if "betacloud" in url:
                return (404, url, "<html><title>404 Not Found</title><body>Position has been closed.</body></html>", {})
            return (
                200,
                url,
                "<html><h1>Junior Python Developer</h1><h2>Alpha Tech</h2><p>We are actively hiring junior software engineers. Review role details, qualifications, and submit application.</p><a href='/apply'>Apply</a></html>",
                {},
            )

        morning_inspector.fetch_page = morning_fetch
        scheduler.verification_service = JobVerificationService(inspector=morning_inspector)

        recruiter_pool = [
            {
                "name": "Jane Doe",
                "title": "Technical Recruiter",
                "company": "Alpha Tech",
                "linkedin_url": "https://www.linkedin.com/in/jane-doe-recruiter-alpha",
            }
        ]

        morning_summary = scheduler.run_morning_final_verification(
            db_session=session,
            resume_profile_id=profile.id,
            sync_sheets=True,
            candidate_recruiter_pool=recruiter_pool,
        )

        logger.info("Final Morning Pass Summary:")
        logger.info("  Candidates Rechecked:    %d", morning_summary.candidates_rechecked)
        logger.info("  Still Verified (Active): %d", morning_summary.still_verified)
        logger.info("  Closed or Expired:       %d", morning_summary.closed_or_expired)
        logger.info("  Google Sheet Rows:       %d", morning_summary.sheet_rows_updated)
        logger.info("  Primary Morning Jobs:    %d", len(morning_summary.primary_morning_jobs))

        assert morning_summary.candidates_rechecked >= 2
        assert morning_summary.still_verified == 1
        assert morning_summary.closed_or_expired == 1
        assert len(morning_summary.primary_morning_jobs) == 1
        assert morning_summary.sheet_rows_updated == 1

        # Confirm Closed Job in DB
        closed_job = session.query(Job).filter(Job.company_name.like("%Beta Cloud%")).first()
        assert closed_job is not None
        assert closed_job.status == "closed", f"Expected closed, got {closed_job.status}"
        logger.info("Expired job 'Beta Cloud' status successfully set to: %s", closed_job.status)

        # Confirm Active Job entered morning output
        active_job_output = morning_summary.primary_morning_jobs[0]
        logger.info("Primary Morning Job:")
        logger.info("  Title:           %s", active_job_output.title)
        logger.info("  Company:         %s", active_job_output.company)
        logger.info("  Match Level:     %s", active_job_output.match_level.value)
        logger.info("  Recruiter 1:     %s", active_job_output.recruiter_1)
        logger.info("  Recruiter Status:%s", active_job_output.recruiter_status.value)
        logger.info("  Sheet Row Index: %d", active_job_output.sheet_row_index)

        # Confirm Morning SearchRun record
        morning_run = (
            session.query(SearchRun)
            .filter(SearchRun.resume_profile_id == profile.id, SearchRun.run_type == "morning_report")
            .order_by(SearchRun.started_at.desc())
            .first()
        )
        assert morning_run is not None
        assert morning_run.status == "completed"
        logger.info("Morning SearchRun audit record created successfully with ID: %s", morning_run.id)

    logger.info("=================================================================")
    logger.info("PHASE 10 SCHEDULED CONTINUOUS OPERATION VERIFIED SUCCESSFULLY!")
    logger.info("=================================================================")


if __name__ == "__main__":
    main()
