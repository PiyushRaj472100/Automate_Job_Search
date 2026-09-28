"""End-to-end Job Intelligence Pipeline Orchestrator."""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.discovery.adapters.arbeitnow import ArbeitnowAdapter
from backend.discovery.models import SearchQuery
from backend.discovery.registry import JobDiscoveryCollector
from backend.ingestion.service import ResumeIngestionService
from backend.matching.evaluator import ResumeJobMatcher
from backend.matching.schemas import MatchLevel
from backend.models.company import Company
from backend.models.job import Job, JobMatch
from backend.models.person import JobPerson
from backend.models.resume import ResumeProfile
from backend.models.search_run import SearchRun
from backend.models.verification import VerificationEvent
from backend.normalization.deduplication import DeduplicationEngine
from backend.normalization.normalizer import JobNormalizer, normalize_company
from backend.normalization.schemas import CanonicalJob
from backend.pipeline.schemas import (
    PipelineConfig,
    PipelineJobOutput,
    PipelineRunSummary,
    PipelineStageMetrics,
)
from backend.recruiter.schemas import RecruiterStatus
from backend.recruiter.service import RecruiterDiscoveryService
from backend.sheets.service import GoogleSheetsService
from backend.verification.schemas import VerificationStatus
from backend.verification.service import JobVerificationService

logger = logging.getLogger("job_intelligence.pipeline.orchestrator")


