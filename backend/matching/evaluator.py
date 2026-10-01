"""Resume and Job Matching Engine with strict fresher logic and zero-fabrication constraints."""

import logging
import re
from typing import Any

from backend.ingestion.schemas import StructuredResumeExtraction
from backend.matching.schemas import EvaluationBreakdown, JobMatchEvaluation, MatchLevel
from backend.models.resume import ResumeProfile
from backend.normalization.normalizer import (
    KNOWN_TECHNICAL_SKILLS,
    normalize_company,
    normalize_title,
)
from backend.normalization.schemas import CanonicalJob

logger = logging.getLogger("job_intelligence.matching.evaluator")

# Keywords that identify entry-level and fresher-friendly opportunities (Strict 0-2 years)
FRESHER_KEYWORDS = [
    "fresher",
    "entry level",
    "entry-level",
    "junior",
    "graduate",
    "trainee",
    "intern",
    "internship",
    "associate",
    "software engineer i",
    "sde 1",
    "sde i",
    "swe 1",
    "swe i",
    "engineer i",
    "developer i",
    "0-1",
    "0-2",
    "0 to 1",
    "0 to 2",
    "0 years",
]

# Keywords that denote mid/senior roles or excessive tenure (> 2 years) that must be rejected
SENIOR_KEYWORDS = [
    "senior",
    "sr.",
    "sr ",
    "lead",
    "principal",
    "staff",
    "architect",
    "director",
    "head of",
    "engineering manager",
    "mid-level",
    "mid level",
    "software engineer ii",
    "swe ii",
    "swe 2",
    "sde ii",
    "sde 2",
    "developer ii",
    "engineer ii",
    "level 2",
    "3+ years",
    "4+ years",
    "5+ years",
    "6+ years",
    "7+ years",
    "8+ years",
    "10+ years",
    "3-5 years",
    "3 to 5 years",
    "2-4 years",
    "2 to 4 years",
    "3-6 years",
    "4-6 years",
    "5-8 years",
    "7-10 years",
    "minimum 3 years",
    "at least 3 years",
    "min 3 years",
    "minimum 4 years",
    "at least 4 years",
    "3+ yrs",
    "4+ yrs",
    "5+ yrs",
]

# Unrelated domain keywords
UNRELATED_DOMAINS = [
    "nurse",
    "physician",
    "account executive",
    "real estate",
    "graphic designer",
    "sales manager",
    "barista",
    "chef",
    "driver",
    "receptionist",
    "legal counsel",
]


