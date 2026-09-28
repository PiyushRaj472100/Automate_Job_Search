"""Comprehensive unit and integration test suite for Job Normalization and Deduplication (Phase 5)."""


from backend.normalization.deduplication import DeduplicationEngine, DuplicateDetector
from backend.normalization.normalizer import (
    JobNormalizer,
    clean_description,
    extract_skills_from_text,
    infer_work_mode,
    normalize_company,
    normalize_location,
    normalize_title,
)
from backend.normalization.schemas import DuplicateMatchReason, WorkMode
from backend.normalization.url_canonicalizer import normalize_url


class TestURLCanonicalization:
    """Verifies tracking parameter removal while strictly preserving critical query parameters."""

    def test_strip_marketing_and_analytics_parameters(self):
        dirty_url = (
            "https://careers.example.com/jobs/123/?"
            "utm_source=linkedin&utm_medium=cpc&utm_campaign=winter2026&"
            "fbclid=IwAR2xyz&gclid=Cj0KCQiA&trk=job_share&ref=aggregator"
        )
        clean = normalize_url(dirty_url)
        assert clean == "https://careers.example.com/jobs/123"
        assert "utm_" not in clean
        assert "fbclid" not in clean
        assert "gclid" not in clean
        assert "trk" not in clean
        assert "ref" not in clean

    def test_preserve_critical_job_identifiers(self):
        job_url_with_ids = (
            "https://jobs.company.com/view?"
            "jobId=40921&gh_jid=987654&role=backend&utm_source=twitter"
        )
        clean = normalize_url(job_url_with_ids)
        assert "jobId=40921" in clean
        assert "gh_jid=987654" in clean
        assert "role=backend" in clean
        assert "utm_source" not in clean

    def test_deterministic_query_parameter_sorting(self):
        url_1 = "https://careers.tech.com/openings?role=backend&id=101"
        url_2 = "https://careers.tech.com/openings?id=101&role=backend"
        assert normalize_url(url_1) == normalize_url(url_2)

    def test_domain_and_protocol_normalization(self):
        url = "HTTP://WWW.EXAMPLE.COM:80/Jobs/SWE/"
        clean = normalize_url(url)
        assert clean == "http://example.com/Jobs/SWE"


class TestFieldNormalization:
    """Verifies standardization of company, title, location, work mode, and skills."""

    def test_company_normalization(self):
        assert normalize_company("Stripe, Inc.") == "Stripe"
        assert normalize_company("Amazon Web Services, Inc.") == "Amazon"
        assert normalize_company("Google LLC") == "Google"
        assert normalize_company("Microsoft Corporation") == "Microsoft"
        assert normalize_company("Acme Technologies Pvt. Ltd.") == "Acme Technologies"
        assert normalize_company("Zendesk GmbH") == "Zendesk"

    def test_title_normalization(self):
        assert normalize_title("Junior SWE (m/f/d) [Remote]") == "Junior Software Engineer"
        assert normalize_title("Sr. Backend Developer | Hybrid") == "Senior Backend Developer"
        assert normalize_title("SDE-1 (0-2 YOE) (REQ-8899)") == "Software Development Engineer-1 (0-2 YOE)"
        assert normalize_title("Jr. Python Dev") == "Junior Python Developer"

    def test_location_and_work_mode(self):
        assert normalize_location("  work from home  ") == "Remote"
        assert normalize_location("Bengaluru, Karnataka, India") == "Bengaluru, India"
        assert infer_work_mode("remote", "Engineer", "New York", "Hybrid office") == WorkMode.REMOTE
        assert infer_work_mode(None, "Software Engineer", "Remote", "Great culture") == WorkMode.REMOTE
        assert infer_work_mode(None, "Software Engineer", "Berlin", "Hybrid 2 days") == WorkMode.HYBRID

    def test_skill_extraction(self):
        text = "We are seeking a Python backend engineer proficient in FastAPI, PostgreSQL, Docker, and AWS."
        skills = extract_skills_from_text(title="Python Engineer", description=text)
        assert "Python" in skills
        assert "FastAPI" in skills
        assert "PostgreSQL" in skills
        assert "Docker" in skills
        assert "AWS" in skills

    def test_html_description_cleaning(self):
        raw_html = "<p>Join our team!</p><ul><li>Python &amp; SQL</li><li>Remote work</li></ul>"
        cleaned = clean_description(raw_html)
        assert "<p>" not in cleaned
        assert "<li>" not in cleaned
        assert "Python & SQL" in cleaned


