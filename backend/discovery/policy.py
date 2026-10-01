"""Legal compliance, access restrictions, and rate limit policies across job source categories."""

from backend.discovery.models import SourcePolicy, SourceType

SOURCE_POLICIES: dict[str, SourcePolicy] = {
    # 1. Arbeitnow (Active Live Provider)
    "arbeitnow": SourcePolicy(
        source_name="arbeitnow",
        source_type=SourceType.OFFICIAL_API,
        base_url="https://www.arbeitnow.com/api/job-board-api",
        official_api_available=True,
        feed_available=True,
        public_page_available=True,
        robots_restrictions="Permitted via public job-board API",
        rate_limit_per_minute=30,
        authentication_required=False,
        permitted_access_method="Official REST API (GET /api/job-board-api)",
        notes="Completely free, authorized public technical job board API.",
    ),
    # 2. Remotive (Active Live Provider)
    "remotive": SourcePolicy(
        source_name="remotive",
        source_type=SourceType.OFFICIAL_API,
        base_url="https://remotive.com/api/remote-jobs",
        official_api_available=True,
        feed_available=True,
        public_page_available=True,
        robots_restrictions="Permitted via public developer API",
        rate_limit_per_minute=20,
        authentication_required=False,
        permitted_access_method="Official REST API (GET /api/remote-jobs)",
        notes="Official public API for remote technical job openings.",
    ),
    # 3. Greenhouse Official Company Boards (Active Provider)
    "greenhouse": SourcePolicy(
        source_name="greenhouse",
        source_type=SourceType.COMPANY_CAREER_PAGE,
        base_url="https://boards-api.greenhouse.io/v1/boards",
        official_api_available=True,
        feed_available=True,
        public_page_available=True,
        robots_restrictions="Permitted via public board API",
        rate_limit_per_minute=40,
        authentication_required=False,
        permitted_access_method="Public Company Career Board API (/v1/boards/{company}/jobs)",
        notes="Official direct company ATS job feeds.",
    ),
    # 4. Lever Official Company Career Postings (Active Provider)
    "lever": SourcePolicy(
        source_name="lever",
        source_type=SourceType.COMPANY_CAREER_PAGE,
        base_url="https://api.lever.co/v0/postings",
        official_api_available=True,
        feed_available=True,
        public_page_available=True,
        robots_restrictions="Permitted via public postings API",
        rate_limit_per_minute=40,
        authentication_required=False,
        permitted_access_method="Public Company Career Postings API (/v0/postings/{company})",
        notes="Official direct company Lever ATS job feeds.",
    ),
    # 4. LinkedIn Jobs (Policy Specification)
    "linkedin": SourcePolicy(
        source_name="linkedin",
        source_type=SourceType.OFFICIAL_API,
        base_url="https://api.linkedin.com/v2",
        official_api_available=True,
        feed_available=False,
        public_page_available=False,
        robots_restrictions="Strict anti-bot, disallows automated scraping in robots.txt",
        rate_limit_per_minute=10,
        authentication_required=True,
        permitted_access_method="LinkedIn Talent Solutions Partner API or Search Engine indexing discovery",
        notes="Never scrape HTML directly; requires official partner OAuth access.",
    ),
    # 5. Indeed (Policy Specification)
    "indeed": SourcePolicy(
        source_name="indeed",
        source_type=SourceType.OFFICIAL_API,
        base_url="https://api.indeed.com",
        official_api_available=True,
        feed_available=False,
        public_page_available=False,
        robots_restrictions="Strict Cloudflare protections, CAPTCHA, and robots.txt disallow",
        rate_limit_per_minute=10,
        authentication_required=True,
        permitted_access_method="Indeed Publisher API / Partner Feed API only",
        notes="Direct HTML scraping forbidden by TOS; requires API key.",
    ),
    # 6. Naukri (Policy Specification)
    "naukri": SourcePolicy(
        source_name="naukri",
        source_type=SourceType.OFFICIAL_API,
        base_url="https://www.naukri.com",
        official_api_available=False,
        feed_available=False,
        public_page_available=False,
        robots_restrictions="Strict bot mitigation, rate-limiting, and authentication requirements",
        rate_limit_per_minute=5,
        authentication_required=True,
        permitted_access_method="Enterprise Recruiter API or Google Custom Search index discovery",
        notes="Never bypass anti-bot systems.",
    ),
    # 7. Wellfound / AngelList (Policy Specification)
    "wellfound": SourcePolicy(
        source_name="wellfound",
        source_type=SourceType.PUBLIC_FEED,
        base_url="https://wellfound.com",
        official_api_available=False,
        feed_available=True,
        public_page_available=True,
        robots_restrictions="Respect rate limits and robots.txt",
        rate_limit_per_minute=15,
        authentication_required=False,
        permitted_access_method="Public RSS / XML Feeds where available",
        notes="Startup and technical early-stage openings.",
    ),
    # 8. Internshala (Policy Specification)
    "internshala": SourcePolicy(
        source_name="internshala",
        source_type=SourceType.PUBLIC_PAGE,
        base_url="https://internshala.com",
        official_api_available=False,
        feed_available=False,
        public_page_available=True,
        robots_restrictions="Follow robots.txt; avoid automated form actions",
        rate_limit_per_minute=10,
        authentication_required=False,
        permitted_access_method="Search Engine indexing or public directory browsing",
        notes="Entry-level and fresher internship discovery.",
    ),
}


def get_source_policy(source_name: str) -> SourcePolicy:
    """Retrieve compliance and access policy for a specific source."""
    return SOURCE_POLICIES.get(
        source_name.lower(),
        SourcePolicy(
            source_name=source_name,
            source_type=SourceType.PUBLIC_PAGE,
            base_url="https://example.com",
            notes="Default fallback policy.",
        ),
    )
