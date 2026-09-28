from backend.sources.linkedin_india import LinkedInIndiaSource
from backend.sources.web_fresher import WebFresherSource
from backend.sources.hasjob import HasjobSource
from backend.sources.arbeitnow import ArbeitnowSource
from backend.sources.jobicy import JobicySource
from backend.sources.remotive import RemotiveSource

# Priority order: LinkedIn India (Verified JD), Web Fresher (Wellfound/Indeed/Internshala), Hasjob India, then global remote
SOURCES = {
    s.name: s for s in [
        LinkedInIndiaSource(),
        WebFresherSource(),
        HasjobSource(),
        JobicySource(),
        RemotiveSource(),
        ArbeitnowSource(),
    ]
}