class ResumeJobMatcher:
    """Evaluates individual jobs against a candidate's resume profile with deep qualitative breakdown."""

    def evaluate(
        self,
        job: CanonicalJob | dict[str, Any],
        profile: StructuredResumeExtraction | ResumeProfile | dict[str, Any],
    ) -> JobMatchEvaluation:
        """Compare a job posting against a candidate's verified resume profile.

        Guarantees:
        - Never attributes a skill to the candidate unless verified in their resume.
        - Never suggests fabricating experience or credentials in missing_improve.
        - Rejects genuinely senior positions.
        - Thoughtfully treats 1+ years as potentially accessible with project work.
        - Provides rich, transparent qualitative explanations rather than raw scores.
        """
        candidate_data = self._extract_candidate_facets(profile)
        job_data = self._extract_job_facets(job)

        # 1. Experience & Seniority Evaluation
        exp_eval = self._evaluate_experience(job_data)

        # 2. Check for Unrelated Non-Technical Roles
        is_unrelated = self._is_unrelated_role(job_data)

        # 3. Skills Evaluation (Strict Zero-Hallucination)
        skills_eval = self._evaluate_skills(candidate_data, job_data)

        # 4. Project Relevance
        project_eval = self._evaluate_projects(candidate_data, job_data)

        # 5. Role Relevance
        role_eval = self._evaluate_role(candidate_data, job_data)

        # 6. Education Assessment
        edu_eval = self._evaluate_education(candidate_data)

        # 7. Location & Work Mode
        loc_eval = self._evaluate_location(candidate_data, job_data)

        # 8. Determine Qualitative Match Level & Concerns
        concerns: list[str] = []
        concerns.extend(exp_eval["concerns"])
        concerns.extend(skills_eval["concerns"])

        if is_unrelated:
            match_level = MatchLevel.REJECTED
            why_it_matches = "This role does not align with your technical software development background."
        elif exp_eval["is_senior"]:
            match_level = MatchLevel.REJECTED
            why_it_matches = (
                f"Role '{job_data['title']}' requires experience beyond entry-level ({exp_eval['experience_summary']}). "
                "It exceeds the 0-2 years experience criteria."
            )
        else:
            match_level, why_it_matches = self._determine_match_level(
                skills_eval=skills_eval,
                project_eval=project_eval,
                exp_eval=exp_eval,
                role_eval=role_eval,
                job_data=job_data,
            )

        breakdown = EvaluationBreakdown(
            role_relevance=role_eval["summary"],
            required_skills=skills_eval["required_skills"],
            preferred_skills=skills_eval["preferred_skills"],
            skills_you_have=skills_eval["skills_you_have"],
            missing_improve=skills_eval["missing_improve"],
            project_relevance=project_eval["summary"],
            experience_assessment=exp_eval["experience_summary"],
            education_assessment=edu_eval,
            location_work_mode=loc_eval,
            concerns=concerns,
        )

        return JobMatchEvaluation(
            job_id=job_data.get("id"),
            resume_profile_id=candidate_data.get("id"),
            match_level=match_level,
            why_it_matches=why_it_matches,
            skills_you_have=skills_eval["skills_you_have"],
            missing_improve=skills_eval["missing_improve"],
            experience_assessment=exp_eval["experience_summary"],
            concerns=concerns,
            breakdown=breakdown,
            is_suitable_fresher=exp_eval["is_suitable_fresher"],
            is_senior_role=exp_eval["is_senior"],
            raw_telemetry={
                "skill_overlap_ratio": skills_eval["overlap_ratio"],
                "project_matches_count": len(project_eval["matched_projects"]),
            },
        )

    def _extract_candidate_facets(self, profile: Any) -> dict[str, Any]:
        """Extract verified skills, projects, and target preferences from candidate profile."""
        skills: set[str] = set()
        roles: list[str] = []
        projects: list[dict[str, Any]] = []
        education: str = "Technical Degree"
        yoe: int = 0
        profile_id = None

        if isinstance(profile, StructuredResumeExtraction):
            skills.update(profile.all_unique_skills())
            roles.extend(profile.likely_target_roles)
            for p in profile.projects:
                projects.append({
                    "title": p.title,
                    "technologies": p.technologies,
                    "description": p.description or "",
                })
            if profile.education:
                education = f"{profile.education[0].degree or 'Degree'} from {profile.education[0].institution or 'University'}"
            yoe = len(profile.experience) + len(profile.internships)

        elif isinstance(profile, ResumeProfile):
            profile_id = profile.id
            if profile.target_role:
                roles.append(profile.target_role)
            if hasattr(profile, "skills") and profile.skills:
                for s in profile.skills:
                    if hasattr(s, "skill") and s.skill:
                        skills.add(s.skill.name)
            yoe = profile.max_experience_years

        elif isinstance(profile, dict):
            profile_id = profile.get("id")
            skills.update(profile.get("skills", []))
            roles.extend(profile.get("target_roles", []))
            if not roles and "target_role" in profile:
                roles.append(profile["target_role"])
            projects = profile.get("projects", [])
            education = profile.get("education", "Computer Science")
            yoe = profile.get("experience_years", 0)

        # Standardize skill names using taxonomy
        normalized_skills: set[str] = set()
        for s in skills:
            s_clean = s.strip().lower()
            normalized_skills.add(KNOWN_TECHNICAL_SKILLS.get(s_clean, s.strip()))

        return {
            "id": profile_id,
            "skills": normalized_skills,
            "roles": roles or ["Software Engineer"],
            "projects": projects,
            "education": education,
            "yoe": yoe,
        }

    def _extract_job_facets(self, job: Any) -> dict[str, Any]:
        """Extract title, description, skills, and constraints from job representation."""
        if isinstance(job, CanonicalJob):
            title = job.title
            company = job.company
            location = job.location
            work_mode = job.work_mode.value
            description = job.description
            skills = job.skills
            job_id = job.id
        elif isinstance(job, dict):
            title = normalize_title(job.get("title", ""))
            company = normalize_company(job.get("company", job.get("company_name", "")))
            location = job.get("location", "Remote")
            work_mode = str(job.get("work_mode", "remote")).lower()
            description = job.get("description", "")
            skills = job.get("skills", [])
            job_id = job.get("id", job.get("job_id"))
        else:
            # SQLAlchemy Job ORM instance or duck-typed entity
            title = normalize_title(getattr(job, "title", ""))
            company = normalize_company(getattr(job, "company_name", getattr(job, "company", "")))
            location = getattr(job, "location", "Remote")
            work_mode = str(getattr(job, "work_mode", "remote")).lower()
            description = getattr(job, "description", "")
            skills = getattr(job, "skills", [])
            job_id = getattr(job, "id", None)


        # Extract technical skills directly from text if sparse
        extracted_skills = set(skills)
        combined_text = f" {title.lower()} {description.lower()} "
        for keyword, canonical in KNOWN_TECHNICAL_SKILLS.items():
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(keyword) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, combined_text):
                extracted_skills.add(canonical)

        return {
            "id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "work_mode": work_mode,
            "description": description,
            "skills": sorted(extracted_skills),
        }

    def _is_unrelated_role(self, job_data: dict[str, Any]) -> bool:
        """Identify completely non-technical roles."""
        lower_title = job_data["title"].lower()
        return any(domain in lower_title for domain in UNRELATED_DOMAINS)

    def _evaluate_experience(self, job_data: dict[str, Any]) -> dict[str, Any]:
        """Evaluate experience constraints and enforce strict 0-2 years fresher/entry-level rules."""
        title_lower = job_data["title"].lower()
        text = f"{title_lower} {job_data['description'][:1000]}".lower()

        # Check for senior or mid-level titles
        senior_title_patterns = [
            r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b", r"\bstaff\b",
            r"\barchitect\b", r"\bdirector\b", r"\bmanager\b", r"\bhead of\b",
            r"\bmid-level\b", r"\bmid level\b", r"\bsde[- ]?ii\b", r"\bswe[- ]?ii\b",
            r"\bsde[- ]?2\b", r"\bswe[- ]?2\b", r"\bengineer[- ]?ii\b", r"\bdeveloper[- ]?ii\b",
        ]
        has_senior_title = any(re.search(pat, title_lower) for pat in senior_title_patterns)
        has_senior_text = any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in SENIOR_KEYWORDS)

        # Check for fresher keywords
        has_fresher_keywords = any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in FRESHER_KEYWORDS)

        # Extract explicit year requirements
        # 1. Range: e.g. '0-2 years', '1-3 years', '3-5 years', '2 to 4 years'
        range_match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?|yoe)", text)
        # 2. Plus: e.g. '3+ years', '1+ years'
        plus_match = re.search(r"(\d+)\s*\+\s*(?:years?|yrs?|yoe)", text)
        # 3. Minimum prefix: e.g. 'minimum of 3 years', 'at least 3 years'
        min_prefix_match = re.search(r"(?:minimum|at least|min\.?)\s*(?:of)?\s*(\d+)\s*(?:years?|yrs?|yoe)", text)
        # 4. Single match: e.g. '3 years experience'
        single_match = re.search(r"(\d+)\s*(?:years?|yrs?|yoe)", text)

        min_years = 0
        max_years = 0
        if range_match:
            min_years = int(range_match.group(1))
            max_years = int(range_match.group(2))
        elif plus_match:
            min_years = int(plus_match.group(1))
            max_years = min_years + 2
        elif min_prefix_match:
            min_years = int(min_prefix_match.group(1))
            max_years = min_years + 2
        elif single_match:
            min_years = int(single_match.group(1))
            max_years = min_years

        # STRICT 0-2 YEARS RULE:
        # If minimum required experience exceeds 2 years (e.g. 3+, 4+, 3-5),
        # or if range is e.g. 2-4+ years with senior wording, mark as senior/ineligible.
        is_senior = has_senior_title or has_senior_text
        if min_years > 2 or (min_years >= 2 and max_years >= 4):
            is_senior = True

        concerns: list[str] = []
        is_suitable_fresher = True
        is_one_plus = (
            ("1+ year" in text or "1+ years" in text or "1-2 year" in text or "1-2 years" in text)
            and not is_senior
            and min_years <= 2
        ) or (min_years == 1 and not any(k in text for k in ["0-1", "0–1", "0-2", "0–2", "0 to 1", "0 to 2"]) and not is_senior)

        if is_senior:
            is_suitable_fresher = False
            summary = f"Requires experience beyond entry-level ({min_years}+ years or mid/senior title). Exceeds 0-2 years criteria."
            concerns.append(f"Role requires ~{min_years}+ years commercial experience, exceeding the 0-2 years target bounds.")
        elif is_one_plus:
            summary = "Stipulates 1+ years experience; highly accessible for freshers with substantive project portfolios or internship experience."
            concerns.append("Job mentions 1+ years preference; portfolio projects and technical foundation will be crucial.")
        elif has_fresher_keywords or min_years == 0 or "0-2" in text or "0–2" in text or "0-1" in text or "0–1" in text:
            summary = "Ideal entry-level opportunity explicitly welcoming freshers and candidates with 0-2 years experience."
        else:
            summary = f"Experience requirement noted as ~{min_years} years. Feasible for an entry-level candidate with strong foundations."

        return {
            "is_senior": is_senior,
            "is_suitable_fresher": is_suitable_fresher,
            "is_one_plus": is_one_plus,
            "experience_summary": summary,
            "concerns": concerns,
        }

    def _evaluate_skills(self, candidate_data: dict[str, Any], job_data: dict[str, Any]) -> dict[str, Any]:
        """Strictly evaluate skill overlap, enforcing zero fabrication."""
        job_skills = job_data["skills"]
        candidate_skills = candidate_data["skills"]

        # Only confirmed skills supported by candidate profile
        skills_you_have = [s for s in job_skills if s in candidate_skills]

        # Missing skills to improve
        missing = [s for s in job_skills if s not in candidate_skills]

        # Actionable recommendations without fabrication
        actionable_improvements: list[str] = []
        for s in missing[:5]:
            actionable_improvements.append(f"Familiarize with {s} fundamentals, documentation, and best practices")

        overlap_ratio = len(skills_you_have) / len(job_skills) if job_skills else 0.5

        concerns: list[str] = []
        if missing:
            concerns.append(f"Missing knowledge in: {', '.join(missing[:3])}")

        return {
            "required_skills": job_skills,
            "preferred_skills": [],
            "skills_you_have": sorted(skills_you_have),
            "missing_improve": actionable_improvements,
            "overlap_ratio": overlap_ratio,
            "concerns": concerns,
        }

    def _evaluate_projects(self, candidate_data: dict[str, Any], job_data: dict[str, Any]) -> dict[str, Any]:
        """Identify which candidate projects directly prove competencies required by the job."""
        matched_projects: list[str] = []
        job_skills_lower = {s.lower() for s in job_data["skills"]}

        for proj in candidate_data["projects"]:
            proj_techs = {t.lower() for t in proj.get("technologies", [])}
            overlapping = proj_techs & job_skills_lower
            if overlapping:
                tech_names = [KNOWN_TECHNICAL_SKILLS.get(t, t.title()) for t in sorted(overlapping)]
                matched_projects.append(f"{proj['title']} (demonstrating {', '.join(tech_names)})")

        if matched_projects:
            summary = f"Direct project evidence: {'; '.join(matched_projects)}."
        else:
            summary = "Candidate has general project background; recommend building a focused repository demonstration."

        return {
            "matched_projects": matched_projects,
            "summary": summary,
        }

    def _evaluate_role(self, candidate_data: dict[str, Any], job_data: dict[str, Any]) -> dict[str, Any]:
        """Evaluate role title alignment."""
        job_title_lower = job_data["title"].lower()
        matched_roles = [r for r in candidate_data["roles"] if r.lower() in job_title_lower or job_title_lower in r.lower()]

        if matched_roles:
            summary = f"Direct role trajectory alignment with your target preference '{matched_roles[0]}'."
        else:
            summary = f"Role '{job_data['title']}' offers strong adjacent software engineering opportunities."

        return {
            "matched_roles": matched_roles,
            "summary": summary,
        }

    def _evaluate_education(self, candidate_data: dict[str, Any]) -> str:
        """Assess education fit."""
        return f"Educational background ({candidate_data['education']}) meets the technical prerequisite for this software role."

    def _evaluate_location(self, candidate_data: dict[str, Any], job_data: dict[str, Any]) -> str:
        """Assess location and work mode."""
        if job_data["work_mode"] == "remote" or job_data["location"] == "Remote":
            return "Remote position offering full geographic flexibility."
        return f"Location: {job_data['location']} ({job_data['work_mode'].capitalize()})."

    def _determine_match_level(
        self,
        skills_eval: dict[str, Any],
        project_eval: dict[str, Any],
        exp_eval: dict[str, Any],
        role_eval: dict[str, Any],
        job_data: dict[str, Any],
    ) -> tuple[MatchLevel, str]:
        """Determine qualitative match tier (STRONG, RELEVANT, POSSIBLE) and generate rationale."""
        overlap = skills_eval["overlap_ratio"]
        has_projects = bool(project_eval["matched_projects"])
        has_role_match = bool(role_eval["matched_roles"])
        skills_have = skills_eval["skills_you_have"]

        is_fresher_job = "entry-level" in exp_eval["experience_summary"].lower() or "fresher" in exp_eval["experience_summary"].lower()

        # Strong Match Criteria: High skill overlap (>= 50%) or fresher role with core skills or projects
        is_strong = exp_eval["is_suitable_fresher"] and (
            overlap >= 0.50
            or (is_fresher_job and len(skills_have) >= 1)
            or (len(skills_have) >= 2 and (has_projects or has_role_match))
        )
        if is_strong:
            level = MatchLevel.STRONG
            why = (
                f"Strong match for '{job_data['title']}' at '{job_data['company']}'. "
                f"You possess core required skills ({', '.join(skills_have[:4])}), backed by "
                f"{project_eval['summary'].lower()} "
                f"{exp_eval['experience_summary']}"
            )
            return level, why


        # Relevant Match: Moderate overlap (>= 35%) or 1+ year role with project compensation
        if (overlap >= 0.35 or has_projects or exp_eval["is_one_plus"]) and len(skills_have) >= 1:
            level = MatchLevel.RELEVANT
            why = (
                f"Relevant opportunity for '{job_data['title']}'. "
                f"You have confirmed capability in {', '.join(skills_have)}, and your "
                f"technical foundation aligns with the position's core requirements. "
                f"{exp_eval['experience_summary']}"
            )
            return level, why

        # Possible Match: Foundational overlap or adjacent stack
        level = MatchLevel.POSSIBLE
        skills_desc = f"in {', '.join(skills_have)}" if skills_have else "in foundational software principles"
        why = (
            f"Possible exploratory match for '{job_data['title']}'. "
            f"While you have competencies {skills_desc}, "
            f"the role places heavier emphasis on tools you have not yet demonstrated ({', '.join(skills_eval['missing_improve'][:2])})."
        )
        return level, why
