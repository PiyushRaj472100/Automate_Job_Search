"""Demonstration and verification script for Job Normalization and Deduplication (Phase 5)."""

import os
import sys

# Ensure repository root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.normalization.deduplication import DeduplicationEngine, DuplicateDetector
from backend.normalization.normalizer import JobNormalizer
from backend.normalization.url_canonicalizer import normalize_url


def run_deduplication_verification():
    print("=" * 80)
    print("PHASE 5: JOB NORMALIZATION & MULTI-SIGNAL DEDUPLICATION VERIFICATION")
    print("=" * 80)

    normalizer = JobNormalizer()
    detector = DuplicateDetector()
    engine = DeduplicationEngine()

    # -------------------------------------------------------------------------
    # TEST CASE 1: Same job from LinkedIn aggregator and Direct Company Site
    # -------------------------------------------------------------------------
    print("\n[TEST CASE 1] Cross-Source Aggregator vs Direct Career Page...")
    linkedin_job = normalizer.normalize({
        "title": "Junior Backend Engineer (m/f/d)",
        "company": "Stripe, Inc.",
        "location": "San Francisco, CA",
        "work_mode": "hybrid",
        "description": "Building payment infrastructure with Python, PostgreSQL, and distributed systems.",
        "url": "https://www.linkedin.com/jobs/view/99887766/?refId=feed_search&trackingId=abc",
        "application_url": "https://www.linkedin.com/jobs/apply/99887766",
        "source": "linkedin",
        "tags": ["Python", "PostgreSQL"],
    })

    company_job = normalizer.normalize({
        "title": "Junior Backend Engineer",
        "company": "Stripe",
        "location": "San Francisco, CA",
        "work_mode": "hybrid",
        "description": "Building payment infrastructure with Python, PostgreSQL, and Docker. 0-2 years experience.",
        "url": "https://stripe.com/jobs/listing/junior-backend-engineer",
        "application_url": "https://boards.greenhouse.io/stripe/jobs/99887766",
        "source": "greenhouse",
        "tags": ["Python", "PostgreSQL", "Docker"],
    })

    result_1 = detector.compare(linkedin_job, company_job)
    print(f"  Comparison Result: is_duplicate={result_1.is_duplicate}, reason='{result_1.match_reason}', confidence={result_1.confidence_score}")
    merged_1 = engine.deduplicate([linkedin_job, company_job])
    print(f"  Result: 2 raw jobs merged into {len(merged_1)} canonical job.")
    c1 = merged_1[0]
    print(f"  Canonical Entity: '{c1.title}' at '{c1.company}' | Sources: {c1.sources} | App URL: {c1.application_url}")
    print(f"  Merged Skills: {c1.skills} | Duplicate Count: {c1.duplicate_count}")
    assert len(merged_1) == 1

    # -------------------------------------------------------------------------
    # TEST CASE 2: Same job carrying different tracking parameters
    # -------------------------------------------------------------------------
    print("\n[TEST CASE 2] Tracking Parameter Sanitization & Canonical URL Matching...")
    url_a = "https://careers.airbnb.com/positions/5001/?utm_source=twitter&utm_medium=social&utm_campaign=spring2026"
    url_b = "https://careers.airbnb.com/positions/5001/?utm_source=newsletter&utm_medium=email"
    print(f"  Raw URL A: {url_a}")
    print(f"  Raw URL B: {url_b}")
    print(f"  Normalized URL A: {normalize_url(url_a)}")
    print(f"  Normalized URL B: {normalize_url(url_b)}")

    job_twitter = normalizer.normalize({"title": "SWE - Backend", "company": "Airbnb", "url": url_a, "source": "twitter"})
    job_email = normalizer.normalize({"title": "Software Engineer - Backend", "company": "Airbnb", "url": url_b, "source": "newsletter"})
    merged_2 = engine.deduplicate([job_twitter, job_email])
    print(f"  Result: 2 raw jobs merged into {len(merged_2)} canonical job. Canonical URL: {merged_2[0].canonical_url}")
    assert len(merged_2) == 1

    # -------------------------------------------------------------------------
    # TEST CASE 3: Same requisition ID across different URLs
    # -------------------------------------------------------------------------
    print("\n[TEST CASE 3] Matching Official Requisition ID with Different URLs...")
    job_req_1 = normalizer.normalize({
        "title": "Junior Python Developer",
        "company": "Databricks Inc.",
        "requisition_id": "REQ-2026-9042",
        "url": "https://remotejobsportal.io/jobs/databricks-python-dev",
        "source": "job_portal",
    })
    job_req_2 = normalizer.normalize({
        "title": "Junior Python Developer",
        "company": "Databricks",
        "requisition_id": "REQ-2026-9042",
        "url": "https://databricks.com/company/careers/openings/req-9042",
        "source": "direct_career_page",
    })
    result_3 = detector.compare(job_req_1, job_req_2)
    print(f"  Comparison Result: is_duplicate={result_3.is_duplicate}, reason='{result_3.match_reason}'")
    merged_3 = engine.deduplicate([job_req_1, job_req_2])
    print(f"  Result: {len(merged_3)} canonical job retained (Requisition: {merged_3[0].requisition_id}).")
    assert len(merged_3) == 1

    # -------------------------------------------------------------------------
    # TEST CASE 4: Same title but different locations (MUST NOT MERGE)
    # -------------------------------------------------------------------------
    print("\n[TEST CASE 4] Same Title But Different Geographic Locations (Negative Guard)...")
    job_ny = normalizer.normalize({"title": "Software Engineer", "company": "Google", "location": "New York, NY", "url": "https://careers.google.com/1", "source": "google"})
    job_london = normalizer.normalize({"title": "Software Engineer", "company": "Google", "location": "London, UK", "url": "https://careers.google.com/2", "source": "google"})
    result_4 = detector.compare(job_ny, job_london)
    print(f"  Comparison Result: is_duplicate={result_4.is_duplicate}, rejection_reason='{result_4.rejection_reason}'")
    merged_4 = engine.deduplicate([job_ny, job_london])
    print(f"  Result: {len(merged_4)} distinct jobs correctly kept separate!")
    for idx, j in enumerate(merged_4, 1):
        print(f"    - Job {idx}: '{j.title}' at '{j.company}' in '{j.location}'")
    assert len(merged_4) == 2

    # -------------------------------------------------------------------------
    # TEST CASE 5: Different jobs with similar titles (MUST NOT MERGE)
    # -------------------------------------------------------------------------
    print("\n[TEST CASE 5] Different Jobs with Similar Titles (Seniority / Specialization Guards)...")
    junior_job = normalizer.normalize({"title": "Junior Backend Engineer", "company": "Uber", "location": "San Francisco, CA", "url": "https://uber.com/1", "source": "uber"})
    senior_job = normalizer.normalize({"title": "Senior Backend Engineer", "company": "Uber", "location": "San Francisco, CA", "url": "https://uber.com/2", "source": "uber"})
    frontend_job = normalizer.normalize({"title": "Junior Frontend Engineer", "company": "Uber", "location": "San Francisco, CA", "url": "https://uber.com/3", "source": "uber"})

    res_seniority = detector.compare(junior_job, senior_job)
    print(f"  Junior vs Senior: is_duplicate={res_seniority.is_duplicate}, rejection_reason='{res_seniority.rejection_reason}'")
    res_spec = detector.compare(junior_job, frontend_job)
    print(f"  Frontend vs Backend: is_duplicate={res_spec.is_duplicate}, rejection_reason='{res_spec.rejection_reason}'")

    merged_5 = engine.deduplicate([junior_job, senior_job, frontend_job])
    print(f"  Result: All {len(merged_5)} distinct roles correctly kept separate!")
    for idx, j in enumerate(merged_5, 1):
        print(f"    - Role {idx}: '{j.title}' (Company: {j.company})")
    assert len(merged_5) == 3

    # -------------------------------------------------------------------------
    # TEST CASE 6: Missing Job ID
    # -------------------------------------------------------------------------
    print("\n[TEST CASE 6] Handling Missing Job ID...")
    job_no_id_1 = normalizer.normalize({"title": "Associate Platform Engineer", "company": "Snowflake Inc.", "location": "Remote", "job_id": None, "url": "https://snowflake.com/jobs/p1", "source": "portal_a"})
    job_no_id_2 = normalizer.normalize({"title": "Associate Platform Engineer", "company": "Snowflake", "location": "Remote", "job_id": None, "url": "https://snowflake.com/jobs/p1?ref=feed", "source": "portal_b"})
    merged_6 = engine.deduplicate([job_no_id_1, job_no_id_2])
    print(f"  Result: Successfully deduplicated via composite signals (Canonical Count: {len(merged_6)}, Duplicates: {merged_6[0].duplicate_count})")
    assert len(merged_6) == 1

    # -------------------------------------------------------------------------
    # TEST CASE 7: Missing Application URL
    # -------------------------------------------------------------------------
    print("\n[TEST CASE 7] Missing Application URL in one source...")
    job_missing_app = normalizer.normalize({"title": "Junior DevOps Engineer", "company": "Cloudflare", "location": "Austin, TX", "url": "https://cloudflare.com/devops", "application_url": None, "source": "source_1"})
    job_with_app = normalizer.normalize({"title": "Junior DevOps Engineer", "company": "Cloudflare", "location": "Austin, TX", "url": "https://cloudflare.com/devops?src=li", "application_url": "https://boards.greenhouse.io/cloudflare/apply/555", "source": "source_2"})
    merged_7 = engine.deduplicate([job_missing_app, job_with_app])
    print(f"  Result: Successfully merged. Preserved direct application URL: '{merged_7[0].application_url}'")
    assert len(merged_7) == 1
    assert merged_7[0].application_url == "https://boards.greenhouse.io/cloudflare/apply/555"

    print("\n" + "=" * 80)
    print("ALL 7 DEDUPLICATION TEST CASES FULLY VERIFIED AND PASSING.")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = run_deduplication_verification()
    sys.exit(0 if success else 1)
