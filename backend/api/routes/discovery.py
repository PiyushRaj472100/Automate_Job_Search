"""FastAPI routes for Job Discovery, Source Policies, Health Checks, and Query Generation."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.discovery.adapters.arbeitnow import ArbeitnowAdapter
from backend.discovery.adapters.greenhouse import GreenhouseAdapter
from backend.discovery.adapters.lever import LeverAdapter
from backend.discovery.models import SearchQuery, SourceHealthCheck, SourcePolicy
from backend.discovery.normalizer import NormalizedJob
from backend.discovery.policy import SOURCE_POLICIES
from backend.discovery.query_engine import SearchQueryEngine
from backend.discovery.registry import DiscoveryExecutionSummary, JobDiscoveryCollector

router = APIRouter(prefix="/discovery", tags=["Job Discovery"])

# Instantiate the standard discovery collector with live providers and career page ATS adapters
collector = JobDiscoveryCollector([ArbeitnowAdapter(), GreenhouseAdapter(), LeverAdapter()])
query_engine = SearchQueryEngine()


class QueryGenerationRequest(BaseModel):
    """Input payload for generating multi-strategy search queries."""

    target_roles: list[str] = Field(default_factory=list, description="Target job titles (e.g. Backend Engineer)")
    skills: list[str] = Field(default_factory=list, description="Technical skills (e.g. Python, FastAPI)")
    locations: list[str] = Field(default_factory=list, description="Preferred locations (e.g. Remote, Bengaluru)")
    work_modes: list[str] = Field(default_factory=lambda: ["remote"], description="Work modes: remote, hybrid, on_site")
    max_queries: int = Field(default=8, ge=1, le=20)


class SearchDiscoveryRequest(BaseModel):
    """Input payload to trigger job discovery across registered sources."""

    queries: list[SearchQuery] = Field(..., description="List of search queries to execute")
    sources: list[str] | None = Field(default=None, description="Optional subset of sources (defaults to all)")


class SearchDiscoveryResponse(BaseModel):
    """Discovered and normalized jobs with telemetry."""

    summary: DiscoveryExecutionSummary
    jobs: list[NormalizedJob]


@router.get("/sources", response_model=dict[str, SourcePolicy])
def list_sources() -> dict[str, SourcePolicy]:
    """List all supported job source categories and their compliance/access policies."""
    return SOURCE_POLICIES


@router.get("/health", response_model=dict[str, SourceHealthCheck])
def check_sources_health() -> dict[str, SourceHealthCheck]:
    """Probe connectivity and health status across all active job source adapters."""
    return collector.health_check_all()


@router.post("/generate-queries", response_model=list[SearchQuery])
def generate_queries(payload: QueryGenerationRequest) -> list[SearchQuery]:
    """Generate multiple diversified search queries based on candidate profile inputs."""
    engine = SearchQueryEngine(max_queries=payload.max_queries)
    return engine.generate_queries({
        "target_roles": payload.target_roles,
        "skills": payload.skills,
        "locations": payload.locations,
        "work_modes": payload.work_modes,
    })


@router.post("/search", response_model=SearchDiscoveryResponse)
def execute_discovery(payload: SearchDiscoveryRequest) -> SearchDiscoveryResponse:
    """Execute job discovery across adapters with full fault isolation and deduplication."""
    if not payload.queries:
        raise HTTPException(status_code=400, detail="At least one SearchQuery is required")

    jobs, summary = collector.discover_jobs(
        queries=payload.queries,
        sources=payload.sources,
    )
    return SearchDiscoveryResponse(summary=summary, jobs=jobs)
