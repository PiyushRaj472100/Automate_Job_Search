"""Continuous Scheduler and Daily Pipeline Orchestrator.

Implements scheduled continuous operation:
- Incremental discovery cycles with source-specific rate limits.
- Retry policies with exponential backoff on transient source failures.
- Fault isolation: individual source failures never halt the pipeline.
- Thread-safe job queue decoupling discovery from processing.
- Persistent tracking in `search_runs` (start/end times, source, status, jobs discovered/accepted/rejected, errors).
- Conservative morning final verification pass re-checking all primary candidates before updating Google Sheets.
"""

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.discovery.adapters.arbeitnow import ArbeitnowAdapter
from backend.discovery.models import RawJobPosting
from backend.discovery.query_engine import SearchQueryEngine
from backend.discovery.registry import JobDiscoveryCollector
from backend.matching.evaluator import ResumeJobMatcher
from backend.matching.schemas import MatchLevel
from backend.models.company import Company
from backend.models.job import Job, JobMatch
from backend.models.person import JobPerson
from backend.models.resume import Resume, ResumeProfile
from backend.models.search_run import SearchRun
from backend.models.verification import VerificationEvent
from backend.normalization.deduplication import DeduplicationEngine
from backend.normalization.normalizer import JobNormalizer, normalize_company
from backend.normalization.schemas import CanonicalJob
from backend.pipeline.schemas import PipelineJobOutput
from backend.recruiter.finder import RecruiterFinder
from backend.recruiter.schemas import RawCandidateProfile
from backend.recruiter.service import RecruiterDiscoveryService
from backend.scheduler.queue import JobQueueManager
from backend.scheduler.rate_limiter import SourceExhaustedError, SourceRateLimiter
from backend.scheduler.schemas import (
    CycleExecutionRecord,
    MorningPassSummary,
    ScheduleConfig,
)
from backend.sheets.service import GoogleSheetsService
from backend.verification.inspector import PageInspector
from backend.verification.schemas import VerificationStatus
from backend.verification.service import JobVerificationService

logger = logging.getLogger("job_intelligence.scheduler.service")


