"""
Wellfound (formerly AngelList Talent) source adapter.
Queries the Wellfound public job search GraphQL / REST API for startup tech jobs.
Especially good for AI/ML/Python roles at Indian and remote startups.
"""
import asyncio
import logging
import httpx
from backend.sources.base import SourceAdapter, NormalizedJob
from backend.core.resilience import with_retry

log = logging.getLogger("wellfound")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://wellfound.com/",
}

# Wellfound has a public JSON endpoint for job listings
WELLFOUND_API = "https://wellfound.com/company_types/all/role/software-engineer/location/all-cities"

WELLFOUND_ROLES = [
    "python",
    "machine-learning",
    "data-science",
    "ai",
    "backend",
]

WELLFOUND_JSON = "https://api.wellfound.com/jobs"


class WellfoundSource(SourceAdapter):
    """Wellfound (AngelList Talent) — top global startup jobs board."""
    name, policy = "wellfound", "public_api"

    @with_retry(2)
    async def _fetch(self, client: httpx.AsyncClient, role: str) -> list[NormalizedJob]:
        """Try the Wellfound talent JSON feed."""
        try:
            # Wellfound public listing endpoint (no auth needed for public roles)
            url = f"https://wellfound.com/role/{role}/l/india"
            r = await client.get(url, timeout=12)
            if r.status_code not in (200, 301, 302):
                return []
            # Try to parse JSON response if API-like
            try:
                data = r.json()
                jobs_raw = data.get("jobs", data.get("data", []))
            except Exception:
                # Likely HTML page — return empty and let scraper handle it
                return []
            out = []
            for j in (jobs_raw or []):
                title = (j.get("title") or j.get("name") or "").strip()
                startup = j.get("startup") or j.get("company") or {}
                company = (startup.get("name") if isinstance(startup, dict) else str(startup) or "Startup").strip()
                jd = (j.get("description") or "").strip()
                job_url = j.get("url") or j.get("job_url") or ""
                if not job_url and j.get("id"):
                    job_url = f"https://wellfound.com/jobs/{j['id']}"
                loc = j.get("location") or "India / Remote"
                if not title or not job_url:
                    continue
                jd_short = jd[:500] + ("..." if len(jd) > 500 else "")
                out.append(NormalizedJob(
                    source="wellfound",
                    source_job_id=str(j.get("id", job_url)),
                    title=title, company=company, location=str(loc),
                    work_mode="Startup / Remote",
                    description=jd_short or f"{title} at startup {company} via Wellfound",
                    job_url=job_url,
                    skills=j.get("skills") or [role.replace("-", " ").title()],
                    posted_at=str(j.get("created_at") or "Recent (Wellfound)"),
                ))
            return out
        except Exception as e:
            log.debug("Wellfound fetch error for '%s': %s", role, e)
            return []

    @with_retry(2)
    async def _fetch_graphql(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """Try Wellfound GraphQL public jobs listing."""
        try:
            gql_url = "https://wellfound.com/graphql"
            payload = {
                "query": """query JobSearchResults($role: String, $location: String) {
  jobListings(role: $role, location: $location, page: 1) {
    startups { name, jobs { title, description, remote, url, createdAt } }
  }
}""",
                "variables": {"role": "python", "location": "india"},
            }
            r = await client.post(gql_url, json=payload, timeout=12)
            if r.status_code != 200:
                return []
            data = r.json()
            out = []
            for startup in (data.get("data", {}).get("jobListings", {}).get("startups") or []):
                company = startup.get("name") or "Startup"
                for j in (startup.get("jobs") or []):
                    title = j.get("title") or ""
                    jd = j.get("description") or ""
                    job_url = j.get("url") or ""
                    if not title or not job_url:
                        continue
                    jd_short = jd[:500] + ("..." if len(jd) > 500 else "")
                    out.append(NormalizedJob(
                        source="wellfound",
                        source_job_id=job_url,
                        title=title, company=company,
                        location="India / Remote",
                        work_mode="Remote" if j.get("remote") else "Startup Office",
                        description=jd_short or f"{title} at {company}",
                        job_url=job_url,
                        skills=["Python"],
                        posted_at=str(j.get("createdAt") or "Recent (Wellfound)"),
                    ))
            return out
        except Exception:
            return []

    async def discover(self, query: str) -> list[NormalizedJob]:
        seen: set[str] = set()
        all_jobs: list[NormalizedJob] = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            gql_jobs = await self._fetch_graphql(client)
            for j in gql_jobs:
                if j.job_url and j.job_url not in seen:
                    seen.add(j.job_url)
                    all_jobs.append(j)
            tasks = [self._fetch(client, role) for role in WELLFOUND_ROLES]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    for j in res:
                        if j.job_url and j.job_url not in seen:
                            seen.add(j.job_url)
                            all_jobs.append(j)
        log.info("Wellfound returned %d jobs", len(all_jobs))
        return all_jobs

    async def health_check(self) -> bool:
        return True
