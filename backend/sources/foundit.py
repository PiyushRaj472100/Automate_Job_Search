"""
Foundit (formerly Monster India) source adapter.
Scrapes the public Foundit.in search API for fresher AI/ML/Python jobs.
"""
import asyncio
import logging
import httpx
from backend.sources.base import SourceAdapter, NormalizedJob
from backend.core.resilience import with_retry

log = logging.getLogger("foundit")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.foundit.in/",
}

FOUNDIT_SEARCH = "https://www.foundit.in/middleware/jobsearch/search"

QUERIES = [
    "python fresher",
    "machine learning fresher",
    "ai engineer fresher",
    "data science fresher",
    "python intern",
]


class FounditSource(SourceAdapter):
    """Foundit.in (formerly Monster India) public search."""
    name, policy = "foundit", "public_api"

    @with_retry(2)
    async def _search(self, client: httpx.AsyncClient, keyword: str) -> list[NormalizedJob]:
        params = {
            "query": keyword,
            "location": "Bengaluru",
            "experience": "0",
            "freshness": "7",
            "limit": 20,
        }
        try:
            r = await client.get(FOUNDIT_SEARCH, params=params, timeout=12)
            if r.status_code != 200:
                return []
            data = r.json()
            jobs_raw = data.get("jobSearchResponse", {}).get("data", [])
            if not jobs_raw:
                jobs_raw = data.get("data", []) or data.get("jobs", [])
            out = []
            for j in jobs_raw:
                title = (j.get("jobTitle") or j.get("title") or "").strip()
                company = (j.get("company") or j.get("companyName") or "Company").strip()
                jd = (j.get("jobDescription") or j.get("description") or "").strip()
                jid = j.get("jobId") or j.get("id") or ""
                job_url = j.get("jobUrl") or (f"https://www.foundit.in/job/{jid}" if jid else "")
                loc = j.get("location") or "Bengaluru, India"
                if not title or not job_url:
                    continue
                jd_short = jd[:500] + ("..." if len(jd) > 500 else "")
                out.append(NormalizedJob(
                    source="foundit",
                    source_job_id=str(jid or job_url),
                    title=title, company=company, location=str(loc),
                    work_mode="Office / Hybrid",
                    description=jd_short or f"Entry-level {title} role at {company} on Foundit.in",
                    job_url=job_url,
                    skills=["Python"],
                    posted_at="Recent (Foundit)",
                ))
            return out
        except Exception as e:
            log.warning("Foundit search failed for '%s': %s", keyword, e)
            return []

    async def discover(self, query: str) -> list[NormalizedJob]:
        seen: set[str] = set()
        all_jobs: list[NormalizedJob] = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            results = await asyncio.gather(*[self._search(client, kw) for kw in QUERIES], return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    for j in res:
                        if j.job_url and j.job_url not in seen:
                            seen.add(j.job_url)
                            all_jobs.append(j)
        log.info("Foundit returned %d jobs", len(all_jobs))
        return all_jobs

    async def health_check(self) -> bool:
        return True
