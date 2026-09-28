import httpx
from backend.core.resilience import with_retry
from backend.sources.base import SourceAdapter, NormalizedJob

JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"


class JobicySource(SourceAdapter):
    name, policy = "jobicy", "public_api"

    @with_retry(2)
    async def _get(self, tag: str = "") -> dict:
        params = {"count": 50}
        if tag and tag in ["python", "dev", "data", "engineering", "backend"]:
            params["tag"] = tag
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(JOBICY_URL, params=params)
            if r.status_code != 200:
                r = await c.get(JOBICY_URL, params={"count": 50})
            r.raise_for_status()
            return r.json()

    async def discover(self, query: str) -> list[NormalizedJob]:
        first_term = query.split()[0].lower() if query.split() else ""
        data = await self._get(tag=first_term)
        terms = [t.lower() for t in query.split() if t]
        out = []
        for j in data.get("jobs", []):
            hay = f"{j.get('jobTitle','')} {j.get('jobDescription','')} {j.get('jobExcerpt','')} {j.get('companyName','')}".lower()
            if terms and not any(t in hay for t in terms):
                continue
            out.append(NormalizedJob(
                source=self.name,
                source_job_id=str(j.get("id")),
                title=j.get("jobTitle", ""),
                company=j.get("companyName", ""),
                location=j.get("jobGeo", "Remote"),
                work_mode="remote",
                description=j.get("jobExcerpt") or j.get("jobDescription"),
                skills=[str(s) for s in (j.get("jobIndustry") if isinstance(j.get("jobIndustry"), list) else [j.get("jobIndustry")]) if s]
            ))
        return out

    async def health_check(self) -> bool:
        try:
            await self._get()
            return True
        except Exception:
            return False
