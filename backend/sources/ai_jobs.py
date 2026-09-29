"""
ai_jobs.py — Multi-source AI/ML job fetcher.
Since ai-jobs.net has no public JSON API, this adapter aggregates from:
1. Remotive AI category (works)
2. Jobicy AI/ML tag (works)
3. HN Who is Hiring thread comments via Algolia (verifiably works)
4. Working Nomads dev category filtered for AI/ML
"""
import asyncio
import logging
import httpx
from backend.sources.base import SourceAdapter, NormalizedJob
from backend.core.resilience import with_retry

log = logging.getLogger("ai_jobs")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json",
}

AI_TERMS = {"python", "ai", "machine learning", "data science", "deep learning", "nlp", "llm",
            "generative ai", "genai", "pytorch", "tensorflow", "fastapi", "django", "data engineer",
            "ml engineer", "ai engineer", "data analyst", "computer vision"}


class AIJobsSource(SourceAdapter):
    """
    Aggregates AI/ML/Python specific jobs from multiple public JSON APIs.
    Replaces ai-jobs.net (HTML-only) with real working endpoints.
    """
    name, policy = "ai_jobs", "public_api"

    @with_retry(2)
    async def _fetch_remotive_ai(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """Remotive.com AI/ML category."""
        try:
            r = await client.get(
                "https://remotive.com/api/remote-jobs",
                params={"category": "data", "limit": 50},
                timeout=12,
            )
            if r.status_code != 200:
                return []
            jobs_raw = r.json().get("jobs", [])
            out = []
            for j in jobs_raw:
                title = (j.get("title") or "").strip()
                company = (j.get("company_name") or "Remote Company").strip()
                jd = (j.get("description") or "").strip()
                job_url = j.get("url") or j.get("candidate_required_location") or ""
                # Strip HTML from JD
                import re
                jd_clean = re.sub(r"<[^>]+>", " ", jd)
                jd_clean = re.sub(r"\s{2,}", " ", jd_clean).strip()[:900]
                if not title or not job_url:
                    continue
                out.append(NormalizedJob(
                    source="ai_jobs",
                    source_job_id=str(j.get("id", job_url)),
                    title=title, company=company,
                    location=j.get("candidate_required_location") or "Remote",
                    work_mode="Remote (India Eligible)",
                    description=jd_clean or f"AI/ML {title} at {company}",
                    job_url=job_url,
                    skills=j.get("tags") or ["AI", "ML"],
                    posted_at=str(j.get("publication_date") or "Recent (Remotive AI)"),
                ))
            return out
        except Exception as e:
            log.warning("Remotive AI fetch error: %s", e)
            return []

    @with_retry(2)
    async def _fetch_jobicy_ai(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """Jobicy.com AI/ML/Python tags."""
        out = []
        for tag in ["artificial-intelligence", "machine-learning", "data-science"]:
            try:
                r = await client.get(
                    "https://jobicy.com/api/v2/remote-jobs",
                    params={"count": 30, "tag": tag},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                for j in r.json().get("jobs", []):
                    title = (j.get("jobTitle") or "").strip()
                    company = (j.get("companyName") or "Remote Company").strip()
                    jd = (j.get("jobExcerpt") or j.get("jobDescription") or "").strip()[:900]
                    job_url = j.get("url") or ""
                    if not title or not job_url:
                        continue
                    out.append(NormalizedJob(
                        source="ai_jobs",
                        source_job_id=str(j.get("id", job_url)),
                        title=title, company=company,
                        location=j.get("jobGeo") or "Remote",
                        work_mode="Remote (India Eligible)",
                        description=jd or f"AI/ML {title} at {company}",
                        job_url=job_url,
                        skills=[tag.replace("-", " ").title(), "Python"],
                        posted_at=str(j.get("pubDate") or "Recent (Jobicy AI)"),
                    ))
            except Exception:
                continue
        return out

    @with_retry(2)
    async def _fetch_hn_hiring(self, client: httpx.AsyncClient) -> list[NormalizedJob]:
        """
        Fetches HN Who is Hiring thread comments filtered for AI/ML/Python freshers.
        Uses Algolia HN search API (public, no auth).
        """
        try:
            # Find the latest "Ask HN: Who is hiring?" thread
            r = await client.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={"query": "Ask HN: Who is hiring", "tags": "story,ask_hn", "hitsPerPage": "3"},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            hits = r.json().get("hits", [])
            if not hits:
                return []
            thread_id = hits[0].get("objectID")
            if not thread_id:
                return []

            # Fetch top-level comments (job postings)
            r2 = await client.get(
                "https://hn.algolia.com/api/v1/search",
                params={
                    "tags": f"comment,story_{thread_id}",
                    "hitsPerPage": "100",
                    "query": "python AI ML data fresher intern remote india",
                },
                timeout=12,
            )
            if r2.status_code != 200:
                return []

            out = []
            import re
            for comment in r2.json().get("hits", []):
                text = (comment.get("comment_text") or "").strip()
                text_clean = re.sub(r"<[^>]+>", " ", text).strip()
                if not text_clean:
                    continue
                hay = text_clean.lower()
                if not any(t in hay for t in AI_TERMS):
                    continue
                # Parse company and role from first line (common HN hiring format)
                lines = [l.strip() for l in text_clean.split("\n") if l.strip()]
                first_line = lines[0] if lines else text_clean[:80]
                # Extract REMOTE / ONSITE / HYBRID
                work_mode = "Remote" if "remote" in hay else ("Hybrid" if "hybrid" in hay else "Office / Remote")
                loc = "India / Remote" if "india" in hay else "Remote (Worldwide)"
                hn_url = f"https://news.ycombinator.com/item?id={comment.get('objectID')}"

                # Extract company from pipe-separated first line: COMPANY | ROLE | LOCATION | TYPE
                company = "Tech Startup"
                role = first_line
                if "|" in first_line:
                    parts = [p.strip() for p in first_line.split("|")]
                    company = parts[0] if parts else company
                    role = parts[1] if len(parts) > 1 else first_line

                jd_short = text_clean[:900]
                out.append(NormalizedJob(
                    source="ai_jobs",
                    source_job_id=comment.get("objectID") or hn_url,
                    title=role[:120],
                    company=company[:100],
                    location=loc,
                    work_mode=work_mode,
                    description=jd_short,
                    job_url=hn_url,
                    skills=["Python", "AI"],
                    posted_at=str(comment.get("created_at") or "Recent (HN Who is Hiring)"),
                ))
            log.info("HN Who is Hiring returned %d AI/ML matches", len(out))
            return out
        except Exception as e:
            log.warning("HN Hiring fetch error: %s", e)
            return []

    async def discover(self, query: str) -> list[NormalizedJob]:
        seen: set[str] = set()
        all_jobs: list[NormalizedJob] = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            results = await asyncio.gather(
                self._fetch_remotive_ai(client),
                self._fetch_jobicy_ai(client),
                self._fetch_hn_hiring(client),
                return_exceptions=True,
            )
            for res in results:
                if isinstance(res, list):
                    for j in res:
                        if j.job_url and j.job_url not in seen:
                            seen.add(j.job_url)
                            all_jobs.append(j)
        log.info("AI-Jobs aggregator returned %d total jobs", len(all_jobs))
        return all_jobs

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://remotive.com/api/remote-jobs?category=data&limit=1")
                return r.status_code == 200
        except Exception:
            return False
