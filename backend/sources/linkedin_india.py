import urllib.parse
import httpx
from bs4 import BeautifulSoup
from backend.core.resilience import with_retry
from backend.sources.base import SourceAdapter, NormalizedJob

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


class LinkedInIndiaSource(SourceAdapter):
    name, policy = "linkedin_india", "public_web"

    @with_retry(2)
    async def _search(self, keywords: str, location: str = "Bengaluru") -> list[NormalizedJob]:
        params = {
            "keywords": keywords,
            "location": location,
            "sortBy": "DD",       # Most recent postings first
            "f_TPR": "r86400",     # Past 24 hours for fresh openings
            "f_E": "1,2",          # 1 = Internship, 2 = Entry level
            "start": 0,
        }
        async with httpx.AsyncClient(headers=HEADERS, timeout=8, follow_redirects=True) as client:
            r = await client.get(BASE_URL, params=params)
            if r.status_code != 200:
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.find_all("li")
            jobs = []

            for c in cards:
                title_el = c.find("h3", class_="base-search-card__title")
                comp_el = c.find("h4", class_="base-search-card__subtitle")
                loc_el = c.find("span", class_="job-search-card__location")
                link_el = c.find("a", class_="base-card__full-link")
                time_el = c.find("time")

                if not title_el or not comp_el or not link_el:
                    continue

                title = title_el.get_text(strip=True)
                company = comp_el.get_text(strip=True)
                loc = loc_el.get_text(strip=True) if loc_el else location
                job_url = link_el.get("href", "").split("?")[0]  # clean tracking params
                posted_time = time_el.get_text(strip=True) if time_el else "Recent (Past 24h)"

                if not job_url.startswith("http"):
                    continue

                jobs.append(NormalizedJob(
                    source="linkedin_india",
                    source_job_id=job_url,
                    title=title,
                    company=company,
                    location=loc,
                    work_mode="Bangalore / Office / Hybrid",
                    description=f"{title} at {company} in {loc}. Entry level / Fresher opportunity. Posted: {posted_time}.",
                    job_url=job_url,
                    skills=[keywords],
                    posted_at=posted_time,
                ))

            return jobs

    async def discover(self, query: str) -> list[NormalizedJob]:
        try:
            return await self._search(keywords=query, location="Bengaluru")
        except Exception:
            return []

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=10) as c:
                r = await c.get(BASE_URL, params={"keywords": "python", "location": "Bengaluru", "f_E": "2"})
                return r.status_code == 200
        except Exception:
            return False
