"""Conservative profile verifier enforcing strict truthfulness and evidence constraints."""

import logging
import re
import urllib.parse
from datetime import UTC, datetime
from typing import Any

from backend.normalization.normalizer import normalize_company
from backend.recruiter.schemas import (
    ProfileVerificationResult,
    RawCandidateProfile,
    RecruiterRoleTier,
    RecruiterStatus,
)

logger = logging.getLogger("job_intelligence.recruiter.verifier")

# Names / titles that represent anonymous, collective, or non-person entities
INVALID_NAME_PATTERNS = [
    r"^linkedin member$",
    r"^hiring team$",
    r"^recruiting team$",
    r"^talent acquisition team$",
    r"^hr department$",
    r"^careers$",
    r"^jobs$",
    r"^anonymous$",
    r"^admin$",
    r"^staffing partner$",
    r"^[a-z0-9_-]+@[a-z0-9_-]+\.[a-z]+$",  # Raw email as name
]

# Standard LinkedIn Profile Regex: https://(www.)linkedin.com/in/{username}/
LINKEDIN_PROFILE_REGEX = re.compile(
    r"^https?://(www\.)?linkedin\.com/in/([a-zA-Z0-9%_-]+)/?$",
    re.IGNORECASE,
)

# Invalid LinkedIn usernames / slugs
RESERVED_LINKEDIN_SLUGS = {
    "search", "feed", "jobs", "messaging", "notifications",
    "login", "signup", "company", "school", "help", "mynetwork",
}


