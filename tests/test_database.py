"""Comprehensive database tests for entities, relationships, constraints, and deduplication."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.application import Application
from backend.models.company import Company
from backend.models.job import Job, JobMatch, JobSource
from backend.models.person import JobPerson, Person
from backend.models.resume import Resume, ResumeProfile, ResumeSkill, Skill
from backend.models.search_run import SearchRun
from backend.models.verification import VerificationEvent


def test_create_company(db_session: Session):
    """Verify company creation, fields, and UUID assignment."""
    company = Company(
        name="Acme Corporation",
        normalized_name="acme corporation",
        domain="acme.com",
        career_page_url="https://acme.com/careers",
    )
    db_session.add(company)
    db_session.flush()

    assert isinstance(company.id, uuid.UUID)
    assert company.name == "Acme Corporation"
    assert company.normalized_name == "acme corporation"
    assert company.created_at is not None
    assert company.updated_at is not None


def test_create_resume_and_profile(db_session: Session):
    """Verify creating a resume, independent resume profiles, and linking skills."""
    resume = Resume(
        file_name="jane_doe_software_engineer.pdf",
        file_path="/resumes/jane_doe_software_engineer.pdf",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        raw_text="Jane Doe. Python, FastAPI, PostgreSQL developer with 1 year experience.",
    )
    db_session.add(resume)
    db_session.flush()

    assert isinstance(resume.id, uuid.UUID)

    # Create independent profile for this resume
    profile = ResumeProfile(
        resume_id=resume.id,
        profile_name="Backend Entry-Level (0-2 YOE)",
        target_role="Junior Backend Developer",
        target_locations=["Bengaluru", "Remote"],
        work_modes=["remote", "hybrid"],
        min_salary=800000,
        max_experience_years=2,
        sheet_tab_name="Jane_Backend_0_2",
        is_active=True,
    )
    db_session.add(profile)
    db_session.flush()

    # Create skill and associate with profile
    skill = Skill(name="fastapi", category="framework")
    db_session.add(skill)
    db_session.flush()

    resume_skill = ResumeSkill(
        resume_profile_id=profile.id,
        skill_id=skill.id,
        years_of_experience=1.5,
        proficiency_level="intermediate",
    )
    db_session.add(resume_skill)
    db_session.flush()

    # Verify query and relationship
    fetched_profile = db_session.get(ResumeProfile, profile.id)
    assert fetched_profile is not None
    assert fetched_profile.resume.file_name == "jane_doe_software_engineer.pdf"
    assert len(fetched_profile.skills) == 1
    assert fetched_profile.skills[0].skill.name == "fastapi"


def test_create_job_with_all_required_contract_fields(db_session: Session):
    """Verify that a job entity stores all mandatory contract fields accurately."""
    company = Company(
        name="TechNova Systems",
        normalized_name="technova systems",
        domain="technova.io",
    )
    source = JobSource(
        name="greenhouse_technova",
        source_type="ats",
        base_url="https://boards.greenhouse.io/technova",
    )
    db_session.add_all([company, source])
    db_session.flush()

    now = datetime.now(UTC)
    dedup_hash = Job.calculate_dedup_hash(
        normalized_company="technova systems",
        normalized_title="associate software engineer",
        normalized_location="remote - india",
        requisition_id="REQ-2026-0901",
    )

    job = Job(
        source_id=source.id,
        company_id=company.id,
        title="Associate Software Engineer",
        company_name="TechNova Systems",
        location="Remote - India",
        work_mode="remote",
        description="We are seeking an entry-level software engineer with Python knowledge.",
        external_job_id="GH-987654",
        requisition_id="REQ-2026-0901",
        posting_date=now - timedelta(days=2),
        updated_date=now - timedelta(days=1),
        job_url="https://boards.greenhouse.io/technova/jobs/987654",
        application_url="https://boards.greenhouse.io/technova/jobs/987654#apply",
        canonical_url="https://boards.greenhouse.io/technova/jobs/987654",
        source="greenhouse",
        first_seen=now,
        last_seen=now,
        last_verified=now,
        status="active",
        normalized_company="technova systems",
        normalized_title="associate software engineer",
        normalized_location="remote - india",
        dedup_hash=dedup_hash,
    )
    db_session.add(job)
    db_session.flush()

    assert isinstance(job.id, uuid.UUID)
    assert job.title == "Associate Software Engineer"
    assert job.company_name == "TechNova Systems"
    assert job.location == "Remote - India"
    assert job.work_mode == "remote"
    assert job.external_job_id == "GH-987654"
    assert job.requisition_id == "REQ-2026-0901"
    assert job.job_url == "https://boards.greenhouse.io/technova/jobs/987654"
    assert job.status == "active"
    assert job.company.name == "TechNova Systems"
    assert job.job_source.name == "greenhouse_technova"


def test_link_job_to_resume_match(db_session: Session):
    """Verify matching a job against a specific resume profile with score and details."""
    resume = Resume(file_name="resume.pdf")
    company = Company(name="CloudCorp", normalized_name="cloudcorp")
    db_session.add_all([resume, company])
    db_session.flush()

    profile = ResumeProfile(
        resume_id=resume.id,
        profile_name="Cloud Engineer",
        target_role="Cloud Engineer",
    )
    job = Job(
        company_id=company.id,
        title="Junior Cloud Engineer",
        company_name="CloudCorp",
        location="Bengaluru",
        work_mode="hybrid",
        description="Entry-level cloud engineer role.",
        job_url="https://cloudcorp.com/jobs/1",
        source="career_site",
        normalized_company="cloudcorp",
        normalized_title="junior cloud engineer",
        normalized_location="bengaluru",
        dedup_hash=Job.calculate_dedup_hash("cloudcorp", "junior cloud engineer", "bengaluru"),
    )
    db_session.add_all([profile, job])
    db_session.flush()

    match = JobMatch(
        resume_profile_id=profile.id,
        job_id=job.id,
        match_score=87.5,
        fit_level="high",
        matched_skills=["Python", "Linux", "Docker"],
        missing_requirements=["Kubernetes"],
        reasoning="Strong foundation in core backend, lacks production Kubernetes experience.",
    )
    db_session.add(match)
    db_session.flush()

    assert match.match_score == 87.5
    assert match.fit_level == "high"
    assert "Kubernetes" in match.missing_requirements
    assert match.resume_profile.profile_name == "Cloud Engineer"
    assert match.job.title == "Junior Cloud Engineer"


def test_historical_verification_events_preservation(db_session: Session):
    """Verify that multiple verification events are preserved historically and not overwritten."""
    company = Company(name="VerifCorp", normalized_name="verifcorp")
    db_session.add(company)
    db_session.flush()

    job = Job(
        company_id=company.id,
        title="Backend Developer",
        company_name="VerifCorp",
        location="Remote",
        work_mode="remote",
        description="Role description",
        job_url="https://verifcorp.com/jobs/101",
        source="career_site",
        normalized_company="verifcorp",
        normalized_title="backend developer",
        normalized_location="remote",
        dedup_hash=Job.calculate_dedup_hash("verifcorp", "backend developer", "remote"),
    )
    db_session.add(job)
    db_session.flush()

    # Day 1 Verification: Active
    event_day1 = VerificationEvent(
        job_id=job.id,
        verified_at=datetime.now(UTC) - timedelta(days=2),
        http_status_code=200,
        final_url="https://verifcorp.com/jobs/101",
        is_active=True,
        verification_method="http_get",
        status_reason="200 OK - Job active",
    )

    # Day 2 Verification: Expired/Closed
    event_day2 = VerificationEvent(
        job_id=job.id,
        verified_at=datetime.now(UTC) - timedelta(days=1),
        http_status_code=404,
        final_url="https://verifcorp.com/jobs/101",
        is_active=False,
        verification_method="http_get",
        status_reason="404 Not Found - Listing expired",
    )

    db_session.add_all([event_day1, event_day2])
    db_session.flush()

    # Ensure all historical events exist and were not overwritten
    events = (
        db_session.execute(
            select(VerificationEvent)
            .where(VerificationEvent.job_id == job.id)
            .order_by(VerificationEvent.verified_at.asc())
        )
        .scalars()
        .all()
    )

    assert len(events) == 2
    assert events[0].is_active is True
    assert events[0].http_status_code == 200
    assert events[1].is_active is False
    assert events[1].http_status_code == 404


def test_create_application_linked_to_resume_and_job(db_session: Session):
    """Verify application record correctly links to both resume and job, with uniqueness."""
    resume = Resume(file_name="alex_dev.pdf")
    company = Company(name="Apex Systems", normalized_name="apex systems")
    db_session.add_all([resume, company])
    db_session.flush()

    job = Job(
        company_id=company.id,
        title="Python Engineer",
        company_name="Apex Systems",
        location="Hyderabad",
        work_mode="on_site",
        description="Python opening",
        job_url="https://apex.com/jobs/55",
        source="career_site",
        normalized_company="apex systems",
        normalized_title="python engineer",
        normalized_location="hyderabad",
        dedup_hash=Job.calculate_dedup_hash("apex systems", "python engineer", "hyderabad"),
    )
    db_session.add(job)
    db_session.flush()

    app = Application(
        resume_id=resume.id,
        job_id=job.id,
        status="to_apply",
        notes="Tailored cover letter highlighting FastAPI projects.",
    )
    db_session.add(app)
    db_session.flush()

    assert app.status == "to_apply"
    assert app.resume.file_name == "alex_dev.pdf"
    assert app.job.title == "Python Engineer"

    # Verify duplicate application for the same resume + job is rejected by constraint
    duplicate_app = Application(
        resume_id=resume.id,
        job_id=job.id,
        status="applied",
    )
    db_session.add(duplicate_app)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_recruiter_discovery_and_job_people(db_session: Session):
    """Verify recruiter profiles and linking to specific job openings."""
    company = Company(name="InnoTech", normalized_name="innotech")
    db_session.add(company)
    db_session.flush()

    person = Person(
        company_id=company.id,
        full_name="Sarah Connor",
        title="Lead Technical Recruiter",
        linkedin_url="https://linkedin.com/in/sarah-connor-talent",
        is_verified=True,
        verification_source="public_company_career_page",
    )
    db_session.add(person)
    db_session.flush()

    job = Job(
        company_id=company.id,
        title="Frontend Developer",
        company_name="InnoTech",
        location="Remote",
        work_mode="remote",
        description="React opening",
        job_url="https://innotech.com/jobs/1",
        source="career_site",
        normalized_company="innotech",
        normalized_title="frontend developer",
        normalized_location="remote",
        dedup_hash=Job.calculate_dedup_hash("innotech", "frontend developer", "remote"),
    )
    db_session.add(job)
    db_session.flush()

    link = JobPerson(
        job_id=job.id,
        person_id=person.id,
        relationship_type="recruiter",
        confidence_score=0.95,
        relevance_reason="Listed as primary hiring contact on public job posting.",
    )
    db_session.add(link)
    db_session.flush()

    assert link.confidence_score == 0.95
    assert link.person.full_name == "Sarah Connor"
    assert link.job.title == "Frontend Developer"


def test_deduplication_strategies(db_session: Session):
    """Verify multi-attribute duplicate detection using hash, canonical URL, and requisitions."""
    company = Company(name="DataCorp", normalized_name="datacorp")
    db_session.add(company)
    db_session.flush()

    hash_1 = Job.calculate_dedup_hash("datacorp", "data analyst", "remote", "REQ-100")
    job1 = Job(
        company_id=company.id,
        title="Data Analyst",
        company_name="DataCorp",
        location="Remote",
        work_mode="remote",
        description="Analytics role",
        requisition_id="REQ-100",
        external_job_id="DC-55",
        job_url="https://datacorp.com/jobs/55",
        canonical_url="https://datacorp.com/jobs/55",
        source="lever",
        normalized_company="datacorp",
        normalized_title="data analyst",
        normalized_location="remote",
        dedup_hash=hash_1,
    )
    db_session.add(job1)
    db_session.flush()

    # 1. Detection via dedup_hash
    match_by_hash = db_session.execute(
        select(Job).where(Job.dedup_hash == hash_1)
    ).scalar_one_or_none()
    assert match_by_hash is not None
    assert match_by_hash.id == job1.id

    # 2. Detection via canonical URL
    match_by_url = db_session.execute(
        select(Job).where(Job.canonical_url == "https://datacorp.com/jobs/55")
    ).scalar_one_or_none()
    assert match_by_url is not None
    assert match_by_url.id == job1.id

    # 3. Detection via requisition_id + company_id
    match_by_req = db_session.execute(
        select(Job).where(
            Job.company_id == company.id,
            Job.requisition_id == "REQ-100",
        )
    ).scalar_one_or_none()
    assert match_by_req is not None
    assert match_by_req.id == job1.id


def test_foreign_key_cascade_deletes(db_session: Session):
    """Verify that deleting a parent Job cascades to matches and verification events."""
    company = Company(name="CascadeCorp", normalized_name="cascadecorp")
    resume = Resume(file_name="resume.pdf")
    db_session.add_all([company, resume])
    db_session.flush()

    profile = ResumeProfile(resume_id=resume.id, profile_name="Dev", target_role="Dev")
    job = Job(
        company_id=company.id,
        title="Dev",
        company_name="CascadeCorp",
        location="Remote",
        work_mode="remote",
        description="Desc",
        job_url="https://cascade.com/1",
        source="site",
        normalized_company="cascadecorp",
        normalized_title="dev",
        normalized_location="remote",
        dedup_hash=Job.calculate_dedup_hash("cascadecorp", "dev", "remote"),
    )
    db_session.add_all([profile, job])
    db_session.flush()

    match = JobMatch(
        resume_profile_id=profile.id,
        job_id=job.id,
        match_score=90.0,
        fit_level="high",
    )
    event = VerificationEvent(
        job_id=job.id,
        http_status_code=200,
        is_active=True,
        verification_method="http_head",
    )
    db_session.add_all([match, event])
    db_session.flush()

    match_id = match.id
    event_id = event.id

    # Delete the job
    db_session.delete(job)
    db_session.flush()


    # Verify children are deleted by cascade
    assert db_session.get(JobMatch, match_id) is None
    assert db_session.get(VerificationEvent, event_id) is None


def test_search_run_creation_and_metrics(db_session: Session):
    """Verify search run audit records and execution metrics."""
    resume = Resume(file_name="resume_search.pdf")
    db_session.add(resume)
    db_session.flush()

    profile = ResumeProfile(
        resume_id=resume.id,
        profile_name="DevOps 0-2",
        target_role="DevOps Engineer",
    )
    db_session.add(profile)
    db_session.flush()

    run = SearchRun(
        resume_profile_id=profile.id,
        run_type="discovery",
        status="completed",
        jobs_discovered=12,
        jobs_verified=10,
        jobs_matched=4,
        metadata_json={"source": "greenhouse", "duration_sec": 42},
    )
    db_session.add(run)
    db_session.flush()

    assert isinstance(run.id, uuid.UUID)
    assert run.jobs_discovered == 12
    assert run.jobs_matched == 4
    assert run.resume_profile.profile_name == "DevOps 0-2"
    assert run.metadata_json["source"] == "greenhouse"

