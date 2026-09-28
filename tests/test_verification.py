"""Unit and integration test suite for Conservative Job Verification Engine."""

import uuid

import httpx

from backend.normalization.schemas import CanonicalJob, WorkMode
from backend.verification.inspector import PageInspector
from backend.verification.schemas import VerificationStatus
from backend.verification.service import JobVerificationService, final_verification_run


class TestConservativeVerificationChecks:
    """Verifies all required verification checks using deterministic fixtures and HTTP simulations."""

    def setup_method(self):
        self.verifier = JobVerificationService()

    def test_working_url_verified(self):
        """Working URL with confirmed title, company, substantive content, and apply button."""
        job = CanonicalJob(
            title="Junior Software Engineer",
            company="Nexus Labs",
            location="Remote",
            work_mode=WorkMode.REMOTE,
            description="Developing backend APIs with Python and FastAPI.",
            job_url="https://nexuslabs.com/careers/junior-swe",
            canonical_url="https://nexuslabs.com/careers/junior-swe",
            primary_source="company_site",
            normalized_company="nexus labs",
            normalized_title="junior software engineer",
            normalized_location="remote",
            dedup_hash="dummy-hash-1",
        )

        valid_html = """
        <html>
            <head><title>Junior Software Engineer - Nexus Labs</title></head>
            <body>
                <h1>Junior Software Engineer</h1>
                <h2>Nexus Labs - Remote</h2>
                <div class="job-description">
                    <p>We are seeking a passionate Junior Software Engineer to join Nexus Labs.</p>
                    <p>Key responsibilities: Build and test scalable microservices using Python, FastAPI, and PostgreSQL.</p>
                    <p>Requirements: 0-2 years of software engineering experience or computer science degree.</p>
                </div>
                <form action="/apply" method="POST">
                    <button type="submit">Apply for this job</button>
                </form>
            </body>
        </html>
        """

        result = self.verifier.verify_job(job, custom_html_override=valid_html, custom_status_override=200)
        assert result.status == VerificationStatus.VERIFIED
        assert result.is_usable is True
        assert result.extracted_signals.title_matched is True
        assert result.extracted_signals.company_matched is True
        assert result.extracted_signals.has_active_application is True

    def test_redirect_handling(self):
        """Redirect from link shortener / tracking URL to final canonical destination."""
        mock_transport = httpx.MockTransport(
            lambda request: httpx.Response(
                302,
                headers={"Location": "https://careers.targetcompany.com/jobs/42"},
            )
            if request.url == "https://bit.ly/target-job-42"
            else httpx.Response(
                200,
                text="""
                <html>
                    <body>
                        <h1>Junior Python Developer</h1>
                        <p>Target Company is hiring! We need Python engineers with 0-2 years experience.</p>
                        <a href="/apply">Apply Now</a>
                    </body>
                </html>
                """,
            )
        )
        custom_client = httpx.Client(transport=mock_transport, follow_redirects=True)
        inspector = PageInspector(custom_client=custom_client)
        verifier = JobVerificationService(inspector=inspector)

        job = {
            "title": "Junior Python Developer",
            "company": "Target Company",
            "location": "Remote",
            "url": "https://bit.ly/target-job-42",
        }

        result = verifier.verify_job(job)
        assert result.status == VerificationStatus.VERIFIED
        assert result.is_usable is True
        assert result.final_url == "https://careers.targetcompany.com/jobs/42"

    def test_404_not_found_closed(self):
        """HTTP 404 response marked CLOSED and not usable."""
        job = {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "url": "https://acme.com/jobs/deleted-404",
        }
        result = self.verifier.verify_job(job, custom_html_override="Not Found", custom_status_override=404)
        assert result.status == VerificationStatus.CLOSED
        assert result.is_usable is False
        assert result.http_status == 404
        assert "404" in result.failure_reason

    def test_410_gone_closed(self):
        """HTTP 410 Gone response marked CLOSED."""
        job = {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "url": "https://acme.com/jobs/permanently-removed",
        }
        result = self.verifier.verify_job(job, custom_html_override="Gone", custom_status_override=410)
        assert result.status == VerificationStatus.CLOSED
        assert result.is_usable is False
        assert result.http_status == 410

    def test_expired_job_notice_closed(self):
        """HTTP 200 but page explicitly contains expired notice ('This position has been filled')."""
        job = {
            "title": "Junior DevOps Engineer",
            "company": "CloudMatrix",
            "url": "https://cloudmatrix.com/jobs/devops",
        }
        expired_html = """
        <html>
            <body>
                <h1>Junior DevOps Engineer</h1>
                <h3>CloudMatrix</h3>
                <div class="alert alert-warning">
                    This position has been filled and is no longer accepting applications.
                </div>
            </body>
        </html>
        """
        result = self.verifier.verify_job(job, custom_html_override=expired_html, custom_status_override=200)
        assert result.status == VerificationStatus.CLOSED
        assert result.is_usable is False
        assert "expired" in result.failure_reason.lower()

    def test_active_application_mechanism_detection(self):
        """Active application form detected and confirmed."""
        job = {
            "title": "Data Analyst",
            "company": "DataStream",
            "url": "https://datastream.io/careers/analyst",
        }
        form_html = """
        <html>
            <body>
                <h1>Data Analyst</h1>
                <p>DataStream is hiring. Requirements: SQL, Python, Excel. Experience needed.</p>
                <form action="/submit-application" method="POST">
                    <input type="file" name="resume" />
                    <button type="submit">Submit Application</button>
                </form>
            </body>
        </html>
        """
        result = self.verifier.verify_job(job, custom_html_override=form_html, custom_status_override=200)
        assert result.status == VerificationStatus.VERIFIED
        assert result.extracted_signals.has_active_application is True

    def test_inaccessible_page_server_error(self):
        """HTTP 500/503 marked UNAVAILABLE and not usable."""
        job = {
            "title": "Backend Engineer",
            "company": "Fintech Global",
            "url": "https://fintech.com/jobs/500",
        }
        result = self.verifier.verify_job(job, custom_html_override="Server Error", custom_status_override=503)
        assert result.status == VerificationStatus.UNAVAILABLE
        assert result.is_usable is False
        assert result.http_status == 503

    def test_mismatched_company_rejected(self):
        """Landing page is for a different company than expected -> REJECTED."""
        job = {
            "title": "Software Engineer",
            "company": "Stripe",
            "url": "https://aggregator.com/jobs/wrong-company",
        }
        mismatched_html = """
        <html>
            <body>
                <h1>Software Engineer</h1>
                <h2>Airbnb Inc. - San Francisco</h2>
                <p>Airbnb is looking for a software engineer with Python experience and cloud infrastructure skills.</p>
                <button>Apply Now</button>
            </body>
        </html>
        """
        result = self.verifier.verify_job(job, custom_html_override=mismatched_html, custom_status_override=200)
        assert result.status == VerificationStatus.REJECTED
        assert result.is_usable is False
        assert "Company mismatch" in result.failure_reason

    def test_mismatched_title_rejected(self):
        """Landing page is for a completely different role -> REJECTED."""
        job = {
            "title": "Junior Python Developer",
            "company": "Spotify",
            "url": "https://spotify.com/careers/sales",
        }
        mismatched_title_html = """
        <html>
            <body>
                <h1>Senior Regional Sales Account Executive</h1>
                <h2>Spotify</h2>
                <p>Lead our enterprise advertising sales team across European territories.</p>
                <button>Apply Now</button>
            </body>
        </html>
        """
        result = self.verifier.verify_job(job, custom_html_override=mismatched_title_html, custom_status_override=200)
        assert result.status == VerificationStatus.REJECTED
        assert result.is_usable is False
        assert "Title mismatch" in result.failure_reason


