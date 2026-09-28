import httpx
from backend.core.resilience import with_retry
from backend.sources.base import SourceAdapter, NormalizedJob

URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource(SourceAdapter):
    name, policy = "arbeitnow", "public_api"

    @with_retry(3)
    async def _get(self) -> dict:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(URL)
            r.raise_for_status()
            return r.json()

    async def discover(self, query: str) -> list[NormalizedJob]:
        data = await self._get()
        terms = [t.lower() for t in query.split() if t]
        out = []
        for j in data.get("data", []):
            hay = f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags',[]))}".lower()
            if terms and not all(t in hay for t in terms):
                continue
            out.append(NormalizedJob(
                source=self.name, source_job_id=j.get("slug"), title=j.get("title", ""),
                company=j.get("company_name", ""), location=j.get("location"),
                work_mode="remote" if j.get("remote") else None,
                description=j.get("description"), job_url=j.get("url"), skills=j.get("tags", [])))
        return out

    async def health_check(self) -> bool:
        try:
            await self._get()
            return True
        except Exception:
            return False
