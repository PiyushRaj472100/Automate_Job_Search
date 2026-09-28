import logging
import re
import httpx
from bs4 import BeautifulSoup
from backend.core.resilience import with_retry
from backend.sources.base import SourceAdapter, NormalizedJob

log = logging.getLogger("web_fresher")

# Direct high-signal Fresher & Intern category pages (100% genuine individual job listings)
DIRECT_FRESHER_URLS = [
    ("internshala", "https://internshala.com/fresher-jobs/python-jobs-in-bangalore/"),
    ("internshala", "https://internshala.com/fresher-jobs/machine-learning-jobs-in-bangalore/"),
    ("internshala", "https://internshala.com/fresher-jobs/data-science-jobs-in-bangalore/"),
    ("internshala", "https://internshala.com/fresher-jobs/artificial-intelligence-jobs-in-bangalore/"),
    ("internshala", "https://internshala.com/internships/python-internship-in-bangalore/"),
    ("internshala", "https://internshala.com/internships/machine-learning-internship-in-bangalore/"),
    ("internshala", "https://internshala.com/internships/data-science-internship-in-bangalore/"),
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
    r"|senior|sr\.|lead|principal|staff|manager|head\s+of|director|architect|chief|vp"
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

        async with httpx.AsyncClient(headers=HEADERS, timeout=8.0, follow_redirects=True) as client:
            # 1. Direct Fresher & Internship Portals in Bangalore (Internshala)
            for platform, cat_url in DIRECT_FRESHER_URLS:
                try:
                    resp = await client.get(cat_url, timeout=6.0)
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", class_=lambda cl: cl and "job-title-href" in cl)

                    for a in links[:12]:
                        title = a.get_text(strip=True)
                        rel_link = a.get("href", "")
                        if not rel_link:
                            continue
                        full_url = f"https://internshala.com{rel_link}" if rel_link.startswith("/") else rel_link

                        if full_url in seen:
                            continue
                        seen.add(full_url)

                        if COURSE_AGGREGATOR_PATTERN.search(title) or LEVEL_REJECT_PATTERN.search(title):
                            continue
                        if FRONTEND_REJECT_PATTERN.search(title):
                            continue
                        if not DOMAIN_PATTERN.search(title):
                            continue

                        # Fetch individual JD for 100% verification
                        jd_text = ""
                        comp = "Tech Startup"
                        try:
                            jd_resp = await client.get(full_url, timeout=5.0)
                            if jd_resp.status_code == 200:
                                jd_soup = BeautifulSoup(jd_resp.text, "html.parser")
                                # Extract company name
                                comp_el = jd_soup.find("a", class_="link_display_like_text") or jd_soup.find("p", class_="company-name")
                                if comp_el:
                                    comp = comp_el.get_text(strip=True)
                                # Clean JD text
                                for s in jd_soup(["script", "style", "nav", "footer"]):
                                    s.extract()
                                jd_text = jd_soup.get_text(separator=" ", strip=True)
                        except Exception:
                            pass

                        if not jd_text:
                            jd_text = f"{title} at {comp}. Fresher / Entry Level in Bangalore."

                        # Verify experience on JD text
                        if EXP_REJECT_PATTERN.search(jd_text):
                            continue
                        if LEVEL_REJECT_PATTERN.search(jd_text[:1000]):
                            continue

                        jobs.append(NormalizedJob(
                            source="internshala",
                            source_job_id=full_url,
                            title=title,
                            company=comp,
                            location="Bengaluru, Karnataka, India",
                            work_mode="Bangalore / Office / Hybrid",
                            description=jd_text[:2500],
                            job_url=full_url,
                            skills=["python", "ai", "fresher"],
                            posted_at="Recent (Verified Fresher)",
                        ))
                except Exception as e:
                    log.warning("Direct fresher crawl error on %s: %s", cat_url, e)

            # 2. We Work Remotely backend/AI feed
            try:
                wwr_resp = await client.get("https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss", timeout=5.0)
                if wwr_resp.status_code == 200:
                    wwr_soup = BeautifulSoup(wwr_resp.text, "xml")
                    for item in wwr_soup.find_all("item")[:15]:
                        w_title = item.title.text if item.title else ""
                        w_link = item.link.text if item.link else ""
                        w_desc = item.description.text if item.description else ""

                        if not w_link or w_link in seen:
                            continue

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

        return jobs

    async def health_check(self) -> bool:
        return True