class ProfileVerifier:
    """Conservatively verifies public professional profiles against job and company contexts."""

    def verify_profile(
        self,
        candidate: RawCandidateProfile | dict[str, Any],
        target_company: str,
        job_context: dict[str, Any] | None = None,
        check_network: bool = False,
    ) -> ProfileVerificationResult:
        """Verify an individual candidate profile.

        Rules:
        - Never fabricate or guess.
        - Never claim job requisition ownership without direct evidence.
        - Reject unrelated employees and wrong company candidates.
        - Assign strict status: VERIFIED, PLAUSIBLE, UNVERIFIED, NOT_FOUND.
        """
        raw = self._coerce_candidate(candidate)
        job_context = job_context or {}

        verification_details: dict[str, Any] = {
            "target_company": target_company,
            "raw_name": raw.name,
            "raw_title": raw.title,
            "raw_company": raw.company,
            "raw_url": raw.linkedin_url,
        }

        # 1. Verify Name
        name_valid, cleaned_name, name_error = self._verify_name(raw.name)
        verification_details["name_valid"] = name_valid
        if not name_valid:
            verification_details["name_error"] = name_error
            return ProfileVerificationResult(
                name=raw.name or "Unknown",
                title=raw.title or "Unknown",
                company=raw.company or target_company,
                linkedin_url=raw.linkedin_url,
                status=RecruiterStatus.NOT_FOUND,
                role_tier=RecruiterRoleTier.UNRELATED,
                confidence=0.0,
                is_job_owner=False,
                relevance_reason=f"Invalid or anonymous profile identity: {name_error}",
                verification_source="name_validator",
                verified_at=datetime.now(UTC),
                verification_details=verification_details,
            )

        # 2. Verify Company
        company_valid, company_reason = self._verify_company(raw.company, target_company)
        verification_details["company_valid"] = company_valid
        verification_details["company_reason"] = company_reason

        # 3. Verify Title & Role Tier (Priority 1-6 or UNRELATED)
        role_tier, title_reason = self._classify_role_tier(raw.title)
        verification_details["role_tier"] = role_tier.name
        verification_details["title_reason"] = title_reason

        # 4. Verify LinkedIn URL
        url_valid, canonical_url, url_error = self._verify_linkedin_url(
            raw.linkedin_url,
            check_network=check_network,
        )
        verification_details["url_valid"] = url_valid
        verification_details["canonical_url"] = canonical_url
        if url_error:
            verification_details["url_error"] = url_error

        # 5. Check Requisition Ownership Evidence
        is_job_owner, ownership_evidence = self._check_requisition_ownership(
            candidate_name=cleaned_name,
            job_context=job_context,
            explicit_claim=raw.claimed_job_ownership,
            claim_evidence=raw.evidence_text,
        )
        verification_details["is_job_owner"] = is_job_owner
        verification_details["ownership_evidence"] = ownership_evidence

        # 6. Calculate Confidence and Assign Status
        status, confidence, relevance_reason = self._determine_status_and_confidence(
            name_valid=name_valid,
            company_valid=company_valid,
            role_tier=role_tier,
            url_valid=url_valid,
            has_url=bool(raw.linkedin_url),
            is_job_owner=is_job_owner,
            ownership_evidence=ownership_evidence,
            title_reason=title_reason,
            company_reason=company_reason,
            url_error=url_error,
        )

        return ProfileVerificationResult(
            name=cleaned_name,
            title=raw.title or "Professional",
            company=raw.company or target_company,
            linkedin_url=canonical_url if url_valid else raw.linkedin_url,
            email=raw.email,
            status=status,
            role_tier=role_tier,
            confidence=round(confidence, 2),
            is_job_owner=is_job_owner,
            relevance_reason=relevance_reason,
            verification_source="profile_verifier",
            verified_at=datetime.now(UTC),
            verification_details=verification_details,
        )

    def _coerce_candidate(self, candidate: RawCandidateProfile | dict[str, Any]) -> RawCandidateProfile:
        if isinstance(candidate, RawCandidateProfile):
            return candidate
        return RawCandidateProfile(
            name=candidate.get("name", candidate.get("full_name", "")),
            title=candidate.get("title"),
            company=candidate.get("company", candidate.get("company_name")),
            linkedin_url=candidate.get("linkedin_url", candidate.get("url")),
            email=candidate.get("email"),
            source=candidate.get("source", "discovery"),
            claimed_job_ownership=candidate.get("claimed_job_ownership", False),
            evidence_text=candidate.get("evidence_text"),
        )

    def _verify_name(self, name: str | None) -> tuple[bool, str, str]:
        """Validate that name belongs to a plausible individual human."""
        if not name or not name.strip():
            return False, "", "Name is missing or empty"

        cleaned = " ".join(name.strip().split())

        # Check blacklist patterns
        lower_name = cleaned.lower()
        for pattern in INVALID_NAME_PATTERNS:
            if re.search(pattern, lower_name):
                return False, cleaned, f"Generic or non-individual placeholder '{cleaned}'"

        # Check for numeric-only or single character names
        alpha_chars = sum(1 for c in cleaned if c.isalpha())
        if alpha_chars < 3:
            return False, cleaned, "Name contains insufficient alphabetical characters"

        return True, cleaned, "Valid individual name"

    def _verify_company(self, candidate_company: str | None, target_company: str) -> tuple[bool, str]:
        """Check whether candidate's stated company matches the hiring company."""
        if not candidate_company or not candidate_company.strip():
            # If candidate company is unspecified, cannot confirm match
            return False, "Candidate company is missing"

        norm_candidate = normalize_company(candidate_company)
        norm_target = normalize_company(target_company)

        if not norm_target:
            return False, "Target company is empty"

        # Exact match
        if norm_candidate == norm_target:
            return True, f"Exact company match ('{norm_candidate}')"

        # Substring / variant match (e.g., 'Google' vs 'Google LLC', 'Nexus Labs' vs 'Nexus')
        if (
            norm_candidate in norm_target
            or norm_target in norm_candidate
            or norm_candidate.replace(" ", "") in norm_target.replace(" ", "")
            or norm_target.replace(" ", "") in norm_candidate.replace(" ", "")
        ):
            return True, f"Affiliated company match ('{norm_candidate}' matches '{norm_target}')"

        return False, f"Wrong company: profile at '{candidate_company}', job at '{target_company}'"

    def _classify_role_tier(self, title: str | None) -> tuple[RecruiterRoleTier, str]:
        """Classify title strictly according to user priority hierarchy."""
        if not title or not title.strip():
            return RecruiterRoleTier.UNRELATED, "Unspecified title"

        lower_title = title.lower()

        # Tier 3: Technical Recruiter
        if any(kw in lower_title for kw in [
            "technical recruiter", "tech recruiter", "it recruiter",
            "engineering recruiter", "developer recruiter", "software recruiter",
        ]):
            return RecruiterRoleTier.TECHNICAL_RECRUITER, "Technical Recruiter"

        # Tier 2: Talent Acquisition
        if any(kw in lower_title for kw in [
            "talent acquisition", "talent partner", "talent specialist",
            "talent lead", "talent advisor", "talent sourcer", "head of talent",
        ]):
            return RecruiterRoleTier.TALENT_ACQUISITION, "Talent Acquisition Specialist"

        # Tier 1: Recruiter (General, Campus, Corporate, Lead)
        if any(kw in lower_title for kw in [
            "recruiter", "recruitment", "campus hiring", "corporate recruiter",
            "university recruiter", "lead recruiter", "senior recruiter",
        ]):
            return RecruiterRoleTier.RECRUITER, "Recruiter"

        # Tier 4: Hiring Manager
        if "hiring manager" in lower_title:
            return RecruiterRoleTier.HIRING_MANAGER, "Explicit Hiring Manager"

        # Tier 5: Engineering Manager / Leadership
        if any(kw in lower_title for kw in [
            "engineering manager", "software engineering manager",
            "director of engineering", "vp of engineering", "head of engineering",
            "engineering lead", "tech lead", "cto",
        ]):
            return RecruiterRoleTier.ENGINEERING_MANAGER, "Engineering Manager / Leadership"

        # Tier 6: Relevant Recruitment / People Professional
        if any(kw in lower_title for kw in [
            "people operations", "people partner", "hr manager", "hr business partner",
            "hrbp", "human resources", "staffing specialist", "staffing partner",
        ]):
            return RecruiterRoleTier.RECRUITMENT_PROFESSIONAL, "Recruitment & People Professional"

        # Unrelated Employee (e.g. Sales, Accounting, Nursing, Logistics, Engineer without hiring context)
        return RecruiterRoleTier.UNRELATED, f"Unrelated employee role: '{title}'"

    def _verify_linkedin_url(
        self,
        url: str | None,
        check_network: bool = False,
    ) -> tuple[bool, str | None, str | None]:
        """Verify LinkedIn profile URL format, structure, and reachability where possible."""
        if not url or not url.strip():
            return False, None, "LinkedIn URL not provided"

        cleaned_url = url.strip()

        # Ensure scheme
        if not cleaned_url.startswith(("http://", "https://")):
            cleaned_url = "https://" + cleaned_url

        parsed = urllib.parse.urlparse(cleaned_url)
        netloc = parsed.netloc.lower()

        # Must be linkedin.com
        if not (netloc == "linkedin.com" or netloc.endswith(".linkedin.com")):
            return False, None, f"Not a valid LinkedIn host: {parsed.netloc}"

        match = LINKEDIN_PROFILE_REGEX.match(cleaned_url)
        if not match:
            return False, None, "URL does not match standard LinkedIn personal profile pattern (/in/{username})"

        username = match.group(2).lower()
        if username in RESERVED_LINKEDIN_SLUGS or len(username) < 3:
            return False, None, f"URL points to reserved or invalid slug: '{username}'"

        canonical_url = f"https://www.linkedin.com/in/{match.group(2)}"

        # Optional active network check
        if check_network:
            try:
                import httpx
                response = httpx.head(canonical_url, follow_redirects=True, timeout=5.0)
                if response.status_code in (404, 410):
                    return False, None, f"Profile URL returned HTTP {response.status_code} (broken)"
            except Exception as e:
                logger.debug("Network verification skipped or failed for %s: %s", canonical_url, e)

        return True, canonical_url, None

    def _check_requisition_ownership(
        self,
        candidate_name: str,
        job_context: dict[str, Any],
        explicit_claim: bool,
        claim_evidence: str | None,
    ) -> tuple[bool, str]:
        """Verify whether there is direct, verifiable evidence of requisition ownership.

        RULE: Never claim that a person owns a job requisition without evidence.
        """
        # 1. Check job post author metadata
        author = str(job_context.get("posted_by", job_context.get("author", ""))).strip().lower()
        if author and candidate_name.lower() in author:
            return True, f"Listed as primary job post author ('{author}')"

        # 2. Check recruiter contact metadata in job
        recruiter_contact = str(job_context.get("recruiter_contact", "")).strip().lower()
        if recruiter_contact and candidate_name.lower() in recruiter_contact:
            return True, "Explicitly designated as job requisition contact"

        # 3. Check job description text for explicit contact cues
        description = str(job_context.get("description", "")).lower()
        cand_lower = candidate_name.lower()
        if cand_lower in description:
            # Check proximity to contact phrases
            for cue in ["reach out to", "contact", "posted by", "hiring manager:", "recruiter:"]:
                if f"{cue} {cand_lower}" in description or f"{cand_lower} is the hiring" in description:
                    return True, f"Referenced in job description as hiring contact ({cue})"

        # 4. Check explicit claim against evidence
        if explicit_claim and claim_evidence and cand_lower in claim_evidence.lower():
            return True, f"Documented provenance: {claim_evidence}"

        # Default conservative position: NO ownership claim
        return False, "No direct evidence of requisition ownership; associated via company talent team."

    def _determine_status_and_confidence(
        self,
        name_valid: bool,
        company_valid: bool,
        role_tier: RecruiterRoleTier,
        url_valid: bool,
        has_url: bool,
        is_job_owner: bool,
        ownership_evidence: str,
        title_reason: str,
        company_reason: str,
        url_error: str | None,
    ) -> tuple[RecruiterStatus, float, str]:
        """Calculate confidence score and assign conservative status."""
        if not name_valid or role_tier == RecruiterRoleTier.UNRELATED:
            reason = f"Rejected: {title_reason}" if not role_tier != RecruiterRoleTier.UNRELATED else "Invalid identity"
            return RecruiterStatus.NOT_FOUND, 0.0, reason

        if not company_valid:
            return RecruiterStatus.UNVERIFIED, 0.15, f"Company mismatch ({company_reason})"

        if has_url and not url_valid:
            return RecruiterStatus.UNVERIFIED, 0.30, f"Invalid or broken profile URL ({url_error})"

        # Scoring components:
        # Base: 0.20 (verified human name)
        # Company verified: +0.30
        # Role verified:
        #   Tiers 1-3 (Recruiter / TA / Tech Recruiter): +0.30
        #   Tiers 4-5 (Hiring / Eng Manager): +0.25
        #   Tier 6 (People Ops / HR): +0.20
        # URL verified: +0.15
        # Direct requisition ownership proof: +0.05
        confidence = 0.20 + 0.30

        if role_tier in (RecruiterRoleTier.RECRUITER, RecruiterRoleTier.TALENT_ACQUISITION, RecruiterRoleTier.TECHNICAL_RECRUITER):
            confidence += 0.30
        elif role_tier in (RecruiterRoleTier.HIRING_MANAGER, RecruiterRoleTier.ENGINEERING_MANAGER):
            confidence += 0.25
        else:
            confidence += 0.20

        if url_valid:
            confidence += 0.15

        if is_job_owner:
            confidence += 0.05

        confidence = min(1.0, confidence)

        # Status Assignment
        ownership_note = (
            " (Requisition Owner)"
            if is_job_owner
            else " (No direct evidence of requisition ownership)"
        )

        if company_valid and role_tier != RecruiterRoleTier.UNRELATED and url_valid and confidence >= 0.80:
            status = RecruiterStatus.VERIFIED
            reason = f"Verified {title_reason} at {company_reason}{ownership_note} with confirmed profile URL."
        elif company_valid and role_tier != RecruiterRoleTier.UNRELATED and (not has_url or not url_valid) and confidence >= 0.50:
            status = RecruiterStatus.PLAUSIBLE
            reason = f"Plausible {title_reason} at {company_reason}{ownership_note}, but profile URL is unverified or absent."
        else:
            status = RecruiterStatus.UNVERIFIED
            reason = f"Unverified candidate: insufficient confidence ({confidence:.2f})."

        return status, confidence, reason
