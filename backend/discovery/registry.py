"""Central Job Discovery Collector and multi-adapter orchestrator."""

import logging

from pydantic import BaseModel, Field

from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import RawJobPosting, SearchQuery, SourceHealthCheck
from backend.discovery.normalizer import NormalizedJob, normalize_job_posting

logger = logging.getLogger("job_intelligence.discovery.registry")


class DiscoveryExecutionSummary(BaseModel):
    """Execution telemetry and metrics for a discovery run across multiple adapters."""

    total_queries: int = 0
    total_raw_found: int = 0
    total_normalized: int = 0
    total_deduplicated: int = 0
    successful_sources: list[str] = Field(default_factory=list)
    failed_sources: dict[str, str] = Field(default_factory=dict)


class JobDiscoveryCollector:
    """Multi-source orchestrator with fault-isolation and output normalization.

    Guarantees that individual adapter failures, rate limits, or network timeouts
    do not interrupt or compromise the overall discovery pipeline.
    """

    def __init__(self, adapters: list[JobSourceAdapter] | None = None) -> None:
        self._adapters: dict[str, JobSourceAdapter] = {}
        if adapters:
            for adapter in adapters:
                self.register(adapter)

    def register(self, adapter: JobSourceAdapter) -> None:
        """Register a job source adapter."""
        self._adapters[adapter.name.lower()] = adapter
        logger.info("Registered job source adapter: %s (%s)", adapter.name, adapter.policy.source_type.value)

    def get_adapter(self, source_name: str) -> JobSourceAdapter | None:
        """Retrieve an adapter by its name."""
        return self._adapters.get(source_name.lower())

    def list_sources(self) -> list[str]:
        """Return list of registered source names."""
        return list(self._adapters.keys())

    def health_check_all(self) -> dict[str, SourceHealthCheck]:
        """Probe all registered adapters and aggregate health diagnostic statuses."""
        results: dict[str, SourceHealthCheck] = {}
        for name, adapter in self._adapters.items():
            try:
                check = adapter.health_check()
                results[name] = check
            except Exception as e:
                logger.error("Adapter '%s' unhandled health check error: %s", name, e)
                results[name] = SourceHealthCheck(
                    source_name=name,
                    is_healthy=False,
                    status_code=None,
                    details=f"Unhandled health check error: {e}",
                )
        return results

    def discover_jobs(
        self,
        queries: list[SearchQuery],
        sources: list[str] | None = None,
    ) -> tuple[list[NormalizedJob], DiscoveryExecutionSummary]:
        """Execute search across registered sources with strict fault isolation and deduplication.

        Args:
            queries: List of SearchQuery objects to run.
            sources: Optional subset of source names to query. If None, all registered are queried.

        Returns:
            Tuple of (list of unique NormalizedJob instances, DiscoveryExecutionSummary)
        """
        summary = DiscoveryExecutionSummary(total_queries=len(queries))
        target_sources = (
            [s.lower() for s in sources if s.lower() in self._adapters]
            if sources
            else list(self._adapters.keys())
        )

        all_raw_postings: list[RawJobPosting] = []

        for query in queries:
            for src_name in target_sources:
                adapter = self._adapters[src_name]
                try:
                    logger.debug("Executing query '%s' against adapter '%s'", query.query_text, src_name)
                    postings = adapter.search(query)
                    all_raw_postings.extend(postings)
                    if src_name not in summary.successful_sources:
                        summary.successful_sources.append(src_name)
                except Exception as e:
                    # Fault Isolation: One source failure must never halt the discovery pipeline
                    err_msg = str(e)
                    logger.error(
                        "Source '%s' failed on query '%s': %s",
                        src_name,
                        query.query_text,
                        err_msg,
                        exc_info=False,
                    )
                    summary.failed_sources[src_name] = err_msg

        summary.total_raw_found = len(all_raw_postings)

        # Normalize and Deduplicate postings
        normalized_jobs: list[NormalizedJob] = []
        seen_dedup_hashes: set[str] = set()

        for raw in all_raw_postings:
            try:
                norm = normalize_job_posting(raw)
                if norm.dedup_hash not in seen_dedup_hashes:
                    seen_dedup_hashes.add(norm.dedup_hash)
                    normalized_jobs.append(norm)
            except Exception as e:
                logger.warning("Error normalizing raw posting from '%s': %s", raw.source_name, e)

        summary.total_normalized = len(all_raw_postings)
        summary.total_deduplicated = len(normalized_jobs)

        logger.info(
            "Discovery run completed: %d raw jobs -> %d unique normalized jobs across %d sources (Failures: %d)",
            summary.total_raw_found,
            summary.total_deduplicated,
            len(summary.successful_sources),
            len(summary.failed_sources),
        )

        return normalized_jobs, summary
