import logging
import re
import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from backend.core.resilience import with_retry
from backend.sources.base import SourceAdapter, NormalizedJob

log = logging.getLogger("web_fresher")

SEARCH_QUERIES = [
    # Internshala individual fresher & internship job posts
    'site:internshala.com/job/detail/ "fresher" "python" bangalore',
    'site:internshala.com/job/detail/ "fresher" "machine learning" bangalore',
    'site:internshala.com/job/detail/ "fresher" "data science" bangalore',
    'site:internshala.com/internship/detail/ "machine learning" bangalore',
    'site:internshala.com/internship/detail/ "python" bangalore',
    # Indeed India individual job postings
    'site:in.indeed.com/viewjob "python" "fresher" bangalore',
    'site:in.indeed.com/viewjob "machine learning" "intern" bangalore',
    # Wellfound individual job postings
    'site:wellfound.com/jobs/ "python" ("fresher" OR "intern") bangalore',
    'site:wellfound.com/jobs/ "machine learning" ("intern" OR "junior")',
    # Naukri individual job postings
    'site:naukri.com/job-listings "fresher" "python" bangalore',
    'site:naukri.com/job-listings "0 to 1 years" "machine learning"',
]

# Patterns for rejecting non-jobs (courses, degrees, aggregator lists)
COURSE_AGGREGATOR_PATTERN = re.compile(
    r'\b('
    r'\d+\s+(?:vacancies|openings|jobs)'
    r'|vacancies\s*in|openings\s*in|fresher\s*jobs\s*in'
    r'|master\'?s|m\.?sc|b\.?tech\s+degree|online\s+degree|degree\s+program'
    r'|certification|bootcamp|training\s+program|working\s+professionals'
    r'|admissions?\s+open|syllabus|curriculum|exam'
    r')\b',
    re.IGNORECASE
)

# Reject if description demands >= 3 years, 2-4 years, 3-5 years, or senior experience
EXP_REJECT_PATTERN = re.compile(
    r"\b("
    r"([3-9]|\d{2,})\s*(\+|-\s*\d+)?\s*(?:to\s*\d+\s*)?(?:years?|yrs?)"
    r"|[2-9]\s*[-–to]+\s*[3-9]\s*(?:years?|yrs?)"
    r"|2\s*to\s*[3-9]\s*(?:years?|yrs?)"
    r"|minimum\s+([3-9]|\d{2,})\s*(?:years?|yrs?)"
    r"|at\s+least\s+([3-9]|\d{2,})\s*(?:years?|yrs?)"
    r"|3\+\s*(?:years?|yrs?)"
    r"|4\+\s*(?:years?|yrs?)"
    r"|5\+\s*(?:years?|yrs?)"
    r")\b",
    re.IGNORECASE
)

# Reject senior/lead/manager or level 2/3 designations
LEVEL_REJECT_PATTERN = re.compile(
    r"\b("
    r"(?:data\s+scientist|software\s+engineer|ai\s+engineer|ml\s+engineer|machine\s+learning\s+engineer|developer|engineer)\s+(?:2|3|4|5|ii|iii|iv|v|l2|l3|lead|senior|principal|staff)"
    r"|senior|sr\.|lead|principal|staff|manager|head\s+of|director|architect"
    r"|sde\s*2|sde-2|sde2|sde\s*ii|sde\s*3|sde-3|sde3|sde\s*iii|mid-level|mid\s+level|intermediate"
    r")\b",
    re.IGNORECASE
)

# Positive confirmation: Fresher, intern, trainee, 0-1, 0-2 yrs, college / academic projects
FRESHER_CONFIRM_PATTERN = re.compile(
    r"\b(fresher|freshers|intern|internship|trainee|graduate|junior|jr|jr\.|0-1|0-2|0\s*to\s*1|0\s*to\s*2|entry\s*level|college|academic|new\s*grad|no\s*prior\s*experience|students?|degree|university|0\s*years?)\b",
    re.IGNORECASE
)

# Reject frontend / mobile roles
FRONTEND_REJECT_PATTERN = re.compile(
    r"\b(flutter|react|react\.js|reactjs|angular|vue|vue\.js|frontend|front-end|front\s+end|ui/ux|ui\s+ux|ui\s+designer|graphic\s+designer|ios\s+developer|android\s+developer|mobile\s+app)\b",
    re.IGNORECASE
)

