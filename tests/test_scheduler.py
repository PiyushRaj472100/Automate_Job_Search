"""Unit and integration tests for Scheduled Continuous Operation (Phase 10)."""

import uuid
from unittest.mock import MagicMock

import pytest

from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import RawJobPosting, SourcePolicy, SourceType
from backend.discovery.registry import JobDiscoveryCollector
from backend.matching.schemas import MatchLevel
from backend.models.job import Job
from backend.models.resume import Resume, ResumeProfile
from backend.models.search_run import SearchRun
from backend.models.verification import VerificationEvent
from backend.scheduler.queue import JobQueueManager
from backend.scheduler.rate_limiter import SourceExhaustedError, SourceRateLimiter
from backend.scheduler.schemas import ScheduleConfig
from backend.scheduler.service import ContinuousScheduler
from backend.verification.inspector import PageInspector
from backend.verification.service import JobVerificationService


class MockHealthyAdapter(JobSourceAdapter):
    """Mock adapter returning valid job postings."""

    def __init__(self, name: str = "healthy_source"):
        policy = SourcePolicy(
            source_name=name,
            source_type=SourceType.OFFICIAL_API,
            base_url=f"https://{name}.com",
            requires_authentication=False,
            rate_limit_per_minute=60,
        )
        super().__init__(policy)
        self.call_count = 0

    def search(self, query):
        self.call_count += 1
        return [
            RawJobPosting(
                source_name=self.name,
                source_type=self.policy.source_type,
                external_job_id=f"{self.name}-job-1",
                title="Junior Python Developer",
                company_name="Nexus Labs",
                location="Remote",
                job_url=f"https://{self.name}.com/jobs/1",
                description="Python, FastAPI developer for entry level role (0-2 years).",
            )
        ]

    def fetch_job(self, external_job_id):
        return None

    def health_check(self):
        return MagicMock(is_healthy=True)


class MockFailingAdapter(JobSourceAdapter):
    """Mock adapter simulating upstream server failure."""

    def __init__(self, name: str = "flaky_source"):
        policy = SourcePolicy(
            source_name=name,
            source_type=SourceType.PUBLIC_FEED,
            base_url=f"https://{name}.com",
            requires_authentication=False,
            rate_limit_per_minute=60,
        )
        super().__init__(policy)
        self.attempts = 0

    def search(self, query):
        self.attempts += 1
        raise ConnectionResetError(f"Connection reset by peer on attempt {self.attempts}")

    def fetch_job(self, external_job_id):
        raise ConnectionResetError("Connection reset")

    def health_check(self):
        return MagicMock(is_healthy=False)


@pytest.fixture
def test_profile(db_session):
    """Create a persistent resume and profile in the test database."""
    resume = Resume(
        file_name="rohan_verma.pdf",
        file_path="/storage/resumes/rohan_verma.pdf",
        file_hash=f"hash_{uuid.uuid4().hex[:12]}",
        raw_text="Rohan Verma. B.Tech CS 2024. Python, FastAPI, PostgreSQL, Docker.",
        spreadsheet_id="test_sheet_12345",
        spreadsheet_url="https://docs.google.com/spreadsheets/d/test_sheet_12345",
    )
    db_session.add(resume)
    db_session.flush()

    profile = ResumeProfile(
        resume_id=resume.id,
        profile_name="Rohan Verma",
        target_role="Junior Backend Engineer",
        target_locations=["Remote"],
        work_modes=["remote"],
        max_experience_years=2,
        is_active=True,
        structured_data={
            "full_name": "Rohan Verma",
            "education": "B.Tech in Computer Science",
            "graduation_year": 2024,
            "experience_years": 1,
            "programming_languages": ["Python", "SQL"],
            "frameworks": ["FastAPI"],
            "databases": ["PostgreSQL"],
            "backend": ["Python", "FastAPI"],
            "tools": ["Docker", "Git"],
            "likely_target_roles": ["Junior Backend Engineer", "Software Engineer", "Python Developer"],
            "seniority": "entry-level",
        },
    )
    db_session.add(profile)
    db_session.commit()
    return profile


