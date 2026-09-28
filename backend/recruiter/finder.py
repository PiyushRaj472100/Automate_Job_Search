"""Recruiter and hiring team finder with conservative prioritization and filtering."""

import logging
import re
from typing import Any

from backend.normalization.normalizer import normalize_company, normalize_title
from backend.normalization.schemas import CanonicalJob
from backend.recruiter.schemas import (
    JobRecruiterDiscoveryResult,
    ProfileVerificationResult,
    RawCandidateProfile,
    RecruiterStatus,
)
from backend.recruiter.verifier import ProfileVerifier

logger = logging.getLogger("job_intelligence.recruiter.finder")


class RecruiterFinder:
    """Discovers, verifies, and prioritizes recruiters and hiring managers for relevant jobs."""

    def __init__(self, verifier: ProfileVerifier | None = None):
        self.verifier = verifier or ProfileVerifier()

    def discover_for_job(
        self,
        job: CanonicalJob | dict[str, Any] | Any,
        candidate_pool: list[RawCandidateProfile | dict[str, Any]] | None = None,
        check_network: bool = False,
    ) -> JobRecruiterDiscoveryResult:
        """Find and verify up to three recruitment professionals for a given job.

        Guarantees:
        - Never fabricates a profile.
        - Never guesses a recruiter.
        - Never claims requisition ownership without explicit evidence.
        - Only VERIFIED profiles are assigned to recruiter_1, recruiter_2, recruiter_3.
        - Respects priority order:
          1. Recruiter
          2. Talent Acquisition
          3. Technical Recruiter
          4. Hiring Manager
          5. Engineering Manager
          6. Relevant recruitment professional
        """
        job_data = self._extract_job_data(job)
        company_name = job_data["company"]

        # Collect candidate profiles
        candidates: list[RawCandidateProfile] = []

        # 1. Extract from job metadata & description
        embedded_candidates = self._extract_embedded_recruiter_signals(job_data)
        candidates.extend(embedded_candidates)

        # 2. Add candidates from external pool if provided
        if candidate_pool:
            for item in candidate_pool:
                if isinstance(item, RawCandidateProfile):
                    candidates.append(item)
                elif isinstance(item, dict):
                    candidates.append(RawCandidateProfile(**item))

        # Deduplicate candidates by name/email/url
        unique_candidates = self._deduplicate_candidates(candidates)

        verified_list: list[ProfileVerificationResult] = []
        plausible_list: list[ProfileVerificationResult] = []
        unverified_list: list[ProfileVerificationResult] = []

        for candidate in unique_candidates:
            result = self.verifier.verify_profile(
                candidate=candidate,
                target_company=company_name,
                job_context=job_data,
                check_network=check_network,
            )

            if result.status == RecruiterStatus.VERIFIED:
                verified_list.append(result)
            elif result.status == RecruiterStatus.PLAUSIBLE:
                plausible_list.append(result)
            elif result.status == RecruiterStatus.UNVERIFIED:
                unverified_list.append(result)
            # NOT_FOUND (unrelated employees or invalid names) are discarded from recruitment queues

        # Sort VERIFIED recruiters strictly by:
        # 1. Direct Requisition Ownership (Evidence first)
        # 2. Priority Hierarchy Tier (1 -> 2 -> 3 -> 4 -> 5 -> 6)
        # 3. Confidence Score descending
        verified_list.sort(
            key=lambda p: (
                0 if p.is_job_owner else 1,
                p.role_tier.value,
                -p.confidence,
            )
        )

        # Overall Status
        if verified_list:
            overall_status = RecruiterStatus.VERIFIED
        elif plausible_list:
            overall_status = RecruiterStatus.PLAUSIBLE
        elif unverified_list:
            overall_status = RecruiterStatus.UNVERIFIED
        else:
            overall_status = RecruiterStatus.NOT_FOUND

        # Primary recruiter columns: Maximum 3, STRICTLY VERIFIED ONLY
        r1 = verified_list[0].to_formatted_display() if len(verified_list) >= 1 else ""
        r2 = verified_list[1].to_formatted_display() if len(verified_list) >= 2 else ""
        r3 = verified_list[2].to_formatted_display() if len(verified_list) >= 3 else ""

        return JobRecruiterDiscoveryResult(
            job_id=job_data.get("id"),
            job_title=job_data["title"],
            company_name=company_name,
            verified_recruiters=verified_list,
            plausible_recruiters=plausible_list,
            unverified_recruiters=unverified_list,
            overall_status=overall_status,
            recruiter_1=r1,
            recruiter_2=r2,
            recruiter_3=r3,
        )

    def _extract_job_data(self, job: Any) -> dict[str, Any]:
        """Extract standardized job data from CanonicalJob, SQLAlchemy Job, or dict."""
        if isinstance(job, CanonicalJob):
            return {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "description": job.description,
                "posted_by": getattr(job, "posted_by", None),
                "author": getattr(job, "author", None),
                "recruiter_contact": getattr(job, "recruiter_contact", None),
            }
        elif isinstance(job, dict):
            return {
                "id": job.get("id"),
                "title": normalize_title(job.get("title", "")),
                "company": normalize_company(job.get("company", job.get("company_name", ""))),
                "description": job.get("description", ""),
                "posted_by": job.get("posted_by"),
                "author": job.get("author"),
                "recruiter_contact": job.get("recruiter_contact"),
            }
        else:
            # SQLAlchemy Job ORM
            return {
                "id": getattr(job, "id", None),
                "title": normalize_title(getattr(job, "title", "")),
                "company": normalize_company(getattr(job, "company_name", getattr(job, "company", ""))),
                "description": getattr(job, "description", ""),
                "posted_by": getattr(job, "posted_by", None),
                "author": getattr(job, "author", None),
                "recruiter_contact": getattr(job, "recruiter_contact", None),
            }

    def _extract_embedded_recruiter_signals(self, job_data: dict[str, Any]) -> list[RawCandidateProfile]:
        """Extract explicit author or contact metadata embedded in the job description."""
        candidates: list[RawCandidateProfile] = []

        # 1. Direct author / posted_by field
        posted_by = job_data.get("posted_by") or job_data.get("author")
        if posted_by and isinstance(posted_by, str) and len(posted_by.strip()) > 2:
            candidates.append(
                RawCandidateProfile(
                    name=posted_by.strip(),
                    title="Job Poster / Talent Acquisition",
                    company=job_data["company"],
                    claimed_job_ownership=True,
                    evidence_text=f"Directly listed as job posting author: {posted_by}",
                    source="job_metadata",
                )
            )

        # 2. Explicit recruiter mention in description (e.g. 'Recruiter: Jane Doe <jane@company.com>')
        desc = job_data.get("description", "")
        recruiter_patterns = [
            r"(?:recruiter|hiring manager|contact|reach out to)\s*:\s*([A-Z][a-z]+ [A-Z][a-z]+)",
            r"(?:posted by|shared by)\s*:\s*([A-Z][a-z]+ [A-Z][a-z]+)",
        ]
        for pattern in recruiter_patterns:
            matches = re.finditer(pattern, desc, re.IGNORECASE)
            for m in matches:
                name = m.group(1).strip()
                candidates.append(
                    RawCandidateProfile(
                        name=name,
                        title="Recruiter",
                        company=job_data["company"],
                        claimed_job_ownership=True,
                        evidence_text=f"Explicitly mentioned in job posting: '{m.group(0)}'",
                        source="job_description",
                    )
                )

        return candidates

    def _deduplicate_candidates(self, candidates: list[RawCandidateProfile]) -> list[RawCandidateProfile]:
        """Deduplicate candidates by lowercased name, merging richer profile data (e.g. LinkedIn URL)."""
        deduped_by_name: dict[str, RawCandidateProfile] = {}

        for c in candidates:
            name_key = c.name.strip().lower()
            if not name_key:
                continue
            if name_key not in deduped_by_name:
                deduped_by_name[name_key] = c
            else:
                existing = deduped_by_name[name_key]
                # If new entry has a LinkedIn URL and existing does not, merge to create complete candidate
                if not existing.linkedin_url and c.linkedin_url:
                    merged_dict = existing.model_dump()
                    merged_dict.update({k: v for k, v in c.model_dump().items() if v is not None and v != ""})
                    deduped_by_name[name_key] = RawCandidateProfile(**merged_dict)
                elif c.claimed_job_ownership and not existing.claimed_job_ownership:
                    existing.claimed_job_ownership = True
                    if c.evidence_text:
                        existing.evidence_text = c.evidence_text

        return list(deduped_by_name.values())
