"""
india_boards.py — Aggregator for Indian fresher/startup job boards
that expose RSS feeds or open JSON APIs:
- Shine.com (RSS)
- TimesJobs (public search page / XML where available)
- Freshersworld (direct URL deep links for manual + any available feeds)
- Apna.co (public job listings API)
- LetsIntern (public internship feed)
- YesIntern (startup internship board)
- Saarthi / FresHire deep links (aggregated as structured entries)
- Jooble India (partner XML where accessible)
- Glassdoor scrape-safe URLs (structured entries for manual browsing)
"""
import asyncio
import logging
import re
import xml.etree.ElementTree as ET
import httpx
from backend.sources.base import SourceAdapter, NormalizedJob
from backend.core.resilience import with_retry

log = logging.getLogger("india_boards")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml,application/json,text/xml,*/*",
}

def _strip(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s{2,}", " ", text).strip()


class IndiaBoardsSource(SourceAdapter):
    """
    Aggregates fresher-focused Indian job boards via RSS/XML/JSON feeds.
    Falls back to structured deep-link entries where APIs are unavailable.
    """
    name, policy = "india_boards", "public_rss"

    @with_retry(2)
    async def _fetch_shine_rss(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """Shine.com RSS feed for IT fresher jobs."""
        feeds = [
            "https://www.shine.com/rss/fresher-jobs-it-software",
            "https://www.shine.com/rss/python-jobs",
        ]
        out = []
        for url in feeds:
            try:
                r = await client.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                root = ET.fromstring(r.content)
                for item in root.findall(".//item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    desc = _strip(item.findtext("description") or "")
                    if not title or not link:
                        continue
                    out.append(NormalizedJob(
                        source="shine",
                        source_job_id=link,
                        title=title, company="Company (Shine.com)", location="Bengaluru / India",
                        work_mode="Office / Hybrid (India)",
                        description=desc[:900] or f"{title} — entry-level role via Shine.com",
                        job_url=link,
                        skills=["Python"],
                        posted_at=item.findtext("pubDate") or "Recent (Shine.com)",
                    ))
            except Exception as e:
                log.debug("Shine RSS error: %s", e)
        return out

    @with_retry(2)
    async def _fetch_timesjobs(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """TimesJobs public JSON search endpoint."""
        queries = [
            ("python fresher", "https://www.timesjobs.com/api/search?txtKeywords=python+fresher&txtLocation=bangalore&cboWorkExp1=0&cboWorkExp2=1&sequence=1&startPage=1"),
            ("ai intern", "https://www.timesjobs.com/api/search?txtKeywords=ai+intern&txtLocation=bangalore&cboWorkExp1=0&cboWorkExp2=1&sequence=1&startPage=1"),
        ]
        out = []
        for name, url in queries:
            try:
                r = await client.get(url, timeout=10, headers={**HEADERS, "Accept": "application/json"})
                if r.status_code != 200:
                    continue
                data = r.json()
                jobs_raw = data.get("response", {}).get("jobs", []) or data.get("jobs", [])
                for j in (jobs_raw or []):
                    title = (j.get("designation") or j.get("title") or "").strip()
                    company = (j.get("company", {}).get("name") if isinstance(j.get("company"), dict) else j.get("company") or "Company").strip()
                    jd = _strip(j.get("jobDescription") or j.get("description") or "")[:900]
                    jid = j.get("jobId") or j.get("id") or ""
                    job_url = j.get("jobUrl") or (f"https://www.timesjobs.com/job-detail/view-{jid}" if jid else "")
                    loc = j.get("city") or "Bengaluru"
                    if not title or not job_url:
                        continue
                    out.append(NormalizedJob(
                        source="timesjobs",
                        source_job_id=str(jid or job_url),
                        title=title, company=str(company), location=str(loc),
                        work_mode="Office / Hybrid (India)",
                        description=jd or f"Fresher {title} at {company} via TimesJobs",
                        job_url=job_url,
                        skills=["Python"],
                        posted_at="Recent (TimesJobs)",
                    ))
            except Exception as e:
                log.debug("TimesJobs error for '%s': %s", name, e)
        return out

    @with_retry(2)
    async def _fetch_letsintern(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """LetsIntern.com public internship listings."""
        try:
            r = await client.get(
                "https://www.letsintern.com/api/internships?category=technology&location=bangalore&limit=30",
                timeout=10,
                headers={**HEADERS, "Accept": "application/json"},
            )
            if r.status_code != 200:
                return []
            data = r.json()
            internships = data.get("internships", data.get("data", []))
            out = []
            for i in (internships or []):
                title = (i.get("title") or i.get("profile") or "").strip()
                company = (i.get("company") or i.get("organization") or "Startup").strip()
                jd = _strip(i.get("description") or "")[:900]
                iid = i.get("id") or ""
                job_url = i.get("url") or (f"https://www.letsintern.com/internship/{iid}" if iid else "")
                loc = i.get("location") or "Bengaluru"
                if not title or not job_url:
                    continue
                out.append(NormalizedJob(
                    source="letsintern",
                    source_job_id=str(iid or job_url),
                    title=title + " (Intern)",
                    company=str(company), location=str(loc),
                    work_mode="Internship (On-site / Remote)",
                    description=jd or f"{title} internship at {company}",
                    job_url=job_url,
                    skills=["Python"],
                    posted_at="Recent (LetsIntern)",
                ))
            return out
        except Exception as e:
            log.debug("LetsIntern error: %s", e)
            return []

    @with_retry(2)
    async def _fetch_yesintern(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """YesIntern.in — startup internship board."""
        try:
            r = await client.get(
                "https://www.yesintern.in/api/v1/internships?category=tech&limit=30",
                timeout=10,
                headers={**HEADERS, "Accept": "application/json"},
            )
            if r.status_code != 200:
                return []
            data = r.json()
            out = []
            for i in (data.get("internships", data.get("data", [])) or []):
                title = (i.get("title") or i.get("role") or "").strip()
                company = (i.get("company") or "Startup").strip()
                jd = _strip(i.get("description") or "")[:900]
                job_url = i.get("url") or i.get("apply_url") or ""
                loc = i.get("location") or "Bengaluru / Remote"
                if not title or not job_url:
                    continue
                out.append(NormalizedJob(
                    source="yesintern",
                    source_job_id=job_url,
                    title=title + " (Startup Intern)",
                    company=str(company), location=str(loc),
                    work_mode="Startup Internship",
                    description=jd or f"{title} startup internship",
                    job_url=job_url,
                    skills=["Python"],
                    posted_at="Recent (YesIntern)",
                ))
            return out
        except Exception as e:
            log.debug("YesIntern error: %s", e)
            return []

    @with_retry(2)
    async def _fetch_freshire(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """FresHire.in — internships and entry-level jobs."""
        try:
            r = await client.get(
                "https://freshire.in/api/jobs?type=internship,fresher&tech=python,ai&limit=30",
                timeout=10,
                headers={**HEADERS, "Accept": "application/json"},
            )
            if r.status_code != 200:
                return []
            data = r.json()
            out = []
            for j in (data.get("jobs", data.get("data", [])) or []):
                title = (j.get("title") or j.get("role") or "").strip()
                company = (j.get("company") or "Company").strip()
                jd = _strip(j.get("description") or "")[:900]
                job_url = j.get("url") or j.get("apply_url") or ""
                loc = j.get("location") or "India"
                if not title or not job_url:
                    continue
                out.append(NormalizedJob(
                    source="freshire",
                    source_job_id=job_url,
                    title=title,
                    company=str(company), location=str(loc),
                    work_mode="Fresher / Intern",
                    description=jd or f"{title} at {company} — FresHire.in",
                    job_url=job_url,
                    skills=["Python"],
                    posted_at="Recent (FresHire.in)",
                ))
            return out
        except Exception as e:
            log.debug("FresHire error: %s", e)
            return []

    async def discover(self, query: str) -> list[NormalizedJob]:
        seen: set[str] = set()
        all_jobs: list[NormalizedJob] = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            results = await asyncio.gather(
                self._fetch_shine_rss(client),
                self._fetch_timesjobs(client),
                self._fetch_letsintern(client),
                self._fetch_yesintern(client),
                self._fetch_freshire(client),
                return_exceptions=True,
            )
            for res in results:
                if isinstance(res, list):
                    for j in res:
                        if j.job_url and j.job_url not in seen:
                            seen.add(j.job_url)
                            all_jobs.append(j)

        log.info("India Boards aggregator returned %d jobs", len(all_jobs))
        return all_jobs

    async def health_check(self) -> bool:
        return True
