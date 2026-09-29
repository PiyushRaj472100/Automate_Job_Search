"""
naukri.py — India largest job portal.
Naukri blocks direct API calls with reCAPTCHA. This adapter uses:
1. Naukri public RSS feeds (the pre-built category feeds work without auth)
2. Structured fallback: constructs deep-link search URLs for the sheet
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
import httpx
from backend.sources.base import SourceAdapter, NormalizedJob
from backend.core.resilience import with_retry

log = logging.getLogger("naukri")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml,application/xml,text/xml,*/*",
}

# Naukri has pre-built category RSS feeds (no auth, no recaptcha)
NAUKRI_RSS_FEEDS = [
    # Fresher IT jobs in Bangalore
    ("https://www.naukri.com/rss/fresher-jobs-in-it-software-bangalore-ncr.rss", "Naukri Fresher IT Bangalore"),
    ("https://www.naukri.com/rss/python-jobs-in-bangalore.rss", "Naukri Python Bangalore"),
    ("https://www.naukri.com/rss/machine-learning-jobs-in-bangalore.rss", "Naukri ML Bangalore"),
    ("https://www.naukri.com/rss/data-science-jobs-in-bangalore.rss", "Naukri Data Science Bangalore"),
    ("https://www.naukri.com/rss/artificial-intelligence-jobs-in-bangalore.rss", "Naukri AI Bangalore"),
    ("https://www.naukri.com/rss/python-developer-jobs-in-bangalore.rss", "Naukri Python Dev Bangalore"),
    ("https://www.naukri.com/rss/fresher-jobs-in-it-software-hyderabad.rss", "Naukri Fresher IT Hyderabad"),
    ("https://www.naukri.com/rss/python-jobs-in-hyderabad.rss", "Naukri Python Hyderabad"),
    ("https://www.naukri.com/rss/deep-learning-jobs-in-bangalore.rss", "Naukri Deep Learning Bangalore"),
    ("https://www.naukri.com/rss/nlp-jobs-in-bangalore.rss", "Naukri NLP Bangalore"),
]

# Also generate direct deep-link search URLs for manual review
NAUKRI_SEARCH_LINKS = [
    ("Python Fresher Bangalore", "https://www.naukri.com/python-fresher-jobs-in-bangalore?experience=0"),
    ("AI Engineer Fresher", "https://www.naukri.com/ai-engineer-fresher-jobs-in-bangalore?experience=0"),
    ("ML Intern Bangalore", "https://www.naukri.com/machine-learning-intern-jobs-in-bangalore?experience=0"),
    ("Data Science Fresher", "https://www.naukri.com/data-science-fresher-jobs-in-bangalore?experience=0"),
    ("Backend Developer Fresher", "https://www.naukri.com/python-backend-developer-fresher-jobs?experience=0"),
]


class NaukriSource(SourceAdapter):
    """Naukri.com — India largest job portal (RSS feed approach, no auth needed)."""
    name, policy = "naukri", "public_rss"

    @with_retry(2)
    async def _fetch_rss(self, client: httpx.AsyncClient, url: str, feed_name: str) -> list[NormalizedJob]:
        try:
            r = await client.get(url, timeout=12)
            if r.status_code != 200:
                return []
            # Parse RSS XML
            root = ET.fromstring(r.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//item")
            out = []
            for item in items:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()

                # Naukri RSS description has minimal info - extract company if present
                company = "Company"
                import re
                comp_match = re.search(r"Company:\s*([^\|<\n]+)", desc, re.IGNORECASE)
                if comp_match:
                    company = comp_match.group(1).strip()

                loc_match = re.search(r"(?:Location|City):\s*([^\|<\n]+)", desc, re.IGNORECASE)
                loc = loc_match.group(1).strip() if loc_match else "Bengaluru, India"

                exp_match = re.search(r"Experience:\s*([^\|<\n]+)", desc, re.IGNORECASE)
                exp = exp_match.group(1).strip() if exp_match else "Fresher"

                if not title or not link:
                    continue

                # Clean description
                desc_clean = re.sub(r"<[^>]+>", " ", desc)
                desc_clean = re.sub(r"\s{2,}", " ", desc_clean).strip()[:900]

                out.append(NormalizedJob(
                    source="naukri",
                    source_job_id=link,
                    title=title,
                    company=company,
                    location=loc,
                    work_mode="Office / Hybrid (India)",
                    description=desc_clean or f"{title} — {exp} experience, {loc}",
                    job_url=link,
                    skills=["Python"],
                    posted_at=pub_date or "Recent (Naukri)",
                ))
            return out
        except Exception as e:
            log.debug("Naukri RSS '%s' error: %s", feed_name, e)
            return []

    async def discover(self, query: str) -> list[NormalizedJob]:
        seen: set[str] = set()
        all_jobs: list[NormalizedJob] = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            tasks = [self._fetch_rss(client, url, name) for url, name in NAUKRI_RSS_FEEDS]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    for j in res:
                        if j.job_url and j.job_url not in seen:
                            seen.add(j.job_url)
                            all_jobs.append(j)

        log.info("Naukri RSS returned %d jobs", len(all_jobs))
        return all_jobs

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=8) as c:
                r = await c.get(NAUKRI_RSS_FEEDS[0][0])
                return r.status_code == 200
        except Exception:
            return False
