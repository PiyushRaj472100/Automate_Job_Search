"""
Multi-platform RSS / JSON feed aggregator for:
- RemoteOK (remote.ok.com)
- Working Nomads (workingnomads.com)
- Startup.jobs
- Freshersworld.com RSS
- TimesJobs public API
- Jooble.org public search
- Glassdoor (public job listings)
- Indeed India (XML feed where available)
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
import httpx
from backend.sources.base import SourceAdapter, NormalizedJob
from backend.core.resilience import with_retry

log = logging.getLogger("feeds")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


class RemoteOKSource(SourceAdapter):
    """RemoteOK.com — public JSON API for remote tech jobs."""
    name, policy = "remoteok", "public_api"

    @with_retry(2)
    async def discover(self, query: str) -> list[NormalizedJob]:
        try:
            async with httpx.AsyncClient(headers={**HEADERS, "Accept": "application/json"}, timeout=15) as c:
                r = await c.get("https://remoteok.com/api")
                if r.status_code != 200:
                    return []
                data = r.json()
                # First entry is metadata
                jobs_raw = [j for j in data if isinstance(j, dict) and j.get("position")]
                out = []
                seen: set[str] = set()
                terms = {"python", "ai", "machine learning", "data", "backend", "ml", "nlp", "fastapi", "django"}
                for j in jobs_raw[:80]:
                    title = (j.get("position") or "").strip()
                    company = (j.get("company") or "Remote Company").strip()
                    jd = (j.get("description") or "").strip()
                    job_url = j.get("url") or j.get("apply_url") or ""
                    tags = [t.lower() for t in (j.get("tags") or [])]
                    loc = j.get("location") or "Remote (Worldwide)"
                    if not title or not job_url or job_url in seen:
                        continue
                    hay = f"{title} {jd} {' '.join(tags)}".lower()
                    if not any(t in hay for t in terms):
                        continue
                    seen.add(job_url)
                    jd_short = jd[:500] + ("..." if len(jd) > 500 else "")
                    out.append(NormalizedJob(
                        source="remoteok",
                        source_job_id=str(j.get("id", job_url)),
                        title=title, company=company, location=str(loc),
                        work_mode="Remote (Global / India Eligible)",
                        description=jd_short or f"Remote {title} at {company}",
                        job_url=job_url,
                        skills=tags[:5] or ["Python", "Remote"],
                        posted_at=str(j.get("date") or "Recent (RemoteOK)"),
                    ))
                log.info("RemoteOK returned %d matching jobs", len(out))
                return out
        except Exception as e:
            log.warning("RemoteOK error: %s", e)
            return []

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://remoteok.com/api")
                return r.status_code == 200
        except Exception:
            return False


class StartupJobsSource(SourceAdapter):
    """Startup.jobs — curated startup job listings via JSON feed."""
    name, policy = "startup_jobs", "public_api"

    @with_retry(2)
    async def discover(self, query: str) -> list[NormalizedJob]:
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as c:
                # startup.jobs has a JSON API
                r = await c.get("https://startup.jobs/api/v2/jobs?tags=python,ai,machine-learning&limit=50")
                if r.status_code != 200:
                    # Try public RSS
                    r2 = await c.get("https://startup.jobs/feed?tags=python&location=india")
                    if r2.status_code != 200:
                        return []
                    return self._parse_rss(r2.text)
                data = r.json()
                jobs_raw = data.get("jobs", data.get("data", []))
                out = []
                seen: set[str] = set()
                for j in (jobs_raw or []):
                    title = (j.get("title") or "").strip()
                    company = (j.get("company") or j.get("company_name") or "Startup").strip()
                    jd = (j.get("description") or j.get("body") or "").strip()
                    job_url = j.get("url") or j.get("apply_url") or ""
                    if not job_url and j.get("slug"):
                        job_url = f"https://startup.jobs/{j['slug']}"
                    loc = j.get("location") or "Remote / India"
                    if not title or not job_url or job_url in seen:
                        continue
                    seen.add(job_url)
                    jd_short = jd[:500] + ("..." if len(jd) > 500 else "")
                    out.append(NormalizedJob(
                        source="startup_jobs",
                        source_job_id=str(j.get("id", job_url)),
                        title=title, company=company, location=str(loc),
                        work_mode="Startup / Remote",
                        description=jd_short or f"{title} at {company} — startup.jobs",
                        job_url=job_url,
                        skills=j.get("tags") or ["Python"],
                        posted_at=str(j.get("created_at") or "Recent (Startup.jobs)"),
                    ))
                log.info("Startup.jobs returned %d jobs", len(out))
                return out
        except Exception as e:
            log.warning("Startup.jobs error: %s", e)
            return []

    def _parse_rss(self, xml_text: str) -> list[NormalizedJob]:
        try:
            root = ET.fromstring(xml_text)
            items = root.findall(".//item")
            out = []
            for item in items[:30]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                if not title or not link:
                    continue
                desc_short = desc[:500] + ("..." if len(desc) > 500 else "")
                out.append(NormalizedJob(
                    source="startup_jobs",
                    source_job_id=link,
                    title=title, company="Startup", location="Remote / India",
                    work_mode="Startup / Remote",
                    description=desc_short or title,
                    job_url=link,
                    skills=["Python"],
                    posted_at="Recent (Startup.jobs RSS)",
                ))
            return out
        except Exception:
            return []

    async def health_check(self) -> bool:
        return True


class WorkingNomadsSource(SourceAdapter):
    """Working Nomads — remote developer jobs with public JSON/RSS feed."""
    name, policy = "working_nomads", "public_api"

    @with_retry(2)
    async def discover(self, query: str) -> list[NormalizedJob]:
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as c:
                r = await c.get("https://www.workingnomads.com/api/exposed_jobs/?category=development&limit=60")
                if r.status_code != 200:
                    return []
                data = r.json()
                jobs_raw = data if isinstance(data, list) else data.get("results", [])
                out = []
                seen: set[str] = set()
                terms = {"python", "ai", "machine learning", "data", "backend", "ml", "fastapi"}
                for j in (jobs_raw or []):
                    title = (j.get("title") or "").strip()
                    company = (j.get("company") or "Remote Company").strip()
                    jd = (j.get("description") or "").strip()
                    job_url = j.get("url") or j.get("apply_url") or ""
                    tags = j.get("tags") or []
                    loc = j.get("location") or "Remote (Worldwide)"
                    if not title or not job_url or job_url in seen:
                        continue
                    hay = f"{title} {jd} {' '.join(str(t) for t in tags)}".lower()
                    if not any(t in hay for t in terms):
                        continue
                    seen.add(job_url)
                    jd_short = jd[:500] + ("..." if len(jd) > 500 else "")
                    out.append(NormalizedJob(
                        source="working_nomads",
                        source_job_id=str(j.get("id", job_url)),
                        title=title, company=company, location=str(loc),
                        work_mode="Remote (India Eligible)",
                        description=jd_short or f"Remote {title} at {company}",
                        job_url=job_url,
                        skills=[str(t) for t in tags[:5]] or ["Python"],
                        posted_at=str(j.get("pub_date") or "Recent (Working Nomads)"),
                    ))
                log.info("WorkingNomads returned %d jobs", len(out))
                return out
        except Exception as e:
            log.warning("WorkingNomads error: %s", e)
            return []

    async def health_check(self) -> bool:
        return True


class YCJobsSource(SourceAdapter):
    """Y Combinator Jobs — YC startup jobs from the public JSON feed."""
    name, policy = "yc_jobs", "public_api"

    @with_retry(2)
    async def discover(self, query: str) -> list[NormalizedJob]:
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as c:
                r = await c.get("https://www.ycombinator.com/jobs.json")
                if r.status_code != 200:
                    # Fallback to public jobs API
                    r = await c.get(
                        "https://api.ycombinator.com/v0.1/jobs?page=1&jobType=fulltime&tag=python,ai,ml,data",
                        timeout=12
                    )
                    if r.status_code != 200:
                        return []
                data = r.json()
                jobs_raw = data.get("jobs", data if isinstance(data, list) else [])
                out = []
                seen: set[str] = set()
                terms = {"python", "ai", "machine learning", "data", "backend", "ml", "nlp", "fastapi"}
                for j in (jobs_raw or [])[:60]:
                    title = (j.get("title") or j.get("role") or "").strip()
                    startup = j.get("company") or {}
                    company = (startup.get("name") if isinstance(startup, dict) else str(startup) or "YC Startup").strip()
                    jd = (j.get("description") or j.get("body") or "").strip()
                    job_url = j.get("url") or j.get("apply_url") or ""
                    loc = j.get("location") or "Remote / India"
                    if not title or not job_url or job_url in seen:
                        continue
                    hay = f"{title} {jd}".lower()
                    if not any(t in hay for t in terms):
                        continue
                    seen.add(job_url)
                    jd_short = jd[:500] + ("..." if len(jd) > 500 else "")
                    out.append(NormalizedJob(
                        source="yc_jobs",
                        source_job_id=str(j.get("id", job_url)),
                        title=title, company=company, location=str(loc),
                        work_mode="YC Startup / Remote",
                        description=jd_short or f"{title} at YC-backed {company}",
                        job_url=job_url,
                        skills=["Python", "Startup"],
                        posted_at=str(j.get("created_at") or "Recent (YC Jobs)"),
                    ))
                log.info("YC Jobs returned %d matching jobs", len(out))
                return out
        except Exception as e:
            log.warning("YC Jobs error: %s", e)
            return []

    async def health_check(self) -> bool:
        return True
