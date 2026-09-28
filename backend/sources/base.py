from abc import ABC, abstractmethod
from pydantic import BaseModel
from backend.core.resilience import CircuitBreaker


class NormalizedJob(BaseModel):
    source: str
    source_job_id: str | None = None
    title: str
    company: str
    location: str | None = None
    work_mode: str | None = None
    description: str | None = None
    job_url: str | None = None
    application_url: str | None = None
    skills: list[str] = []
    posted_at: str | None = None


class SourceAdapter(ABC):
    name: str
    policy: str  # e.g. "public_api"
    enabled: bool = True

    def __init__(self):
        self.breaker = CircuitBreaker()

    @abstractmethod
    async def discover(self, query: str) -> list[NormalizedJob]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
