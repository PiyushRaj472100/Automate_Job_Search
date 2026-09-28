"""Matching service orchestrating profile evaluations and PostgreSQL persistence."""

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from backend.matching.evaluator import ResumeJobMatcher
from backend.matching.schemas import JobMatchEvaluation, MatchLevel
from backend.models.job import Job, JobMatch
from backend.models.resume import ResumeProfile
from backend.normalization.schemas import CanonicalJob

logger = logging.getLogger("job_intelligence.matching.service")


class MatchingService:
    """Evaluates candidate jobs against resume profiles and manages PostgreSQL match records."""

    def __init__(self, matcher: ResumeJobMatcher | None = None) -> None:
        self.matcher = matcher or ResumeJobMatcher()

    def evaluate_job(
        self,
        job: CanonicalJob | Job | dict[str, Any],
        profile: ResumeProfile | dict[str, Any],
    ) -> JobMatchEvaluation:
        """Run qualitative evaluation comparing a job to a candidate's profile."""
        return self.matcher.evaluate(job=job, profile=profile)

    def evaluate_and_record_batch(
        self,
        db_session: Session,
        jobs: Sequence[Job | CanonicalJob],
        profile: ResumeProfile,
    ) -> list[JobMatchEvaluation]:
        """Evaluate a batch of candidate jobs against a profile and record JobMatch entities in PostgreSQL."""
        evaluations: list[JobMatchEvaluation] = []

        for job in jobs:
            eval_result = self.evaluate_job(job=job, profile=profile)
            evaluations.append(eval_result)

            # Persist to database if job has database ID
            job_db_id = getattr(job, "id", None)
            if job_db_id and isinstance(job_db_id, uuid.UUID):
                # Map qualitative level to fit_level string for DB schema compatibility
                fit_level_map = {
                    MatchLevel.STRONG: "high",
                    MatchLevel.RELEVANT: "medium",
                    MatchLevel.POSSIBLE: "low",
                    MatchLevel.REJECTED: "rejected",
                }
                fit_str = fit_level_map.get(eval_result.match_level, "low")

                # Numerical score as secondary metric (never unexplained in user facing text)
                score_map = {
                    MatchLevel.STRONG: 0.90,
                    MatchLevel.RELEVANT: 0.70,
                    MatchLevel.POSSIBLE: 0.45,
                    MatchLevel.REJECTED: 0.10,
                }
                numeric_score = score_map.get(eval_result.match_level, 0.40)

                # Check if existing match exists
                existing = (
                    db_session.query(JobMatch)
                    .filter(
                        JobMatch.resume_profile_id == profile.id,
                        JobMatch.job_id == job_db_id,
                    )
                    .first()
                )

                if existing:
                    existing.match_score = numeric_score
                    existing.fit_level = fit_str
                    existing.matched_skills = eval_result.skills_you_have
                    existing.missing_requirements = eval_result.missing_improve
                    existing.reasoning = eval_result.why_it_matches
                else:
                    match_record = JobMatch(
                        resume_profile_id=profile.id,
                        job_id=job_db_id,
                        match_score=numeric_score,
                        fit_level=fit_str,
                        matched_skills=eval_result.skills_you_have,
                        missing_requirements=eval_result.missing_improve,
                        reasoning=eval_result.why_it_matches,
                    )
                    db_session.add(match_record)

        db_session.commit()
        logger.info(
            "Batch match evaluation complete for profile '%s': %d evaluated",
            profile.profile_name if hasattr(profile, "profile_name") else "profile",
            len(evaluations),
        )
        return evaluations
