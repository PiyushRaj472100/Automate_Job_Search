import httpx
from backend.core.resilience import with_retry
from backend.sources.base import SourceAdapter, NormalizedJob

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(SourceAdapter):
    name, policy = "remotive", "public_api"

    @with_retry(3)
    async def _get(self, search: str = "") -> dict:
        params = {"limit": 50}
        if search:
            params["search"] = search
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(REMOTIVE_URL, params=params)
            r.raise_for_status()
            return r.json()

    async def discover(self, query: str) -> list[NormalizedJob]:
        data = await self._get(search=query)
        out = []
        for j in data.get("jobs", []):
            out.append(NormalizedJob(
                source=self.name,
                source_job_id=str(j.get("id")),
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("candidate_required_location", "Remote"),
                work_mode="remote",
                description=j.get("description"),
                job_url=j.get("url"),
                skills=j.get("tags", [])
            ))
        return out

    async def health_check(self) -> bool:
        try:
            await self._get()
            return True
        except Exception:
            return False
