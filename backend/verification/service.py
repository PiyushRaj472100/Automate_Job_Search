"""Conservative Job Verification Service and Final Morning Verification Run."""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from backend.models.verification import VerificationEvent
from backend.normalization.schemas import CanonicalJob
from backend.verification.inspector import PageInspector
from backend.verification.schemas import (
    ExtractedPageSignals,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger("job_intelligence.verification.service")


class JobVerificationService:
    """Ultra-conservative job accessibility and authenticity verifier.

    Enforces strict validation rules:
    - Never marks uncertain or ambiguous postings as VERIFIED.
    - Confirms live HTTP accessibility, redirects, and non-expired state.
    - Confirms job title, hiring company, and substantive job content.
    - Verifies direct application mechanisms and application URLs separately.
    - Produces persistent, immutable audit events for every verification check.
    """

    def __init__(self, inspector: PageInspector | None = None) -> None:
        self.inspector = inspector or PageInspector()

    def verify_job(
        self,
        job: CanonicalJob | dict[str, Any],
        custom_html_override: str | None = None,
        custom_status_override: int | None = None,
    ) -> VerificationResult:
        """Execute the 15-point conservative verification pipeline on a candidate job.

        Args:
            job: CanonicalJob instance or dictionary representing the job.
            custom_html_override: Optional HTML body for hermetic testing.
            custom_status_override: Optional HTTP status code for hermetic testing.

        Returns:
            VerificationResult with conservative status assignment and diagnostic signals.
        """
        # Unpack job fields
        if isinstance(job, CanonicalJob):
            job_id = job.id
            title = job.title
            company = job.company
            location = job.location
            job_url = job.canonical_url or job.job_url
            app_url = job.application_url
        elif isinstance(job, dict):
            job_id = job.get("id", job.get("job_id"))
            title = job.get("title", "")
            company = job.get("company", job.get("company_name", ""))
            location = job.get("location", "Remote")
            job_url = job.get("canonical_url", job.get("job_url", job.get("url", "")))
            app_url = job.get("application_url", job.get("app_url"))
        else:
            # SQLAlchemy Job ORM instance or generic duck-typed model
            job_id = getattr(job, "id", None)
            title = getattr(job, "title", "")
            company = getattr(job, "company_name", getattr(job, "company", ""))
            location = getattr(job, "location", "Remote")
            job_url = getattr(job, "canonical_url", getattr(job, "job_url", ""))
            app_url = getattr(job, "application_url", None)


        # Step 1-3: Fetch job page and check HTTP status
        if custom_html_override is not None:
            status = custom_status_override if custom_status_override is not None else 200
            final_url = job_url
            body = custom_html_override
            headers: dict[str, Any] = {}
        else:
            status, final_url, body, headers = self.inspector.fetch_page(job_url)

        # -------------------------------------------------------------
        # Check HTTP Accessibility & Error Codes
        # -------------------------------------------------------------
        if status is None:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.UNAVAILABLE,
                is_usable=False,
                url=job_url,
                http_status=None,
                application_url=app_url,
                extracted_signals=ExtractedPageSignals(http_status=None),
                failure_reason="Failed to establish network connection or DNS resolution to job host",
            )

        # Check 4: Detect 404
        if status == 404:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.CLOSED,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=404,
                application_url=app_url,
                extracted_signals=ExtractedPageSignals(http_status=404, final_url=final_url, is_soft_404=True),
                failure_reason="HTTP 404 Not Found: Job listing has been removed",
            )

        # Check 5: Detect 410
        if status == 410:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.CLOSED,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=410,
                application_url=app_url,
                extracted_signals=ExtractedPageSignals(http_status=410, final_url=final_url),
                failure_reason="HTTP 410 Gone: Job listing permanently closed by employer",
            )

        # Check 3: Detect 5xx Upstream Server Errors
        if status >= 500:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.UNAVAILABLE,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=ExtractedPageSignals(http_status=status, final_url=final_url),
                failure_reason=f"HTTP {status} Upstream Server Error",
            )

        # Check 8: Detect Access Denied / 401 / 403
        if status in (401, 403):
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.UNAVAILABLE,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=ExtractedPageSignals(http_status=status, is_access_denied=True),
                failure_reason=f"HTTP {status} Access Denied / WAF blocking candidate traffic",
            )

        # -------------------------------------------------------------
        # Inspect Page HTML Content (Checks 6-14)
        # -------------------------------------------------------------
        signals = self.inspector.inspect_html(
            html_content=body,
            expected_title=title,
            expected_company=company,
            expected_location=location,
            status_code=status,
            final_url=final_url,
        )

        # Check 4: Soft-404 detection
        if signals.is_soft_404:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.CLOSED,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=signals,
                failure_reason="Soft 404 detected: Page text explicitly states position not found",
            )

        # Check 6: Obvious Expired-Job Notice
        if signals.is_expired_notice:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.CLOSED,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=signals,
                failure_reason="Job expired notice detected on page (e.g. 'position has been filled')",
            )

        # Check 7: Login-Only Wall
        if signals.is_login_wall:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.REJECTED,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=signals,
                failure_reason="Login required wall: Job details hidden behind mandatory authentication",
            )

        # Check 8: Access Denied in Body
        if signals.is_access_denied:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.UNAVAILABLE,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=signals,
                failure_reason="Bot detection / Cloudflare security challenge blocked page extraction",
            )

        # Check 10: Confirm Job Title
        if not signals.title_matched:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.REJECTED,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=signals,
                failure_reason=f"Title mismatch: Expected '{title}' not found on destination page",
            )

        # Check 11: Confirm Company
        if not signals.company_matched:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.REJECTED,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=signals,
                failure_reason=f"Company mismatch: Expected hiring company '{company}' not found on destination page",
            )

        # Check 13: Substantive Job Content Confirmation
        if not signals.has_substantive_content:
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.REJECTED,
                is_usable=False,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                extracted_signals=signals,
                failure_reason="Landing page lacks substantive job description or qualifications content",
            )

        # -------------------------------------------------------------
        # Check 14-15: Verify Application Mechanism & Application URL
        # -------------------------------------------------------------
        app_status = None
        app_usable = False

        if app_url and app_url.strip():
            # If in mock mode or live mode
            if custom_html_override is not None:
                app_status = 200
                app_usable = True
            else:
                app_status, app_usable = self.inspector.verify_application_url(app_url)

            if not app_usable and app_status in (404, 410):
                return VerificationResult(
                    job_id=job_id,
                    status=VerificationStatus.CLOSED,
                    is_usable=False,
                    url=job_url,
                    final_url=final_url,
                    http_status=status,
                    application_url=app_url,
                    application_url_status=app_status,
                    application_usable=False,
                    extracted_signals=signals,
                    failure_reason=f"Application URL returned HTTP {app_status} (application path defunct)",
                )

        # Conservative Status Decision:
        # VERIFIED: Confirmed accessible, content verified, active application mechanism confirmed, app URL verified
        if signals.has_active_application and (not app_url or app_usable):
            return VerificationResult(
                job_id=job_id,
                status=VerificationStatus.VERIFIED,
                is_usable=True,
                url=job_url,
                final_url=final_url,
                http_status=status,
                application_url=app_url,
                application_url_status=app_status,
                application_usable=app_usable or signals.has_active_application,
                extracted_signals=signals,
                raw_headers=headers,
            )

        # ACTIVE: Reachable, company/title matched, but application path is generic
        return VerificationResult(
            job_id=job_id,
            status=VerificationStatus.ACTIVE,
            is_usable=True,
            url=job_url,
            final_url=final_url,
            http_status=status,
            application_url=app_url,
            application_url_status=app_status,
            application_usable=app_usable,
            extracted_signals=signals,
            raw_headers=headers,
        )

    def record_event(
        self,
        db_session: Session,
        job_id: uuid.UUID,
        result: VerificationResult,
    ) -> VerificationEvent:
        """Create and commit an immutable VerificationEvent in PostgreSQL."""
        event = VerificationEvent(
            job_id=job_id,
            verified_at=result.timestamp,
            http_status_code=result.http_status,
            final_url=result.final_url,
            is_active=result.is_usable,
            verification_method="conservative_content_and_url_inspection",
            status_reason=result.failure_reason or f"Verified: {result.status.value}",
            raw_response_headers={
                "status": result.status.value,
                "is_usable": result.is_usable,
                "failure_reason": result.failure_reason,
                "signals": result.extracted_signals.model_dump(),
                "headers": result.raw_headers,
            },
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        logger.info(
            "Recorded VerificationEvent for job %s: status=%s usable=%s",
            job_id,
            result.status.value,
            result.is_usable,
        )
        return event


def final_verification_run(
    candidate_jobs: list[CanonicalJob],
    db_session: Session | None = None,
    service: JobVerificationService | None = None,
) -> tuple[list[CanonicalJob], list[VerificationResult]]:
    """Callable morning verification gatekeeper.

    Re-verifies all candidate jobs immediately prior to publishing to the Google Sheets
    daily application dashboard.

    Guarantees:
    - Filters out CLOSED, UNAVAILABLE, and REJECTED jobs.
    - Only jobs marked VERIFIED or ACTIVE are returned for sheet publishing.
    - Creates verification history audit events in PostgreSQL when db_session is supplied.

    Returns:
        Tuple of (verified_jobs_ready_to_publish, all_verification_results)
    """
    verifier = service or JobVerificationService()
    verified_jobs: list[CanonicalJob] = []
    all_results: list[VerificationResult] = []

    logger.info("Executing final morning verification run on %d candidate jobs", len(candidate_jobs))

    for job in candidate_jobs:
        result = verifier.verify_job(job)
        all_results.append(result)

        if db_session and job.id:
            try:
                # Ensure job.id is UUID if passed as string
                job_uuid = job.id if isinstance(job.id, uuid.UUID) else uuid.UUID(str(job.id))
                verifier.record_event(db_session, job_uuid, result)
            except Exception as e:
                logger.warning("Failed to record verification event for job '%s': %s", job.id, e)

        if result.is_usable and result.status in (VerificationStatus.VERIFIED, VerificationStatus.ACTIVE):
            verified_jobs.append(job)
        else:
            logger.info(
                "Job '%s' at '%s' withheld from morning sheet: Status=%s Reason=%s",
                job.title,
                job.company,
                result.status.value,
                result.failure_reason,
            )

    logger.info(
        "Final morning check complete: %d of %d jobs confirmed usable (%d withheld)",
        len(verified_jobs),
        len(candidate_jobs),
        len(candidate_jobs) - len(verified_jobs),
    )
    return verified_jobs, all_results
