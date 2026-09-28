from backend.sources.linkedin_india import LinkedInIndiaSource
from backend.sources.instahyre import InstahyreSource
from backend.sources.hasjob import HasjobSource
from backend.sources.arbeitnow import ArbeitnowSource
from backend.sources.jobicy import JobicySource
from backend.sources.remotive import RemotiveSource

# Priority order: LinkedIn India first, Instahyre, Hasjob India, then global remote
SOURCES = {
    s.name: s for s in [
        LinkedInIndiaSource(),
        InstahyreSource(),
        HasjobSource(),
        JobicySource(),
        RemotiveSource(),
        ArbeitnowSource(),
    ]
}
