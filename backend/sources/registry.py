from backend.sources.linkedin_india import LinkedInIndiaSource
from backend.sources.hasjob import HasjobSource
from backend.sources.arbeitnow import ArbeitnowSource
from backend.sources.jobicy import JobicySource
from backend.sources.remotive import RemotiveSource

# Priority order: LinkedIn India first, Hasjob India, then global remote
SOURCES = {
    s.name: s for s in [
        LinkedInIndiaSource(),
        HasjobSource(),
        JobicySource(),
        RemotiveSource(),
        ArbeitnowSource(),
    ]
}
