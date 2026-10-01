"""Lever public career board API adapter."""

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from backend.discovery.base import JobSourceAdapter
from backend.discovery.models import RawJobPosting, SearchQuery, SourceHealthCheck
from backend.discovery.policy import get_source_policy

logger = logging.getLogger("job_intelligence.discovery.adapters.lever")

# Default curated list of tech companies using Lever ATS career pages
DEFAULT_LEVER_COMPANIES = [
    "netflix",
    "atlassian",
    "spotify",
    "canva",
    "docker",
    "postman",
    "palantir",
    "auth0",
    "carta",
    "brex",
    "twitch",
    "sourcegraph",
    "benchling",
    "deliveroo",
    "monzo",
]


class LeverAdapter(JobSourceAdapter):
    """Adapter for Lever public company career postings API.

    Endpoint: https://api.lever.co/v0/postings/{company}?mode=json
    Policy: Authorized public ATS REST API, free, no authentication required.
    """

    def __init__(self, target_companies: list[str] | None = None, timeout: float = 10.0) -> None:
        policy = get_source_policy("lever")
        super().__init__(policy=policy)
        self.target_companies = target_companies or DEFAULT_LEVER_COMPANIES
        self.timeout = timeout

    def health_check(self) -> SourceHealthCheck:
        """Probe Lever API for liveness and latency."""
        start_time = time.perf_counter()
        try:
            self._enforce_rate_limit()
            test_company = self.target_companies[0] if self.target_companies else "spotify"
            url = f"{self.policy.base_url}/{test_company}?mode=json"
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    url,
                    headers={"User-Agent": "JobIntelligencePlatform/1.0 (Compliance Probe)"},
                )
            latency = (time.perf_counter() - start_time) * 1000.0

            if response.status_code == 200:
                return SourceHealthCheck(
                    source_name=self.name,
                    is_healthy=True,
                    status_code=response.status_code,
                    response_time_ms=round(latency, 2),
                    details=f"Lever public career board API operational (checked {test_company})",
                )
            return SourceHealthCheck(
                source_name=self.name,
                is_healthy=False,
                status_code=response.status_code,
                response_time_ms=round(latency, 2),
                details=f"Unexpected status code: {response.status_code}",
            )
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000.0
            logger.warning("Lever health check probe failed: %s", e)
            return SourceHealthCheck(
                source_name=self.name,
                is_healthy=False,
                status_code=None,
                response_time_ms=round(latency, 2),
                details=f"Connection failure: {e}",
            )

    def search(self, query: SearchQuery) -> list[RawJobPosting]:
        """Search Lever career boards across target companies for relevant entry-level positions."""
        results: list[RawJobPosting] = []
        role_tokens = [t.lower() for t in query.role_title.split() if len(t) > 2]
        skill_tokens = [s.lower() for s in query.skills]

        with httpx.Client(timeout=self.timeout) as client:
            for company in self.target_companies:
                try:
                    self._enforce_rate_limit()
                    url = f"{self.policy.base_url}/{company}?mode=json"
                    response = client.get(
                        url,
                        headers={"User-Agent": "JobIntelligencePlatform/1.0 (Direct Career Discovery)"},
                    )
                    if response.status_code != 200:
                        continue

                    postings_list = response.json()
                    if not isinstance(postings_list, list):
                        continue

                    for job_raw in postings_list:
                        title = job_raw.get("text", "")
                        title_lower = title.lower()

                        # Exclude senior, staff, lead, or mid-level II/2 roles immediately
                        senior_patterns = [
                            r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b",
                            r"\bstaff\b", r"\bdirector\b", r"\bmanager\b", r"\bhead of\b",
                            r"\bmid-level\b", r"\bmid level\b", r"\bii\b", r"\biii\b", r"\biv\b",
                            r"\b2\b", r"\b3\b", r"\b4\b", r"\bsde[- ]?ii\b", r"\bswe[- ]?ii\b",
                            r"\bsde[- ]?2\b", r"\bswe[- ]?2\b", r"\bengineer[- ]?ii\b",
                        ]
                        if any(re.search(pat, title_lower) for pat in senior_patterns):
                            continue

                        # Check role keyword alignment
                        matches_role = any(t in title_lower for t in role_tokens) if role_tokens else True
                        if not matches_role:
                            continue

                        categories = job_raw.get("categories") or {}
                        location_name = categories.get("location", "Remote") if isinstance(categories, dict) else "Remote"
                        desc_plain = job_raw.get("descriptionPlain", "") or ""
                        clean_desc = re.sub(r"\s+", " ", desc_plain).strip()

                        work_mode = "unknown"
                        desc_lower = clean_desc.lower()
                        if "remote" in location_name.lower() or "remote" in title_lower or "remote" in desc_lower[:300]:
                            work_mode = "remote"
                        elif "hybrid" in location_name.lower() or "hybrid" in desc_lower[:300]:
                            work_mode = "hybrid"

                        job_id = str(job_raw.get("id", ""))
                        hosted_url = job_raw.get("hostedUrl") or f"https://jobs.lever.co/{company}/{job_id}"
                        apply_url = job_raw.get("applyUrl") or hosted_url

                        posting_date = None
                        created_at = job_raw.get("createdAt")
                        if created_at:
                            try:
                                posting_date = datetime.fromtimestamp(created_at / 1000.0, tz=UTC)
                            except Exception:
                                pass

                        posting = RawJobPosting(
                            source_name="lever",
                            external_job_id=f"lever_{company}_{job_id}",
                            requisition_id=job_id,
                            title=title,
                            company_name=company.replace("-", " ").title(),
                            location=location_name or "Remote",
                            work_mode=work_mode,
                            description=clean_desc or title,
                            job_url=hosted_url,
                            application_url=apply_url,
                            posting_date=posting_date,
                            tags=skill_tokens,
                            raw_payload=job_raw,
                        )
                        results.append(posting)

                        if len(results) >= query.limit:
                            return results

                except Exception as e:
                    logger.debug("Failed to query Lever board for %s: %s", company, e)
                    continue

        return results

    def fetch_job(self, job_id_or_url: str) -> RawJobPosting | None:
        """Fetch a specific Lever job posting by URL or composite ID."""
        match = re.search(r"lever\.co/([^/]+)/([a-f0-9-]+)", job_id_or_url)
        if not match:
            return None

        company = match.group(1)
        job_id = match.group(2)
        url = f"{self.policy.base_url}/{company}/{job_id}"

        try:
            self._enforce_rate_limit()
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers={"User-Agent": "JobIntelligencePlatform/1.0"})
                if resp.status_code != 200:
                    return None
                data = resp.json()
                title = data.get("text", "")
                categories = data.get("categories") or {}
                location_name = categories.get("location", "Remote") if isinstance(categories, dict) else "Remote"
                desc_plain = data.get("descriptionPlain", "") or ""

                return RawJobPosting(
                    source_name="lever",
                    external_job_id=f"lever_{company}_{job_id}",
                    requisition_id=job_id,
                    title=title,
                    company_name=company.replace("-", " ").title(),
                    location=location_name,
                    work_mode="remote" if "remote" in location_name.lower() else "unknown",
                    description=desc_plain or title,
                    job_url=data.get("hostedUrl") or job_id_or_url,
                    application_url=data.get("applyUrl") or job_id_or_url,
                    tags=[],
                    raw_payload=data,
                )
        except Exception as e:
            logger.warning("Failed to fetch Lever job %s: %s", job_id_or_url, e)
            return None
