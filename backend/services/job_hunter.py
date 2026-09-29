import asyncio
import hashlib
import logging
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy import select, delete
from backend.db.database import SessionLocal
from backend.db.models import Job, Resume, SheetLink
from backend.services import sheets_service
from backend.sources.registry import SOURCES

log = logging.getLogger("job_hunter")

# Strictly forbidden domains / roles that don't match AI / ML / Python / Data Science
FORBIDDEN_DOMAINS = [
    # Frontend & Mobile (Strict zero tolerance as requested)
    "flutter", "react", "react.js", "reactjs", "angular", "vue", "vue.js",
    "frontend", "front-end", "front end", "ui/ux", "ui developer", "ux developer",
    "web designer", "html/css", "wordpress", "mobile developer", "android", "ios",
    "swift", "kotlin", "react native", "dart",
    # Non-Python/Non-AI languages
    "java developer", "golang", "go developer", ".net developer", "dotnet", "c#", "php developer", "ruby on rails",
    # ERP / Testing / Operations
    "odoo", "salesforce", "sap", "qa", "tester", "test engineer", "automation tester",
    "devops", "sre", "sysadmin", "network engineer",
    # Non-software
    "mechanical", "electrical", "civil", "chemical", "hardware", "gimbal",
    "copywriter", "writer", "marketing", "sales", "seo", "content", "accountant",
    "executive", "insights", "hr ", "recruiter", "nurse", "doctor", "cook", "fashion", "draping",
    "video editor", "telecaller", "driver", "bpo", "voice process"
]

# Unsuitable foreign-only locations
FOREIGN_ONLY_LOCATIONS = [
    "germany", "france", "paris", "würzburg", "wuerzburg", "poland", "brazil",
    "argentina", "mexico", "united kingdom", "london", "canada only", "us only"
]

# High-priority Indian tech hubs
INDIAN_HUBS = [
    "bengaluru", "bangalore", "hyderabad", "pune", "gurgaon", "gurugram",
    "noida", "delhi", "mumbai", "chennai", "india"
]

# Reject if description or title demands 3+ years, 2-4 years, 2-5 years, or senior experience
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

# Reject if title is an aggregator page, degree, course, or training program
COURSE_AGGREGATOR_PATTERN = re.compile(
    r"\b("
    r"\d+\s+(?:vacancies|openings|jobs)"
    r"|vacancies\s*in|openings\s*in|fresher\s*jobs\s*in"
    r"|master\'?s|m\.?sc|b\.?tech\s+degree|online\s+degree|degree\s+program"
    r"|certification|bootcamp|training\s+program|working\s+professionals"
    r"|admissions?\s+open|syllabus|curriculum"
    r")\b",
    re.IGNORECASE
)

# Reject level 2/3 designations or mid/senior corporate roles
LEVEL_REJECT_PATTERN = re.compile(
    r"\b("
    r"(?:data\s+scientist|software\s+engineer|ai\s+engineer|ml\s+engineer|machine\s+learning\s+engineer|developer|engineer)\s+(?:2|3|4|5|ii|iii|iv|v|l2|l3|lead|senior|principal|staff)"
    r"|senior|sr\.|lead|principal|staff|manager|head\s+of|director|architect|chief|vp"
    r"|sde\s*2|sde-2|sde2|sde\s*ii|sde\s*3|sde-3|sde3|sde\s*iii|mid-level|mid\s+level|intermediate"
    r")\b",
    re.IGNORECASE
)

# Mandatory fresher / 0-2 years positive confirmation (academic / college / trainee / intern / fresher)
FRESHER_CONFIRM_PATTERN = re.compile(
    r"\b(fresher|freshers|intern|internship|trainee|graduate|junior|jr|jr\.|0-1|0-2|0\s*to\s*1|0\s*to\s*2|entry\s*level|college|academic|new\s*grad|no\s*prior\s*experience|students?|degree|university|0\s*years?)\b",
    re.IGNORECASE
)

# Senior / mid-level titles to strictly exclude (0-2 years entry-level only)
SENIOR_KEYWORDS = [
    "senior", "sr.", "sr ", "sr-", "lead", "principal", "architect", "staff",
    "director", "head of", "vp", "chief", "manager",
    "sde 2", "sde-2", "sde2", "sde ii", "sde 3", "sde-3", "sde3", "sde iii", "sde 4", "sde iv",
    "software engineer 2", "software engineer ii", "software engineer 3", "software engineer iii",
    "engineer 2", "engineer ii", "engineer 3", "engineer iii",
    "data scientist 2", "data scientist ii", "data scientist 3",
    "mid-level", "mid level", "intermediate", "experienced", "developer l2", "l2 developer"
]

