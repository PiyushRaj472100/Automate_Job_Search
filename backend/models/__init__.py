"""Domain models registry for Personal Job Intelligence Platform."""

from backend.db.base import Base
from backend.models.application import Application
from backend.models.company import Company
from backend.models.job import Job, JobMatch, JobSource
from backend.models.person import JobPerson, Person
from backend.models.resume import Resume, ResumeProfile, ResumeSkill, Skill
from backend.models.search_run import SearchRun
from backend.models.verification import VerificationEvent

__all__ = [
    "Application",
    "Base",
    "Company",
    "Job",
    "JobMatch",
    "JobPerson",
    "JobSource",
    "Person",
    "Resume",
    "ResumeProfile",
    "ResumeSkill",
    "SearchRun",
    "Skill",
    "VerificationEvent",
]
