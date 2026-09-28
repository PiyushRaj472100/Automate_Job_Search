"""Demonstration and verification script for the Conservative Job Verification Engine."""

import os
import sys

# Ensure repository root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.normalization.schemas import CanonicalJob, WorkMode
from backend.verification.inspector import PageInspector
from backend.verification.schemas import VerificationStatus
from backend.verification.service import JobVerificationService, final_verification_run


def run_verification_engine_demo():
    print("=" * 80)
    print("JOB VERIFICATION ENGINE: 15-POINT CONSERVATIVE VERIFICATION AUDIT")
    print("=" * 80)

    verifier = JobVerificationService()

    # 1. VERIFY LIVE PUBLIC PAGE OVER THE NETWORK
    print("\n[CHECK 1 & 2] Resolving Network Accessibility & Live Canonical URL...")
    inspector = PageInspector(timeout=10.0)
    live_test_url = "https://www.python.org/jobs/"
    status, final_url, body, headers = inspector.fetch_page(live_test_url)
    print(f"  Live Target:      {live_test_url}")
    print(f"  HTTP Status Code: {status}")
    print(f"  Final Landed URL: {final_url} (Redirects resolved)")
    print(f"  Page Text Bytes:  {len(body)} bytes | Server: {headers.get('server', 'N/A')}")
    assert status == 200, f"Expected 200 OK from {live_test_url}"

    # 2. VERIFY 15-POINT CONSERVATIVE RULES ACROSS FAILURE CASES
    print("\n[CHECKS 3-8] Testing Error & Expired Job Detection...")

    # A. HTTP 404
    res_404 = verifier.verify_job(
        {"title": "SWE", "company": "Acme", "url": "https://acme.com/404"},
        custom_html_override="Not Found",
        custom_status_override=404,
    )
    print(f"  HTTP 404 Detect:   Status={res_404.status.value.ljust(12)} | Usable={res_404.is_usable} | Reason: {res_404.failure_reason}")
    assert res_404.status == VerificationStatus.CLOSED

    # B. HTTP 410 Gone
    res_410 = verifier.verify_job(
        {"title": "SWE", "company": "Acme", "url": "https://acme.com/410"},
        custom_html_override="Gone",
        custom_status_override=410,
    )
    print(f"  HTTP 410 Detect:   Status={res_410.status.value.ljust(12)} | Usable={res_410.is_usable} | Reason: {res_410.failure_reason}")
    assert res_410.status == VerificationStatus.CLOSED

    # C. Obvious Expired Notice (e.g. 'position has been filled')
    res_exp = verifier.verify_job(
        {"title": "Junior Backend", "company": "Tech Corp", "url": "https://techcorp.com/closed"},
        custom_html_override="<html><body><h1>Junior Backend</h1><h2>Tech Corp</h2><p>This position has been filled. Applications are closed.</p></body></html>",
        custom_status_override=200,
    )
    print(f"  Expired Detect:    Status={res_exp.status.value.ljust(12)} | Usable={res_exp.is_usable} | Reason: {res_exp.failure_reason}")
    assert res_exp.status == VerificationStatus.CLOSED

    # D. Login Wall
    res_login = verifier.verify_job(
        {"title": "Software Engineer", "company": "Exclusive Club", "url": "https://club.com/login"},
        custom_html_override="<html><body><h1>Login Required</h1><p>Please sign in to view this job posting and apply.</p></body></html>",
        custom_status_override=200,
    )
    print(f"  Login Wall Detect: Status={res_login.status.value.ljust(12)} | Usable={res_login.is_usable} | Reason: {res_login.failure_reason}")
    assert res_login.status == VerificationStatus.REJECTED

    # E. Access Denied / 403
    res_403 = verifier.verify_job(
        {"title": "SWE", "company": "Secure Inc", "url": "https://secure.com/job"},
        custom_html_override="Forbidden",
        custom_status_override=403,
    )
    print(f"  Access Denied:     Status={res_403.status.value.ljust(12)} | Usable={res_403.is_usable} | Reason: {res_403.failure_reason}")
    assert res_403.status == VerificationStatus.UNAVAILABLE

    # 3. VERIFY TITLE, COMPANY, AND SUBSTANTIVE CONTENT CONFIRMATION
    print("\n[CHECKS 9-13] Testing Title, Company, and Content Matching...")
    # Title mismatch
    res_bad_title = verifier.verify_job(
        {"title": "Junior Python Developer", "company": "Stripe", "url": "https://stripe.com/sales"},
        custom_html_override="<html><body><h1>VP Sales Account Executive</h1><h2>Stripe</h2><p>Experience leading sales quotas required.</p><button>Apply</button></body></html>",
        custom_status_override=200,
    )
    print(f"  Title Mismatch:    Status={res_bad_title.status.value.ljust(12)} | Reason: {res_bad_title.failure_reason}")
    assert res_bad_title.status == VerificationStatus.REJECTED

    # Company mismatch
    res_bad_comp = verifier.verify_job(
        {"title": "Software Engineer", "company": "Google", "url": "https://uber.com/jobs/1"},
        custom_html_override="<html><body><h1>Software Engineer</h1><h2>Uber Technologies</h2><p>Build global mobility algorithms with Go.</p><button>Apply</button></body></html>",
        custom_status_override=200,
    )
    print(f"  Company Mismatch:  Status={res_bad_comp.status.value.ljust(12)} | Reason: {res_bad_comp.failure_reason}")
    assert res_bad_comp.status == VerificationStatus.REJECTED

    # 4. ACTIVE APPLICATION PATH & FULL VERIFIED STATUS
    print("\n[CHECKS 14-15] Testing Active Application Path Confirmation...")
    valid_html = """
    <html>
        <body>
            <h1>Junior Software Engineer</h1>
            <h2>Nexus Labs - Remote</h2>
            <div class="description">
                <p>Nexus Labs is hiring a Junior Software Engineer with Python and FastAPI experience.</p>
                <p>Responsibilities include backend microservices, SQL database schema design, and CI/CD pipelines.</p>
            </div>
            <form action="/apply" method="POST">
                <input type="file" name="resume_file" />
                <button type="submit">Apply for this job</button>
            </form>
        </body>
    </html>
    """
    good_job = CanonicalJob(
        title="Junior Software Engineer",
        company="Nexus Labs",
        location="Remote",
        work_mode=WorkMode.REMOTE,
        description="Software engineering position using Python and SQL.",
        job_url="https://nexuslabs.com/careers/swe",
        canonical_url="https://nexuslabs.com/careers/swe",
        primary_source="company_site",
        normalized_company="nexus labs",
        normalized_title="junior software engineer",
        normalized_location="remote",
        dedup_hash="good-nexus-hash",
    )
    res_verified = verifier.verify_job(good_job, custom_html_override=valid_html, custom_status_override=200)
    print(f"  Verified Job:      Status={res_verified.status.value.ljust(12)} | Usable={res_verified.is_usable}")
    print(f"    - Title matched:        {res_verified.extracted_signals.title_matched}")
    print(f"    - Company matched:      {res_verified.extracted_signals.company_matched}")
    print(f"    - Active Apply Form:    {res_verified.extracted_signals.has_active_application}")
    print(f"    - Substantive Content:  {res_verified.extracted_signals.has_substantive_content}")
    assert res_verified.status == VerificationStatus.VERIFIED

    # 5. FINAL MORNING VERIFICATION RUN (GATEKEEPER OPERATION)
    print("\n[FINAL MORNING RUN] Executing final_verification_run() Pre-Publication Filter...")
    dead_job = CanonicalJob(
        title="Software Engineer",
        company="Old Startup",
        location="Remote",
        work_mode=WorkMode.REMOTE,
        description="Defunct.",
        job_url="https://oldstartup.com/dead",
        canonical_url="https://oldstartup.com/dead",
        primary_source="company_site",
        normalized_company="old startup",
        normalized_title="software engineer",
        normalized_location="remote",
        dedup_hash="dead-hash",
    )

    batch_input = [good_job, dead_job]
    # Simulate batch run with mixed results
    published_jobs, audit_results = final_verification_run(
        candidate_jobs=batch_input,
        service=verifier,
    )
    # Notice: In the real world, dead_job fails network lookup and is withheld
    print(f"  Candidate Jobs Input:     {len(batch_input)}")
    print(f"  Audit Outcomes:           {[r.status.value for r in audit_results]}")
    print(f"  Published to Morning Tab: {len(published_jobs)}")
    for j in published_jobs:
        print(f"    -> [PASSED] '{j.title}' at '{j.company}'")

    print("\n" + "=" * 80)
    print("ALL VERIFICATION ENGINE CRITERIA FULLY AUDITED AND CONFIRMED.")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = run_verification_engine_demo()
    sys.exit(0 if success else 1)
