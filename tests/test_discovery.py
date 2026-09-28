"""Unit and integration tests for Job Source Architecture & Discovery Framework."""

import pytest
from fastapi.testclient import TestClient

from backend.discovery.adapters.mock_source import MockJobSourceAdapter
from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import RawJobPosting, SearchQuery, SourcePolicy, SourceType
from backend.discovery.normalizer import (
    clean_tracking_params,
    infer_work_mode,
    normalize_company,
    normalize_job_posting,
    normalize_location,
    normalize_title,
)
from backend.discovery.policy import get_source_policy
from backend.discovery.query_engine import SearchQueryEngine
from backend.discovery.registry import JobDiscoveryCollector
from backend.main import create_application


class TestJobSourceAdapterInterface:
    """Verifies that the common JobSourceAdapter interface is enforced."""

    def test_cannot_instantiate_abstract_adapter(self):
        policy = SourcePolicy(
            source_name="incomplete",
            source_type=SourceType.PUBLIC_PAGE,
            base_url="https://example.com",
        )
        with pytest.raises(TypeError):
            JobSourceAdapter(policy=policy)  # type: ignore

    def test_mock_adapter_implements_interface(self):
        adapter = MockJobSourceAdapter()
        assert adapter.name == "mock_source"
        assert adapter.policy.source_name == "mock_source"

        health = adapter.health_check()
        assert health.is_healthy is True
        assert health.status_code == 200

        query = SearchQuery(
            query_text="Junior Python",
            role_title="Backend Engineer",
            skills=["Python"],
            experience_level="junior",
        )
        results = adapter.search(query)
        assert len(results) > 0
        assert isinstance(results[0], RawJobPosting)

        fetched = adapter.fetch_job(results[0].external_job_id)
        assert fetched is not None
        assert fetched.title == results[0].title


class TestSourceHealthChecks:
    """Verifies health check operations and status diagnostics."""

    def test_healthy_source_check(self):
        adapter = MockJobSourceAdapter(should_fail_health=False)
        check = adapter.health_check()
        assert check.is_healthy is True
        assert check.status_code == 200
        assert check.response_time_ms >= 0

    def test_unhealthy_source_check(self):
        adapter = MockJobSourceAdapter(should_fail_health=True)
        check = adapter.health_check()
        assert check.is_healthy is False
        assert check.status_code == 503
        assert "unavailable" in check.details.lower()

    def test_policy_lookup(self):
        arbeitnow_pol = get_source_policy("arbeitnow")
        assert arbeitnow_pol.official_api_available is True
        assert arbeitnow_pol.rate_limit_per_minute == 30

        linkedin_pol = get_source_policy("linkedin")
        assert linkedin_pol.authentication_required is True
        assert "anti-bot" in linkedin_pol.robots_restrictions.lower()


class TestSearchQueryEngine:
    """Verifies that the search query engine generates rich, diversified queries."""

    def test_generate_multiple_queries_from_profile(self):
        engine = SearchQueryEngine(max_queries=10)
        profile_data = {
            "target_roles": ["Backend Developer", "Software Engineer"],
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "locations": ["Bengaluru"],
            "work_modes": ["remote"],
        }
        queries = engine.generate_queries(profile_data)

        # Must generate multiple queries (not dependent on one)
        assert len(queries) >= 5

        query_texts = [q.query_text.lower() for q in queries]

        # Verify entry-level terms are included
        has_fresher = any("fresher" in t for t in query_texts)
        has_junior = any("junior" in t for t in query_texts)
        has_entry = any("entry level" in t for t in query_texts)
        assert has_fresher or has_junior or has_entry

        # Verify skills are leveraged
        assert any("python" in t for t in query_texts)

        # Verify remote is covered
        assert any("remote" in t for t in query_texts)

        # Verify role title is preserved
        assert all(q.role_title for q in queries)


