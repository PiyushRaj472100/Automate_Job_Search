"""Text, company, title, location, date, and skill normalization engine."""

import html
import logging
import re
from datetime import UTC, datetime
from typing import Any

from backend.discovery.models import RawJobPosting
from backend.models.job import Job
from backend.normalization.schemas import CanonicalJob, WorkMode
from backend.normalization.url_canonicalizer import normalize_url

logger = logging.getLogger("job_intelligence.normalization.normalizer")

# Technical skills vocabulary for extraction and standardization
KNOWN_TECHNICAL_SKILLS: dict[str, str] = {
    "python": "Python",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "GCP",
    "google cloud": "GCP",
    "azure": "Azure",
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "node": "Node.js",
    "golang": "Go",
    "rust": "Rust",
    "java": "Java",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "graphql": "GraphQL",
    "rest": "REST APIs",
    "restful": "REST APIs",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "llm": "LLMs",
    "genai": "Generative AI",
    "ci/cd": "CI/CD",
    "linux": "Linux",
    "git": "Git",
    "sql": "SQL",
}

# Regex patterns for stripping corporate noise from company names
LEGAL_SUFFIXES_REGEX = re.compile(
    r"(?i)\b(inc|incorporated|llc|ltd|limited|pvt|private|gmbh|corp|corporation|co|plc|s\.?a\.?|b\.?v\.?|ag)\b\.?",
)

# Common company branding cleanups
COMPANY_ALIASES: dict[str, str] = {
    "amazon web services": "Amazon",
    "amazon.com": "Amazon",
    "google llc": "Google",
    "google inc": "Google",
    "microsoft corporation": "Microsoft",
    "meta platforms": "Meta",
    "apple inc": "Apple",
}


