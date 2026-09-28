"""Constants, tab names, and header specifications for Google Sheets integration."""

from enum import StrEnum

# Sheet / Worksheet Tab Names
TAB_DASHBOARD = "Dashboard"
TAB_JOBS = "Jobs"
TAB_RECRUITERS = "Recruiters"
TAB_APPLICATIONS = "Applications"
TAB_SYSTEM_STATUS = "System Status"

ALL_TABS = [
    TAB_DASHBOARD,
    TAB_JOBS,
    TAB_RECRUITERS,
    TAB_APPLICATIONS,
    TAB_SYSTEM_STATUS,
]


class ApplicationStatus(StrEnum):
    """Job application lifecycle statuses supported in the operational spreadsheet."""

    NEW = "NEW"
    REVIEWED = "REVIEWED"
    SAVED = "SAVED"
    APPLIED = "APPLIED"
    ASSESSMENT = "ASSESSMENT"
    INTERVIEW = "INTERVIEW"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    OFFER = "OFFER"
    CLOSED = "CLOSED"


APPLICATION_STATUS_VALUES = [s.value for s in ApplicationStatus]

# Exact headers required by the engineering contract for Jobs sheet
JOBS_HEADERS = [
    "Date Found",
    "Job Title",
    "Company",
    "Experience",
    "Location",
    "Work Mode",
    "Job Link",
    "Direct Application Link",
    "Source",
    "Job ID",
    "First Seen",
    "Last Verified",
    "Verification Status",
    "Source Quality",
    "Match Level",
    "Why It Matches",
    "Required Skills",
    "Skills You Have",
    "Missing / Improve",
    "Resume",
    "Recruiter 1",
    "Recruiter 2",
    "Recruiter 3",
    "Application Status",
    "Applied Date",
    "Follow-up Date",
    "Notes",
]

# Headers for Dashboard sheet (KPI summary & morning action center)
DASHBOARD_HEADERS = [
    "Metric",
    "Value",
    "Description",
    "Last Updated",
]

DASHBOARD_ACTION_HEADERS = [
    "Priority",
    "Job Title",
    "Company",
    "Match Level",
    "Direct Application Link",
    "Recommended Resume",
    "Missing / Improve",
    "Recruiter Profiles",
    "Status",
    "Verification Status",
]

# Headers for Recruiters sheet
RECRUITERS_HEADERS = [
    "Recruiter Name",
    "Title",
    "Company",
    "LinkedIn URL",
    "Email",
    "Verified",
    "Verification Source",
    "Associated Jobs",
    "Notes",
]

# Headers for Applications sheet
APPLICATIONS_HEADERS = [
    "Application ID",
    "Job Title",
    "Company",
    "Direct Application Link",
    "Status",
    "Applied Date",
    "Follow-up Date",
    "Resume",
    "Notes",
]

# Headers for System Status sheet
SYSTEM_STATUS_HEADERS = [
    "Component",
    "Status",
    "Last Verified",
    "Details",
    "Audit Log",
]

SYSTEM_STATUS_REQUIRED_METRICS = [
    "Pipeline status",
    "Last discovery",
    "Last verification",
    "Jobs discovered",
    "Jobs verified",
    "Strong matches",
    "Relevant matches",
    "Closed/rejected",
    "Source errors",
]

TAB_HEADERS_MAP = {
    TAB_DASHBOARD: DASHBOARD_HEADERS,
    TAB_JOBS: JOBS_HEADERS,
    TAB_RECRUITERS: RECRUITERS_HEADERS,
    TAB_APPLICATIONS: APPLICATIONS_HEADERS,
    TAB_SYSTEM_STATUS: SYSTEM_STATUS_HEADERS,
}
