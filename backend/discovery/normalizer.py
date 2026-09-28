"""Job normalization and canonicalization engine."""

import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field

from backend.discovery.models import RawJobPosting
from backend.models.job import Job


class NormalizedJob(BaseModel):
    """Standardized, deduplicated job entity matching the PostgreSQL jobs schema."""

    external_job_id: str | None = None
    requisition_id: str | None = None
    title: str
    company_name: str
    location: str
    work_mode: str
    description: str
    job_url: str
    application_url: str | None = None
    canonical_url: str
    source: str
    posting_date: datetime | None = None
    normalized_company: str
    normalized_title: str
    normalized_location: str
    dedup_hash: str
    tags: list[str] = Field(default_factory=list)


def clean_tracking_params(url: str) -> str:
    """Strip marketing and telemetry tracking query parameters from job URLs."""
    if not url:
        return url

    parsed = urlparse(url)
    tracking_prefixes = ("utm_", "ref", "source", "trk", "tracking", "gh_jid", "refId")
    filtered_queries = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if not any(k.lower().startswith(prefix) for prefix in tracking_prefixes)
    ]
    new_query = urlencode(filtered_queries)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path.rstrip("/"),
        parsed.params,
        new_query,
        "",  # Strip fragment
    ))


def normalize_title(title: str) -> str:
    """Normalize job title string by cleaning extra whitespace and standardizing abbreviations."""
    cleaned = title.strip()
    # Normalize common abbreviations
    cleaned = re.sub(r"\b[sS]r\.?(?=\s|$)", "Senior", cleaned)
    cleaned = re.sub(r"\b[jJ]r\.?(?=\s|$)", "Junior", cleaned)
    cleaned = re.sub(r"\b[sS][wW][eE]\b", "Software Engineer", cleaned)
    cleaned = re.sub(r"\b[sS]/[wW]\b", "Software", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_company(company: str) -> str:
    """Normalize company name by stripping legal suffixes and excess symbols."""
    cleaned = company.strip()
    # Remove common legal suffixes and their trailing periods
    cleaned = re.sub(r"(?i)\b(inc|incorporated|llc|ltd|limited|pvt|private)\b\.?", "", cleaned)
    # Strip any trailing punctuation and multiple spaces
    cleaned = re.sub(r"[\s,\.\-]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()



def normalize_location(location: str) -> str:
    """Normalize location description."""
    cleaned = location.strip()
    if not cleaned or cleaned.lower() in ("remote", "anywhere", "work from home", "wfh"):
        return "Remote"
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def infer_work_mode(raw_mode: str, title: str, location: str, description: str) -> str:
    """Infer work mode (remote, hybrid, on_site) from multiple text cues."""
    raw_mode_lower = (raw_mode or "").lower()
    if "remote" in raw_mode_lower:
        return "remote"
    if "hybrid" in raw_mode_lower:
        return "hybrid"
    if "on_site" in raw_mode_lower or "onsite" in raw_mode_lower or "in-office" in raw_mode_lower:
        return "on_site"

    combined_text = f"{title} {location} {description[:300]}".lower()
    if any(k in combined_text for k in ["remote", "work from home", "wfh", "anywhere"]):
        return "remote"
    if "hybrid" in combined_text:
        return "hybrid"
    return "on_site"


def normalize_job_posting(raw: RawJobPosting) -> NormalizedJob:
    """Transform a RawJobPosting into a validated, normalized, deduplicated NormalizedJob."""
    norm_title = normalize_title(raw.title)
    norm_company = normalize_company(raw.company_name)
    norm_location = normalize_location(raw.location)
    work_mode = infer_work_mode(raw.work_mode, raw.title, raw.location, raw.description)
    canonical_url = clean_tracking_params(raw.job_url)
    clean_app_url = clean_tracking_params(raw.application_url) if raw.application_url else None

    dedup_hash = Job.calculate_dedup_hash(
        normalized_company=norm_company,
        normalized_title=norm_title,
        normalized_location=norm_location,
        requisition_id=raw.requisition_id,
    )

    return NormalizedJob(
        external_job_id=raw.external_job_id,
        requisition_id=raw.requisition_id,
        title=norm_title,
        company_name=raw.company_name.strip(),
        location=norm_location,
        work_mode=work_mode,
        description=raw.description.strip(),
        job_url=raw.job_url.strip(),
        application_url=clean_app_url,
        canonical_url=canonical_url,
        source=raw.source_name.strip().lower(),
        posting_date=raw.posting_date,
        normalized_company=norm_company,
        normalized_title=norm_title,
        normalized_location=norm_location,
        dedup_hash=dedup_hash,
        tags=[t.strip() for t in raw.tags if t.strip()],
    )
