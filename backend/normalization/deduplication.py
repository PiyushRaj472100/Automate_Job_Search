"""Multi-signal duplicate detection and canonical record merging engine."""

import logging
from difflib import SequenceMatcher

from backend.normalization.schemas import (
    CanonicalJob,
    DuplicateMatchReason,
    DuplicateMatchResult,
    WorkMode,
)

logger = logging.getLogger("job_intelligence.normalization.deduplication")

# Seniority level keywords that distinguish fundamentally different job openings
SENIORITY_TOKENS = {
    "junior": {"junior", "jr", "entry", "fresher", "graduate", "associate", "0-2"},
    "mid": {"mid", "intermediate", "experienced", "level 2", "ii"},
    "senior": {"senior", "sr", "lead", "principal", "staff", "architect", "director", "head"},
}

# Domain specialization keywords that distinguish roles with otherwise similar titles
SPECIALIZATION_TOKENS = {
    "frontend": {"frontend", "front-end", "ui", "client"},
    "backend": {"backend", "back-end", "server", "distributed systems"},
    "devops": {"devops", "sre", "infrastructure", "platform", "cloud"},
    "data_ai": {"data", "machine learning", "ml", "ai", "deep learning", "nlp"},
    "mobile": {"android", "ios", "mobile", "flutter", "react native"},
}


def string_similarity(a: str, b: str) -> float:
    """Calculate character-level sequence matcher ratio between two strings."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def token_jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Calculate Jaccard similarity between two token sets."""
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def get_seniority_tier(title: str) -> str | None:
    """Identify seniority tier from title tokens."""
    tokens = set(title.lower().replace("-", " ").split())
    for tier, keywords in SENIORITY_TOKENS.items():
        if tokens & keywords:
            return tier
    return None


def get_specialization(title: str) -> str | None:
    """Identify core engineering specialization from title."""
    lower_title = title.lower()
    for spec, keywords in SPECIALIZATION_TOKENS.items():
        if any(k in lower_title for k in keywords):
            return spec
    return None


