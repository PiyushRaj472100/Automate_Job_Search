"""Comprehensive unit and integration tests for the Resume/Job Matching Engine."""


from backend.matching.evaluator import ResumeJobMatcher
from backend.matching.schemas import MatchLevel
from backend.matching.service import MatchingService
from backend.models.company import Company
from backend.models.job import Job, JobMatch
from backend.models.resume import Resume, ResumeProfile
from backend.normalization.schemas import CanonicalJob, WorkMode


class TestResumeJobMatchingEngine:
    """Verifies all required matching criteria, fresher logic, and zero-fabrication guarantees."""

    def setup_method(self):
        self.matcher = ResumeJobMatcher()

        # Standard baseline candidate profile: Junior Python Backend Engineer
        self.candidate_profile = {
            "target_roles": ["Junior Backend Engineer", "Software Engineer", "Python Developer"],
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Git"],
            "education": "B.Tech in Computer Science",
            "experience_years": 1,
            "projects": [
                {
                    "title": "Scalable REST Microservice",
                    "technologies": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                    "description": "Architected high-throughput async API with relational schema design and containerization.",
                },
                {
                    "title": "Real-time Notification Service",
                    "technologies": ["Python", "Redis", "WebSockets"],
                    "description": "Built event-driven pub/sub messaging queue.",
                },
            ],
            "locations": ["Remote", "Bengaluru"],
            "work_modes": ["remote"],
        }

    def test_perfect_match(self):
        """Candidate's skills, projects, and target role align perfectly with entry-level opening."""
        job = CanonicalJob(
            title="Junior Backend Engineer",
            company="Nexus Labs",
            location="Remote",
            work_mode=WorkMode.REMOTE,
            description="Seeking a junior backend developer with Python, FastAPI, PostgreSQL, and Docker experience (0-2 years).",
            job_url="https://nexuslabs.com/careers/junior-backend",
            canonical_url="https://nexuslabs.com/careers/junior-backend",
            primary_source="company_site",
            normalized_company="nexus labs",
            normalized_title="junior backend engineer",
            normalized_location="remote",
            dedup_hash="hash-perfect-1",
        )

        evaluation = self.matcher.evaluate(job=job, profile=self.candidate_profile)

        assert evaluation.match_level == MatchLevel.STRONG
        assert evaluation.is_suitable_fresher is True
        assert evaluation.is_senior_role is False
        assert set(evaluation.skills_you_have) >= {"Python", "FastAPI", "PostgreSQL", "Docker"}
        assert "Nexus Labs" in evaluation.why_it_matches
        assert "Scalable REST Microservice" in evaluation.breakdown.project_relevance

    def test_partial_match(self):
        """Candidate has core fundamentals but is missing several specific auxiliary tools."""
        job = {
            "title": "Associate Software Engineer",
            "company": "CloudMatrix Systems",
            "location": "Remote",
            "description": (
                "Join our platform team. Requirements: Python and SQL fundamentals (0-2 years). "
                "Familiarity with Kubernetes, AWS, and Kafka is a plus."
            ),
        }

        evaluation = self.matcher.evaluate(job=job, profile=self.candidate_profile)

        assert evaluation.match_level in (MatchLevel.STRONG, MatchLevel.RELEVANT)
        assert "Python" in evaluation.skills_you_have
        # Missing skills must be highlighted without recommending fabrication
        assert any("Kubernetes" in m for m in evaluation.missing_improve)
        assert any("AWS" in m for m in evaluation.missing_improve)
        assert not any("fake" in m.lower() for m in evaluation.missing_improve)

    def test_missing_required_skill(self):
        """Job requires a completely different primary language/ecosystem."""
        job = {
            "title": "Junior Embedded Firmware Developer",
            "company": "Hardware Tech",
            "location": "Remote",
            "description": "Looking for entry-level engineer skilled in C++, Linux kernel, and RTOS architecture.",
        }

        evaluation = self.matcher.evaluate(job=job, profile=self.candidate_profile)

        # Candidate knows Python, not C++
        assert evaluation.match_level == MatchLevel.POSSIBLE
        assert "C++" not in evaluation.skills_you_have
        assert any("C++" in m for m in evaluation.missing_improve)
        assert any("missing" in c.lower() for c in evaluation.concerns)

    def test_senior_role_rejected(self):
        """Genuinely senior/lead role must be rejected for entry-level candidates."""
        # Senior by title
        job_senior_title = {
            "title": "Senior Backend Architect",
            "company": "Enterprise Global",
            "location": "Remote",
            "description": "Python, PostgreSQL, microservices. Lead architectural decisions.",
        }
        eval_senior = self.matcher.evaluate(job=job_senior_title, profile=self.candidate_profile)
        assert eval_senior.match_level == MatchLevel.REJECTED
        assert eval_senior.is_senior_role is True
        assert eval_senior.is_suitable_fresher is False
        assert "senior" in eval_senior.why_it_matches.lower()

        # Senior by explicit YOE requirement (7+ years)
        job_senior_yoe = {
            "title": "Software Engineer",
            "company": "Big Tech Corp",
            "location": "Remote",
            "description": "Requires 7+ years of professional backend software development experience.",
        }
        eval_yoe = self.matcher.evaluate(job=job_senior_yoe, profile=self.candidate_profile)
        assert eval_yoe.match_level == MatchLevel.REJECTED
        assert eval_yoe.is_senior_role is True

    def test_fresher_role_strongly_considered(self):
        """Roles explicitly labeled 'Fresher' or 'Graduate Trainee' receive strong consideration."""
        job_fresher = {
            "title": "Graduate Trainee Software Engineer",
            "company": "Infosys",
            "location": "Bengaluru, India",
            "description": "Fresher batch 2024 hiring. Python or Java programming with SQL basics.",
        }

        evaluation = self.matcher.evaluate(job=job_fresher, profile=self.candidate_profile)
        assert evaluation.match_level == MatchLevel.STRONG
        assert evaluation.is_suitable_fresher is True
        assert "fresher" in evaluation.experience_assessment.lower()

    def test_0_to_2_years_matched(self):
        """Job specifying 0-2 years experience window."""
        job_0_2 = {
            "title": "Junior Python Developer",
            "company": "Startup Co",
            "location": "Remote",
            "description": "Looking for developers with 0-2 years of experience in Python and REST APIs.",
        }

        evaluation = self.matcher.evaluate(job=job_0_2, profile=self.candidate_profile)
        assert evaluation.match_level == MatchLevel.STRONG
        assert evaluation.is_suitable_fresher is True
        assert "0–2" in evaluation.experience_assessment or "0-2" in evaluation.experience_assessment

    def test_1_plus_years_carefully_considered_not_rejected(self):
        """1+ years roles must not be automatically rejected if candidate has relevant skills/projects."""
        job_1_plus = {
            "title": "Software Engineer I - Python",
            "company": "Fintech Stream",
            "location": "Remote",
            "description": "Requires 1+ years of experience with Python, FastAPI, and relational databases.",
        }

        evaluation = self.matcher.evaluate(job=job_1_plus, profile=self.candidate_profile)

        # Must NOT be automatically rejected!
        assert evaluation.match_level in (MatchLevel.STRONG, MatchLevel.RELEVANT)
        assert evaluation.is_suitable_fresher is True
        # Explicit note in experience assessment
        assert "1+" in evaluation.experience_assessment

    def test_unrelated_job_rejected(self):
        """Completely unrelated non-technical vacancies must be rejected."""
        unrelated_jobs = [
            {"title": "Registered Nurse - ICU", "company": "Memorial Hospital", "description": "Patient care."},
            {"title": "Commercial Real Estate Broker", "company": "CBRE", "description": "Property sales."},
            {"title": "Senior Sales Account Executive", "company": "SaaS Sales Inc", "description": "Closing quotas."},
        ]

        for job in unrelated_jobs:
            eval_unrelated = self.matcher.evaluate(job=job, profile=self.candidate_profile)
            assert eval_unrelated.match_level == MatchLevel.REJECTED
            assert "technical" in eval_unrelated.why_it_matches or "software" in eval_unrelated.why_it_matches

    def test_project_based_match(self):
        """Candidate's primary proof of a technology comes directly from a portfolio project."""
        job = {
            "title": "Junior Backend Engineer",
            "company": "Modern Apps",
            "location": "Remote",
            "description": "Seeking Python developer to build async WebSockets and Redis messaging services.",
        }

        evaluation = self.matcher.evaluate(job=job, profile=self.candidate_profile)

        assert evaluation.match_level in (MatchLevel.STRONG, MatchLevel.RELEVANT)
        # Verify the Redis project was specifically detected
        assert "Real-time Notification Service" in evaluation.breakdown.project_relevance
        assert "Redis" in evaluation.breakdown.project_relevance

    def test_database_persistence_of_job_match(self, db_session):
        """Verify MatchingService evaluates and persists JobMatch entities to PostgreSQL."""
        # Create test resume and profile
        resume = Resume(
            file_name="rohan_verma.pdf",
            file_path="/resumes/rohan_verma.pdf",
        )
        db_session.add(resume)
        db_session.flush()

        profile = ResumeProfile(
            resume_id=resume.id,
            profile_name="Backend Engineer",
            target_role="Junior Backend Engineer",
            max_experience_years=2,
        )
        db_session.add(profile)
        db_session.flush()

        comp = Company(name="Test Co", normalized_name="test co")
        db_session.add(comp)
        db_session.flush()

        job_entity = Job(
            title="Junior Backend Engineer",
            company_name="Test Co",
            location="Remote",
            work_mode="remote",
            description="Python and FastAPI developer needed.",
            job_url="https://testco.com/job/1",
            canonical_url="https://testco.com/job/1",
            source="manual",
            normalized_company="test co",
            normalized_title="junior backend engineer",
            normalized_location="remote",
            dedup_hash="dedup-test-match-999",
            company_id=comp.id,
        )
        db_session.add(job_entity)
        db_session.flush()

        service = MatchingService()
        evaluations = service.evaluate_and_record_batch(
            db_session=db_session,
            jobs=[job_entity],
            profile=profile,
        )

        assert len(evaluations) == 1
        # Query saved JobMatch in DB
        match_db = (
            db_session.query(JobMatch)
            .filter(
                JobMatch.resume_profile_id == profile.id,
                JobMatch.job_id == job_entity.id,
            )
            .first()
        )
        assert match_db is not None
        assert match_db.fit_level in ("high", "medium", "low")
        assert match_db.reasoning is not None