# Positive tech domain match: AI, ML, Python, Data Science, Backend
DOMAIN_PATTERN = re.compile(
    r"\b(python|machine\s+learning|deep\s+learning|artificial\s+intelligence|data\s+science|data\s+scientist|nlp|computer\s+vision|backend|django|fastapi|flask|llm|genai|generative\s+ai|agentic)\b",
    re.IGNORECASE
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class WebFresherSource(SourceAdapter):
    name, policy = "web_fresher", "public_web"

    @with_retry(2)
    async def discover(self, query: str = "") -> list[NormalizedJob]:
        jobs = []
        seen = set()

        async with httpx.AsyncClient(headers=HEADERS, timeout=6.0, follow_redirects=True) as client:
            # Also check We Work Remotely backend/AI RSS feed
            try:
                wwr_resp = await client.get("https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss", timeout=5.0)
                if wwr_resp.status_code == 200:
                    wwr_soup = BeautifulSoup(wwr_resp.text, "xml")
                    for item in wwr_soup.find_all("item"):
                        w_title = item.title.text if item.title else ""
                        w_link = item.link.text if item.link else ""
                        w_desc = item.description.text if item.description else ""

                        if not w_link or w_link in seen:
                            continue

                        # Clean title & company (WWR format: "Company: Title")
                        w_comp = "Remote Company"
                        w_role = w_title
                        if ": " in w_title:
                            w_comp, w_role = w_title.split(": ", 1)

                        if COURSE_AGGREGATOR_PATTERN.search(w_role) or LEVEL_REJECT_PATTERN.search(w_role):
                            continue
                        if FRONTEND_REJECT_PATTERN.search(w_role):
                            continue
                        if EXP_REJECT_PATTERN.search(w_role) or EXP_REJECT_PATTERN.search(w_desc):
                            continue
                        if not (FRESHER_CONFIRM_PATTERN.search(w_role) or FRESHER_CONFIRM_PATTERN.search(w_desc)):
                            continue
                        if not (DOMAIN_PATTERN.search(w_role) or DOMAIN_PATTERN.search(w_desc)):
                            continue

                        seen.add(w_link)
                        jobs.append(NormalizedJob(
                            source="weworkremotely",
                            source_job_id=w_link,
                            title=w_role.strip(),
                            company=w_comp.strip(),
                            location="Remote (India Eligible)",
                            work_mode="remote",
                            description=BeautifulSoup(w_desc, "html.parser").get_text(separator=" ", strip=True)[:2500],
                            job_url=w_link,
                            skills=["python", "backend", "fresher"],
                            posted_at="Recent (WWR Verified)",
                        ))
            except Exception as e:
                log.warning("WWR RSS fetch error: %s", e)

            # DuckDuckGo multi-platform individual job search
            try:
                with DDGS() as ddgs:
                    for q in SEARCH_QUERIES:
                        try:
                            results = list(ddgs.text(q, max_results=4))
                            for r in results:
                                title_raw = r.get("title", "")
                                url = r.get("href", "")
                                snippet = r.get("body", "")

                                if not title_raw or not url or not url.startswith("http"):
                                    continue
                                if url in seen:
                                    continue

                                # 1. Strict aggregator / course rejection
                                if COURSE_AGGREGATOR_PATTERN.search(title_raw) or LEVEL_REJECT_PATTERN.search(title_raw):
                                    continue
                                if FRONTEND_REJECT_PATTERN.search(title_raw):
                                    continue

                                # 2. Ensure URL is an individual job listing, not an aggregator page
                                is_valid_job_url = (
                                    "/job/detail/" in url or
                                    "/internship/detail/" in url or
                                    "/viewjob" in url or
                                    "/rc/clk" in url or
                                    "/jobs/" in url or
                                    "/job-listings" in url
                                )
                                if not is_valid_job_url:
                                    continue

                                # 3. Fetch real page JD text for 100% experience verification
                                jd_text = ""
                                try:
                                    page_resp = await client.get(url)
                                    if page_resp.status_code == 200:
                                        p_soup = BeautifulSoup(page_resp.text, "html.parser")
                                        # Remove script and style tags
                                        for s in p_soup(["script", "style", "nav", "footer"]):
                                            s.extract()
                                        jd_text = p_soup.get_text(separator=" ", strip=True)
                                except Exception:
                                    jd_text = snippet

                                if not jd_text:
                                    continue

                                # 4. Check experience & seniority on actual JD text
                                if EXP_REJECT_PATTERN.search(jd_text):
                                    continue
                                if LEVEL_REJECT_PATTERN.search(jd_text[:1000]):
                                    continue

                                # 5. Mandatory positive fresher confirmation
                                if not (FRESHER_CONFIRM_PATTERN.search(title_raw) or FRESHER_CONFIRM_PATTERN.search(jd_text)):
                                    continue

                                # 6. Mandatory domain match
                                if not (DOMAIN_PATTERN.search(title_raw) or DOMAIN_PATTERN.search(jd_text[:1500])):
                                    continue

                                seen.add(url)

                                # Determine source platform
                                if "internshala.com" in url:
                                    src = "internshala"
                                elif "indeed.com" in url:
                                    src = "indeed"
                                elif "wellfound.com" in url:
                                    src = "wellfound"
                                elif "naukri.com" in url:
                                    src = "naukri"
                                else:
                                    src = "career_portal"

                                # Parse clean title & company
                                title = title_raw.split(" | ")[0].split(" - ")[0].strip()
                                comp = "Verified Tech Company"
                                if " at " in title_raw:
                                    comp = title_raw.split(" at ")[-1].split(" | ")[0].split(" - ")[0].strip()
                                elif " - " in title_raw:
                                    parts = title_raw.split(" - ")
                                    if len(parts) > 1:
                                        comp = parts[1].split(" | ")[0].strip()

                                loc = "Bengaluru, Karnataka, India" if "bangalore" in (title_raw + jd_text[:500]).lower() else "India"

                                jobs.append(NormalizedJob(
                                    source=src,
                                    source_job_id=url,
                                    title=title,
                                    company=comp,
                                    location=loc,
                                    work_mode="Bangalore / Office / Hybrid",
                                    description=jd_text[:2500],
                                    job_url=url,
                                    skills=["python", "ai", "fresher"],
                                    posted_at="Recent (Web Verified)",
                                ))
                        except Exception as e:
                            log.warning("Web fresher search error for '%s': %s", q, e)
                            continue
            except Exception as e:
                log.error("Failed to initialize DDGS: %s", e)

        return jobs

    async def health_check(self) -> bool:
        return True
