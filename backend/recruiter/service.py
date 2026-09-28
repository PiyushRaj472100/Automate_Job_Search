"""Recruiter discovery service orchestrating profile verification and PostgreSQL persistence."""

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.models.job import Job
from backend.models.person import JobPerson, Person
from backend.normalization.normalizer import normalize_company
from backend.recruiter.finder import RecruiterFinder
from backend.recruiter.schemas import (
    JobRecruiterDiscoveryResult,
    ProfileVerificationResult,
    RawCandidateProfile,
    RecruiterStatus,
)
from backend.recruiter.verifier import ProfileVerifier

logger = logging.getLogger("job_intelligence.recruiter.service")


class RecruiterDiscoveryService:
    """End-to-end service for discovering, verifying, and persisting recruiters."""

    def __init__(
        self,
        verifier: ProfileVerifier | None = None,
        finder: RecruiterFinder | None = None,
    ):
        self.verifier = verifier or ProfileVerifier()
        self.finder = finder or RecruiterFinder(verifier=self.verifier)

    def discover_and_record_for_job(
        self,
        db_session: Session,
        job: Job,
        candidate_pool: list[RawCandidateProfile | dict[str, Any]] | None = None,
        check_network: bool = False,
    ) -> JobRecruiterDiscoveryResult:
        """Discover recruiters for a single job and persist verified relationships in PostgreSQL."""
        discovery_result = self.finder.discover_for_job(
            job=job,
            candidate_pool=candidate_pool,
            check_network=check_network,
        )

        # Ensure company exists in DB
        company_id = job.company_id
        if not company_id and job.company_name:
            norm_name = normalize_company(job.company_name)
            company = db_session.query(Company).filter(Company.normalized_name == norm_name).first()
            if not company:
                company = Company(name=job.company_name, normalized_name=norm_name)
                db_session.add(company)
                db_session.flush()
            company_id = company.id
            job.company_id = company_id

        # Persist VERIFIED and PLAUSIBLE candidates into Person and JobPerson
        for rec in discovery_result.verified_recruiters + discovery_result.plausible_recruiters:
            person = self._get_or_create_person(
                db_session=db_session,
                rec=rec,
                company_id=company_id,
            )

            # Link via JobPerson if not already linked
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

        db_session.commit()
        return discovery_result

    def discover_batch_for_jobs(
        self,
        db_session: Session,
        jobs: Sequence[Job],
        candidate_pools_by_company: dict[str, list[RawCandidateProfile | dict[str, Any]]] | None = None,
        check_network: bool = False,
    ) -> list[JobRecruiterDiscoveryResult]:
        """Run recruiter discovery across multiple jobs."""
        candidate_pools_by_company = candidate_pools_by_company or {}
        results: list[JobRecruiterDiscoveryResult] = []

        for job in jobs:
            pool = candidate_pools_by_company.get(
                normalize_company(job.company_name),
                candidate_pools_by_company.get(job.company_name, []),
            )
            res = self.discover_and_record_for_job(
                db_session=db_session,
                job=job,
                candidate_pool=pool,
                check_network=check_network,
            )
            results.append(res)

        return results

    def _get_or_create_person(
        self,
        db_session: Session,
        rec: ProfileVerificationResult,
        company_id: uuid.UUID | None,
    ) -> Person:
        """Find existing Person by LinkedIn URL or name/company, or create new."""
        query = db_session.query(Person)
        if rec.linkedin_url:
            person = query.filter(Person.linkedin_url == rec.linkedin_url).first()
            if person:
                # Update verification status
                person.is_verified = (rec.status == RecruiterStatus.VERIFIED)
                person.verification_details = rec.verification_details
                return person

        # Fallback to name and company_id
        if company_id:
            person = query.filter(
                Person.full_name == rec.name,
                Person.company_id == company_id,
            ).first()
            if person:
                return person

        # Create new Person
        person = Person(
            full_name=rec.name,
            title=rec.title,
            company_id=company_id,
            linkedin_url=rec.linkedin_url,
            email=rec.email,
            is_verified=(rec.status == RecruiterStatus.VERIFIED),
            verification_source=rec.verification_source,
            verification_details=rec.verification_details,
        )
        db_session.add(person)
        db_session.flush()
        return person