class DuplicateDetector:
    """Multi-signal evaluator that determines if two job postings represent the exact same role."""

    def compare(self, job_a: CanonicalJob, job_b: CanonicalJob) -> DuplicateMatchResult:
        """Compare two CanonicalJob instances and return a detailed DuplicateMatchResult."""
        # -------------------------------------------------------------
        # NEGATIVE GUARDS: Rules that strictly prevent incorrect merges
        # -------------------------------------------------------------

        # Guard 1: Company mismatch
        comp_sim = string_similarity(job_a.normalized_company, job_b.normalized_company)
        company_matches = (
            job_a.normalized_company == job_b.normalized_company
            or job_a.normalized_company in job_b.normalized_company
            or job_b.normalized_company in job_a.normalized_company
            or comp_sim >= 0.88
        )
        if not company_matches:
            return DuplicateMatchResult(
                is_duplicate=False,
                confidence_score=0.0,
                rejection_reason=f"Company mismatch: '{job_a.company}' vs '{job_b.company}'",
            )

        # Guard 2: Seniority level mismatch (e.g. Junior vs Senior / Staff)
        tier_a = get_seniority_tier(job_a.title)
        tier_b = get_seniority_tier(job_b.title)
        if tier_a and tier_b and tier_a != tier_b:
            return DuplicateMatchResult(
                is_duplicate=False,
                confidence_score=0.1,
                rejection_reason=f"Seniority tier mismatch: {tier_a} vs {tier_b}",
            )

        # Guard 3: Specialization mismatch (e.g. Frontend vs Backend)
        spec_a = get_specialization(job_a.title)
        spec_b = get_specialization(job_b.title)
        if spec_a and spec_b and spec_a != spec_b:
            return DuplicateMatchResult(
                is_duplicate=False,
                confidence_score=0.1,
                rejection_reason=f"Specialization mismatch: {spec_a} vs {spec_b}",
            )

        # Guard 4: Location conflict for on-site / hybrid roles
        # If neither is Remote and locations are distinct geographic entities, do not merge!
        both_remote = (job_a.location == "Remote" or job_a.work_mode == WorkMode.REMOTE) and (
            job_b.location == "Remote" or job_b.work_mode == WorkMode.REMOTE
        )
        loc_a_norm = job_a.normalized_location
        loc_b_norm = job_b.normalized_location
        locations_compatible = (
            both_remote
            or loc_a_norm == loc_b_norm
            or loc_a_norm in loc_b_norm
            or loc_b_norm in loc_a_norm
            or string_similarity(loc_a_norm, loc_b_norm) >= 0.80
        )
        if not locations_compatible:
            return DuplicateMatchResult(
                is_duplicate=False,
                confidence_score=0.2,
                rejection_reason=f"Geographic location conflict: '{job_a.location}' vs '{job_b.location}'",
            )

        # -------------------------------------------------------------
        # POSITIVE SIGNALS: Multiple corroborating identifiers
        # -------------------------------------------------------------

        # Signal 1: Matching ATS Requisition ID
        if job_a.requisition_id and job_b.requisition_id:
            clean_req_a = job_a.requisition_id.lower().replace("-", "").replace("_", "").strip()
            clean_req_b = job_b.requisition_id.lower().replace("-", "").replace("_", "").strip()
            if clean_req_a == clean_req_b:
                return DuplicateMatchResult(
                    is_duplicate=True,
                    confidence_score=1.0,
                    match_reason=DuplicateMatchReason.REQUISITION_ID,
                    signals={"requisition_id": job_a.requisition_id},
                )

        # Signal 2: Matching Canonical Application URL
        if job_a.application_url and job_b.application_url:
            if job_a.application_url == job_b.application_url:
                return DuplicateMatchResult(
                    is_duplicate=True,
                    confidence_score=1.0,
                    match_reason=DuplicateMatchReason.APPLICATION_URL,
                    signals={"application_url": job_a.application_url},
                )

        # Signal 3: Matching Canonical Job URL
        if job_a.canonical_url and job_b.canonical_url:
            if job_a.canonical_url == job_b.canonical_url:
                return DuplicateMatchResult(
                    is_duplicate=True,
                    confidence_score=1.0,
                    match_reason=DuplicateMatchReason.CANONICAL_URL,
                    signals={"canonical_url": job_a.canonical_url},
                )

        # Signal 4: Matching Company + External Job ID
        if job_a.job_id and job_b.job_id and company_matches:
            if job_a.job_id.strip() == job_b.job_id.strip():
                return DuplicateMatchResult(
                    is_duplicate=True,
                    confidence_score=0.98,
                    match_reason=DuplicateMatchReason.COMPANY_AND_JOB_ID,
                    signals={"job_id": job_a.job_id},
                )

        # Signal 5: Composite exact match on Normalized (Company, Title, Location)
        if (
            job_a.normalized_company == job_b.normalized_company
            and job_a.normalized_title == job_b.normalized_title
            and loc_a_norm == loc_b_norm
        ):
            return DuplicateMatchResult(
                is_duplicate=True,
                confidence_score=0.95,
                match_reason=DuplicateMatchReason.COMPOSITE_EXACT,
                signals={"composite": f"{job_a.normalized_company}|{job_a.normalized_title}"},
            )

        # Signal 6: Multi-Signal Semantic & Token Overlap (e.g. Cross-source LinkedIn vs Career Page)
        title_sim = string_similarity(job_a.normalized_title, job_b.normalized_title)
        title_tokens_a = set(job_a.normalized_title.split())
        title_tokens_b = set(job_b.normalized_title.split())
        title_jaccard = token_jaccard_similarity(title_tokens_a, title_tokens_b)

        skill_jaccard = token_jaccard_similarity(set(job_a.skills), set(job_b.skills))

        # Check description similarity if titles are very close
        desc_sim = 0.0
        if job_a.description and job_b.description:
            # Sample first 400 chars of cleaned description
            desc_sim = string_similarity(job_a.description[:400], job_b.description[:400])

        is_cross_source_semantic_match = (
            company_matches
            and (title_sim >= 0.85 or title_jaccard >= 0.70)
            and locations_compatible
            and (skill_jaccard >= 0.50 or desc_sim >= 0.75)
        )

        if is_cross_source_semantic_match:
            combined_conf = round(0.5 * title_sim + 0.25 * comp_sim + 0.25 * max(skill_jaccard, desc_sim), 2)
            return DuplicateMatchResult(
                is_duplicate=True,
                confidence_score=min(combined_conf, 0.95),
                match_reason=DuplicateMatchReason.SEMANTIC_SIMILARITY,
                signals={
                    "title_similarity": round(title_sim, 2),
                    "skill_jaccard": round(skill_jaccard, 2),
                    "description_similarity": round(desc_sim, 2),
                },
            )

        return DuplicateMatchResult(
            is_duplicate=False,
            confidence_score=round(max(title_sim, comp_sim) * 0.5, 2),
            rejection_reason="Insufficient similarity across multi-signal evaluation",
        )