class TestScheduledContinuousOperation:
    """Verifies scheduled continuous operation, rate limits, queues, retry backoff, and morning verification."""

    def test_rate_limiter_and_exponential_backoff_retry(self):
        """Rule: Source-specific rate limits and retry with exponential backoff on failure."""
        limiter = SourceRateLimiter(rate_limits={"test_source": 120}, default_rate_limit=60)
        attempts = 0

        def flaky_func():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("Transient network glitch")
            return "SUCCESS"

        result, retries = limiter.execute_with_retry(
            source_name="test_source",
            func=flaky_func,
            max_retries=3,
            backoff_base_seconds=0.01,  # Fast backoff for test speed
        )

        assert result == "SUCCESS"
        assert retries == 2
        assert attempts == 3

    def test_source_repeated_failure_raises_exhausted_without_stopping_others(self):
        """Rule: If a source repeatedly fails, record failure and do not stop other sources."""
        limiter = SourceRateLimiter(rate_limits={"failing_source": 120})

        def always_fails():
            raise TimeoutError("Upstream server timeout")

        with pytest.raises(SourceExhaustedError) as exc_info:
            limiter.execute_with_retry(
                source_name="failing_source",
                func=always_fails,
                max_retries=2,
                backoff_base_seconds=0.01,
            )

        assert exc_info.value.source_name == "failing_source"
        assert exc_info.value.attempts == 3

    def test_job_queue_manager_fifo_buffering(self):
        """Verify thread-safe JobQueueManager enqueues and batch dequeues jobs."""
        queue = JobQueueManager(maxsize=100)
        assert queue.is_empty()

        jobs = [{"id": f"job_{i}", "title": f"Dev {i}"} for i in range(10)]
        enqueued = queue.enqueue_batch(jobs)
        assert enqueued == 10
        assert queue.size() == 10

        batch1 = queue.dequeue_batch(batch_size=4)
        assert len(batch1) == 4
        assert batch1[0]["id"] == "job_0"
        assert queue.size() == 6

        batch2 = queue.dequeue_batch(batch_size=10)
        assert len(batch2) == 6
        assert queue.is_empty()

    def test_discovery_cycle_with_fault_isolation_and_search_run_tracking(
        self, db_session, test_profile
    ):
        """Verify discovery cycle:

        - Executes healthy source
        - Catches failing source with retry backoff
        - Records search_run rows for each source with:
          start time, end time, source, status, jobs discovered, jobs accepted, jobs rejected, errors
        - Discovered jobs enqueued and processed into database.
        """
        healthy_adapter = MockHealthyAdapter("arbeitnow")
        failing_adapter = MockFailingAdapter("broken_feed")

        collector = JobDiscoveryCollector()
        collector.register(healthy_adapter)
        collector.register(failing_adapter)

        # Mock PageInspector to verify healthy job
        mock_inspector = PageInspector()
        mock_inspector.fetch_page = MagicMock(
            return_value=(
                200,
                "https://arbeitnow.com/jobs/1",
                "<html><h1>Junior Python Developer</h1><h2>Nexus Labs</h2><p>We are actively hiring junior software engineers to develop robust FastAPI and Python services. Review job details, qualifications, and submit application.</p><a href='/apply'>Apply</a></html>",
                {},
            )
        )
        ver_service = JobVerificationService(inspector=mock_inspector)

        config = ScheduleConfig(
            max_retries_per_source=2,
            retry_backoff_base_seconds=0.01,
            min_match_level=MatchLevel.RELEVANT,
        )
        scheduler = ContinuousScheduler(
            config=config,
            discovery_collector=collector,
            verification_service=ver_service,
        )

        records = scheduler.run_discovery_cycle(
            db_session=db_session,
            resume_profile_id=test_profile.id,
        )

        # Verify cycle records
        assert len(records) == 2

        # 1. Healthy source succeeded
        healthy_rec = next(r for r in records if r.source_name == "arbeitnow")
        assert healthy_rec.status == "completed"
        assert healthy_rec.jobs_discovered >= 1
        assert healthy_rec.jobs_accepted >= 1

        # 2. Flaky source failed without halting healthy source
        failing_rec = next(r for r in records if r.source_name == "broken_feed")
        assert failing_rec.status == "failed"
        assert len(failing_rec.errors) >= 1
        assert failing_rec.retries_attempted == 3  # 1 initial + 2 retries

        # 3. Check search_runs persisted in PostgreSQL
        search_runs = (
            db_session.query(SearchRun)
            .filter(SearchRun.resume_profile_id == test_profile.id)
            .all()
        )
        assert len(search_runs) >= 2

        # Check fields tracked in search_runs
        for run in search_runs:
            assert run.started_at is not None
            assert run.completed_at is not None
            assert run.source in ("arbeitnow", "broken_feed")
            assert run.status in ("completed", "failed")
            assert "jobs_accepted" in run.metadata_json
            assert "jobs_rejected" in run.metadata_json

        # Check job persisted in DB
        persisted_job = (
            db_session.query(Job)
            .filter(Job.company_name == "Nexus Labs")
            .first()
        )
        assert persisted_job is not None
        assert persisted_job.status == "active"

    def test_morning_final_verification_pass(self, db_session, test_profile):
        """Rule: Final Morning Pass:

        - Recheck all primary candidates before morning report.
        - Dead / 404 / closed jobs must NOT become VERIFIED.
        - Status updated to closed.
        - Still-verified jobs enter primary morning view and update Google Sheets.
        - Audit trail recorded in search_runs.
        """
        healthy_adapter = MockHealthyAdapter("arbeitnow")
        collector = JobDiscoveryCollector()
        collector.register(healthy_adapter)

        # 1. Setup two candidate jobs:
        #    Job A: Remains active & verified (200 OK)
        #    Job B: Expired overnight (404 Not Found)
        custom_feed = [
            {
                "title": "Junior Python Developer",
                "company": "Nexus Labs",
                "location": "Remote",
                "job_url": "https://nexuslabs.com/jobs/junior-python",
                "description": "Python, FastAPI developer (0-2 years).",
                "source": "company_site",
            },
            {
                "title": "Software Engineer - Python",
                "company": "Overnight Closed Co",
                "location": "Remote",
                "job_url": "https://closedco.com/jobs/expired",
                "description": "Python engineer role (1+ years).",
                "source": "company_site",
            },
        ]

        # Initial inspector verifies both during discovery
        initial_inspector = PageInspector()
        initial_inspector.fetch_page = MagicMock(
            return_value=(
                200,
                "https://example.com/job",
                "<html><h1>Junior Python Developer</h1><h1>Software Engineer - Python</h1><h2>Nexus Labs</h2><h2>Overnight Closed Co</h2><p>We are actively hiring junior software engineers to develop robust FastAPI and Python services. Review job details, qualifications, and submit your application.</p><a href='/apply'>Apply</a></html>",
                {},
            )
        )
        ver_service = JobVerificationService(inspector=initial_inspector)

        config = ScheduleConfig(
            max_retries_per_source=1,
            retry_backoff_base_seconds=0.01,
            sync_to_sheets=True,
        )
        scheduler = ContinuousScheduler(
            config=config,
            discovery_collector=collector,
            verification_service=ver_service,
        )
        scheduler.sheets_service.append_job_row = MagicMock(return_value=2)

        # Run initial discovery to populate candidates in DB
        scheduler.run_discovery_cycle(
            db_session=db_session,
            resume_profile_id=test_profile.id,
            sources=["arbeitnow"],
            custom_feed=custom_feed,
        )

        # Confirm candidates are in DB as active
        jobs_in_db = db_session.query(Job).filter(Job.status == "active").all()
        assert len(jobs_in_db) >= 2

        # 2. Morning Final Verification: Job B now returns 404 (Closed)
        morning_inspector = PageInspector()

        def morning_fetch(url):
            if "expired" in url or "closedco" in url:
                return (404, url, "<html><title>404 Not Found</title><body>Job Closed</body></html>", {})
            return (
                200,
                url,
                "<html><h1>Junior Python Developer</h1><h2>Nexus Labs</h2><p>We are actively hiring for our engineering teams. Review qualifications, role details, and submit application. Substantive details about the engineering role and responsibilities are provided here.</p><a href='/apply'>Apply</a></html>",
                {},
            )

        morning_inspector.fetch_page = morning_fetch
        scheduler.verification_service = JobVerificationService(inspector=morning_inspector)

        # Recruiter candidate pool for morning recruiter discovery
        recruiter_pool = [
            {
                "name": "Sarah Connor",
                "title": "Lead Technical Recruiter",
                "company": "Nexus Labs",
                "linkedin_url": "https://www.linkedin.com/in/sarah-connor-recruiter",
            }
        ]

        # Run Morning Pass
        morning_summary = scheduler.run_morning_final_verification(
            db_session=db_session,
            resume_profile_id=test_profile.id,
            sync_sheets=True,
            candidate_recruiter_pool=recruiter_pool,
        )

        # 3. Assertions on Morning Pass
        assert morning_summary.candidates_rechecked >= 2
        assert morning_summary.still_verified >= 1
        assert morning_summary.closed_or_expired >= 1
        assert len(morning_summary.primary_morning_jobs) >= 1
        assert morning_summary.sheet_rows_updated >= 1

        # Job B must NOT be verified; its DB status must be 'closed'
        closed_job = db_session.query(Job).filter(Job.company_name.like("%Overnight Closed%")).first()
        assert closed_job is not None
        assert closed_job.status == "closed"

        # Verification event audit trail
        events = db_session.query(VerificationEvent).filter(VerificationEvent.job_id == closed_job.id).all()
        assert any(e.is_active is False for e in events)

        # Morning search_run audit record
        morning_run = (
            db_session.query(SearchRun)
            .filter(SearchRun.resume_profile_id == test_profile.id, SearchRun.run_type == "morning_report")
            .first()
        )
        assert morning_run is not None
        assert morning_run.status == "completed"
        assert morning_run.jobs_discovered == morning_summary.candidates_rechecked
        assert morning_run.jobs_verified == morning_summary.still_verified
        assert morning_run.metadata_json["closed_or_expired"] == morning_summary.closed_or_expired
