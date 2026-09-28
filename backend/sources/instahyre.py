import asyncio
import httpx
import logging
from backend.core.resilience import with_retry
from backend.sources.base import SourceAdapter, NormalizedJob

log = logging.getLogger("instahyre")

INSTAHYRE_API = "https://www.instahyre.com/api/v1/job_search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


class InstahyreSource(SourceAdapter):
    name, policy = "instahyre", "public_api"

    @with_retry(2)
    async def _fetch_skills(self, skill: str, location: str = "Bangalore") -> list[NormalizedJob]:
        params = {
            "skills": skill,
            "location": location,
        }
        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            r = await client.get(INSTAHYRE_API, params=params)
            if r.status_code != 200:
                log.warning("Instahyre returned status %d for skill %s", r.status_code, skill)
                return []

            data = r.json()
            objects = data.get("objects", [])
            jobs = []

            for obj in objects:
                title = obj.get("title") or ""
                emp = obj.get("employer", {})
                company = emp.get("company_name") or "Tech Company"
                public_url = obj.get("public_url")
                if not public_url:
                    job_id = obj.get("id")
                    public_url = f"https://www.instahyre.com/job-{job_id}/" if job_id else ""

                if not title or not public_url:
                    continue

                locs = obj.get("locations") or location
                keywords = obj.get("keywords") or []

                jobs.append(NormalizedJob(
                    source="instahyre",
                    source_job_id=str(obj.get("id", public_url)),
                    title=title,
                    company=company,
                    location=locs,
                    work_mode="Bangalore / Hybrid / Office",
                    description=f"{title} at {company} in {locs}. Skills: {', '.join(keywords[:5])}.",
                    job_url=public_url,
                    skills=keywords,
                    posted_at="Recent (Instahyre)",
                ))

            return jobs

    async def discover(self, query: str) -> list[NormalizedJob]:
        # Target AI, ML, Python, Data Science concurrently
        target_skills = ["python", "machine-learning", "artificial-intelligence", "data-science"]
        tasks = [self._fetch_skills(sk, location="Bangalore") for sk in target_skills]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_jobs = []
        for r in results:
            if isinstance(r, list):
                all_jobs.extend(r)
        return all_jobs

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=8) as c:
                r = await c.get(INSTAHYRE_API, params={"skills": "python", "location": "Bangalore"})
                return r.status_code == 200
        except Exception:
            return False
