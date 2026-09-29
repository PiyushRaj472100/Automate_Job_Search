"""
Sources registry — 20+ verified job source adapters, priority-ordered.

TIER 1  — Official company career portals (Greenhouse, Lever, Ashby, Hirist) — 80+ companies
TIER 2  — Top Indian tech/startup platforms (LinkedIn, Instahyre, Cutshort, Wellfound)
TIER 3  — Major Indian job boards (Naukri RSS, Foundit, Internshala)
TIER 4  — Indian fresher boards (Shine, TimesJobs, LetsIntern, YesIntern, FresHire)
TIER 5  — Specialized AI/ML (Remotive AI + Jobicy AI + HN Who is Hiring)
TIER 6  — Remote-first boards (RemoteOK, Working Nomads, Remotive, Jobicy, Arbeitnow)
TIER 7  — Startup/YC communities (Startup.jobs, YC Jobs, Hasjob, WebFresher)
"""
from backend.sources.company_portals import CompanyPortalsSource
from backend.sources.linkedin_india import LinkedInIndiaSource
from backend.sources.instahyre import InstahyreSource
from backend.sources.cutshort import CutshortSource
from backend.sources.wellfound import WellfoundSource
from backend.sources.naukri import NaukriSource
from backend.sources.foundit import FounditSource
from backend.sources.internshala import InternshalaSource
from backend.sources.india_boards import IndiaBoardsSource
from backend.sources.ai_jobs import AIJobsSource
from backend.sources.feeds import RemoteOKSource, StartupJobsSource, WorkingNomadsSource, YCJobsSource
from backend.sources.remotive import RemotiveSource
from backend.sources.jobicy import JobicySource
from backend.sources.arbeitnow import ArbeitnowSource
from backend.sources.hasjob import HasjobSource
from backend.sources.web_fresher import WebFresherSource

SOURCES = {
    s.name: s for s in [
        # TIER 1: Official company career pages — highest quality signal
        CompanyPortalsSource(),
        # TIER 2: Top Indian tech & startup job platforms
        LinkedInIndiaSource(),
        InstahyreSource(),
        CutshortSource(),
        WellfoundSource(),
        # TIER 3: Major Indian job boards
        NaukriSource(),
        FounditSource(),
        InternshalaSource(),
        # TIER 4: Fresher-specific Indian boards
        IndiaBoardsSource(),
        # TIER 5: AI/ML specialized aggregator
        AIJobsSource(),
        # TIER 6: Remote-first boards (India-eligible)
        RemoteOKSource(),
        WorkingNomadsSource(),
        RemotiveSource(),
        JobicySource(),
        ArbeitnowSource(),
        # TIER 7: Community feeds & startup aggregators
        StartupJobsSource(),
        YCJobsSource(),
        HasjobSource(),
        WebFresherSource(),
    ]
}
