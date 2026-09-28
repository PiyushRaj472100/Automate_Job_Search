"""End-to-end integration tests for the unified Job Intelligence Pipeline."""

import io
from unittest.mock import MagicMock

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import SourcePolicy, SourceType
from backend.discovery.registry import JobDiscoveryCollector
from backend.matching.schemas import MatchLevel
from backend.models.job import JobMatch
from backend.models.person import Person
from backend.models.resume import Resume
from backend.models.search_run import SearchRun
from backend.pipeline.orchestrator import JobIntelligencePipeline
from backend.pipeline.schemas import PipelineConfig
from backend.verification.inspector import PageInspector
from backend.verification.schemas import VerificationStatus
from backend.verification.service import JobVerificationService


class FailingSourceAdapter(JobSourceAdapter):
    """Source adapter that simulates network timeout or upstream failure."""

    def __init__(self):
        policy = SourcePolicy(
            source_name="failing_feed",
            source_type=SourceType.PUBLIC_FEED,
            base_url="https://failing-feed.com",
            requires_authentication=False,
        )
        super().__init__(policy)

    def search(self, query):
        raise ConnectionResetError("Remote server closed connection unexpectedly")

    def fetch_job(self, external_job_id):
        raise ConnectionResetError("Remote server closed connection unexpectedly")

    def health_check(self):
        return MagicMock(is_healthy=False)


