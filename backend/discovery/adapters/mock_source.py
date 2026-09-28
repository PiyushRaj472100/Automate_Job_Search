"""Deterministic mock job source adapter for hermetic testing and development."""

from datetime import UTC, datetime
from typing import Any

from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import (
    RawJobPosting,
    SearchQuery,
    SourceHealthCheck,
    SourcePolicy,
    SourceType,
)

# Deterministic fixture dataset clearly separated from live data
MOCK_FIXTURE_POSTINGS: list[dict[str, Any]] = [
    {
        "id": "mock-job-001",
        "title": "Junior Python Developer",
        "company": "Nexus AI Labs",
        "location": "Remote",
        "work_mode": "remote",
        "description": "Looking for a fresher / entry-level Python developer with FastAPI, PostgreSQL, and Docker experience.",
        "url": "https://careers.nexusailabs.com/jobs/mock-job-001?utm_source=mock_campaign",
        "app_url": "https://careers.nexusailabs.com/apply/mock-job-001",
        "tags": ["Python", "FastAPI", "PostgreSQL", "Entry Level"],
        "requisition_id": "REQ-2026-01",
    },
    {
        "id": "mock-job-002",
        "title": "Associate Software Engineer",
        "company": "CloudMatrix Systems LLC",
        "location": "Bengaluru, India",
        "work_mode": "hybrid",
        "description": "Graduate / 0-2 years experience required. Backend development in Python or Java with RESTful APIs.",
        "url": "https://jobs.cloudmatrix.com/openings/mock-002?ref=indeed",
        "app_url": "https://jobs.cloudmatrix.com/apply/mock-002",
        "tags": ["Backend", "Python", "Docker", "REST"],
        "requisition_id": "REQ-2026-02",
    },
    {
        "id": "mock-job-003",
        "title": "Junior Backend Engineer",
        "company": "Fintech Stream Inc.",
        "location": "Remote",
        "work_mode": "remote",
        "description": "Entry-level position for passionate engineers skilled in Python, SQL databases, and modern CI/CD.",
        "url": "https://fintechstream.io/careers/mock-003",
        "app_url": "https://fintechstream.io/apply/mock-003",
        "tags": ["Python", "SQL", "CI/CD", "Remote"],
        "requisition_id": "REQ-2026-03",
    },
    {
        "id": "mock-job-004",
        "title": "Junior AI/ML Engineer",
        "company": "Cortex Intelligence",
        "location": "San Francisco, CA",
        "work_mode": "on_site",
        "description": "0-1 years experience or master graduate with PyTorch, NLP, and LLM prompt engineering skills.",
        "url": "https://cortex.ai/jobs/mock-004",
        "app_url": "https://cortex.ai/apply/mock-004",
        "tags": ["AI/ML", "Python", "PyTorch"],
        "requisition_id": "REQ-2026-04",
    },
]


class MockJobSourceAdapter(JobSourceAdapter):
    """Hermetic test adapter returning deterministic mock jobs with fault simulation capabilities."""

    def __init__(
        self,
        should_fail_search: bool = False,
        should_fail_health: bool = False,
        failure_exception: Exception | None = None,
        custom_fixtures: list[dict[str, Any]] | None = None,
    ) -> None:
        policy = SourcePolicy(
            source_name="mock_source",
            source_type=SourceType.PUBLIC_FEED,
            base_url="https://mock.internal.test",
            official_api_available=True,
            feed_available=True,
            public_page_available=True,
            robots_restrictions="Mock source for hermetic testing only",
            rate_limit_per_minute=1000,
            authentication_required=False,
            permitted_access_method="In-memory Mock Fixtures",
            notes="Separated test fixture data - never routes to production networks.",
        )
        super().__init__(policy=policy)
        self.should_fail_search = should_fail_search
        self.should_fail_health = should_fail_health
        self.failure_exception = failure_exception or RuntimeError("Simulated upstream network timeout")
        self.fixtures = custom_fixtures if custom_fixtures is not None else MOCK_FIXTURE_POSTINGS

    def health_check(self) -> SourceHealthCheck:
        """Simulate health check probe."""
        if self.should_fail_health:
            return SourceHealthCheck(
                source_name=self.name,
                is_healthy=False,
                status_code=503,
                response_time_ms=50.0,
                details="Mock upstream server unavailable (simulated 503)",
            )
        return SourceHealthCheck(
            source_name=self.name,
            is_healthy=True,
            status_code=200,
            response_time_ms=1.5,
            details="Mock source healthy (in-memory fixtures active)",
        )

    def search(self, query: SearchQuery) -> list[RawJobPosting]:
        """Search mock fixture jobs matching keywords or query text."""
        self._enforce_rate_limit()

        if self.should_fail_search:
            raise self.failure_exception

        results: list[RawJobPosting] = []
        tokens = set(query.query_text.lower().split())
        if query.skills:
            tokens.update(s.lower() for s in query.skills)

        for fix in self.fixtures:
            item_text = f"{fix['title']} {fix['company']} {fix['description']} {' '.join(fix.get('tags', []))}".lower()

            # Match if any token is present or if query is generic
            matches = any(token in item_text for token in tokens) or len(tokens) == 0

            # Filter location if requested
            if query.location and query.location.lower() not in fix["location"].lower() and fix["location"] != "Remote":
                matches = False

            # Filter work mode if requested
            if query.work_mode and query.work_mode != fix["work_mode"]:
                matches = False

            if matches:
                results.append(
                    RawJobPosting(
                        source_name=self.name,
                        external_job_id=fix["id"],
                        requisition_id=fix.get("requisition_id"),
                        title=fix["title"],
                        company_name=fix["company"],
                        location=fix["location"],
                        work_mode=fix["work_mode"],
                        description=fix["description"],
                        job_url=fix["url"],
                        application_url=fix.get("app_url"),
                        posting_date=datetime.now(UTC),
                        tags=fix.get("tags", []),
                        raw_payload=fix,
                    )
                )

        return results[: query.limit]

    def fetch_job(self, job_id_or_url: str) -> RawJobPosting | None:
        """Fetch mock job by ID or URL."""
        for fix in self.fixtures:
            if fix["id"] == job_id_or_url or fix["url"] == job_id_or_url:
                return RawJobPosting(
                    source_name=self.name,
                    external_job_id=fix["id"],
                    requisition_id=fix.get("requisition_id"),
                    title=fix["title"],
                    company_name=fix["company"],
                    location=fix["location"],
                    work_mode=fix["work_mode"],
                    description=fix["description"],
                    job_url=fix["url"],
                    application_url=fix.get("app_url"),
                    posting_date=datetime.now(UTC),
                    tags=fix.get("tags", []),
                    raw_payload=fix,
                )
        return None
