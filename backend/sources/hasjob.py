import xml.etree.ElementTree as ET
import httpx
from backend.core.resilience import with_retry
from backend.sources.base import SourceAdapter, NormalizedJob

HASJOB_FEED = "https://hasjob.co/feed"


class HasjobSource(SourceAdapter):
    name, policy = "hasjob_india", "public_feed"

    @with_retry(2)
    async def _fetch_feed(self) -> list[NormalizedJob]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(HASJOB_FEED)
            if r.status_code != 200:
                return []

            root = ET.fromstring(r.text)
            entries = root.findall("{http://www.w3.org/2005/Atom}entry")
            jobs = []

            for e in entries:
                title_el = e.find("{http://www.w3.org/2005/Atom}title")
                link_el = e.find("{http://www.w3.org/2005/Atom}link")
                content_el = e.find("{http://www.w3.org/2005/Atom}content")

                title = title_el.text if title_el is not None and title_el.text else ""
                job_url = link_el.attrib.get("href", "") if link_el is not None else ""
                desc = content_el.text if content_el is not None and content_el.text else ""

                if not title or not job_url:
                    continue

                # Parse company domain from hasjob url (e.g. https://hasjob.co/company.com/xxx)
                parts = job_url.replace("https://hasjob.co/", "").split("/")
                comp = parts[0] if parts else "Startup"
                comp_clean = comp.split(".")[0].capitalize()

                jobs.append(NormalizedJob(
                    source="hasjob_india",
                    source_job_id=job_url,
                    title=title,
                    company=comp_clean,
                    location="Bengaluru / India (Remote)",
                    work_mode="Bangalore / Remote",
                    description=desc[:500] if desc else title,
                    job_url=job_url,
                    skills=["tech", "python", "ai"]
                ))

            return jobs

    async def discover(self, query: str) -> list[NormalizedJob]:
        all_jobs = await self._fetch_feed()
        q_terms = [t.lower() for t in query.split() if t]
        if not q_terms:
            return all_jobs

        matched = []
        for j in all_jobs:
            hay = f"{j.title} {j.description} {j.company}".lower()
            if any(t in hay for t in q_terms):
                matched.append(j)
        return matched

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(HASJOB_FEED)
                return r.status_code == 200
        except Exception:
            return False