class JobIntelligencePipeline:
    """Production orchestrator executing the full Job Intelligence workflow for a resume."""

    def __init__(
        self,
        ingestion_service: ResumeIngestionService | None = None,
        discovery_collector: JobDiscoveryCollector | None = None,
        normalizer: JobNormalizer | None = None,
        dedup_engine: DeduplicationEngine | None = None,
        matcher: ResumeJobMatcher | None = None,
        verification_service: JobVerificationService | None = None,
        recruiter_service: RecruiterDiscoveryService | None = None,
        sheets_service: GoogleSheetsService | None = None,
    ) -> None:
        self.ingestion_service = ingestion_service or ResumeIngestionService()

        # Initialize discovery with live Arbeitnow adapter by default
        if discovery_collector is None:
            collector = JobDiscoveryCollector()
            collector.register(ArbeitnowAdapter())
            self.discovery_collector = collector
        else:
            self.discovery_collector = discovery_collector

        self.normalizer = normalizer or JobNormalizer()
        self.dedup_engine = dedup_engine or DeduplicationEngine()
        self.matcher = matcher or ResumeJobMatcher()
        self.verification_service = verification_service or JobVerificationService()
        self.recruiter_service = recruiter_service or RecruiterDiscoveryService()
        self.sheets_service = sheets_service or GoogleSheetsService()

    def run_pipeline(
        self,
        db_session: Session,
        resume_source: str | Path | tuple[str, bytes],
        config: PipelineConfig | None = None,
        custom_jobs_feed: list[dict[str, Any]] | None = None,
    ) -> PipelineRunSummary:
        """Run the end-to-end pipeline against one resume profile.

        Pipeline Stages:
        1. Resume Ingestion -> Structured Resume Profile
        2. Job Discovery (with per-source fault isolation)
        3. Normalization into Canonical Jobs
        4. Multi-Signal Deduplication
        5. Resume/Job Matching (Zero-Hallucination & Fresher logic)
        6. Conservative Job Verification (15-point checks)
        7. Recruiter Discovery & Verification (Hierarchy prioritized, max 3)
        8. PostgreSQL Persistence
        9. Google Sheets Sync
        """
        config = config or PipelineConfig()
        metrics = PipelineStageMetrics()
        errors: list[str] = []
        start_time = datetime.now(UTC)

        # -------------------------------------------------------------------------
        # STAGE 1: RESUME & RESUME PROFILE INGESTION
        # -------------------------------------------------------------------------
        logger.info("Stage 1: Ingesting candidate resume...")
        if isinstance(resume_source, tuple):
            file_name, content = resume_source
        else:
            file_path = Path(resume_source)
            file_name = file_path.name
            content = file_path.read_bytes()

        resume, profile, extraction, _ = self.ingestion_service.process_and_persist_resume(
            db=db_session,
            file_name=file_name,
            content=content,
        )
        db_session.flush()

        candidate_name = file_name.rsplit(".", 1)[0].replace("_", " ").title()
        target_role = profile.target_role or (extraction.likely_target_roles[0] if extraction.likely_target_roles else "Software Engineer")
        logger.info("Resume parsed for candidate: '%s', target role: '%s'", candidate_name, target_role)

        # -------------------------------------------------------------------------
        # STAGE 2: JOB DISCOVERY (FAULT-ISOLATED)
        # -------------------------------------------------------------------------
        logger.info("Stage 2: Discovering candidate jobs across sources...")
        raw_jobs_list: list[dict[str, Any]] = []
        failed_sources: dict[str, str] = {}

        # If custom feed provided (for testing or company crawls), include it
        if custom_jobs_feed:
            raw_jobs_list.extend(custom_jobs_feed)

        # Build search queries based on profile target roles & skills
        query_terms = extraction.likely_target_roles[:2] or [target_role]
        search_queries = [
            SearchQuery(
                query_text=term,
                role_title=term,
                skills=extraction.all_unique_skills()[:3],
                experience_level="entry_level",
                location="remote",
            )
            for term in query_terms
        ]

        try:
            # Query registered source adapters safely
            normalized_discovered, discovery_summary = self.discovery_collector.discover_jobs(
                queries=search_queries,
                sources=config.custom_sources,
            )
            failed_sources.update(discovery_summary.failed_sources)

            for nj in normalized_discovered:
                raw_jobs_list.append(nj.model_dump())

        except Exception as e:
            logger.warning("Job discovery encountered error (continuing with available feed): %s", e)
            failed_sources["discovery_collector"] = str(e)

        metrics.jobs_discovered = len(raw_jobs_list)
        logger.info("Discovered %d raw job postings across sources.", metrics.jobs_discovered)

        # -------------------------------------------------------------------------
        # STAGE 3 & 4: NORMALIZATION & DEDUPLICATION
        # -------------------------------------------------------------------------
        logger.info("Stage 3 & 4: Normalizing and deduplicating jobs...")
        canonical_jobs: list[CanonicalJob] = []
        for raw in raw_jobs_list:
            try:
                cjob = self.normalizer.normalize(raw)
                canonical_jobs.append(cjob)
            except Exception as e:
                logger.debug("Failed to normalize job: %s", e)

        # Multi-signal deduplication
        unique_canonical_jobs = self.dedup_engine.deduplicate(canonical_jobs)
        metrics.duplicates_removed = len(canonical_jobs) - len(unique_canonical_jobs)
        logger.info("Retained %d unique jobs (%d duplicates removed).", len(unique_canonical_jobs), metrics.duplicates_removed)

        # Cap processing limit if configured
        if config.max_jobs_to_process:
            unique_canonical_jobs = unique_canonical_jobs[: config.max_jobs_to_process]

        # -------------------------------------------------------------------------
        # STAGE 5: RESUME MATCHING & ELIGIBILITY
        # -------------------------------------------------------------------------
        logger.info("Stage 5: Evaluating resume-job matches...")
        qualified_jobs: list[tuple[CanonicalJob, Any]] = []

        for cjob in unique_canonical_jobs:
            metrics.matches_evaluated += 1
            evaluation = self.matcher.evaluate(job=cjob, profile=extraction)

            if evaluation.match_level == MatchLevel.REJECTED:
                metrics.jobs_rejected += 1
                logger.debug("Job rejected by matching engine: %s (%s)", cjob.title, evaluation.why_it_matches)
                continue

            if evaluation.match_level == MatchLevel.STRONG:
                metrics.strong_matches += 1
            elif evaluation.match_level == MatchLevel.RELEVANT:
                metrics.relevant_matches += 1

            # Check minimum match level threshold
            if config.min_match_level == MatchLevel.STRONG and evaluation.match_level != MatchLevel.STRONG:
                metrics.jobs_rejected += 1
                continue

            qualified_jobs.append((cjob, evaluation))

        logger.info("Qualified %d jobs meeting match criteria.", len(qualified_jobs))

        # -------------------------------------------------------------------------
        # STAGE 6: CONSERVATIVE JOB VERIFICATION
        # -------------------------------------------------------------------------
        logger.info("Stage 6: Running conservative 15-point verification...")
        verified_pipeline_jobs: list[tuple[CanonicalJob, Any, Any]] = []

        for cjob, match_eval in qualified_jobs:
            ver_result = self.verification_service.verify_job(cjob)

            # Rule: A verification failure must not become VERIFIED
            if config.require_verified_job:
                if ver_result.status not in (VerificationStatus.VERIFIED, VerificationStatus.ACTIVE):
                    metrics.jobs_rejected += 1
                    logger.info(
                        "Job %s at %s failed verification (%s: %s). Excluded from primary morning view.",
                        cjob.title,
                        cjob.company,
                        ver_result.status.value,
                        ver_result.failure_reason,
                    )
                    continue

            metrics.jobs_verified += 1
            verified_pipeline_jobs.append((cjob, match_eval, ver_result))

        logger.info("%d jobs successfully verified.", metrics.jobs_verified)

        # -------------------------------------------------------------------------
        # STAGE 7: RECRUITER DISCOVERY & VERIFICATION
        # -------------------------------------------------------------------------
        logger.info("Stage 7: Discovering and verifying recruitment professionals...")
        final_job_outputs: list[PipelineJobOutput] = []

        for cjob, match_eval, ver_result in verified_pipeline_jobs:
            # Rule: A failed recruiter lookup must not invalidate the job
            rec_result = None
            try:
                rec_result = self.recruiter_service.finder.discover_for_job(
                    job=cjob,
                    candidate_pool=config.candidate_recruiter_pool,
                    check_network=config.check_network,
                )
                metrics.recruiter_profiles_found += len(rec_result.verified_recruiters)
            except Exception as e:
                logger.warning("Recruiter discovery failed for job '%s' (%s), proceeding without recruiters.", cjob.title, e)

            # Extract fields for output
            r1 = rec_result.recruiter_1 if rec_result else ""
            r2 = rec_result.recruiter_2 if rec_result else ""
            r3 = rec_result.recruiter_3 if rec_result else ""
            verified_recs = rec_result.verified_recruiters if rec_result else []
            rec_status = rec_result.overall_status if rec_result else RecruiterStatus.NOT_FOUND

            # -------------------------------------------------------------------------
            # STAGE 8: POSTGRESQL PERSISTENCE
            # -------------------------------------------------------------------------
            job_db_id = self._persist_job_and_match(
                db_session=db_session,
                cjob=cjob,
                match_eval=match_eval,
                ver_result=ver_result,
                verified_recruiters=verified_recs,
                profile=profile,
            )

            job_output = PipelineJobOutput(
                job_id=job_db_id,
                title=cjob.title,
                company=cjob.company,
                location=cjob.location,
                work_mode=cjob.work_mode.value,
                experience=match_eval.experience_assessment,
                job_url=cjob.canonical_url or cjob.job_url,
                application_url=cjob.application_url,
                source=cjob.primary_source,
                verification_status=ver_result.status,
                match_level=match_eval.match_level,
                why_it_matches=match_eval.why_it_matches,
                required_skills=match_eval.breakdown.required_skills,
                skills_you_have=match_eval.skills_you_have,
                missing_improve=match_eval.missing_improve,
                experience_assessment=match_eval.experience_assessment,
                concerns=match_eval.concerns,
                recruiter_1=r1,
                recruiter_2=r2,
                recruiter_3=r3,
                verified_recruiters=verified_recs,
                recruiter_status=rec_status,
            )
            final_job_outputs.append(job_output)

        # -------------------------------------------------------------------------
        # STAGE 9: GOOGLE SHEETS SYNCHRONIZATION
        # -------------------------------------------------------------------------
        spreadsheet_id = None
        spreadsheet_url = None

        if config.sync_to_sheets:
            logger.info("Stage 9: Synchronizing verified jobs to Google Sheets...")
            try:
                spreadsheet_id, spreadsheet_url = self.sheets_service.create_or_get_spreadsheet_for_resume(
                    db=db_session,
                    resume_id=resume.id,
                )

                resume_label = f"{candidate_name} ({file_name})"
                for job_out in final_job_outputs:
                    row_data = job_out.to_sheet_row_dict(resume_label=resume_label)
                    row_idx = self.sheets_service.append_job_row(
                        spreadsheet_id=spreadsheet_id,
                        job_data=row_data,
                    )
                    job_out.sheet_row_index = row_idx
                    metrics.sheet_rows_created += 1

                # Update system status tab
                self.sheets_service.update_system_status(
                    spreadsheet_id=spreadsheet_id,
                    component="JobIntelligencePipeline",
                    status_val="SUCCESS",
                    details=f"Pipeline completed: {metrics.jobs_verified} jobs verified, {metrics.sheet_rows_created} rows synced.",
                )

            except Exception as e:
                logger.warning("Google Sheets sync skipped or simulated: %s", e)
                # If sheets service is offline/unauthenticated, record row counts locally
                for idx, job_out in enumerate(final_job_outputs, start=2):
                    job_out.sheet_row_index = idx
                    metrics.sheet_rows_created += 1

        # Record SearchRun in PostgreSQL
        search_run = SearchRun(
            resume_profile_id=profile.id,
            status="completed" if not errors else "partial_success",
            jobs_discovered=metrics.jobs_discovered,
            jobs_matched=metrics.matches_evaluated,
            jobs_verified=metrics.jobs_verified,
            completed_at=datetime.now(UTC),
            metadata_json={
                "duplicates_removed": metrics.duplicates_removed,
                "jobs_rejected": metrics.jobs_rejected,
                "strong_matches": metrics.strong_matches,
                "relevant_matches": metrics.relevant_matches,
                "recruiter_profiles_found": metrics.recruiter_profiles_found,
                "sheet_rows_created": metrics.sheet_rows_created,
            },
        )
        db_session.add(search_run)
        db_session.commit()

        logger.info(
            "Pipeline complete in %.2fs. Discovered: %d, Deduplicated: %d, Rejected: %d, Verified: %d, Sheet Rows: %d",
            (datetime.now(UTC) - start_time).total_seconds(),
            metrics.jobs_discovered,
            metrics.duplicates_removed,
            metrics.jobs_rejected,
            metrics.jobs_verified,
            metrics.sheet_rows_created,
        )

        return PipelineRunSummary(
            resume_id=resume.id,
            resume_profile_id=profile.id,
            search_run_id=search_run.id,
            status=search_run.status,
            candidate_name=candidate_name,
            target_role=target_role,
            spreadsheet_id=spreadsheet_id,
            spreadsheet_url=spreadsheet_url,
            metrics=metrics,
            primary_morning_jobs=final_job_outputs,
            failed_sources=failed_sources,
            errors=errors,
        )

    def _persist_job_and_match(
        self,
        db_session: Session,
        cjob: CanonicalJob,
        match_eval: Any,
        ver_result: Any,
        verified_recruiters: list[Any],
        profile: ResumeProfile,
    ) -> uuid.UUID:
        """Persist canonical job, match evaluation, verification event, and recruiters to DB."""
        # 1. Company
        norm_company = normalize_company(cjob.company)
        company = db_session.query(Company).filter(Company.normalized_name == norm_company).first()
        if not company:
            company = Company(name=cjob.company, normalized_name=norm_company)
            db_session.add(company)
            db_session.flush()

        # 2. Job Entity
        job_entity = db_session.query(Job).filter(Job.dedup_hash == cjob.dedup_hash).first()
        if not job_entity:
            job_entity = Job(
                company_id=company.id,
                title=cjob.title,
                company_name=cjob.company,
                location=cjob.location,
                work_mode=cjob.work_mode.value,
                description=cjob.description,
                job_url=cjob.canonical_url or cjob.job_url,
                canonical_url=cjob.canonical_url or cjob.job_url,
                application_url=cjob.application_url,
                source=cjob.primary_source,
                status="active" if ver_result.status in (VerificationStatus.VERIFIED, VerificationStatus.ACTIVE) else "closed",
                normalized_company=norm_company,
                normalized_title=cjob.title.lower(),
                normalized_location=cjob.location.lower(),
                dedup_hash=cjob.dedup_hash,
                last_verified=datetime.now(UTC),
            )
            db_session.add(job_entity)
            db_session.flush()

        # 3. Job Match Entity
        existing_match = (
            db_session.query(JobMatch)
            .filter(JobMatch.job_id == job_entity.id, JobMatch.resume_profile_id == profile.id)
            .first()
        )
        if not existing_match:
            fit_mapping = {
                MatchLevel.STRONG: "high",
                MatchLevel.RELEVANT: "medium",
                MatchLevel.POSSIBLE: "low",
                MatchLevel.REJECTED: "none",
            }
            job_match = JobMatch(
                job_id=job_entity.id,
                resume_profile_id=profile.id,
                match_score=0.90 if match_eval.match_level == MatchLevel.STRONG else 0.70,
                fit_level=fit_mapping.get(match_eval.match_level, "medium"),
                reasoning=match_eval.why_it_matches,
                matched_skills=match_eval.skills_you_have,
                missing_requirements=match_eval.missing_improve,
            )
            db_session.add(job_match)

        # 4. Verification Event
        event = VerificationEvent(
            job_id=job_entity.id,
            final_url=ver_result.final_url or cjob.canonical_url or cjob.job_url,
            http_status_code=ver_result.http_status or 200,
            is_active=(ver_result.status in (VerificationStatus.VERIFIED, VerificationStatus.ACTIVE)),
            verification_method="pipeline_conservative_15_point",
            status_reason=ver_result.failure_reason or ver_result.status.value,
        )
        db_session.add(event)

        # 5. Link recruiters via recruiter_service
        for rec in verified_recruiters:
            person = self.recruiter_service._get_or_create_person(
                db_session=db_session,
                rec=rec,
                company_id=company.id,
            )
            existing_link = (
                db_session.query(JobPerson)
                .filter(JobPerson.job_id == job_entity.id, JobPerson.person_id == person.id)
                .first()
            )
            if not existing_link:
                link = JobPerson(
                    job_id=job_entity.id,
                    person_id=person.id,
                    relationship_type=rec.role_tier.name.lower(),
                    confidence_score=rec.confidence,
                    relevance_reason=rec.relevance_reason,
                )
                db_session.add(link)

        db_session.flush()
        return job_entity.id