class TestFinalMorningVerificationRun:
    """Verifies the batch gatekeeper operation filtering jobs before Google Sheets publication."""

    def test_final_verification_run_filters_unusable_jobs(self):
        good_job = CanonicalJob(
            id=uuid.uuid4(),
            title="Junior Software Engineer",
            company="Alpha Tech",
            location="Remote",
            work_mode=WorkMode.REMOTE,
            description="Software engineering position using Python and SQL.",
            job_url="https://alphatech.com/jobs/1",
            canonical_url="https://alphatech.com/jobs/1",
            primary_source="company_site",
            normalized_company="alpha tech",
            normalized_title="junior software engineer",
            normalized_location="remote",
            dedup_hash="good-hash",
        )

        dead_job = CanonicalJob(
            id=uuid.uuid4(),
            title="Junior Software Engineer",
            company="Beta Corp",
            location="Remote",
            work_mode=WorkMode.REMOTE,
            description="Old position.",
            job_url="https://betacorp.com/jobs/404",
            canonical_url="https://betacorp.com/jobs/404",
            primary_source="company_site",
            normalized_company="beta corp",
            normalized_title="junior software engineer",
            normalized_location="remote",
            dedup_hash="dead-hash",
        )

        # Mock transport for deterministic batch run
        mock_transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text="""
                <html>
                    <body>
                        <h1>Junior Software Engineer</h1>
                        <p>Alpha Tech is looking for engineers with Python and SQL experience. Apply below.</p>
                        <button>Apply Now</button>
                    </body>
                </html>
                """,
            )
            if "alphatech" in str(request.url)
            else httpx.Response(404, text="Not Found")
        )

        custom_client = httpx.Client(transport=mock_transport, follow_redirects=True)
        service = JobVerificationService(inspector=PageInspector(custom_client=custom_client))

        verified_jobs, all_results = final_verification_run(
            candidate_jobs=[good_job, dead_job],
            service=service,
        )

        # ONLY the good job should pass to the morning sheet list!
        assert len(verified_jobs) == 1
        assert verified_jobs[0].company == "Alpha Tech"
        assert len(all_results) == 2
        assert all_results[0].status == VerificationStatus.VERIFIED
        assert all_results[1].status == VerificationStatus.CLOSED

    def test_record_verification_event_in_db(self, db_session):
        """Verify immutable VerificationEvent creation and storage in PostgreSQL."""
        from backend.models.company import Company
        from backend.models.job import Job

        # Create dummy job in db
        comp = Company(name="Test Co", normalized_name="test co")
        db_session.add(comp)
        db_session.flush()

        job_entity = Job(
            title="Junior Software Engineer",
            company_name="Test Co",
            location="Remote",
            work_mode="remote",
            description="Testing verification events.",
            job_url="https://testco.com/jobs/1",
            canonical_url="https://testco.com/jobs/1",
            source="manual",
            normalized_company="test co",
            normalized_title="junior software engineer",
            normalized_location="remote",
            dedup_hash="test-dedup-hash-1234",
            company_id=comp.id,
        )
        db_session.add(job_entity)
        db_session.flush()

        service = JobVerificationService()
        result = service.verify_job(
            job=job_entity,
            custom_html_override=(
                "<html><body>"
                "<h1>Junior Software Engineer</h1>"
                "<h2>Test Co - Remote</h2>"
                "<p>Test Co is seeking an entry-level software engineer with Python and SQL experience.</p>"
                "<p>Build scalable backend systems, write automated tests, and collaborate with team members.</p>"
                "<button>Apply for this job</button>"
                "</body></html>"
            ),
            custom_status_override=200,
        )


        event = service.record_event(db_session, job_entity.id, result)
        assert event.id is not None
        assert event.job_id == job_entity.id
        assert event.is_active is True
        assert event.http_status_code == 200
        assert "VERIFIED" in (event.status_reason or "")
        assert event.raw_response_headers is not None
        assert event.raw_response_headers["status"] == "VERIFIED"

    def test_real_public_page_verification(self):
        """Verify real public web page over the internet."""
        inspector = PageInspector(timeout=10.0)
        # Probe reliable public site (python.org)
        status, final_url, body, _ = inspector.fetch_page("https://www.python.org")
        if status is not None:
            assert status == 200
            assert "python" in final_url.lower()
            assert len(body) > 500

