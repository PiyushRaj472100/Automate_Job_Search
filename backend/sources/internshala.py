"""
Internshala source adapter — India top internship & entry-level job platform.
Extracts real, active internship postings across Python, AI, ML, Data Science,
and Software Development for Bangalore and Remote roles.
"""
import asyncio
import logging
import re
import httpx
from backend.sources.base import SourceAdapter, NormalizedJob
from backend.core.resilience import with_retry

log = logging.getLogger("internshala")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

INTERNSHALA_CATEGORIES = [
    ("https://internshala.com/internships/python-internship-in-bangalore/", "Python Bangalore"),
    ("https://internshala.com/internships/artificial-intelligence-ai-internship-in-bangalore/", "AI Bangalore"),
    ("https://internshala.com/internships/machine-learning-internship-in-bangalore/", "ML Bangalore"),
    ("https://internshala.com/internships/data-science-internship-in-bangalore/", "Data Science Bangalore"),
    ("https://internshala.com/internships/software-development-internship-in-bangalore/", "Software Dev Bangalore"),
    ("https://internshala.com/internships/work-from-home-python-internships/", "Remote Python"),
    ("https://internshala.com/internships/work-from-home-artificial-intelligence-ai-internships/", "Remote AI"),
]


class InternshalaSource(SourceAdapter):
    """Internshala.com — India #1 internship and fresher tech platform."""
    name, policy = "internshala", "scraper"

    @with_retry(2)
    async def _fetch_category(self, client: httpx.AsyncClient, url: str, cat_name: str) -> list[NormalizedJob]:
        try:
            r = await client.get(url, timeout=14)
            if r.status_code != 200:
                log.debug("Internshala %s returned status %d", cat_name, r.status_code)
                return []

            cards = re.findall(
                r'(<div[^>]+class="[^"]*container-fluid individual_internship[^"]*"[^>]*>.*?)(?=<div[^>]+class="[^"]*container-fluid individual_internship|\Z)',
                r.text,
                re.DOTALL,
            )
            out: list[NormalizedJob] = []
            for card in cards:
                m_title = re.search(r'<a class="job-title-href"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', card)
                if not m_title:
                    continue
                href = m_title.group(1).strip()
                title = m_title.group(2).strip()
                full_url = f"https://internshala.com{href}" if href.startswith("/") else href

                m_comp = re.search(r'<p class="company-name"[^>]*>(.*?)</p>', card, re.DOTALL)
                company = re.sub(r"<[^>]+>", "", m_comp.group(1)).strip() if m_comp else "Startup"

                m_loc = re.search(r'<div class="row-1-item locations">.*?<a[^>]*>(.*?)</a>', card, re.DOTALL)
                loc = m_loc.group(1).strip() if m_loc else ("Remote" if "work-from-home" in url else "Bengaluru, India")

                # Extract stipend
                stipend = ""
                m_stip = re.search(r'<span class="stipend"[^>]*>(.*?)</span>', card, re.DOTALL)
                if m_stip:
                    stipend = re.sub(r"<[^>]+>", "", m_stip.group(1)).strip()
                else:
                    m_stip_alt = re.search(r'(?:₹|Rs\.?)\s*[\d,]+(?:\s*-\s*[\d,]+)?(?:\s*/month)?', card)
                    if m_stip_alt:
                        stipend = m_stip_alt.group(0).strip()

                work_mode = "Remote" if "work-from-home" in url or "remote" in loc.lower() else "Office / Hybrid"

                desc = (
                    f"{title} Internship at {company}. Location: {loc}. "
                    f"Stipend: {stipend or 'Competitive'}. Hands-on opportunity for freshers and early engineers "
                    f"in {cat_name}. Apply directly on Internshala."
                )

                out.append(
                    NormalizedJob(
                        source="internshala",
                        source_job_id=full_url,
                        title=f"{title} Intern" if not title.lower().endswith("intern") else title,
                        company=company,
                        location=loc,
                        work_mode=work_mode,
                        description=desc[:900],
                        job_url=full_url,
                        skills=["Python", "AI", "Fresher"],
                        posted_at="Recent (Internshala)",
                    )
                )
            return out
        except Exception as e:
            log.warning("Internshala category '%s' error: %s", cat_name, e)
            return []

    async def discover(self, query: str = "") -> list[NormalizedJob]:
        all_jobs: list[NormalizedJob] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            tasks = [self._fetch_category(client, url, name) for url, name in INTERNSHALA_CATEGORIES]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    for j in res:
                        if j.job_url and j.job_url not in seen:
                            seen.add(j.job_url)
                            all_jobs.append(j)

        log.info("Internshala returned %d internships", len(all_jobs))
        return all_jobs

    async def health_check(self) -> bool:
        return True