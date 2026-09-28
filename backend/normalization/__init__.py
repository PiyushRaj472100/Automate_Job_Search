"""Job Normalization and Multi-Signal Deduplication package."""

from backend.normalization.deduplication import (
    DeduplicationEngine,
    DuplicateDetector,
    JobMerger,
    string_similarity,
    token_jaccard_similarity,
)
from backend.normalization.normalizer import (
    JobNormalizer,
    clean_description,
    extract_requisition_id,
    extract_skills_from_text,
    infer_work_mode,
    normalize_company,
    normalize_location,
    normalize_title,
    parse_date,
)
from backend.normalization.schemas import (
    CanonicalJob,
    DuplicateMatchReason,
    DuplicateMatchResult,
    WorkMode,
)
from backend.normalization.url_canonicalizer import (
    extract_canonical_from_html,
    normalize_url,
    resolve_redirects,
)

__all__ = [
    "CanonicalJob",
    "DeduplicationEngine",
    "DuplicateDetector",
    "DuplicateMatchReason",
    "DuplicateMatchResult",
    "JobMerger",
    "JobNormalizer",
    "WorkMode",
    "clean_description",
    "extract_canonical_from_html",
    "extract_requisition_id",
    "extract_skills_from_text",
    "infer_work_mode",
    "normalize_company",
    "normalize_location",
    "normalize_title",
    "normalize_url",
    "parse_date",
    "resolve_redirects",
    "string_similarity",
    "token_jaccard_similarity",
]
