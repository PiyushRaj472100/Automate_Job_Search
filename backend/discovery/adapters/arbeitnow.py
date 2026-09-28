"""Arbeitnow job board official API adapter."""

import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import RawJobPosting, SearchQuery, SourceHealthCheck
from backend.discovery.policy import get_source_policy

logger = logging.getLogger("job_intelligence.discovery.adapters.arbeitnow")


class ArbeitnowAdapter(JobSourceAdapter):
    """Adapter for Arbeitnow official public technical job board API.

    API Documentation / Endpoint: https://www.arbeitnow.com/api/job-board-api
    Policy: Authorized REST API, free, no authentication required, 30 req/min.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        policy = get_source_policy("arbeitnow")
        super().__init__(policy=policy)
        self.timeout = timeout

    def health_check(self) -> SourceHealthCheck:
        """Perform a liveness and latency probe against the Arbeitnow API."""
        start_time = time.perf_counter()
        try:
            self._enforce_rate_limit()
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    self.policy.base_url,
                    params={"page": 1},
                    headers={"User-Agent": "JobIntelligencePlatform/1.0 (Compliance Probe)"},
                )
            latency = (time.perf_counter() - start_time) * 1000.0

            if response.status_code == 200:
                return SourceHealthCheck(
                    source_name=self.name,
                    is_healthy=True,
                    status_code=response.status_code,
                    response_time_ms=round(latency, 2),
                    details="Arbeitnow API operational and responding",
                )
            return SourceHealthCheck(
                source_name=self.name,
                is_healthy=False,
                status_code=response.status_code,
                response_time_ms=round(latency, 2),
                details=f"Unexpected status code: {response.status_code}",
            )
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000.0
            logger.warning("Arbeitnow health check probe failed: %s", e)
            return SourceHealthCheck(
                source_name=self.name,
                is_healthy=False,
                status_code=None,
                response_time_ms=round(latency, 2),
                details=f"Connection failure: {e}",
            )

    def search(self, query: SearchQuery) -> list[RawJobPosting]:
        """Search Arbeitnow job postings matching the search query parameters."""
        self._enforce_rate_limit()
        postings: list[RawJobPosting] = []

        # Construct search query string (preferring role or primary skill)
        search_term = query.query_text
        if query.skills:
            search_term = f"{query.role_title} {query.skills[0]}"

        params: dict[str, Any] = {"search": search_term}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    self.policy.base_url,
                    params=params,
                    headers={"User-Agent": "JobIntelligencePlatform/1.0 (Job Discovery Engine)"},
                )

            if response.status_code != 200:
                logger.warning(
                    "Arbeitnow search query '%s' failed with status %d",
                    search_term,
                    response.status_code,
                )
                return []

            data = response.json()
            items = data.get("data", [])
            for item in items[: query.limit]:
                posting = self._map_to_raw_posting(item)
                if posting:
                    postings.append(posting)

            logger.info("Arbeitnow found %d jobs for query '%s'", len(postings), search_term)
            return postings

        except Exception as e:
            logger.error("Arbeitnow search exception for query '%s': %s", search_term, e)
            # Crucial requirement: failure in this source must not crash the whole discovery pipeline
            return []

    def fetch_job(self, job_id_or_url: str) -> RawJobPosting | None:
        """Fetch a specific job posting from Arbeitnow by slug or URL."""
        # Arbeitnow slug lookup via API search
        slug = job_id_or_url.split("/")[-1] if "/" in job_id_or_url else job_id_or_url
        query = SearchQuery(
            query_text=slug,
            role_title=slug,
            limit=5,
        )
        results = self.search(query)
        for job in results:
            if job.external_job_id == slug or slug in job.job_url:
                return job
        return results[0] if results else None

    def _map_to_raw_posting(self, item: dict[str, Any]) -> RawJobPosting | None:
        """Map Arbeitnow API response item to RawJobPosting."""
        title = item.get("title")
        company = item.get("company_name")
        url = item.get("url")

        if not title or not company or not url:
            return None

        # Determine work mode
        is_remote = item.get("remote", False)
        work_mode = "remote" if is_remote else "unknown"

        # Parse publication timestamp
        created_at_val = item.get("created_at")
        posting_date = None
        if isinstance(created_at_val, int | float):
            posting_date = datetime.fromtimestamp(created_at_val, tz=UTC)

        slug = item.get("slug") or url.rstrip("/").split("/")[-1]

        return RawJobPosting(
            source_name=self.name,
            external_job_id=slug,
            requisition_id=None,
            title=title.strip(),
            company_name=company.strip(),
            location=item.get("location") or ("Remote" if is_remote else "Unknown"),
            work_mode=work_mode,
            description=item.get("description") or title,
            job_url=url.strip(),
            application_url=url.strip(),  # Arbeitnow application direct link is the job url
            posting_date=posting_date,
            tags=item.get("tags") or [],
            raw_payload=item,
        )
