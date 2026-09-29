"""
Cutshort.io source adapter — tech / startup job platform with public search API.
Great for AI, ML, Python, backend roles at Indian startups.
"""
import asyncio
import logging
import httpx
from backend.sources.base import SourceAdapter, NormalizedJob
from backend.core.resilience import with_retry

log = logging.getLogger("cutshort")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://cutshort.io/",
}

CUTSHORT_SEARCH = "https://cutshort.io/api/web/jobs/search"

SKILL_QUERIES = [
    {"skills": ["Python"], "min_exp": 0, "max_exp": 1},
    {"skills": ["Machine Learning"], "min_exp": 0, "max_exp": 2},
    {"skills": ["Artificial Intelligence"], "min_exp": 0, "max_exp": 2},
    {"skills": ["Data Science"], "min_exp": 0, "max_exp": 1},
    {"skills": ["FastAPI"], "min_exp": 0, "max_exp": 2},
    {"skills": ["Deep Learning"], "min_exp": 0, "max_exp": 2},
]


class CutshortSource(SourceAdapter):
    """Cutshort.io — tech/startup job search with public API."""
    name, policy = "cutshort", "public_api"

    @with_retry(2)
    async def _search(self, client: httpx.AsyncClient, skills: list[str], min_exp: int, max_exp: int) -> list[NormalizedJob]:
        payload = {
            "skill_names": skills,
            "min_exp": min_exp,
            "max_exp": max_exp,
            "location_names": ["Bengaluru", "Remote"],
            "job_type": ["full-time", "internship"],
            "page": 1,
            "per_page": 20,
        }
        try:
            r = await client.post(CUTSHORT_SEARCH, json=payload, timeout=12)
            if r.status_code != 200:
                return []
            data = r.json()
            jobs_raw = data.get("data", {}).get("jobs", []) or data.get("jobs", [])
            out = []
            for j in jobs_raw:
                title = (j.get("title") or "").strip()
                company_obj = j.get("company") or {}
                company = (company_obj.get("name") or j.get("company_name") or "Startup").strip()
                jd = (j.get("description") or "").strip()
                job_url = j.get("job_url") or j.get("url") or ""
                if not job_url and j.get("short_code"):
                    job_url = f"https://cutshort.io/job/{j['short_code']}"
                loc_list = j.get("locations") or ["Bengaluru"]
                loc = loc_list[0] if loc_list else "Bengaluru"
                if not title or not job_url:
                    continue
                jd_short = jd[:500] + ("..." if len(jd) > 500 else "")
                out.append(NormalizedJob(
                    source="cutshort",
                    source_job_id=str(j.get("id", job_url)),
                    title=title, company=company, location=str(loc),
                    work_mode="Startup / Hybrid",
                    description=jd_short or f"{title} at {company} — Indian startup via Cutshort.io",
                    job_url=job_url,
                    skills=skills,
                    posted_at="Recent (Cutshort)",
                ))
            return out
        except Exception as e:
            log.warning("Cutshort search failed %s: %s", skills, e)
            return []

    async def discover(self, query: str) -> list[NormalizedJob]:
        seen: set[str] = set()
        all_jobs: list[NormalizedJob] = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            tasks = [self._search(client, q["skills"], q["min_exp"], q["max_exp"]) for q in SKILL_QUERIES]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    for j in res:
                        if j.job_url and j.job_url not in seen:
                            seen.add(j.job_url)
                            all_jobs.append(j)
        log.info("Cutshort returned %d jobs", len(all_jobs))
        return all_jobs

    async def health_check(self) -> bool:
        return True
