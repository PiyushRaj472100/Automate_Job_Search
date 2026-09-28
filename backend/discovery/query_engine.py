"""Search query generation engine for translating candidate profiles into multi-strategy search queries."""

import logging
from typing import Any

from backend.discovery.models import SearchQuery
from backend.ingestion.schemas import StructuredResumeExtraction
from backend.models.resume import ResumeProfile

logger = logging.getLogger("job_intelligence.discovery.query_engine")

ENTRY_LEVEL_TERMS: list[str] = [
    "fresher",
    "junior",
    "graduate",
    "entry level",
    "0-2 years",
    "associate",
]


class SearchQueryEngine:
    """Generates a rich, diversified set of job search queries tailored to a candidate profile.

    Avoids single-point-of-failure query strategies by combining:
    - Target roles with varied entry-level qualifiers
    - Target roles coupled with primary technical skills
    - Standalone skill-focused fresher queries
    - Work-mode specific searches (e.g. remote)
    - Location-constrained searches where desired
    """

    def __init__(self, max_queries: int = 12) -> None:
        self.max_queries = max_queries

    def extract_profile_data(
        self,
        profile_source: ResumeProfile | StructuredResumeExtraction | dict[str, Any],
    ) -> dict[str, Any]:
        """Extract standardized search facets regardless of profile source representation."""
        roles: list[str] = []
        skills: list[str] = []
        locations: list[str] = []
        work_modes: list[str] = []

        if isinstance(profile_source, ResumeProfile):
            if profile_source.target_role:
                roles.append(profile_source.target_role)
            if profile_source.target_locations:
                locations.extend(profile_source.target_locations)
            if profile_source.work_modes:
                work_modes.extend(profile_source.work_modes)
            # Associated skills from relationships if loaded
            if hasattr(profile_source, "skills") and profile_source.skills:
                skills.extend([s.skill.name for s in profile_source.skills if hasattr(s, "skill") and s.skill])

        elif isinstance(profile_source, StructuredResumeExtraction):
            roles.extend(profile_source.likely_target_roles)
            skills.extend(profile_source.all_unique_skills())
            work_modes.append("remote")

        elif isinstance(profile_source, dict):
            roles.extend(profile_source.get("target_roles", []))
            if not roles and "target_role" in profile_source:
                roles.append(profile_source["target_role"])
            skills.extend(profile_source.get("skills", []))
            locations.extend(profile_source.get("locations", []))
            work_modes.extend(profile_source.get("work_modes", []))

        # Fallbacks if sparse
        if not roles:
            roles = ["Software Engineer", "Backend Developer"]
        if not work_modes:
            work_modes = ["remote", "on_site"]

        # Clean and deduplicate while preserving order
        clean_roles = [r.strip() for r in roles if r and r.strip()]
        clean_skills = [s.strip() for s in skills if s and s.strip()]
        clean_locations = [loc.strip() for loc in locations if loc and loc.strip()]

        return {
            "roles": clean_roles,
            "skills": clean_skills,
            "locations": clean_locations,
            "work_modes": work_modes,
        }

    def generate_queries(
        self,
        profile_source: ResumeProfile | StructuredResumeExtraction | dict[str, Any],
    ) -> list[SearchQuery]:
        """Generate diverse SearchQuery objects from a candidate's profile."""
        data = self.extract_profile_data(profile_source)
        roles: list[str] = data["roles"]
        skills: list[str] = data["skills"]
        locations: list[str] = data["locations"]
        work_modes: list[str] = data["work_modes"]

        generated: list[SearchQuery] = []
        seen_query_texts: set[str] = set()

        def add_query(
            text: str,
            role: str,
            used_skills: list[str],
            level: str,
            loc: str | None = None,
            mode: str | None = None,
        ) -> None:
            normalized_text = " ".join(text.strip().split())
            lower_text = normalized_text.lower()
            if lower_text not in seen_query_texts and len(generated) < self.max_queries:
                seen_query_texts.add(lower_text)
                generated.append(
                    SearchQuery(
                        query_text=normalized_text,
                        role_title=role,
                        skills=used_skills,
                        experience_level=level,
                        location=loc,
                        work_mode=mode,
                    )
                )

        primary_role = roles[0]
        top_skills = skills[:4]

        # Extract base role without prefixes like 'junior' or 'entry level'
        base_role = primary_role
        for prefix in ["junior", "fresher", "entry level", "entry-level", "graduate", "associate", "sr.", "senior"]:
            if base_role.lower().startswith(prefix):
                base_role = base_role[len(prefix):].strip()
        if not base_role:
            base_role = primary_role

        # Strategy 1: Primary Role + Entry-Level Keywords (e.g. "Junior Backend Engineer", "Software Engineer Fresher")
        for term in ["junior", "fresher", "entry level", "graduate", "0-2 years"]:
            add_query(
                text=f"{term.title()} {base_role}",
                role=primary_role,
                used_skills=[],
                level=term,
            )

        # Strategy 2: Alternate Target Roles + Junior/Entry Level
        for alt_role in roles[1:3]:
            alt_base = alt_role
            for prefix in ["junior", "fresher", "entry level", "entry-level", "graduate", "associate"]:
                if alt_base.lower().startswith(prefix):
                    alt_base = alt_base[len(prefix):].strip()
            add_query(
                text=f"Junior {alt_base or alt_role}",
                role=alt_role,
                used_skills=[],
                level="junior",
            )

        # Strategy 3: Role + Primary Technical Skill
        for skill in top_skills[:2]:
            add_query(
                text=f"{skill} {primary_role}",
                role=primary_role,
                used_skills=[skill],
                level="entry_level",
            )

        # Strategy 4: Role + Primary Skill + Entry-Level Qualifier (e.g. "Python Backend Engineer Junior")
        if top_skills:
            primary_skill = top_skills[0]
            add_query(
                text=f"{primary_skill} {primary_role} Junior",
                role=primary_role,
                used_skills=[primary_skill],
                level="junior",
            )
            add_query(
                text=f"{primary_skill} {primary_role} 0-2 years",
                role=primary_role,
                used_skills=[primary_skill],
                level="0-2 years",
            )

        # Strategy 5: Remote Exploration
        if "remote" in [m.lower() for m in work_modes]:
            add_query(
                text=f"Remote Junior {primary_role}",
                role=primary_role,
                used_skills=[],
                level="junior",
                mode="remote",
            )
            if top_skills:
                add_query(
                    text=f"Remote {top_skills[0]} Developer Junior",
                    role=primary_role,
                    used_skills=[top_skills[0]],
                    level="junior",
                    mode="remote",
                )

        # Strategy 6: Geographic Location Specific Searches
        for loc in locations[:2]:
            add_query(
                text=f"{primary_role} {loc} Fresher",
                role=primary_role,
                used_skills=[],
                level="fresher",
                loc=loc,
            )

        # Strategy 7: Secondary skill combinations if available
        if len(top_skills) >= 2:
            combined = f"{top_skills[0]} {top_skills[1]}"
            add_query(
                text=f"{combined} Junior Developer",
                role=primary_role,
                used_skills=top_skills[:2],
                level="junior",
            )

        logger.info(
            "Generated %d diverse search queries for role '%s' across %d skills",
            len(generated),
            primary_role,
            len(top_skills),
        )
        return generated