def build_sample_pdf(name: str, education: str, skills_str: str) -> bytes:
    """Generate a real valid PDF in memory using ReportLab."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, f"Candidate Name: {name}")
    c.drawString(100, 725, "Email: rohan.verma@example.com | Bengaluru, India")
    c.drawString(100, 700, f"Education: {education}")
    c.drawString(100, 675, f"Technical Skills: {skills_str}")
    c.drawString(100, 650, "Projects: Scalable Microservice API in Python, FastAPI, PostgreSQL, Docker.")
    c.drawString(100, 625, "Experience: Backend Engineering Intern (6 months) in Python REST APIs.")
    c.save()
    return buffer.getvalue()


class TestJobIntelligencePipelineE2E:
    """Verifies end-to-end pipeline orchestration, fault tolerance, and persistence."""

    def setup_method(self):
        self.sample_resume_content = build_sample_pdf(
            name="Rohan Verma",
            education="B.Tech in Computer Science and Engineering, 2024",
            skills_str="Python, FastAPI, PostgreSQL, Docker, Git, SQL",
        )

    def test_complete_end_to_end_pipeline_run(self, db_session):
        """Execute a full pipeline run against one resume and verify all stage metrics and outputs."""
        # Simulated feed containing:
        # 1. Strong entry-level match (0-2 yrs Python / FastAPI / Docker)
        # 2. Duplicate of Job 1 (same canonical job with tracking parameters)
        # 3. Relevant match (Software Engineer I Python 1+ years)
        # 4. Senior role (Senior Backend Architect - must be rejected)
        # 5. Unrelated job (Registered Nurse ICU - must be rejected)
        # 6. Dead/Expired job (returns 404 - must fail verification and be excluded)
        test_feed = [
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
                "job_url": "https://nexuslabs.com/careers/junior-backend?utm_source=linkedin&utm_medium=feed",
                "description": "Seeking junior engineer with Python, FastAPI, PostgreSQL, and Docker experience (0-2 years).",
                "source": "linkedin",
            },
            {
                "title": "Software Engineer I - Python",
                "company": "Fintech Stream",
                "location": "Remote",
                "job_url": "https://fintechstream.com/jobs/swe-1",
                "description": "Platform team opening for Python and FastAPI developers. 1+ years experience preferred.",
                "source": "company_site",
            },
            {
                "title": "Senior Backend Architect",
                "company": "Big Tech Corp",
                "location": "Remote",
                "job_url": "https://bigtech.com/jobs/arch-99",
                "description": "Python architect. Requires 8+ years distributed systems leadership experience.",
                "source": "company_site",
            },
            {
                "title": "Registered Nurse - ICU",
                "company": "Memorial Hospital",
                "location": "Bengaluru",
                "job_url": "https://hospital.org/jobs/rn-icu",
                "description": "Patient care and critical vital monitoring.",
                "source": "healthcare_board",
            },
            {
                "title": "Junior Python Developer",
                "company": "Dead Links Inc",
                "location": "Remote",
                "job_url": "https://deadlinks.com/job/404",
                "description": "Python entry level position.",
                "source": "public_feed",
            },
        ]

        # Candidate recruiter pool for recruiter discovery
        recruiter_pool = [
            {
                "name": "Sarah Connor",
                "title": "Lead Technical Recruiter",
                "company": "Nexus Labs",
                "linkedin_url": "https://www.linkedin.com/in/sarah-connor-recruiter/",
                "email": "sarah.c@nexuslabs.com",
            },
            {
                "name": "Alex Rivera",
                "title": "Talent Acquisition Partner",
                "company": "Fintech Stream",
                "linkedin_url": "https://www.linkedin.com/in/alex-rivera-ta/",
            },
        ]

        mock_inspector = PageInspector()

        def mock_fetch(url):
            if "404" in url or "deadlinks" in url:
                return (404, url, "<html><title>404 Not Found</title><body>404 Not Found</body></html>", {})
            # Return valid page matching titles & companies
            html = (
                "<html><head><title>Careers</title></head><body>"
                "<h1>Junior Backend Engineer</h1><h2>Nexus Labs</h2>"
                "<h1>Software Engineer I - Python</h1><h2>Fintech Stream</h2>"
                "<p>We are hiring! Substantive role details and requirements are listed below. Apply now!</p>"
                "<a href='https://company.com/apply'>Apply for this job</a>"
                "</body></html>"
            )
            return (200, url, html, {})

        mock_inspector.fetch_page = mock_fetch
        ver_service = JobVerificationService(inspector=mock_inspector)

        pipeline = JobIntelligencePipeline(
            discovery_collector=JobDiscoveryCollector(adapters=[]),
            verification_service=ver_service,
        )

        config = PipelineConfig(
            min_match_level=MatchLevel.RELEVANT,
            require_verified_job=True,
            candidate_recruiter_pool=recruiter_pool,
            sync_to_sheets=True,
        )

        # Run pipeline
        summary = pipeline.run_pipeline(
            db_session=db_session,
            resume_source=("rohan_verma_resume.pdf", self.sample_resume_content),
            config=config,
            custom_jobs_feed=test_feed,
        )

        # 1. Verification of Metrics
        assert summary.metrics.jobs_discovered >= 6
        assert summary.metrics.duplicates_removed >= 1  # Deduplicated tracking params
        assert summary.metrics.jobs_rejected >= 3      # Senior role + Unrelated Nurse + 404 Dead Link
        assert summary.metrics.jobs_verified >= 2      # Nexus Labs + Fintech Stream
        assert len(summary.primary_morning_jobs) == 2  # Only the 2 qualified, verified jobs

        # 2. Check Primary Morning Output
        job1 = summary.primary_morning_jobs[0]
        assert "Nexus Labs" in job1.company
        assert job1.match_level in (MatchLevel.STRONG, MatchLevel.RELEVANT)
        assert job1.verification_status in (VerificationStatus.VERIFIED, VerificationStatus.ACTIVE)
        assert "Sarah Connor" in job1.recruiter_1
        assert "Python" in job1.skills_you_have

        job2 = summary.primary_morning_jobs[1]
        assert "Fintech Stream" in job2.company
        assert job2.match_level in (MatchLevel.STRONG, MatchLevel.RELEVANT)
        assert "Alex Rivera" in job2.recruiter_1

        # 3. Check PostgreSQL System of Record
        resume_db = db_session.query(Resume).filter(Resume.id == summary.resume_id).first()
        assert resume_db is not None
        assert len(resume_db.profiles) >= 1

        search_run_db = (
            db_session.query(SearchRun)
            .filter(SearchRun.resume_profile_id == summary.resume_profile_id)
            .first()
        )
        assert search_run_db is not None
        assert search_run_db.status == "completed"

        job_matches_db = (
            db_session.query(JobMatch)
            .filter(JobMatch.resume_profile_id == summary.resume_profile_id)
            .all()
        )
        assert len(job_matches_db) >= 2

        people_db = db_session.query(Person).all()
        assert len(people_db) >= 2
        assert any(p.full_name == "Sarah Connor" for p in people_db)

        # 4. Check Google Sheet Rows Simulated
        assert summary.metrics.sheet_rows_created >= 2
        for job_out in summary.primary_morning_jobs:
            assert job_out.sheet_row_index is not None
            row_dict = job_out.to_sheet_row_dict(resume_label="Rohan Verma")
            assert "Date Found" in row_dict
            assert "Job Title" in row_dict
            assert "Recruiter 1" in row_dict

    def test_failed_source_does_not_stop_pipeline(self, db_session):
        """Rule: A failed source must not stop the entire pipeline."""
        collector = JobDiscoveryCollector()
        collector.register(FailingSourceAdapter())

        mock_inspector = PageInspector()
        mock_inspector.fetch_page = MagicMock(
            return_value=(
                200,
                "https://resilient.io/jobs/1",
                "<html><h1>Junior Python Developer</h1><h2>Resilient Tech</h2><p>Python developer role. Apply now!</p><a href='/apply'>Apply for this job</a></html>",
                {},
            )
        )
        ver_service = JobVerificationService(inspector=mock_inspector)

        pipeline = JobIntelligencePipeline(
            discovery_collector=collector,
            verification_service=ver_service,
        )

        # Provided fallback feed alongside the failing source adapter
        fallback_feed = [
            {
                "title": "Junior Python Developer",
                "company": "Resilient Tech",
                "location": "Remote",
                "job_url": "https://resilient.io/jobs/1",
                "description": "Python, FastAPI developer for entry level role (0-2 years).",
                "source": "company_site",
            }
        ]

        summary = pipeline.run_pipeline(
            db_session=db_session,
            resume_source=("candidate_test.pdf", self.sample_resume_content),
            custom_jobs_feed=fallback_feed,
        )

        # Failing source was captured in telemetry without raising fatal exception
        assert "failing_feed" in summary.failed_sources
        # The pipeline proceeded and processed the available jobs
        assert summary.metrics.jobs_discovered >= 1
        assert len(summary.primary_morning_jobs) >= 1
        assert summary.primary_morning_jobs[0].company == "Resilient Tech"

    def test_failed_recruiter_lookup_does_not_invalidate_job(self, db_session):
        """Rule: A failed recruiter lookup must not invalidate the job."""
        mock_inspector = PageInspector()
        mock_inspector.fetch_page = MagicMock(
            return_value=(
                200,
                "https://solidworks.com/jobs/101",
                "<html><h1>Junior Python Developer</h1><h2>Solid Works</h2><p>Python engineering opening. Apply now!</p><a href='/apply'>Apply for this job</a></html>",
                {},
            )
        )
        ver_service = JobVerificationService(inspector=mock_inspector)

        pipeline = JobIntelligencePipeline(
            discovery_collector=JobDiscoveryCollector(adapters=[]),
            verification_service=ver_service,
        )

        # Mock the recruiter service finder to raise an error
        mock_finder = MagicMock()
        mock_finder.discover_for_job.side_effect = RuntimeError("LinkedIn scraper rate limited")
        pipeline.recruiter_service.finder = mock_finder

        feed = [
            {
                "title": "Junior Python Developer",
                "company": "Solid Works",
                "location": "Remote",
                "job_url": "https://solidworks.com/jobs/101",
                "description": "Python engineer (0-2 years).",
                "source": "company_site",
            }
        ]

        summary = pipeline.run_pipeline(
            db_session=db_session,
            resume_source=("candidate_test.pdf", self.sample_resume_content),
            custom_jobs_feed=feed,
        )

        # Job must NOT be invalidated!
        assert len(summary.primary_morning_jobs) == 1
        job_out = summary.primary_morning_jobs[0]
        assert job_out.company == "Solid Works"
        assert job_out.recruiter_1 == ""  # Recruiter slots gracefully empty

    def test_verification_failure_must_not_become_verified(self, db_session):
        """Rule: A verification failure must not become VERIFIED."""
        # Mock inspector returning 410 Gone / expired
        mock_inspector = PageInspector()
        mock_inspector.fetch_page = MagicMock(
            return_value=(410, "https://expired-job.com/1", "<html>410 Gone. Position closed.</html>", {})
        )
        ver_service = JobVerificationService(inspector=mock_inspector)
        pipeline = JobIntelligencePipeline(
            discovery_collector=JobDiscoveryCollector(adapters=[]),
            verification_service=ver_service,
        )

        expired_feed = [
            {
                "title": "Junior Python Developer",
                "company": "Expired Co",
                "location": "Remote",
                "job_url": "https://expired-job.com/1",
                "description": "Python opening.",
                "source": "company_site",
            }
        ]

        summary = pipeline.run_pipeline(
            db_session=db_session,
            resume_source=("candidate_test.pdf", self.sample_resume_content),
            custom_jobs_feed=expired_feed,
            config=PipelineConfig(require_verified_job=True),
        )

        # Expired job MUST NOT become VERIFIED and MUST NOT be in morning view
        assert summary.metrics.jobs_verified == 0
        assert len(summary.primary_morning_jobs) == 0
        assert summary.metrics.jobs_rejected >= 1
