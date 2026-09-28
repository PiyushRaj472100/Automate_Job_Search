"""Abstract base class for all job source adapters."""

import logging
import time
from abc import ABC, abstractmethod

from backend.discovery.models import RawJobPosting, SearchQuery, SourceHealthCheck, SourcePolicy

logger = logging.getLogger("job_intelligence.discovery.adapter")


class JobSourceAdapter(ABC):
    """Abstract common interface for modular job source integrations.

    Every source adapter must independently implement search, fetch_job,
    and health_check operations.
    """

    def __init__(self, policy: SourcePolicy) -> None:
        self.policy = policy
        self._last_request_time: float = 0.0

    @property
    def name(self) -> str:
        """Return the unique name identifier of the source."""
        return self.policy.source_name

    def _enforce_rate_limit(self) -> None:
        """Throttle requests to respect the source's rate limits."""
        if self.policy.rate_limit_per_minute <= 0:
            return

        interval = 60.0 / self.policy.rate_limit_per_minute
        elapsed = time.time() - self._last_request_time
        if elapsed < interval:
            sleep_duration = interval - elapsed
            time.sleep(sleep_duration)
        self._last_request_time = time.time()

    @abstractmethod
    def search(self, query: SearchQuery) -> list[RawJobPosting]:
        """Search the source for job postings matching the query.

        Args:
            query: Normalized SearchQuery object

        Returns:
            List of RawJobPosting instances
        """
        pass

    @abstractmethod
    def fetch_job(self, job_id_or_url: str) -> RawJobPosting | None:
        """Retrieve a specific job posting by its external ID or URL.

        Args:
            job_id_or_url: Source job ID or direct canonical URL

        Returns:
            RawJobPosting if found, otherwise None
        """
        pass

    @abstractmethod
    def health_check(self) -> SourceHealthCheck:
        """Perform a connectivity and health probe against the source.

        Returns:
            SourceHealthCheck reporting status, latency, and diagnostics
        """
        pass