class ContinuousScheduler:
    """Continuous automated orchestrator managing incremental discovery, queuing, and morning passes."""

    def __init__(
        self,
        config: ScheduleConfig | None = None,
        discovery_collector: JobDiscoveryCollector | None = None,
        verification_service: JobVerificationService | None = None,
        recruiter_service: RecruiterDiscoveryService | None = None,
        sheets_service: GoogleSheetsService | None = None,
    ) -> None:
        self.config = config or ScheduleConfig()

        # Job Discovery
        if discovery_collector:
            self.collector = discovery_collector
        else:
            self.collector = JobDiscoveryCollector()
            self.collector.register(ArbeitnowAdapter())

        # Services
        self.normalizer = JobNormalizer()
        self.deduplicator = DeduplicationEngine()
        self.matcher = ResumeJobMatcher()
        self.inspector = PageInspector()
        self.verification_service = verification_service or JobVerificationService(inspector=self.inspector)
        self.recruiter_finder = RecruiterFinder(verifier=None)
        self.recruiter_service = recruiter_service or RecruiterDiscoveryService(finder=self.recruiter_finder)
        self.sheets_service = sheets_service or GoogleSheetsService()
        self.query_engine = SearchQueryEngine()

        # Rate Limiting & Queue
        self.rate_limiter = SourceRateLimiter(
            rate_limits=self.config.source_rate_limits,
            default_rate_limit=self.config.source_rate_limits.get("default", 20),
        )
        self.queue = JobQueueManager()

        # Incremental watermarks (high water mark per source)
        self._source_watermarks: dict[str, datetime] = {}

        # Daemon lifecycle control
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_morning_pass_date: str | None = None

    # -------------------------------------------------------------------------
    # STAGE 1: INCREMENTAL DISCOVERY CYCLES & QUEUE ENQUEUE
    # -------------------------------------------------------------------------
    def run_discovery_cycle(
        self,
        db_session: Session,
        resume_profile_id: uuid.UUID,
        sources: list[str] | None = None,
        custom_feed: list[dict[str, Any]] | None = None,
        candidate_recruiter_pool: list[RawCandidateProfile | dict[str, Any]] | None = None,
    ) -> list[CycleExecutionRecord]:
        """Execute one discovery cycle across configured sources with rate limiting and retry policies.

        Guarantees:
        - Source failure does not stop other sources.
        - Exhausted source records failure in search_runs.
        - Discovered jobs buffer through the JobQueueManager before processing.
        """
        profile = db_session.query(ResumeProfile).filter(ResumeProfile.id == resume_profile_id).first()
        if not profile:
            raise ValueError(f"ResumeProfile with ID {resume_profile_id} not found")

        # Determine target queries from profile
        struct = profile.structured_data or {}
        profile_dict = {
            "target_roles": struct.get("likely_target_roles") or [profile.target_role or "Software Engineer"],
            "skills": (
                struct.get("programming_languages", [])
                + struct.get("frameworks", [])
                + struct.get("backend", [])
            ) or ["Python", "FastAPI"],
            "locations": profile.target_locations or ["Remote"],
        }
        queries = self.query_engine.generate_queries(profile_dict)

        registered_sources = self.collector.list_sources()
        target_sources = (
            [s for s in sources if s.lower() in registered_sources]
            if sources
            else registered_sources
        )

        cycle_records: list[CycleExecutionRecord] = []
        raw_jobs_by_source: dict[str, list[RawJobPosting | dict[str, Any]]] = {}

        # 1. Gather custom feed if provided
        if custom_feed:
            feed_source = custom_feed[0].get("source", "custom_feed") if custom_feed else "custom_feed"
            raw_jobs_by_source.setdefault(feed_source, []).extend(custom_feed)

        # 2. Incremental Discovery per source
        for src_name in target_sources:
            adapter = self.collector.get_adapter(src_name)
            if not adapter:
                continue

            cycle_rec = CycleExecutionRecord(
                source_name=src_name,
                started_at=datetime.now(UTC),
            )
            raw_jobs_by_source[src_name] = []

            # Check incremental watermark
            last_run = self._source_watermarks.get(src_name)

            try:
                # Execute with rate limit and exponential backoff retry
                postings: list[RawJobPosting] = []

                def _fetch_from_adapter(adp=adapter) -> list[RawJobPosting]:
                    batch: list[RawJobPosting] = []
                    for q in queries:
                        batch.extend(adp.search(q))
                    return batch

                result_postings, retries_attempted = self.rate_limiter.execute_with_retry(
                    source_name=src_name,
                    func=_fetch_from_adapter,
                    max_retries=self.config.max_retries_per_source,
                    backoff_base_seconds=self.config.retry_backoff_base_seconds,
                )

                # Incremental filter against watermark
                now_utc = datetime.now(UTC)
                if self.config.incremental and last_run:
                    result_postings = [
                        p for p in result_postings
                        if not p.posted_at or p.posted_at > last_run
                    ]

                raw_jobs_by_source[src_name].extend(result_postings)
                self._source_watermarks[src_name] = now_utc

                cycle_rec.jobs_discovered = len(result_postings)
                cycle_rec.retries_attempted = retries_attempted
                cycle_rec.status = "completed"
                cycle_rec.completed_at = datetime.now(UTC)

            except SourceExhaustedError as exc:
                # Source repeatedly failed: record failure and continue with other sources
                logger.error("Source '%s' repeatedly failed: %s", src_name, exc)
                cycle_rec.status = "failed"
                cycle_rec.completed_at = datetime.now(UTC)
                cycle_rec.retries_attempted = exc.attempts
                cycle_rec.errors.append(str(exc.last_error))

                # Record source failure in search_runs
                self._record_search_run(
                    db_session=db_session,
                    profile_id=profile.id,
                    run_type="discovery",
                    source=src_name,
                    started_at=cycle_rec.started_at,
                    completed_at=cycle_rec.completed_at,
                    status="failed",
                    discovered=0,
                    accepted=0,
                    rejected=0,
                    error=str(exc.last_error),
                    metadata={"retries": exc.attempts, "error_type": type(exc.last_error).__name__},
                )
            except Exception as exc:
                logger.error("Unexpected error querying source '%s': %s", src_name, exc)
                cycle_rec.status = "failed"
                cycle_rec.completed_at = datetime.now(UTC)
                cycle_rec.errors.append(str(exc))
                self._record_search_run(
                    db_session=db_session,
                    profile_id=profile.id,
                    run_type="discovery",
                    source=src_name,
                    started_at=cycle_rec.started_at,
                    completed_at=cycle_rec.completed_at,
                    status="failed",
                    discovered=0,
                    accepted=0,
                    rejected=0,
                    error=str(exc),
                    metadata={"error": str(exc)},
                )

            cycle_records.append(cycle_rec)

        # -------------------------------------------------------------------------
        # STAGE 2: QUEUE ENQUEUE
        # -------------------------------------------------------------------------
        for _src_name, postings in raw_jobs_by_source.items():
            if postings:
                self.queue.enqueue_batch(postings)

        # -------------------------------------------------------------------------
        # STAGE 3 & 4: QUEUE CONSUMPTION, PROCESSING, VERIFICATION & DB PERSISTENCE
        # -------------------------------------------------------------------------
        if not self.queue.is_empty():
            batch_items = self.queue.dequeue_batch(batch_size=1000)
            accepted_count, rejected_count = self._process_and_persist_batch(
                db_session=db_session,
                profile=profile,
                raw_items=batch_items,
                candidate_recruiter_pool=candidate_recruiter_pool,
            )

            # Update records for completed sources
            for rec in cycle_records:
                if rec.status == "completed":
                    rec.jobs_accepted = accepted_count
                    rec.jobs_rejected = rejected_count
                    self._record_search_run(
                        db_session=db_session,
                        profile_id=profile.id,
                        run_type="discovery",
                        source=rec.source_name,
                        started_at=rec.started_at,
                        completed_at=rec.completed_at,
                        status="completed",
                        discovered=rec.jobs_discovered,
                        accepted=accepted_count,
                        rejected=rejected_count,
                        error=None,
                        metadata={
                            "retries_attempted": rec.retries_attempted,
                            "incremental": self.config.incremental,
                        },
                    )

        db_session.commit()
        return cycle_records

    # -------------------------------------------------------------------------
    # STAGE 5: FINAL MORNING PASS (REVERIFY ALL PRIMARY CANDIDATES)
    # -------------------------------------------------------------------------
    def run_morning_final_verification(
        self,
        db_session: Session,
        resume_profile_id: uuid.UUID,
        sync_sheets: bool = True,
        candidate_recruiter_pool: list[RawCandidateProfile | dict[str, Any]] | None = None,
    ) -> MorningPassSummary:
        """Execute conservative final morning verification pass before morning report.

        Requirements:
        - Recheck all primary candidates currently in DB for active resume.
        - Conservative 15-point check: failures (404, closed, login wall) NEVER become VERIFIED.
        - Mark dead/expired jobs as closed or unavailable.
        - Still-verified jobs enter the primary morning view and update Google Sheets.
        - Record full audit trail in search_runs.
        """
        start_time = datetime.now(UTC)
        profile = db_session.query(ResumeProfile).filter(ResumeProfile.id == resume_profile_id).first()
        if not profile:
            raise ValueError(f"ResumeProfile with ID {resume_profile_id} not found")

        summary = MorningPassSummary(
            started_at=start_time,
        )

        logger.info("Executing Morning Final Verification Pass for profile '%s'...", profile.id)

        # 1. Fetch all candidate jobs currently matched and marked active
        matches = (
            db_session.query(JobMatch)
            .join(Job, JobMatch.job_id == Job.id)
            .filter(
                JobMatch.resume_profile_id == profile.id,
                Job.status == "active",
            )
            .all()
        )

        summary.candidates_rechecked = len(matches)
        logger.info("Found %d primary candidate jobs to recheck.", len(matches))

        verified_outputs: list[PipelineJobOutput] = []

        for match in matches:
            job: Job = match.job
            target_url = job.canonical_url or job.job_url

            # Conservative 15-point verification check
            ver_result = self.verification_service.verify_job(
                job={
                    "id": job.id,
                    "title": job.title,
                    "company": job.company_name,
                    "location": job.location,
                    "job_url": target_url,
                    "application_url": job.application_url,
                }
            )

            # Record VerificationEvent
            is_active = ver_result.status in (VerificationStatus.VERIFIED, VerificationStatus.ACTIVE)
            event = VerificationEvent(
                job_id=job.id,
                final_url=ver_result.final_url or target_url,
                http_status_code=ver_result.http_status or 200,
                is_active=is_active,
                verification_method="morning_final_recheck",
                status_reason=ver_result.failure_reason or ver_result.status.value,
            )
            db_session.add(event)

            if not is_active:
                # Job has expired, closed, or became invalid
                logger.info(
                    "Job '%s' @ '%s' failed morning recheck (%s). Updating status to closed.",
                    job.title,
                    job.company_name,
                    ver_result.status.value,
                )
                job.status = "closed"
                summary.closed_or_expired += 1
            else:
                job.last_verified = datetime.now(UTC)
                summary.still_verified += 1

                # Discovered recruiters for this verified job
                rec_res = self.recruiter_service.finder.discover_for_job(
                    job=job,
                    candidate_pool=candidate_recruiter_pool,
                    check_network=False,
                )

                # Persist verified recruiters
                for rec in rec_res.verified_recruiters:
                    person = self.recruiter_service._get_or_create_person(
                        db_session=db_session,
                        rec=rec,
                        company_id=job.company_id,
                    )
                    existing_link = (
                        db_session.query(JobPerson)
                        .filter(JobPerson.job_id == job.id, JobPerson.person_id == person.id)
                        .first()
                    )
                    if not existing_link:
                        link = JobPerson(
                            job_id=job.id,
                            person_id=person.id,
                            relationship_type=rec.role_tier.name.lower(),
                            confidence_score=rec.confidence,
                            relevance_reason=rec.relevance_reason,
                        )
                        db_session.add(link)

                # Build PipelineJobOutput
                out = PipelineJobOutput(
                    job_id=job.id,
                    title=job.title,
                    company=job.company_name,
                    location=job.location or "Remote",
                    work_mode=job.work_mode or "remote",
                    experience="Entry-Level / Fresher" if match.fit_level == "high" else "1+ Years",
                    job_url=job.job_url,
                    application_url=job.application_url,
                    source=job.source,
                    verification_status=ver_result.status,
                    match_level=MatchLevel.STRONG if match.fit_level == "high" else MatchLevel.RELEVANT,
                    why_it_matches=match.reasoning or "Confirmed relevant match during continuous cycle.",
                    required_skills=match.matched_skills + match.missing_requirements,
                    skills_you_have=match.matched_skills,
                    missing_improve=match.missing_requirements,
                    experience_assessment="Validated",
                    recruiter_1=rec_res.recruiter_1,
                    recruiter_2=rec_res.recruiter_2,
                    recruiter_3=rec_res.recruiter_3,
                    verified_recruiters=rec_res.verified_recruiters,
                    recruiter_status=rec_res.overall_status,
                )
                verified_outputs.append(out)

        summary.primary_morning_jobs = verified_outputs
        summary.completed_at = datetime.now(UTC)

        # -------------------------------------------------------------------------
        # STAGE 6: GOOGLE SHEETS SYNCHRONIZATION
        # -------------------------------------------------------------------------
        if sync_sheets and self.config.sync_to_sheets:
            resume = db_session.query(Resume).filter(Resume.id == profile.resume_id).first()
            if resume and resume.spreadsheet_id:
                try:
                    sheet_rows = [
                        job_out.to_sheet_row_dict(resume_label=resume.file_name or "Resume")
                        for job_out in verified_outputs
                    ]
                    for job_out, row_dict in zip(verified_outputs, sheet_rows, strict=False):
                        row_idx = self.sheets_service.append_job_row(
                            spreadsheet_id=resume.spreadsheet_id,
                            job_data=row_dict,
                        )
                        job_out.sheet_row_index = row_idx

                    summary.sheet_rows_updated = len(sheet_rows)
                    logger.info("Updated Google Sheet with %d morning verified jobs.", len(sheet_rows))
                except Exception as exc:
                    logger.warning("Google Sheet sync failed or skipped: %s", exc)
                    summary.errors.append(str(exc))
            else:
                # Assign simulated indices when no sheet ID is attached
                for i, job_out in enumerate(verified_outputs, start=2):
                    job_out.sheet_row_index = i
                summary.sheet_rows_updated = len(verified_outputs)

        # -------------------------------------------------------------------------
        # STAGE 7: SEARCH RUN AUDIT RECORD
        # -------------------------------------------------------------------------
        self._record_search_run(
            db_session=db_session,
            profile_id=profile.id,
            run_type="morning_report",
            source="all",
            started_at=summary.started_at,
            completed_at=summary.completed_at,
            status="completed",
            discovered=summary.candidates_rechecked,
            accepted=summary.still_verified,
            rejected=summary.closed_or_expired,
            error=summary.errors[0] if summary.errors else None,
            metadata={
                "candidates_rechecked": summary.candidates_rechecked,
                "still_verified": summary.still_verified,
                "closed_or_expired": summary.closed_or_expired,
                "sheet_rows_updated": summary.sheet_rows_updated,
            },
        )

        db_session.commit()
        return summary

    # -------------------------------------------------------------------------
    # INTERNAL PROCESSING & PERSISTENCE
    # -------------------------------------------------------------------------
    def _process_and_persist_batch(
        self,
        db_session: Session,
        profile: ResumeProfile,
        raw_items: list[RawJobPosting | dict[str, Any]],
        candidate_recruiter_pool: list[RawCandidateProfile | dict[str, Any]] | None = None,
    ) -> tuple[int, int]:
        """Normalize, deduplicate, evaluate match, verify, and persist queued items."""
        # 1. Normalize
        normalized_jobs: list[CanonicalJob] = []
        for raw in raw_items:
            try:
                norm = self.normalizer.normalize(raw)
                normalized_jobs.append(norm)
            except Exception as e:
                logger.debug("Failed to normalize job: %s", e)

        # 2. Deduplicate
        unique_jobs = self.deduplicator.deduplicate(normalized_jobs)

        # 3. Match against profile
        struct = profile.structured_data or {}
        profile_dict = {
            "target_roles": struct.get("likely_target_roles") or [profile.target_role or "Software Engineer"],
            "skills": (
                struct.get("programming_languages", [])
                + struct.get("frameworks", [])
                + struct.get("backend", [])
            ) or ["Python", "FastAPI"],
            "education": struct.get("education", "B.Tech in Computer Science"),
            "experience_years": struct.get("experience_years", 0),
            "locations": profile.target_locations or ["Remote"],
            "work_modes": profile.work_modes or ["remote"],
        }

        accepted_count = 0
        rejected_count = 0

        for cjob in unique_jobs:
            eval_res = self.matcher.evaluate(
                job=cjob,
                profile=profile_dict,
            )

            # Filter against configured criteria (e.g. at least RELEVANT)
            if eval_res.match_level.value < self.config.min_match_level.value:
                rejected_count += 1
                continue

            # Conservative initial verification
            ver_res = self.verification_service.verify_job(
                job=cjob,
            )

            if ver_res.status not in (VerificationStatus.VERIFIED, VerificationStatus.ACTIVE):
                rejected_count += 1
                continue

            # Persist qualified, verified job
            self._persist_job_and_match(
                db_session=db_session,
                profile=profile,
                cjob=cjob,
                eval_res=eval_res,
                ver_res=ver_res,
                candidate_recruiter_pool=candidate_recruiter_pool,
            )
            accepted_count += 1

        db_session.flush()
        return accepted_count, rejected_count

    def _persist_job_and_match(
        self,
        db_session: Session,
        profile: ResumeProfile,
        cjob: CanonicalJob,
        eval_res: Any,
        ver_res: Any,
        candidate_recruiter_pool: list[RawCandidateProfile | dict[str, Any]] | None = None,
    ) -> uuid.UUID:
        """Persist or update company, job, job_match, and verification_event."""
        norm_company = normalize_company(cjob.company)
        company = db_session.query(Company).filter(Company.normalized_name == norm_company).first()
        if not company:
            company = Company(name=cjob.company, normalized_name=norm_company)
            db_session.add(company)
            db_session.flush()

        dedup_hash = Job.calculate_dedup_hash(
            normalized_company=cjob.company,
            normalized_title=cjob.title,
            normalized_location=cjob.location,
            requisition_id=cjob.requisition_id,
        )

        job_entity = db_session.query(Job).filter(Job.dedup_hash == dedup_hash).first()
        if not job_entity:
            job_entity = Job(
                company_id=company.id,
                title=cjob.title,
                company_name=cjob.company,
                location=cjob.location,
                work_mode=cjob.work_mode.value,
                description=cjob.description,
                external_job_id=cjob.job_id,
                requisition_id=cjob.requisition_id,
                job_url=cjob.canonical_url or cjob.job_url,
                application_url=cjob.application_url,
                canonical_url=cjob.canonical_url or cjob.job_url,
                source=cjob.primary_source,
                normalized_company=cjob.company,
                normalized_title=cjob.title.lower().strip(),
                normalized_location=cjob.location.lower().strip(),
                dedup_hash=dedup_hash,
                status="active",
                last_verified=datetime.now(UTC),
            )
            db_session.add(job_entity)
            db_session.flush()

        # JobMatch
        existing_match = (
            db_session.query(JobMatch)
            .filter(JobMatch.job_id == job_entity.id, JobMatch.resume_profile_id == profile.id)
            .first()
        )
        if not existing_match:
            job_match = JobMatch(
                job_id=job_entity.id,
                resume_profile_id=profile.id,
                match_score=0.90 if eval_res.match_level == MatchLevel.STRONG else 0.70,
                fit_level="high" if eval_res.match_level == MatchLevel.STRONG else "medium",
                reasoning=eval_res.why_it_matches,
                matched_skills=eval_res.skills_you_have,
                missing_requirements=eval_res.missing_improve,
            )
            db_session.add(job_match)

        # VerificationEvent
        event = VerificationEvent(
            job_id=job_entity.id,
            final_url=ver_res.final_url or cjob.canonical_url or cjob.job_url,
            http_status_code=ver_res.http_status or 200,
            is_active=True,
            verification_method="continuous_cycle_check",
            status_reason=ver_res.failure_reason or ver_res.status.value,
        )
        db_session.add(event)

        return job_entity.id

    def _record_search_run(
        self,
        db_session: Session,
        profile_id: uuid.UUID,
        run_type: str,
        source: str,
        started_at: datetime,
        completed_at: datetime | None,
        status: str,
        discovered: int,
        accepted: int,
        rejected: int,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SearchRun:
        """Create and persist a search_run tracking record in PostgreSQL."""
        meta = metadata or {}
        meta["jobs_accepted"] = accepted
        meta["jobs_rejected"] = rejected
        if error:
            meta["errors"] = [error]

        run = SearchRun(
            resume_profile_id=profile_id,
            run_type=run_type,
            source=source,
            started_at=started_at,
            completed_at=completed_at or datetime.now(UTC),
            status=status,
            jobs_discovered=discovered,
            jobs_verified=accepted,
            jobs_matched=accepted,
            error_message=error,
            metadata_json=meta,
        )
        db_session.add(run)
        db_session.flush()
        return run

    # -------------------------------------------------------------------------
    # LIFECYCLE (DAEMON & BACKGROUND EXECUTION)
    # -------------------------------------------------------------------------
    def start_background_loop(self, db_session_factory: Any, resume_profile_id: uuid.UUID) -> None:
        """Launch background scheduled operation thread."""
        if self._running:
            return

        self._running = True

        def _loop():
            logger.info("Continuous scheduler daemon started.")
            while self._running:
                now_str = datetime.now(UTC).strftime("%H:%M")
                today_str = datetime.now(UTC).strftime("%Y-%m-%d")

                with db_session_factory() as session:
                    # 1. Run discovery cycle
                    try:
                        self.run_discovery_cycle(
                            db_session=session,
                            resume_profile_id=resume_profile_id,
                        )
                    except Exception as e:
                        logger.error("Continuous discovery cycle encountered error: %s", e)

                    # 2. Check if morning report is due
                    if now_str == self.config.morning_report_time and self._last_morning_pass_date != today_str:
                        try:
                            self.run_morning_final_verification(
                                db_session=session,
                                resume_profile_id=resume_profile_id,
                            )
                            self._last_morning_pass_date = today_str
                        except Exception as e:
                            logger.error("Morning final verification encountered error: %s", e)

                # Sleep before checking again (e.g. 60s)
                interval_secs = min(3600, int(self.config.discovery_interval_hours * 3600))
                time.sleep(interval_secs)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop background execution."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info("Continuous scheduler stopped.")

    @property
    def is_running(self) -> bool:
        """Return True if background loop is active."""
        return self._running
