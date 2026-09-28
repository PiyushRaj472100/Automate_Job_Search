"""Comprehensive unit and integration tests for recruiter and hiring-person discovery."""

from unittest.mock import MagicMock, patch

from backend.models.company import Company
from backend.models.job import Job
from backend.models.person import JobPerson, Person
from backend.recruiter.finder import RecruiterFinder
from backend.recruiter.schemas import (
    RawCandidateProfile,
    RecruiterRoleTier,
    RecruiterStatus,
)
from backend.recruiter.service import RecruiterDiscoveryService
from backend.recruiter.verifier import ProfileVerifier


class TestRecruiterDiscoveryAndVerification:
    """Verifies profile verification, prioritization hierarchy, truthfulness, and persistence."""

    def setup_method(self):
        self.verifier = ProfileVerifier()
        self.finder = RecruiterFinder(verifier=self.verifier)

        self.sample_job = {
            "title": "Junior Backend Engineer",
            "company": "Nexus Labs",
            "location": "Remote",
            "description": "Seeking Python engineer with FastAPI experience.",
        }

    def test_valid_profile(self):
        """A valid recruiter profile at the matching company with verified LinkedIn URL."""
        candidate = RawCandidateProfile(
            name="Sarah Connor",
            title="Senior Technical Recruiter",
            company="Nexus Labs",
            linkedin_url="https://www.linkedin.com/in/sarah-connor-recruiter/",
            email="sarah.c@nexuslabs.com",
        )

        result = self.verifier.verify_profile(candidate, target_company="Nexus Labs")

        assert result.status == RecruiterStatus.VERIFIED
        assert result.role_tier == RecruiterRoleTier.TECHNICAL_RECRUITER
        assert result.confidence >= 0.85
        assert result.name == "Sarah Connor"
        assert result.company == "Nexus Labs"
        assert result.linkedin_url == "https://www.linkedin.com/in/sarah-connor-recruiter"
        assert result.verified_at is not None
        assert "Verified" in result.relevance_reason

    def test_wrong_company(self):
        """Candidate works at a completely different company and must not be verified for this job."""
        candidate = RawCandidateProfile(
            name="Alice Walker",
            title="Lead Recruiter",
            company="Acme Global Corporation",
            linkedin_url="https://www.linkedin.com/in/alicewalker/",
        )

        result = self.verifier.verify_profile(candidate, target_company="Nexus Labs")

        assert result.status == RecruiterStatus.UNVERIFIED
        assert result.confidence <= 0.20
        assert "Wrong company" in result.relevance_reason
        assert result.verification_details["company_valid"] is False

    def test_wrong_person(self):
        """Generic or placeholder names (e.g. 'LinkedIn Member', 'Hiring Team') must be rejected."""
        placeholders = [
            "LinkedIn Member",
            "Hiring Team",
            "HR Department",
            "Recruiting Team",
            "Anonymous",
            "  ",
            "12345",
        ]

        for placeholder in placeholders:
            candidate = RawCandidateProfile(
                name=placeholder,
                title="Technical Recruiter",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/valid-slug/",
            )
            result = self.verifier.verify_profile(candidate, target_company="Nexus Labs")
            assert result.status == RecruiterStatus.NOT_FOUND
            assert result.confidence == 0.0
            assert "Invalid" in result.relevance_reason or "Generic" in result.relevance_reason

    def test_broken_url(self):
        """Malformed or broken profile URLs must fail URL verification and prevent VERIFIED status."""
        invalid_urls = [
            "not-a-valid-url",
            "https://twitter.com/recruiter",
            "https://www.linkedin.com/in/search",  # Reserved slug
            "https://www.linkedin.com/feed",      # Not a profile path
        ]

        for url in invalid_urls:
            candidate = RawCandidateProfile(
                name="John Doe",
                title="Recruiter",
                company="Nexus Labs",
                linkedin_url=url,
            )
            result = self.verifier.verify_profile(candidate, target_company="Nexus Labs")
            assert result.status != RecruiterStatus.VERIFIED
            assert result.verification_details["url_valid"] is False

        # Active HTTP 404 test
        with patch("httpx.head") as mock_head:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_head.return_value = mock_resp

            candidate_404 = RawCandidateProfile(
                name="Jane Doe",
                title="Recruiter",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/janedoe-nonexistent/",
            )
            res_404 = self.verifier.verify_profile(
                candidate_404,
                target_company="Nexus Labs",
                check_network=True,
            )
            assert res_404.status != RecruiterStatus.VERIFIED
            assert "broken" in str(res_404.verification_details.get("url_error", "")).lower()

    def test_relevant_recruiter_prioritization(self):
        """Profiles must be strictly prioritized according to user specification:
        1. Recruiter
        2. Talent Acquisition
        3. Technical Recruiter
        4. Hiring Manager
        5. Engineering Manager
        6. Relevant recruitment professional
        """
        candidates = [
            RawCandidateProfile(
                name="Eva Manager",
                title="Engineering Manager",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/evamanager/",
            ),
            RawCandidateProfile(
                name="Paul People",
                title="People Operations Specialist",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/paulpeople/",
            ),
            RawCandidateProfile(
                name="Helen Hire",
                title="Hiring Manager",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/helenhire/",
            ),
            RawCandidateProfile(
                name="Tina Talent",
                title="Talent Acquisition Partner",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/tinatalent/",
            ),
            RawCandidateProfile(
                name="Tom Tech",
                title="Technical Recruiter",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/tomtech/",
            ),
            RawCandidateProfile(
                name="Rachel Recruiter",
                title="Corporate Recruiter",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/rachelrecruiter/",
            ),
        ]

        discovery = self.finder.discover_for_job(self.sample_job, candidate_pool=candidates)

        assert discovery.overall_status == RecruiterStatus.VERIFIED
        assert len(discovery.verified_recruiters) == 6

        # Order must strictly follow:
        # Tier 1: Rachel (Recruiter)
        # Tier 2: Tina (Talent Acquisition)
        # Tier 3: Tom (Technical Recruiter)
        # Tier 4: Helen (Hiring Manager)
        # Tier 5: Eva (Engineering Manager)
        # Tier 6: Paul (People Ops)
        names_in_order = [p.name for p in discovery.verified_recruiters]
        expected_order = [
            "Rachel Recruiter",
            "Tina Talent",
            "Tom Tech",
            "Helen Hire",
            "Eva Manager",
            "Paul People",
        ]
        assert names_in_order == expected_order

        # Primary columns must contain ONLY the top 3
        assert "Rachel Recruiter" in discovery.recruiter_1
        assert "Tina Talent" in discovery.recruiter_2
        assert "Tom Tech" in discovery.recruiter_3
        # Ensure 4th and beyond are not in primary columns
        assert "Helen Hire" not in (discovery.recruiter_1, discovery.recruiter_2, discovery.recruiter_3)

    def test_unrelated_employee_rejected(self):
        """Employees in non-hiring/non-recruiting roles must be rejected."""
        unrelated_candidates = [
            RawCandidateProfile(
                name="Mark Accountant",
                title="Senior Financial Analyst",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/markaccountant/",
            ),
            RawCandidateProfile(
                name="Cindy Sales",
                title="Commercial Account Executive",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/cindysales/",
            ),
            RawCandidateProfile(
                name="Bob Builder",
                title="Facilities Maintenance Specialist",
                company="Nexus Labs",
                linkedin_url="https://www.linkedin.com/in/bobbuilder/",
            ),
        ]

        for cand in unrelated_candidates:
            result = self.verifier.verify_profile(cand, target_company="Nexus Labs")
            assert result.status == RecruiterStatus.NOT_FOUND
            assert result.role_tier == RecruiterRoleTier.UNRELATED
            assert result.confidence == 0.0

        discovery = self.finder.discover_for_job(self.sample_job, candidate_pool=unrelated_candidates)
        assert len(discovery.verified_recruiters) == 0
        assert discovery.recruiter_1 == ""
        assert discovery.recruiter_2 == ""
        assert discovery.recruiter_3 == ""
        assert discovery.overall_status == RecruiterStatus.NOT_FOUND

    def test_never_claim_requisition_ownership_without_evidence(self):
        """Never claim that a person owns a requisition without explicit evidence."""
        # Case A: Standard recruiter with no job description mention
        cand_general = RawCandidateProfile(
            name="Clara Oswald",
            title="Senior Recruiter",
            company="Nexus Labs",
            linkedin_url="https://www.linkedin.com/in/claraoswald/",
        )
        res_general = self.verifier.verify_profile(cand_general, target_company="Nexus Labs")
        assert res_general.is_job_owner is False
        assert "No direct evidence of requisition ownership" in res_general.relevance_reason

        # Case B: Explicit author / contact evidence in job posting
        job_with_evidence = {
            "title": "Junior Backend Engineer",
            "company": "Nexus Labs",
            "posted_by": "Clara Oswald",
            "description": "Reach out to Clara Oswald for any questions regarding this role.",
        }
        res_evidence = self.verifier.verify_profile(
            cand_general,
            target_company="Nexus Labs",
            job_context=job_with_evidence,
        )
        assert res_evidence.is_job_owner is True
        assert "(Requisition Owner)" in res_evidence.relevance_reason

    def test_database_persistence_of_people_and_job_links(self, db_session):
        """Verify verified people and their association to jobs are saved in PostgreSQL."""
        comp = Company(name="Nexus Labs", normalized_name="nexus labs")
        db_session.add(comp)
        db_session.flush()

        job = Job(
            title="Junior Backend Engineer",
            company_name="Nexus Labs",
            company_id=comp.id,
            location="Remote",
            work_mode="remote",
            description="Python developer needed.",
            job_url="https://nexuslabs.com/job/201",
            canonical_url="https://nexuslabs.com/job/201",
            source="company_site",
            normalized_company="nexus labs",
            normalized_title="junior backend engineer",
            normalized_location="remote",
            dedup_hash="dedup-hash-recruiter-pers-1",
        )
        db_session.add(job)
        db_session.flush()

        candidate = RawCandidateProfile(
            name="Liam Neeson",
            title="Head of Talent Acquisition",
            company="Nexus Labs",
            linkedin_url="https://www.linkedin.com/in/liam-neeson-ta/",
            email="liam@nexuslabs.com",
        )

        service = RecruiterDiscoveryService()
        result = service.discover_and_record_for_job(
            db_session=db_session,
            job=job,
            candidate_pool=[candidate],
        )

        assert result.overall_status == RecruiterStatus.VERIFIED
        assert "Liam Neeson" in result.recruiter_1

        # Query database to confirm persistence
        person_db = db_session.query(Person).filter(
            Person.full_name == "Liam Neeson",
            Person.company_id == comp.id,
        ).first()
        assert person_db is not None
        assert person_db.full_name == "Liam Neeson"
        assert person_db.is_verified is True
        assert person_db.company_id == comp.id

        link_db = db_session.query(JobPerson).filter(
            JobPerson.job_id == job.id,
            JobPerson.person_id == person_db.id,
        ).first()
        assert link_db is not None
        assert link_db.confidence_score >= 0.80
        assert link_db.relationship_type == "talent_acquisition"