class JobMerger:
    """Merges duplicate CanonicalJob postings into an enriched, unified canonical record."""

    @staticmethod
    def merge(primary: CanonicalJob, secondary: CanonicalJob, reason: DuplicateMatchReason) -> CanonicalJob:
        """Merge secondary duplicate job into the primary canonical job."""
        # Determine preferred URLs (prefer direct career portal over aggregators)
        authoritative_sources = {"greenhouse", "lever", "workday", "ashby", "company_site", "career_page"}
        is_secondary_more_authoritative = (
            secondary.primary_source.lower() in authoritative_sources
            and primary.primary_source.lower() not in authoritative_sources
        )

        final_job_url = secondary.job_url if is_secondary_more_authoritative else primary.job_url
        final_app_url = secondary.application_url or primary.application_url
        final_canonical_url = secondary.canonical_url if is_secondary_more_authoritative else primary.canonical_url

        # Combine alternate URLs
        merged_urls = list(dict.fromkeys(
            primary.alternate_urls
            + secondary.alternate_urls
            + [primary.job_url, secondary.job_url, primary.canonical_url, secondary.canonical_url]
        ))

        # Retain requisition ID and job ID
        merged_req_id = primary.requisition_id or secondary.requisition_id
        merged_job_id = primary.job_id or secondary.job_id

        # Merge unique sources
        merged_sources = list(dict.fromkeys(primary.sources + secondary.sources))

        # Merge unique skills
        merged_skills = sorted(set(primary.skills + secondary.skills))

        # Retain richest description
        merged_description = primary.description if len(primary.description) >= len(secondary.description) else secondary.description

        # Aggregate dates
        posting_dates = [d for d in [primary.posting_date, secondary.posting_date] if d]
        final_posting_date = min(posting_dates) if posting_dates else None

        first_seens = [d for d in [primary.first_seen, secondary.first_seen] if d]
        final_first_seen = min(first_seens) if first_seens else primary.first_seen

        last_seens = [d for d in [primary.last_seen, secondary.last_seen] if d]
        final_last_seen = max(last_seens) if last_seens else primary.last_seen

        # Deduplication tracking
        merged_reasons = list(dict.fromkeys(primary.match_reasons + [reason]))
        merged_payloads = primary.raw_payloads + secondary.raw_payloads

        # Create updated canonical job
        primary.job_url = final_job_url
        primary.application_url = final_app_url
        primary.canonical_url = final_canonical_url
        primary.alternate_urls = merged_urls
        primary.requisition_id = merged_req_id
        primary.job_id = merged_job_id
        primary.sources = merged_sources
        primary.skills = merged_skills
        primary.description = merged_description
        primary.posting_date = final_posting_date
        primary.first_seen = final_first_seen
        primary.last_seen = final_last_seen
        primary.duplicate_count += 1
        primary.match_reasons = merged_reasons
        primary.raw_payloads = merged_payloads

        return primary


class DeduplicationEngine:
    """Clustering and deduplication engine for batch and stream job processing."""

    def __init__(self) -> None:
        self.detector = DuplicateDetector()
        self.merger = JobMerger()

    def deduplicate(self, jobs: list[CanonicalJob]) -> list[CanonicalJob]:
        """Deduplicate a list of CanonicalJob instances, clustering and merging duplicates."""
        if not jobs:
            return []

        canonical_records: list[CanonicalJob] = []

        for candidate in jobs:
            merged = False
            for existing in canonical_records:
                result = self.detector.compare(existing, candidate)
                if result.is_duplicate and result.match_reason:
                    logger.info(
                        "Duplicate detected [%s]: '%s' at '%s' (Confidence: %.2f)",
                        result.match_reason.value,
                        candidate.title,
                        candidate.company,
                        result.confidence_score,
                    )
                    self.merger.merge(existing, candidate, result.match_reason)
                    merged = True
                    break

            if not merged:
                canonical_records.append(candidate)

        logger.info(
            "Deduplication finished: %d raw jobs reduced to %d canonical entities (%d duplicates merged)",
            len(jobs),
            len(canonical_records),
            len(jobs) - len(canonical_records),
        )
        return canonical_records
