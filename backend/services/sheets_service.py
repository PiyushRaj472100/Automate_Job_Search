import json
import logging
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials
from backend.core.config import get_settings

log = logging.getLogger("sheets")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client() -> gspread.Client | None:
    settings = get_settings()
    creds = None
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        try:
            creds = Credentials.from_service_account_file(
                settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        except Exception as e:
            log.error("Failed to load service account file: %s", e)
            return None
    elif settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            data = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            creds = Credentials.from_service_account_info(data, scopes=SCOPES)
        except Exception as e:
            log.error("Failed to parse service account JSON: %s", e)
            return None

    if not creds:
        return None

    return gspread.authorize(creds)


def get_service_account_email() -> str:
    settings = get_settings()
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        try:
            with open(settings.GOOGLE_SERVICE_ACCOUNT_FILE, "r") as f:
                data = json.load(f)
                return data.get("client_email", "")
        except Exception:
            pass
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            data = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            return data.get("client_email", "")
        except Exception:
            pass
    return "job-intelligence-sheets@automate-job-search-510002.iam.gserviceaccount.com"


def create_or_get_spreadsheet(resume_id: str, filename: str, sheet_url: str | None = None) -> dict:
    client = get_gspread_client()
    if not client:
        raise ValueError("Google Service Account credentials not configured.")

    settings = get_settings()
    sa_email = get_service_account_email()
    target_url = (sheet_url or settings.GOOGLE_SHEET_URL or "").strip()

    if target_url:
        try:
            sh = client.open_by_url(target_url)
        except Exception as e:
            raise ValueError(
                f"Could not open Google Sheet. Please make sure you clicked 'Share' on your Google Sheet, "
                f"pasted '{sa_email}' into 'Add people and groups', chose 'Editor', and clicked Share. (Details: {e})"
            )
    else:
        title = f"PJIP - Job Tracker - {filename} ({resume_id[:8]})"
        try:
            sh = client.create(title)
        except Exception as e:
            if "quota" in str(e).lower() or "403" in str(e):
                raise ValueError(
                    f"Google Service Accounts have 0MB storage quota and cannot own new files. "
                    f"Please create an empty Google Sheet in your personal Google Drive (e.g. sheets.new), "
                    f"share it with '{sa_email}' as Editor, and set GOOGLE_SHEET_URL in your .env file."
                )
            raise

    # Initialize tabs: Summary, Discovered Jobs, Applications
    try:
        ws_summary = sh.worksheet("Summary")
    except gspread.WorksheetNotFound:
        ws_summary = sh.sheet1
        ws_summary.update_title("Summary")

    if not ws_summary.get_all_values():
        ws_summary.append_rows([
            ["Personal Job Intelligence Platform - Job Search Tracker"],
            ["Resume File", filename],
            ["Resume ID", resume_id],
            ["Created At", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")],
            [],
            ["Metric", "Value"],
            ["Total Discovered Jobs", "=COUNTA('Discovered Jobs'!A2:A)"],
            ["Applications", "=COUNTA('Applications'!A2:A)"],
        ])

    try:
        sh.worksheet("Discovered Jobs")
    except gspread.WorksheetNotFound:
        ws_jobs = sh.add_worksheet(title="Discovered Jobs", rows=1000, cols=10)
        ws_jobs.append_row([
            "Company Name", "Role / Title", "Application Link", "Work Mode",
            "Location", "Approx Salary", "LinkedIn Referral Links", "Status",
            "Source", "Discovered At"
        ])

    try:
        sh.worksheet("Applications")
    except gspread.WorksheetNotFound:
        ws_apps = sh.add_worksheet(title="Applications", rows=500, cols=8)
        ws_apps.append_row([
            "Company", "Role", "Job Link", "Status", "Applied Date", "Notes"
        ])

    if settings.GOOGLE_SHEETS_SHARE_USER_EMAIL and not settings.GOOGLE_SHEET_URL:
        try:
            sh.share(settings.GOOGLE_SHEETS_SHARE_USER_EMAIL, perm_type="user", role="writer", notify=True)
            log.info("Shared sheet %s with %s", sh.id, settings.GOOGLE_SHEETS_SHARE_USER_EMAIL)
        except Exception as e:
            log.warning("Could not share sheet with %s: %s", settings.GOOGLE_SHEETS_SHARE_USER_EMAIL, e)

    return {
        "spreadsheet_id": sh.id,
        "spreadsheet_url": sh.url,
    }


def sync_jobs_to_sheet(spreadsheet_id: str, jobs: list[dict]) -> int:
    client = get_gspread_client()
    if not client:
        raise ValueError("Google Service Account credentials not configured.")

    sh = client.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet("Discovered Jobs")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Discovered Jobs", rows=1000, cols=10)
        ws.append_row([
            "Company Name", "Role / Title", "Application Link", "Work Mode",
            "Location", "Approx Salary", "LinkedIn Referral Links", "Status",
            "Source", "Discovered At"
        ])

    # Deduplicate against already existing URLs in column C
    existing_records = ws.col_values(3)  # Application Link column
    existing_urls = set(existing_records[1:]) if len(existing_records) > 1 else set()

    rows = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for j in jobs:
        link = j.get("job_url", "") or j.get("application_url", "")
        if link and link in existing_urls:
            continue
        existing_urls.add(link)

        # Generate referral search URLs
        comp = j.get("company", "").strip()
        comp_encoded = comp.replace(" ", "%20")
        referrals = j.get("referral_links") or (
            f"1. Bangalore Recruiter: https://www.linkedin.com/search/results/people/?keywords=technical%20recruiter%20at%20{comp_encoded}%20Bengaluru\n"
            f"2. Eng Manager: https://www.linkedin.com/search/results/people/?keywords=engineering%20manager%20at%20{comp_encoded}%20Bengaluru\n"
            f"3. Talent Acquisition: https://www.linkedin.com/search/results/people/?keywords=talent%20acquisition%20{comp_encoded}%20India"
        ) if comp else "N/A"

        salary = j.get("salary") or (
            f"{j.get('min_salary')} - {j.get('max_salary')}"
            if j.get("min_salary") and j.get("max_salary")
            else "Not specified"
        )

        rows.append([
            comp,
            j.get("title", ""),
            link,
            j.get("work_mode", "Not specified"),
            j.get("location", "Not specified"),
            salary,
            referrals,
            j.get("status", "NEW"),
            j.get("source", "web"),
            now_str,
        ])

    if rows:
        ws.append_rows(rows)

    return len(rows)