def normalize_company(company: str) -> str:
    """Normalize and standardize company names."""
    if not company:
        return "Unknown Company"

    cleaned = company.strip()
    # Check for direct alias
    cleaned_lower = cleaned.lower()
    for alias_pattern, canonical_name in COMPANY_ALIASES.items():
        if alias_pattern in cleaned_lower:
            return canonical_name

    # Remove legal suffixes
    cleaned = LEGAL_SUFFIXES_REGEX.sub("", cleaned)
    # Remove trailing punctuation, multiple spaces
    cleaned = re.sub(r"[\s,\.\-]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or company.strip()


def normalize_title(title: str) -> str:
    """Normalize and clean job titles, expanding abbreviations and removing bracket noise."""
    if not title:
        return "Software Engineer"

    cleaned = title.strip()

    # 1. Remove gender bias tags: (m/f/d), (w/m/d), (f/m/x), (all genders), etc.
    cleaned = re.sub(r"(?i)\s*[\(\[](m/f/d|w/m/d|f/m/d|d/f/m|m/w/d|f/m/x|all genders)[\)\]]", "", cleaned)

    # 2. Remove bracketed location/remote tags from title: [Remote], (Remote), [Hybrid], | Remote
    cleaned = re.sub(r"(?i)\s*[\(\[](remote|hybrid|on-site|onsite)[\)\]]", "", cleaned)
    cleaned = re.sub(r"(?i)\s*[-|/]\s*(remote|hybrid|work from home)\b", "", cleaned)

    # 3. Remove bracketed requisition codes like (REQ-12345) or [Job ID 987]
    cleaned = re.sub(r"(?i)\s*[\(\[](?:req|job\s*id)[:#\s-]*[a-z0-9_-]+[\)\]]", "", cleaned)

    # 4. Standardize common abbreviations
    cleaned = re.sub(r"\b[sS][wW][eE]\b", "Software Engineer", cleaned)
    cleaned = re.sub(r"\b[sS][dD][eE]\b", "Software Development Engineer", cleaned)
    cleaned = re.sub(r"\b[sS][rR][eE]\b", "Site Reliability Engineer", cleaned)
    cleaned = re.sub(r"\b[qQ][aA]\b", "Quality Assurance", cleaned)
    cleaned = re.sub(r"\b[sS]r\.?(?=\s|$)", "Senior", cleaned)
    cleaned = re.sub(r"\b[jJ]r\.?(?=\s|$)", "Junior", cleaned)
    cleaned = re.sub(r"\b[dD]ev\b", "Developer", cleaned)

    # 5. Clean excess whitespace and trailing delimiters
    cleaned = re.sub(r"[\s,\.\-|/]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or title.strip()


def normalize_location(location: str) -> str:
    """Standardize geographic locations and identify remote roles."""
    if not location or not location.strip():
        return "Remote"

    cleaned = location.strip()
    lower_loc = cleaned.lower()

    if any(k in lower_loc for k in ["remote", "wfh", "anywhere", "work from home", "virtual", "telecommute"]):
        return "Remote"

    # Simplify repetitive hierarchy e.g. "Bengaluru, Karnataka, India" -> "Bengaluru, India"
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if len(parts) >= 3:
        cleaned = f"{parts[0]}, {parts[-1]}"

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def infer_work_mode(
    raw_mode: str | None,
    title: str,
    location: str,
    description: str,
) -> WorkMode:
    """Infer work mode (remote, hybrid, on_site) from multiple text cues."""
    combined = f"{raw_mode or ''} {title} {location} {description[:400]}".lower()

    if "remote" in combined or "wfh" in combined or "work from home" in combined:
        return WorkMode.REMOTE
    if "hybrid" in combined:
        return WorkMode.HYBRID
    if any(k in combined for k in ["on_site", "onsite", "in-office", "office only"]):
        return WorkMode.ON_SITE

    return WorkMode.ON_SITE if location != "Remote" else WorkMode.REMOTE


def clean_description(raw_desc: str) -> str:
    """Strip HTML markup and normalize whitespace in job descriptions."""
    if not raw_desc:
        return ""

    # Unescape HTML entities
    text = html.unescape(raw_desc)
    # Replace block HTML tags with newlines
    text = re.sub(r"(?i)<(br|p|div|li)[^>]*>", "\n", text)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple consecutive newlines and spaces
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_date(date_val: Any) -> datetime | None:
    """Parse varied date formats (datetime, timestamp, ISO string) into timezone-aware UTC datetime."""
    if not date_val:
        return None

    if isinstance(date_val, datetime):
        return date_val if date_val.tzinfo else date_val.replace(tzinfo=UTC)

    if isinstance(date_val, int | float):
        # Handle seconds or milliseconds
        ts = date_val / 1000.0 if date_val > 10000000000 else float(date_val)
        try:
            return datetime.fromtimestamp(ts, tz=UTC)
        except Exception:
            return None

    if isinstance(date_val, str):
        clean_str = date_val.strip()
        if clean_str.endswith("Z") or clean_str.endswith("z"):
            clean_str = clean_str[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(clean_str)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            pass

        # Fallback common date patterns
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                parsed = datetime.strptime(clean_str, fmt)
                return parsed.replace(tzinfo=UTC)
            except Exception:
                continue

    return None



def extract_skills_from_text(title: str, description: str, tags: list[str] | None = None) -> list[str]:
    """Identify and normalize technical skills mentioned in the job title, tags, or description."""
    found_skills: set[str] = set()

    # Add any explicit tags matching known skills
    if tags:
        for t in tags:
            t_lower = t.lower().strip()
            if t_lower in KNOWN_TECHNICAL_SKILLS:
                found_skills.add(KNOWN_TECHNICAL_SKILLS[t_lower])

    combined_text = f" {title.lower()} {description.lower()} "
    for keyword, canonical_name in KNOWN_TECHNICAL_SKILLS.items():
        # Match as whole word or boundary
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(keyword) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, combined_text):
            found_skills.add(canonical_name)

    return sorted(found_skills)


def extract_requisition_id(
    raw_req: str | None,
    raw_id: str | None,
    title: str,
    description: str,
    url: str,
) -> str | None:
    """Extract or discover requisition identifier from structured or unstructured fields."""
    if raw_req and raw_req.strip():
        return raw_req.strip()

    # Search for explicit patterns like REQ-12345, #123456, Job ID: 45678
    combined = f"{title} {url} {description[:600]}"
    match = re.search(r"(?i)\b(?:req|requisition|job\s*id)[:#\s-]*([A-Z0-9_-]{4,15})\b", combined)
    if match:
        return match.group(1).strip()

    return raw_id.strip() if raw_id and raw_id.strip() else None


class JobNormalizer:
    """Production-grade job normalizer translating heterogeneous source postings to CanonicalJob."""

    @staticmethod
    def normalize(raw: RawJobPosting | dict[str, Any]) -> CanonicalJob:
        """Transform a raw posting or dictionary into a validated CanonicalJob."""
        # Unpack raw fields
        if isinstance(raw, RawJobPosting):
            raw_title = raw.title
            raw_company = raw.company_name
            raw_location = raw.location
            raw_mode = raw.work_mode
            raw_desc = raw.description
            raw_job_id = raw.external_job_id
            raw_req_id = raw.requisition_id
            raw_url = raw.job_url
            raw_app_url = raw.application_url
            raw_posting_date = raw.posting_date
            raw_tags = raw.tags
            source_name = raw.source_name
            raw_payload = raw.raw_payload or {}
        else:
            raw_title = raw.get("title", "")
            raw_company = raw.get("company", raw.get("company_name", ""))
            raw_location = raw.get("location", "Remote")
            raw_mode = raw.get("work_mode")
            raw_desc = raw.get("description", "")
            raw_job_id = raw.get("job_id", raw.get("external_job_id"))
            raw_req_id = raw.get("requisition_id")
            raw_url = raw.get("job_url", raw.get("url", ""))
            raw_app_url = raw.get("application_url", raw.get("app_url"))
            raw_posting_date = raw.get("posting_date", raw.get("created_at"))
            raw_tags = raw.get("tags", [])
            source_name = raw.get("source", raw.get("source_name", "unknown"))
            raw_payload = raw.get("raw_payload", raw)

        # 1. Normalize core descriptors
        title = normalize_title(raw_title)
        company = normalize_company(raw_company)
        location = normalize_location(raw_location)
        description = clean_description(raw_desc)
        work_mode = infer_work_mode(raw_mode, title, location, description)

        # 2. Canonicalize URLs and strip tracking parameters
        canonical_url = normalize_url(raw_url)
        canonical_app_url = normalize_url(raw_app_url) if raw_app_url else None

        # 3. Extract or normalize requisition and job IDs
        req_id = extract_requisition_id(raw_req_id, raw_job_id, raw_title, raw_desc, raw_url)
        job_id = raw_job_id.strip() if raw_job_id else None

        # 4. Dates
        posting_date = parse_date(raw_posting_date)

        # 5. Skills extraction
        skills = extract_skills_from_text(title, description, raw_tags)

        # 6. Normalized comparison keys
        normalized_company = company.lower().strip()
        normalized_title = title.lower().strip()
        normalized_location = location.lower().strip()

        # 7. Compute deterministic deduplication fingerprint
        dedup_hash = Job.calculate_dedup_hash(
            normalized_company=normalized_company,
            normalized_title=normalized_title,
            normalized_location=normalized_location,
            requisition_id=req_id,
        )

        return CanonicalJob(
            title=title,
            company=company,
            location=location,
            work_mode=work_mode,
            description=description,
            job_id=job_id,
            requisition_id=req_id,
            job_url=raw_url.strip(),
            application_url=canonical_app_url,
            canonical_url=canonical_url,
            alternate_urls=[canonical_url] if canonical_url else [],
            posting_date=posting_date,
            updated_date=posting_date,
            skills=skills,
            sources=[source_name.lower().strip()],
            primary_source=source_name.lower().strip(),
            normalized_company=normalized_company,
            normalized_title=normalized_title,
            normalized_location=normalized_location,
            dedup_hash=dedup_hash,
            raw_payloads=[raw_payload] if raw_payload else [],
        )
