"""Constants, tab names, and header specifications for Google Sheets integration."""

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

# Headers for Dashboard sheet
DASHBOARD_HEADERS = [
    "Metric",
    "Value",
    "Description",
    "Last Updated",
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

TAB_HEADERS_MAP = {
    TAB_DASHBOARD: DASHBOARD_HEADERS,
    TAB_JOBS: JOBS_HEADERS,
    TAB_RECRUITERS: RECRUITERS_HEADERS,
    TAB_APPLICATIONS: APPLICATIONS_HEADERS,
    TAB_SYSTEM_STATUS: SYSTEM_STATUS_HEADERS,
}