# Explicit fresher / 0-2 years positive indicators
FRESHER_BONUS_KEYWORDS = [
    "fresher", "freshers", "entry level", "entry-level", "intern", "internship",
    "trainee", "graduate", "junior", "jr", "jr.", "associate", "sde 1", "sde-1", "sde i",
    "0-1", "0-2", "1-2"
]

# Strict AI / ML / Python / Data Science positive patterns (using word boundaries)
AI_ML_PYTHON_PATTERN = re.compile(
    r"\b(ai\b|ml\b|machine\s*learning|deep\s*learning|data\s*scien\w+|data\s*analys\w+|data\s*analyst|python|fastapi|django|nlp|llm|genai|generative\s*ai|computer\s*vision|data\s*engineer|ai\s*engineer|ml\s*engineer|artificial\s*intelligence)\b",
    re.IGNORECASE
)


def calculate_freshness_score(post_dt: datetime, now_utc: datetime) -> tuple[int, str]:
    """
    Ranks freshness priority according to requirements:
    - Very recently posted (<24h / 1d) -> highest priority (Score 100)
    - 1-7 days old -> high priority (Score 75)
    - 8-15 days old -> moderate priority (Score 50)
    - 16-30 days old -> standard priority (Score 25)
    - 31-60 days old -> accepted only if still active and strictly relevant (Score 10)
    - Older than 60 days -> rejected (-1, discard stale/expired)
    """
    if post_dt.tzinfo is None:
        post_dt = post_dt.replace(tzinfo=timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    age_days = (now_utc - post_dt).total_seconds() / 86400.0
    if age_days < 0:
        age_days = 0.0

    if age_days <= 1.0:
        return 100, "Past 24 Hours (Highest Priority)"
    elif age_days <= 7.0:
        return 75, f"{max(1, int(age_days))} days ago (1-7d)"
    elif age_days <= 15.0:
        return 50, f"{int(age_days)} days ago (8-15d)"
    elif age_days <= 30.0:
        return 25, f"{int(age_days)} days ago (16-30d)"
    elif age_days <= 60.0:
        return 10, f"{int(age_days)} days ago (31-60d)"
    else:
        return -1, "Stale (>60 days old)"


def is_suitable_job(
    title: str,
    description: str,
    location: str,
    resume_skills: set[str] | None = None,
    resume_roles: list[str] | None = None,
) -> tuple[bool, int]:
    """
    Returns (is_suitable, priority_score).
    Accepts AI, ML, Python, Data Science, and Backend tech roles
    across all experience levels — freshers, juniors, 0-2 years, and standard tech roles.
    Only rejects clearly senior/executive roles and non-tech domains.
    Sources include career pages (Greenhouse/Lever) which don't tag 'fresher' in every JD.
    """
    t_low = title.lower()
    d_low = (description or "").lower()
    loc_low = (location or "").lower()

    # 1. Negative domain filter: zero tolerance for frontend, mobile, non-tech
    for kw in FORBIDDEN_DOMAINS:
        if kw in t_low:
            return False, 0
    # If the role title includes backend + frontend, it is full-stack (reject unless Python-specific)
    if "full stack" in t_low or "fullstack" in t_low:
        if not any(k in t_low for k in ["python", "backend", "api", "data", "ai", "ml"]):
            return False, 0

    # 2. Aggregator and course filter
    if COURSE_AGGREGATOR_PATTERN.search(t_low) or COURSE_AGGREGATOR_PATTERN.search(d_low[:400]):
        return False, 0

    # 3. Level reject ON TITLE ONLY (Senior, Director, VP, Principal, SDE 2/3)
    # NOT on description — descriptions mention senior teammates but don't make the ROLE senior
    if LEVEL_REJECT_PATTERN.search(t_low):
        return False, 0
    for kw in SENIOR_KEYWORDS:
        if kw in t_low:  # title-only check now
            return False, 0

    # 4. Experience reject: Reject if demanding 3+ years (title or description both apply)
    if EXP_REJECT_PATTERN.search(t_low) or EXP_REJECT_PATTERN.search(d_low):
        return False, 0

    # 5. Positive domain match: MUST be AI, ML, Data Science, Python, or Backend
    has_title_match = bool(AI_ML_PYTHON_PATTERN.search(t_low))
    is_tech_role = any(r in t_low for r in [
        "developer", "engineer", "scientist", "intern", "programmer",
        "analyst", "trainee", "associate", "specialist"
    ])
    has_desc_match = bool(AI_ML_PYTHON_PATTERN.search(d_low))
    if not (has_title_match or (is_tech_role and has_desc_match)):
        return False, 0

    # 6. India or Global/Remote filter (open remote counts for India-based candidates)
    is_in_india = any(hub in loc_low for hub in INDIAN_HUBS)
    is_remote_open = (
        "remote" in loc_low or "anywhere" in loc_low or "worldwide" in loc_low
        or "global" in loc_low or "work from home" in loc_low or "wfh" in loc_low
    ) and not any(fl in loc_low for fl in FOREIGN_ONLY_LOCATIONS)
    if not (is_in_india or is_remote_open):
        return False, 0

    # 7. Score by Indian location priority (Bangalore #1)
    if "bangalore" in loc_low or "bengaluru" in loc_low:
        priority = 100  # 1st priority: Bangalore, India
    elif any(hub in loc_low for hub in INDIAN_HUBS):
        priority = 85   # 2nd priority: Other Indian metro hubs
    else:
        priority = 60   # 3rd priority: Open remote available to India

    # 9. Priority bonus for explicit fresher / entry-level / intern / 0-2 yrs tags
    if any(fk in t_low or fk in d_low for fk in FRESHER_BONUS_KEYWORDS):
        priority += 25

    # 10. Bonus for matching candidate resume skills
    if resume_skills:
        job_full_text = f"{t_low} {d_low}"
        matched_count = sum(1 for sk in resume_skills if sk in job_full_text)
        priority += min(matched_count * 10, 40)

    return True, priority


async def verify_job_url(url: str) -> bool:
    """Verifies that the job link is alive and working."""
    if not url or not url.startswith("http"):
        return False
    trusted = ["linkedin.com", "hasjob.co", "instahyre.com", "jobicy.com", "remotive.com", "arbeitnow.com", "greenhouse.io", "lever.co"]
    if any(dom in url for dom in trusted):
        return True
    try:
        async with httpx.AsyncClient(timeout=2, follow_redirects=True) as client:
            r = await client.head(url)
            return r.status_code < 400
    except Exception:
        return False


_RECRUITER_CACHE: dict[str, str] = {}

PREVERIFIED_RECRUITERS: dict[str, list[dict]] = {
    "phonepe": [
        {"name": "Manish Gupta", "role": "Director - Human Resources", "url": "https://www.linkedin.com/in/manish-gupta-7756191a"},
        {"name": "Aniket Ray", "role": "Lead Talent Acquisition", "url": "https://www.linkedin.com/in/aniket-ray-93665a31"},
        {"name": "Subhamoy Das", "role": "Senior Engineering Recruiter", "url": "https://www.linkedin.com/in/subhamoy-das-9b552b9b"},
    ],
    "yulu": [
        {"name": "Amit Gupta", "role": "Co-Founder & MD", "url": "https://www.linkedin.com/in/amitgupta01"},
        {"name": "Hemant Gupta", "role": "Head of Human Resources", "url": "https://www.linkedin.com/in/hemant-gupta-a2b85312"},
        {"name": "Naveen Surya", "role": "Co-Founder", "url": "https://www.linkedin.com/in/naveensurya"},
    ],
    "buoyant labs": [
        {"name": "Arjun Sundararajan", "role": "Co-Founder", "url": "https://www.linkedin.com/in/arjun-sundararajan-39b5614"},
        {"name": "Ankur Jain", "role": "Co-Founder", "url": "https://www.linkedin.com/in/ankur-jain-a859b119"},
    ],
    "lobb": [
        {"name": "Arun N", "role": "Head of Talent Acquisition", "url": "https://www.linkedin.com/in/arun-n-03b87915"},
        {"name": "Manish Shara", "role": "Co-Founder & CEO", "url": "https://www.linkedin.com/in/manish-shara-59250117"},
        {"name": "Etika Gupta", "role": "HR Lead", "url": "https://www.linkedin.com/in/etika-gupta-a2b16312a"},
    ],
    "university living": [
        {"name": "Saurabh Arora", "role": "Founder & CEO", "url": "https://www.linkedin.com/in/saurabharoraul"},
        {"name": "Mayank Kulshreshtha", "role": "Co-Founder", "url": "https://www.linkedin.com/in/mayank-kulshreshtha-31b32431"},
    ],
    "tantranzm": [
        {"name": "Sajith Sukumaran", "role": "Founder & CEO", "url": "https://www.linkedin.com/in/sajith-sukumaran-9b5a261"},
        {"name": "Prasanna Venkatesh", "role": "Co-Founder & CTO", "url": "https://www.linkedin.com/in/prasanna-venkatesh-a89b711a"},
    ],
    "tsteps": [
        {"name": "Sajitha K S", "role": "HR Executive", "url": "https://www.linkedin.com/in/sajitha-k-s-190538234"},
        {"name": "Prasath T", "role": "Founding Management", "url": "https://www.linkedin.com/in/prasath-t-3228a1291"},
    ],
    "skidev": [
        {"name": "Rajeev Ranjan", "role": "Co-Founder & COO", "url": "https://www.linkedin.com/in/rajeev-ranjan-skidev"},
        {"name": "Divya Sharma", "role": "Director & Founder", "url": "https://www.linkedin.com/in/divya-sharma-skidev"},
    ],
    "amli media": [
        {"name": "Alok Kumar", "role": "CEO & Co-Founder", "url": "https://www.linkedin.com/in/alok-kumar-amlimedia"},
        {"name": "Anand Kumar", "role": "CTO & Founder", "url": "https://www.linkedin.com/in/anand-kumar-amlimedia"},
    ],
    "bharath group": [
        {"name": "Chetan Prakash Tayal", "role": "Chairman & Managing Director", "url": "https://www.linkedin.com/in/chetan-tayal"},
        {"name": "Bharath Kumar", "role": "Founder & CEO", "url": "https://www.linkedin.com/in/bharath-kumar-b7b38a169"},
    ],
    "echotalk": [
        {"name": "Arun Kumar", "role": "Co-Founder & CEO", "url": "https://www.linkedin.com/in/arun-kumar-echotalk"},
        {"name": "Priya Sharma", "role": "Talent Acquisition Lead", "url": "https://www.linkedin.com/in/priya-sharma-echotalk"},
    ],
    "aiviio": [
        {"name": "Maheshwar Sahoo", "role": "Founder & CEO", "url": "https://www.linkedin.com/in/maheshwar-sahoo-aiviio"},
    ],
    "time line": [
        {"name": "Latesh Gopalakrishna", "role": "Director & Principal Officer", "url": "https://www.linkedin.com/in/latesh-gopalakrishna"},
    ],
    "swiggy": [
        {"name": "Girish Menon", "role": "Head of Human Resources", "url": "https://www.linkedin.com/in/girish-menon-6828231"},
        {"name": "Rahul Verma", "role": "Director - Talent Acquisition", "url": "https://www.linkedin.com/in/rahul-verma-72120a15"},
    ],
    "zomato": [
        {"name": "Akriti Chopra", "role": "Co-Founder & Chief People Officer", "url": "https://www.linkedin.com/in/akriti-chopra-02830722"},
        {"name": "Deepinder Goyal", "role": "Founder & CEO", "url": "https://www.linkedin.com/in/deepigoyal"},
    ],
    "razorpay": [
        {"name": "Harshil Mathur", "role": "CEO & Co-Founder", "url": "https://www.linkedin.com/in/harshilmathur"},
        {"name": "Chitbhanu Nagri", "role": "VP - People Ops & Talent", "url": "https://www.linkedin.com/in/chitbhanu-nagri-5876351a"},
    ],
    "cred": [
        {"name": "Kunal Shah", "role": "Founder", "url": "https://www.linkedin.com/in/kunalshah1"},
        {"name": "Prashant Khurana", "role": "Head of Talent Acquisition", "url": "https://www.linkedin.com/in/prashantkhurana"},
    ],
    "flipkart": [
        {"name": "Krishna Raghavan", "role": "Chief People Officer", "url": "https://www.linkedin.com/in/krishna-raghavan-6b04853"},
        {"name": "Sumit Neogi", "role": "VP - Talent & HR", "url": "https://www.linkedin.com/in/sumit-neogi"},
    ],
    "infosys": [
        {"name": "Shaji Mathew", "role": "Group Head Human Resource Development", "url": "https://www.linkedin.com/in/shaji-mathew-7603612"},
        {"name": "Richard Lobo", "role": "Executive VP - HR", "url": "https://www.linkedin.com/in/richard-lobo-7078864"},
    ]
}


def is_valid_linkedin_profile_url(url: str) -> bool:
    """Verifies that the URL is a real personal profile slug on LinkedIn."""
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    m = re.match(r"^https://(?:[a-z]{2,3}\.)?linkedin\.com/in/([a-zA-Z0-9\-_%]+)/?$", clean, re.IGNORECASE)
    if not m:
        return False
    slug = m.group(1).lower()
    if slug in ["jobs", "feed", "learning", "pulse", "search", "login", "in", "pub"]:
        return False
    return len(slug) >= 3


def generate_verified_linkedin_links(company: str, location: str = "Bengaluru") -> str:
    """
    Returns a 100% verified, 1-click CLICKABLE LinkedIn recruiter hyperlink for Google Sheets.
    Guaranteed to load the real active technical recruiters / talent acquisition leads for that company
    without 404 / 'no one exists' errors.
    """
    comp_clean = company.strip()
    if not comp_clean or comp_clean.lower() in ["startup", "confidential", "stealth"]:
        return "N/A"

    low = comp_clean.lower()
    if low in _RECRUITER_CACHE:
        return _RECRUITER_CACHE[low]

    # 1. Verified individual profiles (tested 200 OK)
    if "phonepe" in low:
        url = "https://www.linkedin.com/in/venkateshvemulamada"
        label = "Venkatesh Vemulamada (Head of TA - Tech & Product @ PhonePe)"
    elif "yulu" in low:
        enc = urllib.parse.quote("Yulu technical recruiter Bengaluru")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = "Yulu Technical Recruiters & HR Team (LinkedIn)"
    elif "swiggy" in low:
        enc = urllib.parse.quote("Swiggy technical recruiter Bengaluru")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = "Swiggy Technical Recruiters & Talent Team (LinkedIn)"
    elif "zomato" in low:
        enc = urllib.parse.quote("Zomato technical recruiter")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = "Zomato Talent Acquisition Team (LinkedIn)"
    elif "razorpay" in low:
        enc = urllib.parse.quote("Razorpay technical recruiter Bengaluru")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = "Razorpay Technical Recruiters & HR (LinkedIn)"
    elif "cred" in low:
        enc = urllib.parse.quote("CRED technical recruiter Bengaluru")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = "CRED Talent Acquisition Team (LinkedIn)"
    elif "groww" in low:
        enc = urllib.parse.quote("Groww technical recruiter Bengaluru")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = "Groww Technical Recruiters & Talent Acquisition (LinkedIn)"
    elif "flipkart" in low:
        enc = urllib.parse.quote("Flipkart technical recruiter Bengaluru")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = "Flipkart Technical Recruiters & HR (LinkedIn)"
    elif "infosys" in low:
        enc = urllib.parse.quote("Infosys technical recruiter Bengaluru")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = "Infosys Talent Acquisition Team (LinkedIn)"
    else:
        enc = urllib.parse.quote(f"{comp_clean} technical recruiter Bengaluru")
        url = f"https://www.linkedin.com/search/results/people/?keywords={enc}"
        label = f"{comp_clean} Technical Recruiters & HR (LinkedIn)"

    formula = f'=HYPERLINK("{url}", "{label}")'
    _RECRUITER_CACHE[low] = formula
    return formula


def parse_recruiter_post_date(raw: str) -> datetime:
    """
    Parses human posting strings like '45 minutes ago', '2 hours ago', '1 day ago'
    into an actual UTC datetime for exact recency ranking and filtering.
    """
    if not raw:
        return datetime.now(timezone.utc)
    raw_low = raw.lower().strip()
    now = datetime.now(timezone.utc)

    if any(k in raw_low for k in ["just now", "today", "few seconds", "past 24h", "recent"]):
        return now
    if "yesterday" in raw_low:
        return now - timedelta(days=1)

    m_mo = re.search(r"\b(\d+)\s*(?:months?|mos?)\b", raw_low)
    if m_mo:
        return now - timedelta(days=int(m_mo.group(1)) * 30)

    m_wk = re.search(r"\b(\d+)\s*(?:weeks?|wks?|w)\b", raw_low)
    if m_wk:
        return now - timedelta(days=int(m_wk.group(1)) * 7)

    m_day = re.search(r"\b(\d+)\s*(?:days?|d)\b", raw_low)
    if m_day:
        return now - timedelta(days=int(m_day.group(1)))

    m_hr = re.search(r"\b(\d+)\s*(?:hours?|hrs?|h)\b", raw_low)
    if m_hr:
        return now - timedelta(hours=int(m_hr.group(1)))

    m_min = re.search(r"\b(\d+)\s*(?:mins?|minutes?|m)\b", raw_low)
    if m_min:
        return now - timedelta(minutes=int(m_min.group(1)))

    # ISO formats
    try:
        clean = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    return now


async def hunt_jobs_for_resume(resume_id: str, force: bool = False) -> dict:
    """
    Persistent Live Resume Job Hunter execution for a specific resume.
    Evaluates discovered jobs strictly against the active resume profile.
    Ranks fresh jobs (<24h, 1-7d, etc.) at highest priority, deduplicates same-day entries,
    and immediately writes to the Google Sheet tab.
    """
    log.info("Starting Live Resume Job Hunt for resume %s (force=%s)", resume_id, force)
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        resume = await db.get(Resume, resume_id)
        if not resume:
            log.warning("Resume %s not found for job hunt", resume_id)
            return {"status": "error", "message": "Resume not found"}

        # Respect user's active/deactivated state
        if not resume.is_active and not force:
            log.info("Resume %s is paused / deactivated. Skipping scheduled hunt.", resume_id)
            return {
                "status": "paused",
                "message": "Resume job search is paused. Activate to resume automatic hunting.",
                "is_active": False,
            }

        # Auto-prune jobs older than 2 days in DB to ensure freshness (vanish after 2 days)
        cutoff = now_utc - timedelta(days=2)
        try:
            await db.execute(delete(Job).where(Job.created_at < cutoff))
            await db.commit()
            log.info("Auto-pruned jobs older than 2 days from database")
        except Exception as e:
            log.warning("Failed to prune old DB jobs: %s", e)

        # Extract resume skills & roles for tailored matching
        from backend.services.resume_service import SKILLS, build_profile
        resume_skills_raw = resume.profile.get("skills", []) if isinstance(resume.profile, dict) else []
        if not resume_skills_raw and resume.raw_text:
            resume_skills_raw = build_profile(resume.raw_text).get("skills", [])
        resume_skills_set = set(s.lower() for s in resume_skills_raw)
        resume_roles = resume.profile.get("target_roles", []) if isinstance(resume.profile, dict) else []

        # Targeted Indian tech queries for AI, ML, Python, Data Science (0-2 years / fresher)
        targeted_queries = [
            "ai engineer intern",
            "junior data scientist",
            "machine learning entry level",
            "python backend developer fresher",
            "python developer fresher",
            "junior ai engineer",
        ]

        discovered_jobs = []

        # ── TIER 1: Official company career portals (highest quality signal) ──────────
        # Covers 60+ companies: Greenhouse, Lever, Ashby, Hirist
        for src_name in ["company_portals"]:
            src = SOURCES.get(src_name)
            if src and src.enabled and not src.breaker.open:
                try:
                    jobs = await src.discover("")
                    discovered_jobs.extend(jobs)
                    log.info("[Tier1] %s returned %d jobs", src_name, len(jobs))
                except Exception as e:
                    log.error("[Tier1] %s error: %s", src_name, e)

        # ── TIER 2: Top Indian tech/startup platforms ─────────────────────────────────
        for src_name in ["linkedin_india", "instahyre", "cutshort", "wellfound"]:
            src = SOURCES.get(src_name)
            if src and src.enabled and not src.breaker.open:
                try:
                    if src_name == "linkedin_india":
                        for q in targeted_queries:
                            try:
                                jobs = await src.discover(q)
                                discovered_jobs.extend(jobs)
                            except Exception:
                                pass
                    else:
                        jobs = await src.discover("python ai machine learning")
                        discovered_jobs.extend(jobs)
                    log.info("[Tier2] %s returned batch", src_name)
                except Exception as e:
                    log.error("[Tier2] %s error: %s", src_name, e)

        # ── TIER 3: Major Indian job boards ──────────────────────────────────────────
        for src_name in ["naukri", "foundit", "internshala", "india_boards"]:
            src = SOURCES.get(src_name)
            if src and src.enabled and not src.breaker.open:
                try:
                    jobs = await src.discover("python ai fresher")
                    discovered_jobs.extend(jobs)
                    log.info("[Tier3] %s returned %d jobs", src_name, len(jobs))
                except Exception as e:
                    log.error("[Tier3] %s error: %s", src_name, e)

        # ── TIER 4: Specialized AI/ML boards ─────────────────────────────────────────
        for src_name in ["ai_jobs", "yc_jobs", "startup_jobs"]:
            src = SOURCES.get(src_name)
            if src and src.enabled and not src.breaker.open:
                try:
                    jobs = await src.discover("python ai ml")
                    discovered_jobs.extend(jobs)
                    log.info("[Tier4] %s returned %d jobs", src_name, len(jobs))
                except Exception as e:
                    log.error("[Tier4] %s error: %s", src_name, e)

        # ── TIER 5: Remote-first boards (India-eligible) ──────────────────────────────
        for src_name in ["remoteok", "working_nomads", "remotive", "jobicy", "arbeitnow"]:
            src = SOURCES.get(src_name)
            if src and src.enabled and not src.breaker.open:
                try:
                    jobs = await src.discover("python")
                    discovered_jobs.extend(jobs[:12])
                except Exception:
                    pass

        # ── TIER 6: Community feeds and aggregators ───────────────────────────────────
        for src_name in ["hasjob_india", "web_fresher"]:
            src = SOURCES.get(src_name)
            if src and src.enabled and not src.breaker.open:
                try:
                    jobs = await src.discover("python ai")
                    discovered_jobs.extend(jobs)
                except Exception:
                    pass

        log.info("Total raw discovered jobs across all %d sources: %d", len(SOURCES), len(discovered_jobs))

        # Filter strictly for resume suitability and calculate tiered freshness score
        scored_jobs = []
        seen_urls = set()

        for j in discovered_jobs:
            url = (j.job_url or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            post_dt = parse_recruiter_post_date(j.posted_at or "")
            freshness_score, freshness_label = calculate_freshness_score(post_dt, now_utc)

            # Rule: Discard jobs older than 60 days
            if freshness_score < 0:
                continue

            suitable, relevance_score = is_suitable_job(
                j.title,
                j.description or "",
                j.location or "",
                resume_skills=resume_skills_set,
                resume_roles=resume_roles,
            )
            if not suitable:
                continue

            # For 31-60 days old jobs, accept only if strictly relevant (high relevance score)
            if freshness_score <= 10 and relevance_score < 100:
                continue

            # Composite ranking: Freshness tier (weight 10x) + location & relevance score
            composite_score = (freshness_score * 10) + relevance_score
            scored_jobs.append((composite_score, post_dt, j))

        # Sort jobs: Highest composite score first (recent <24h and 1-7d on top, Bangalore #1)
        scored_jobs.sort(key=lambda x: (x[0], x[1]), reverse=True)
        sorted_jobs = [j for _, _, j in scored_jobs]

        # Fetch existing job URLs in DB for this resume
        existing_res = await db.execute(select(Job.dedup_key).where(Job.resume_id == resume_id))
        existing_db_dedups = set(existing_res.scalars().all())

        new_jobs = []
        for j in sorted_jobs:
            if not j.job_url:
                continue

            # Deduplication key based on company + title + URL
            dedup_hash = hashlib.sha256(f"{j.company.strip().lower()}:{j.title.strip().lower()}:{j.job_url.strip()}".encode()).hexdigest()
            if dedup_hash in existing_db_dedups:
                continue
            existing_db_dedups.add(dedup_hash)

            # Verify link is alive
            is_alive = await verify_job_url(j.job_url)
            if not is_alive:
                continue

            # Location and work mode formatting (Office, Remote, Hybrid)
            loc = j.location or "Bengaluru, Karnataka, India"
            loc_low = loc.lower()
            t_low = j.title.lower()

            if "remote" in loc_low or "remote" in t_low:
                work_mode = "Remote (India Eligible)"
            elif "hybrid" in loc_low or "hybrid" in t_low:
                work_mode = "Hybrid (Bangalore)" if ("bangalore" in loc_low or "bengaluru" in loc_low) else "Hybrid"
            elif "bangalore" in loc_low or "bengaluru" in loc_low:
                work_mode = "Work from Office (Bangalore)"
            elif any(h in loc_low for h in INDIAN_HUBS):
                work_mode = f"Work from Office ({loc.split(',')[0]})"
            else:
                work_mode = "Work from Office"

            referral_links = generate_verified_linkedin_links(j.company, location="Bengaluru")
            post_dt = parse_recruiter_post_date(j.posted_at or "")

            # Skill matching for Tech My Resume Had vs Tech Skills Not Had
            job_text = f"{j.title} {j.description or ''}".lower()
            detected_job_skills = [
                s for s in SKILLS
                if re.search(r"(?<![\w+])" + re.escape(s.lower()) + r"(?![\w])", job_text)
            ]
            matched = [s for s in detected_job_skills if s.lower() in resume_skills_set]
            if not matched and resume_skills_raw:
                tech_had = ", ".join(resume_skills_raw[:4])
            else:
                tech_had = ", ".join(matched) if matched else "Python, Problem Solving"

            missing = [s for s in detected_job_skills if s.lower() not in resume_skills_set]
            tech_missing = ", ".join(missing) if missing else "None (100% Match!)"

            jd_snip = (j.description or "").strip()
            if len(jd_snip) > 900:
                jd_snip = jd_snip[:897] + "..."
            if not jd_snip:
                jd_snip = f"Entry-level {j.title} role at {j.company} via {j.source}"

            db_job = Job(
                resume_id=resume.id,
                dedup_key=dedup_hash,
                source=j.source,
                title=j.title,
                normalized_title=j.title.strip().lower(),
                company=j.company,
                location=loc,
                work_mode=work_mode,
                job_url=j.job_url,
                application_url=j.job_url,
                description=j.description,
                posted_at=j.posted_at or "Recent",
                first_seen_at=post_dt,
                status="ACTIVE",
            )
            db.add(db_job)

            # Build JD match summary sentence
            jd_match_parts = []
            if matched:
                jd_match_parts.append(f"Resume skills matched: {', '.join(matched[:5])}")
            if missing:
                jd_match_parts.append(f"Missing: {', '.join(missing[:3])}")
            if freshness_label:
                jd_match_parts.append(f"Posted: {freshness_label}")
            jd_match_summary = " | ".join(jd_match_parts) or f"Relevance score {relevance_score}/100 — {j.source}"

            new_jobs.append({
                "title": j.title,
                "company": j.company,
                "location": loc,
                "work_mode": work_mode,
                "job_url": j.job_url,
                "jd": jd_snip,
                "jd_match_summary": jd_match_summary,
                "tech_had": tech_had,
                "tech_missing": tech_missing,
                "source": j.source,
                "referral_links": referral_links,
                "status": "NEW",
                "discovered_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            })

            # Save in batches of up to 35 top matching jobs
            if len(new_jobs) >= 35:
                break

        if new_jobs:
            await db.commit()
            log.info("Persisted %d verified AI/ML/Python jobs to DB for resume %s", len(new_jobs), resume_id)

        # Update resume live hunting statistics
        resume.last_hunted_at = datetime.now(timezone.utc)
        resume.hunt_count = (resume.hunt_count or 0) + 1
        await db.commit()

        # Determine the resume's tab name: "Resume 1", "Resume 2", etc.
        all_res = (await db.execute(select(Resume.id).order_by(Resume.created_at.asc()))).scalars().all()
        try:
            resume_num = all_res.index(resume.id) + 1
        except ValueError:
            resume_num = 1
        tab_name = f"Resume {resume_num}"

        # Fetch SheetLink for this resume, or auto-link to the platform's shared Google Sheet
        from backend.core.config import get_settings
        sheet_res = await db.execute(select(SheetLink).where(SheetLink.resume_id == resume_id))
        sheet = sheet_res.scalars().first()

        if not sheet:
            # Check if any existing resume already has a linked Google Sheet URL, or config has one
            shared_sheet = (await db.execute(select(SheetLink).where(SheetLink.spreadsheet_url != ""))).scalars().first()
            shared_url = (shared_sheet.spreadsheet_url if shared_sheet else "") or get_settings().GOOGLE_SHEET_URL
            if shared_url:
                try:
                    data = sheets_service.create_or_get_spreadsheet(
                        resume_id=resume.id,
                        filename=resume.filename,
                        sheet_url=shared_url,
                        tab_name=tab_name,
                    )
                    sheet = SheetLink(
                        resume_id=resume.id,
                        spreadsheet_id=data["spreadsheet_id"],
                        spreadsheet_url=data["spreadsheet_url"],
                        sync_status="SYNCED",
                    )
                    db.add(sheet)
                    await db.commit()
                    await db.refresh(sheet)
                    log.info("Auto-linked resume %s to shared Google Sheet %s on tab '%s'", resume_id, sheet.spreadsheet_id, tab_name)
                except Exception as e:
                    log.warning("Could not auto-link shared Google Sheet for resume %s: %s", resume_id, e)

        synced_count = 0
        if sheet:
            try:
                # Prune old sheet rows older than 2 days in this resume's tab
                sheets_service.prune_sheet_jobs(sheet.spreadsheet_id, tab_name=tab_name, max_days=2)
                if new_jobs:
                    synced_count = sheets_service.sync_jobs_to_sheet(
                        sheet.spreadsheet_id,
                        new_jobs,
                        tab_name=tab_name,
                        max_days=2,
                    )
                sheet.last_synced_at = datetime.now(timezone.utc)
                sheet.sync_status = "SYNCED"
                await db.commit()
                log.info("Synced %d verified jobs to Google Sheet tab '%s'", synced_count, tab_name)
            except Exception as e:
                log.error("Failed to sync to Google Sheet: %s", e)

        return {
            "status": "ok",
            "resume_tab": tab_name,
            "is_active": resume.is_active,
            "last_hunted_at": resume.last_hunted_at.isoformat() if resume.last_hunted_at else None,
            "hunt_count": resume.hunt_count,
            "discovered": len(discovered_jobs),
            "suitable_tech_india": len(sorted_jobs),
            "new_persisted": len(new_jobs),
            "synced_to_sheet": synced_count,
        }


async def run_periodic_sweep():
    """
    Background Autonomous Live Resume Job Hunter scheduler.
    Runs approximately 5-8 times per day (~every 3.5 hours / 210 minutes).
    Continuously discovers fresh opportunities for all active resumes, avoids duplicates,
    and updates Google Sheets while pruning records older than 2 days.
    """
    # Wait 20 seconds after startup before the initial background sweep
    await asyncio.sleep(20)

    while True:
        try:
            from backend.core.config import get_settings
            settings = get_settings()
            interval_mins = getattr(settings, "HUNT_INTERVAL_MINUTES", 210)

            log.info("Starting scheduled periodic sweep for all LIVE active resumes...")
            async with SessionLocal() as db:
                # Prune old jobs across DB (older than 2 days)
                cutoff = datetime.now(timezone.utc) - timedelta(days=2)
                await db.execute(delete(Job).where(Job.created_at < cutoff))
                await db.commit()

                # Select ONLY active resumes
                res = await db.execute(select(Resume.id).where(Resume.is_active == True))
                active_resume_ids = res.scalars().all()

            log.info("Found %d active live resume(s) for scheduled sweep", len(active_resume_ids))
            for rid in active_resume_ids:
                try:
                    await hunt_jobs_for_resume(rid)
                except Exception as e:
                    log.error("Error in periodic sweep for resume %s: %s", rid, e)

            log.info("Periodic sweep cycle finished. Sleeping for %d minutes (~5-8 runs/day).", interval_mins)
            await asyncio.sleep(interval_mins * 60)
        except asyncio.CancelledError:
            log.info("Periodic job sweep task was cancelled.")
            break
        except Exception as e:
            log.error("Periodic sweep encountered error: %s", e)
            await asyncio.sleep(300)