class TestRequiredDuplicateCases:
    """Explicitly tests the 7 required deduplication test cases from the engineering contract."""

    def setup_method(self):
        self.normalizer = JobNormalizer()
        self.detector = DuplicateDetector()
        self.engine = DeduplicationEngine()

    def test_case_1_same_job_from_linkedin_and_company_site(self):
        """Case 1: Same job from LinkedIn aggregator and direct company career site."""
        linkedin_job = self.normalizer.normalize({
            "title": "Junior Backend Engineer (m/f/d)",
            "company": "Stripe, Inc.",
            "location": "San Francisco, CA",
            "work_mode": "hybrid",
            "description": "Building payment infrastructure with Python, PostgreSQL, and distributed systems.",
            "url": "https://www.linkedin.com/jobs/view/99887766/?refId=feed_search&trackingId=abc",
            "application_url": "https://www.linkedin.com/jobs/apply/99887766",
            "source": "linkedin",
            "tags": ["Python", "PostgreSQL"],
        })

        company_job = self.normalizer.normalize({
            "title": "Junior Backend Engineer",
            "company": "Stripe",
            "location": "San Francisco, CA",
            "work_mode": "hybrid",
            "description": "Building payment infrastructure with Python, PostgreSQL, and Docker. 0-2 years experience.",
            "url": "https://stripe.com/jobs/listing/junior-backend-engineer",
            "application_url": "https://boards.greenhouse.io/stripe/jobs/99887766",
            "source": "greenhouse",
            "tags": ["Python", "PostgreSQL", "Docker"],
        })

        result = self.detector.compare(linkedin_job, company_job)
        assert result.is_duplicate is True
        assert result.confidence_score >= 0.85

        merged_list = self.engine.deduplicate([linkedin_job, company_job])
        assert len(merged_list) == 1
        canonical = merged_list[0]
        assert "linkedin" in canonical.sources
        assert "greenhouse" in canonical.sources
        assert canonical.duplicate_count == 2
        # Merged skills should contain union of both
        assert "Docker" in canonical.skills
        assert "Python" in canonical.skills

    def test_case_2_same_job_with_tracking_parameters(self):
        """Case 2: Same job URL carrying different marketing campaign tracking parameters."""
        job_twitter = self.normalizer.normalize({
            "title": "Software Engineer - Backend",
            "company": "Airbnb",
            "location": "Remote",
            "url": "https://careers.airbnb.com/positions/5001/?utm_source=twitter&utm_campaign=spring2026",
            "source": "twitter_feed",
        })

        job_newsletter = self.normalizer.normalize({
            "title": "Software Engineer - Backend",
            "company": "Airbnb",
            "location": "Remote",
            "url": "https://careers.airbnb.com/positions/5001/?utm_source=newsletter&utm_medium=email",
            "source": "email_feed",
        })

        result = self.detector.compare(job_twitter, job_newsletter)
        assert result.is_duplicate is True
        assert result.match_reason == DuplicateMatchReason.CANONICAL_URL
        assert result.confidence_score == 1.0

        merged_list = self.engine.deduplicate([job_twitter, job_newsletter])
        assert len(merged_list) == 1
        assert merged_list[0].duplicate_count == 2

    def test_case_3_same_requisition_with_different_urls(self):
        """Case 3: Same requisition ID posted across different domains/aggregators."""
        job_aggregator = self.normalizer.normalize({
            "title": "Junior Python Developer",
            "company": "Databricks Inc.",
            "location": "Remote",
            "requisition_id": "REQ-2026-9042",
            "url": "https://remotejobsportal.io/jobs/databricks-python-dev",
            "source": "remote_portal",
        })

        job_official = self.normalizer.normalize({
            "title": "Junior Python Developer",
            "company": "Databricks",
            "location": "Remote",
            "requisition_id": "REQ-2026-9042",
            "url": "https://databricks.com/company/careers/openings/req-9042",
            "source": "company_site",
        })

        result = self.detector.compare(job_aggregator, job_official)
        assert result.is_duplicate is True
        assert result.match_reason == DuplicateMatchReason.REQUISITION_ID
        assert result.confidence_score == 1.0

        merged_list = self.engine.deduplicate([job_aggregator, job_official])
        assert len(merged_list) == 1
        assert merged_list[0].requisition_id == "REQ-2026-9042"

    def test_case_4_same_title_but_different_locations(self):
        """Case 4: Same job title at the same company but in distinct non-remote locations (MUST NOT MERGE)."""
        job_ny = self.normalizer.normalize({
            "title": "Software Engineer",
            "company": "Google",
            "location": "New York, NY",
            "url": "https://careers.google.com/jobs/results/111",
            "source": "google_careers",
        })

        job_london = self.normalizer.normalize({
            "title": "Software Engineer",
            "company": "Google",
            "location": "London, UK",
            "url": "https://careers.google.com/jobs/results/222",
            "source": "google_careers",
        })

        result = self.detector.compare(job_ny, job_london)
        assert result.is_duplicate is False
        assert "location conflict" in (result.rejection_reason or "").lower()

        merged_list = self.engine.deduplicate([job_ny, job_london])
        assert len(merged_list) == 2  # Correctly kept separate!

    def test_case_5_different_jobs_with_similar_titles(self):
        """Case 5: Similar titles representing different seniority or specialization tracks (MUST NOT MERGE)."""
        # Seniority difference: Junior vs Senior
        junior_job = self.normalizer.normalize({
            "title": "Junior Backend Engineer",
            "company": "Uber",
            "location": "San Francisco, CA",
            "url": "https://uber.com/careers/junior-backend",
            "source": "uber_careers",
        })

        senior_job = self.normalizer.normalize({
            "title": "Senior Backend Engineer",
            "company": "Uber",
            "location": "San Francisco, CA",
            "url": "https://uber.com/careers/senior-backend",
            "source": "uber_careers",
        })

        result_seniority = self.detector.compare(junior_job, senior_job)
        assert result_seniority.is_duplicate is False
        assert "seniority tier mismatch" in (result_seniority.rejection_reason or "").lower()

        # Specialization difference: Frontend vs Backend
        frontend_job = self.normalizer.normalize({
            "title": "Junior Frontend Engineer",
            "company": "Uber",
            "location": "San Francisco, CA",
            "url": "https://uber.com/careers/junior-frontend",
            "source": "uber_careers",
        })

        result_spec = self.detector.compare(junior_job, frontend_job)
        assert result_spec.is_duplicate is False
        assert "specialization mismatch" in (result_spec.rejection_reason or "").lower()

        merged_list = self.engine.deduplicate([junior_job, senior_job, frontend_job])
        assert len(merged_list) == 3  # All 3 correctly kept separate!

    def test_case_6_missing_job_id(self):
        """Case 6: Missing external job ID from both sources; successfully deduplicated via composite signals."""
        job_1 = self.normalizer.normalize({
            "title": "Associate Platform Engineer",
            "company": "Snowflake Inc.",
            "location": "Remote",
            "job_id": None,
            "url": "https://snowflake.com/jobs/platform-eng",
            "source": "source_a",
        })

        job_2 = self.normalizer.normalize({
            "title": "Associate Platform Engineer",
            "company": "Snowflake",
            "location": "Remote",
            "job_id": None,
            "url": "https://snowflake.com/jobs/platform-eng?ref=jobboard",
            "source": "source_b",
        })

        result = self.detector.compare(job_1, job_2)
        assert result.is_duplicate is True
        assert result.confidence_score >= 0.95

        merged_list = self.engine.deduplicate([job_1, job_2])
        assert len(merged_list) == 1
        assert merged_list[0].duplicate_count == 2

    def test_case_7_missing_application_url(self):
        """Case 7: One source provides an application URL, the other does not; successfully merged with app URL retained."""
        job_without_app_url = self.normalizer.normalize({
            "title": "Junior DevOps Engineer",
            "company": "Cloudflare",
            "location": "Austin, TX",
            "url": "https://cloudflare.com/careers/devops",
            "application_url": None,
            "source": "feed_one",
        })

        job_with_app_url = self.normalizer.normalize({
            "title": "Junior DevOps Engineer",
            "company": "Cloudflare",
            "location": "Austin, TX",
            "url": "https://cloudflare.com/careers/devops?ref=partner",
            "application_url": "https://boards.greenhouse.io/cloudflare/apply/555",
            "source": "feed_two",
        })

        result = self.detector.compare(job_without_app_url, job_with_app_url)
        assert result.is_duplicate is True

        merged_list = self.engine.deduplicate([job_without_app_url, job_with_app_url])
        assert len(merged_list) == 1
        assert merged_list[0].application_url == "https://boards.greenhouse.io/cloudflare/apply/555"
        assert set(merged_list[0].sources) == {"feed_one", "feed_two"}
