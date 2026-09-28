"""Job discovery architecture package."""

from backend.discovery.adapters.arbeitnow import ArbeitnowAdapter
from backend.discovery.adapters.mock_source import MockJobSourceAdapter
from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import (
    RawJobPosting,
    SearchQuery,
    SourceHealthCheck,
    SourcePolicy,
    SourceType,
)
from backend.discovery.normalizer import (
    NormalizedJob,
    clean_tracking_params,
    normalize_job_posting,
)
from backend.discovery.policy import SOURCE_POLICIES, get_source_policy
from backend.discovery.query_engine import SearchQueryEngine
from backend.discovery.registry import DiscoveryExecutionSummary, JobDiscoveryCollector

__all__ = [
    "ArbeitnowAdapter",
    "DiscoveryExecutionSummary",
    "JobDiscoveryCollector",
    "JobSourceAdapter",
    "MockJobSourceAdapter",
    "NormalizedJob",
    "RawJobPosting",
    "SOURCE_POLICIES",
    "SearchQuery",
    "SearchQueryEngine",
    "SourceHealthCheck",
    "SourcePolicy",
    "SourceType",
    "clean_tracking_params",
    "get_source_policy",
    "normalize_job_posting",
]