class TestJobNormalizer:
    """Verifies job normalization, deduplication hashes, and URL sanitization."""

    def test_url_sanitization(self):
        dirty_url = "https://example.com/jobs/123/?utm_source=linkedin&utm_medium=cpc&ref=aggregator#apply"
        clean = clean_tracking_params(dirty_url)
        assert "utm_source" not in clean
        assert "utm_medium" not in clean
        assert "ref=" not in clean
        assert clean == "https://example.com/jobs/123"

    def test_normalization_rules(self):
        assert normalize_title("Jr. SWE - Backend") == "Junior Software Engineer - Backend"
        assert normalize_company("Acme Technologies Pvt. Ltd.") == "Acme Technologies"
        assert normalize_location("  wfh  ") == "Remote"
        assert infer_work_mode("unknown", "Software Engineer", "Remote", "Great team") == "remote"

    def test_normalize_raw_posting(self):
        raw = RawJobPosting(
            source_name="mock_source",
            external_job_id="test-001",
            requisition_id="REQ-42",
            title="Jr. Software Developer",
            company_name="Innovate Tech LLC",
            location="Remote",
            work_mode="remote",
            description="Entry level python developer needed.",
            job_url="https://innovate.tech/jobs/42?utm_campaign=winter",
            application_url="https://innovate.tech/apply/42",
            tags=["Python", "FastAPI"],
        )
        norm = normalize_job_posting(raw)

        assert norm.title == "Junior Software Developer"
        assert norm.company_name == "Innovate Tech LLC"
        assert norm.normalized_company == "Innovate Tech"
        assert norm.work_mode == "remote"
        assert norm.canonical_url == "https://innovate.tech/jobs/42"
        assert norm.dedup_hash is not None
        assert len(norm.dedup_hash) == 64  # SHA-256


class TestFaultIsolationAndCollector:
    """Verifies that one failing source NEVER stops or crashes the discovery pipeline."""

    def test_collector_survives_source_failure(self):
        # Setup one failing adapter and one healthy adapter
        failing_adapter = MockJobSourceAdapter(
            should_fail_search=True,
            failure_exception=ConnectionResetError("Simulated upstream network reset"),
        )
        # Give failing adapter a distinct name
        failing_adapter.policy.source_name = "failing_feed"

        healthy_adapter = MockJobSourceAdapter(should_fail_search=False)

        collector = JobDiscoveryCollector([failing_adapter, healthy_adapter])

        query = SearchQuery(
            query_text="Python",
            role_title="Backend Engineer",
            skills=["Python"],
        )

        # Discovery must succeed without raising an unhandled exception
        jobs, summary = collector.discover_jobs(queries=[query])

        # Verify summary reflects partial failure without halting
        assert "failing_feed" in summary.failed_sources
        assert "mock_source" in summary.successful_sources
        assert len(jobs) > 0
        assert summary.total_deduplicated == len(jobs)

    def test_collector_deduplicates_duplicate_postings(self):
        adapter = MockJobSourceAdapter()
        collector = JobDiscoveryCollector([adapter])

        # Run multiple overlapping queries
        q1 = SearchQuery(query_text="Python", role_title="Developer")
        q2 = SearchQuery(query_text="FastAPI", role_title="Developer")

        jobs, summary = collector.discover_jobs(queries=[q1, q2])

        # All jobs must have unique dedup_hashes
        hashes = [j.dedup_hash for j in jobs]
        assert len(hashes) == len(set(hashes))


class TestDiscoveryAPIEndpoints:
    """Verifies FastAPI endpoints for job discovery, source health, and query generation."""

    @pytest.fixture
    def client(self):
        app = create_application()
        return TestClient(app)

    def test_sources_endpoint(self, client):
        response = client.get("/api/v1/discovery/sources")
        assert response.status_code == 200
        data = response.json()
        assert "arbeitnow" in data
        assert "linkedin" in data
        assert data["arbeitnow"]["official_api_available"] is True

    def test_generate_queries_endpoint(self, client):
        payload = {
            "target_roles": ["Backend Developer"],
            "skills": ["Python", "FastAPI"],
            "locations": ["Remote"],
            "work_modes": ["remote"],
            "max_queries": 6,
        }
        response = client.post("/api/v1/discovery/generate-queries", json=payload)
        assert response.status_code == 200
        queries = response.json()
        assert len(queries) >= 3
        assert all("query_text" in q for q in queries)

    def test_search_endpoint_with_mock(self, client):
        payload = {
            "queries": [
                {
                    "query_text": "Junior Python",
                    "role_title": "Backend Developer",
                    "skills": ["Python"],
                    "experience_level": "junior",
                    "limit": 5,
                }
            ]
        }
        response = client.post("/api/v1/discovery/search", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "jobs" in data
