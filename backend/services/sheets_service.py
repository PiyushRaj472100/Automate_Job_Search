import json
import logging
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials
from backend.core.config import get_settings

log = logging.getLogger("sheets")

import re

import base64

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Production Google Cloud Service Account for autonomous Sheets integration
_B64_SA = (
    "ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAiYXV0b21hdGUt"
    "am9iLXNlYXJjaC01MTAwMDIiLAogICJwcml2YXRlX2tleV9pZCI6ICJjNjEzYWE2YzAzY2MwN2M1"
    "ZjdlNTIyOTFmNzBiYzM1ZTVhZjZmNThhIiwKICAicHJpdmF0ZV9rZXkiOiAiLS0tLS1CRUdJTiBQ"
    "UklWQVRFIEtFWS0tLS0tXG5NSUlFdlFJQkFEQU5CZ2txaGtpRzl3MEJBUUVGQUFTQ0JLY3dnZ1Nq"
    "QWdFQUFvSUJBUUM0MHhhSVFZMythTDd5XG56V3NuSVNiOHp6cGg5N2o4MTNOcS93bUxGdUZobUUv"
    "MWRieW9BWURmQnRXWi9MS3JSNE1LUDQ0RDRvN3d4U0dEXG5nRE40Z1pWUzk5djJwSnNxb3h5ekkr"
    "RXlCVkRGdDAvcUh1dFR3L0JsQUEyQnFEaHcrcVRTQ25kbzJGd29sUU1OXG56NkIwNndUbXBFT1ZY"
    "WXB0bVRMTVdEMFp3ZmFVSnFsL3k1U0w4VXJaZUYwY2ZBVVNmUzJ3VXJ0SzZNZVZiUTRoXG5rSyto"
    "QkE0WU9sV3RJK1BkNTZQNWtDaG5jTUNTODgvYlZ0YmNKbzBXMzdlRlVKK3k1RjUxWGJZR2ZnbDhP"
    "QWNyXG5XYU9sTFdIRE9GQnhrTUxYem5tQ0RsblhuYWpDTUZBa0RiMkpTV1ZCK3hpeDRPZEpVQlU0"
    "OWVLUlFUUVNpdGNNXG5Qbk9zUUc1MUFnTUJBQUVDZ2dFQVdhOW9wQ2EzV2VnSEhIZnNrcGpHTysv"
    "czR5UWJtbW1MNHJRdU05V2UrVVk1XG5LcUYrc2NIRkFMUm15eW14bzJaNG9tenpvMVA1UzhGRXdY"
    "Umd4WTJQNGFwUGpSQVVFVzBFSExPQTc4NWZnd213XG5XQ20zeExaMFBQWjVGMTBEUW1PRnZqeUE5"
    "Qm5sSW5Zb2ZMZXZJM3oxckZ1eVJkVVZ1cGdYNjh1M25udWVCUVluXG5LMkZ1NVYzSWRpT0xiQURq"
    "OTY5bjk1RmlsM2xzNGRmdE9RaW9XYUpYYzhsaUZOY0JFekFiY0ZmRktlL3VSemphXG5WZW1GOHZZ"
    "Q0hkaGZqSUo2Uk9tL3ZZa1hRWTgyVFRLRWFvQXd0TVlxL0tKUWVYTzNLRmRON3h4b2QrL0JCNVk1"
    "XG5RM0pGd2Fxb0dkdnVYL2xXMURLUVhwMGhwQWRJSWoySnpBSlVPQXF3OHdLQmdRRDA2cGk0OURj"
    "OUtaQmtCaTZaXG5IeGZ3T2o5UmRrbWpxVlh3YkZ0bEZSL2xGdjZYVGoxR3YrTzlaejQyVXVCQ3ZN"
    "UnJQL2NnSlh1c1JZK2ZveTQ1XG5EdWkxZi9uOGdGc2g3MDhvY2dQeWYybEZSMVBVZHV5TThyN3BS"
    "RXB4T3NuK0hJeFJWR2prVFVBVUkc2ndvOEVTXG51OUpNNzEvTTJmL3FJZlY0a2dlMkpLVFZzd0tC"
    "Z1FEQk1GRG85UXBJMXJQbjBNcnh6ZkcweVI3Q0xQcERRU0tuXG50RVJ0RHVYN21CY3BhYlVKOVho"
    "ajU4bmhyVXFCK1J6Y2tKN01VK2MzUWs1TWpBVWQ5M1RxT0pxVktVUytWdXFLXG5HbGY0OUFiS2Nk"
    "UGlhNTdwckdyd3AvRHZjTEQycmhFZENZamx4dHk3N012UE5DcW1wdFJSa2RGOXhhUVJlalFxXG5j"
    "VGFHY3Zibk53S0JnUUNzNVVRRkpWb3Rrajc5YmFQTnNyYWFmdlFlRk93dFhpaHQvb0NTbmxRU3pL"
    "WFR1SWJuXG5nQ1ZNbXlxKy9NaVdORjVRL0NvQUJwWUU2bUpXcHNMRnd2R2kxNEpwcjA4bWFLTXdB"
    "VFVxSnFueEgwWmRzY3FTXG5RZmRtQXpDdU9IdEtLV3NoS3Y2VlZMZU14R3JHSmdQeHJxZnFhZjN1"
    "Um1NMExONzJTOWlueTd5Vm93S0JnQTEyXG5aMzBFYm5ZSytEaUVWVkFxY05pUFYyUmlyQUg1elFk"
    "d3lYL3NGTnpHaVg2cVRpSm1oOEEyaTl2OUxuOEdOQnV1XG52Rkl5MnA4QU1PS21zMGlXVVFCdGQy"
    "QkRvdlc4cXRWNjVueUR6T0ZZczFKSSs2Yi9DK2kvVzB2a1I0QzVPcG9TXG5hd2JRSjl1MHNiTTd5"
    "R2thb1JzYUZVWTFlcXg1SHArQ2lqRXVXOFJiQW9HQVNkUmpqL2N0OGZLOEpTYTdxRUFPXG5wa0dx"
    "eXJNQ243amhEUlZxQ2NFVlhBdDY1QzZaZzJ0RjlHYVU2UzBBOWVwMUVQZ285OG9nemNTL3RDTkkr"
    "S1hBXG5MY3p6elZ5SnZmR0g3d3FaYVN3cUtCNVJ6ZWdRejlXYjZ6dllsZUpBZS8wS0Uwai9HbzlC"
    "ZlJncElOcmsxU2NvXG5ycU5uc3pKRnJMMVhJU3ZzanhENWovOD1cbi0tLS0tRU5EIFBSSVZBVEUg"
    "S0VZLS0tLS1cbiIsCiAgImNsaWVudF9lbWFpbCI6ICJqb2ItaW50ZWxsaWdlbmNlLXNoZWV0c0Bh"
    "dXRvbWF0ZS1qb2Itc2VhcmNoLTUxMDAwMi5pYW0uZ3NlcnZpY2VhY2NvdW50LmNvbSIsCiAgImNs"
    "aWVudF9pZCI6ICIxMTIwMTE1MTczODY1Nzc3OTEwOTIiLAogICJhdXRoX3VyaSI6ICJodHRwczov"
    "L2FjY291bnRzLmdvb2dsZS5jb20vby9vYXV0aDIvYXV0aCIsCiAgInRva2VuX3VyaSI6ICJodHRw"
    "czovL29hdXRoMi5nb29nbGVhcGlzLmNvbS90b2tlbiIsCiAgImF1dGhfcHJvdmlkZXJfeDUwOV9j"
    "ZXJ0X3VybCI6ICJodHRwczovL3d3dy5nb29nbGVhcGlzLmNvbS9vYXV0aDIvdjEvY2VydHMiLAog"
    "ICJjbGllbnRfeDUwOV9jZXJ0X3VybCI6ICJodHRwczovL3d3dy5nb29nbGVhcGlzLmNvbS9yb2Jv"
    "dC92MS9tZXRhZGF0YS94NTA5L2pvYi1pbnRlbGxpZ2VuY2Utc2hlZXRzJTQwYXV0b21hdGUtam9i"
    "LXNlYXJjaC01MTAwMDIuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLAogICJ1bml2ZXJzZV9kb21h"
    "aW4iOiAiZ29vZ2xlYXBpcy5jb20iCn0K"
)


def _get_default_sa_info() -> dict:
    try:
        return json.loads(base64.b64decode(_B64_SA).decode("utf-8"))
    except Exception:
        return {}


def get_gspread_client() -> gspread.Client | None:
    settings = get_settings()
    creds = None
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        try:
            creds = Credentials.from_service_account_file(
                settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        except Exception as e:
            log.warning("Could not load service account file, attempting fallback: %s", e)
    elif settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            data = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            creds = Credentials.from_service_account_info(data, scopes=SCOPES)
        except Exception as e:
            log.warning("Could not parse service account JSON, attempting fallback: %s", e)

    # Built-in fallback ensuring zero deployment breakage on Render/Cloud
    if not creds:
        try:
            creds = Credentials.from_service_account_info(_get_default_sa_info(), scopes=SCOPES)
        except Exception as e:
            log.error("Failed to initialize default service account: %s", e)
            return None

    return gspread.authorize(creds)


def get_service_account_email() -> str:
    settings = get_settings()
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        try:
            with open(settings.GOOGLE_SERVICE_ACCOUNT_FILE, "r") as f:
                data = json.load(f)
                if data.get("client_email"):
                    return data["client_email"]
        except Exception:
            pass
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            data = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            if data.get("client_email"):
                return data["client_email"]
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

    sh = None
    if target_url:
        # Extract spreadsheet key if full URL given
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", target_url)
        sheet_key = m.group(1) if m else target_url.strip()
        try:
            sh = client.open_by_key(sheet_key)
        except Exception:
            try:
                sh = client.open_by_url(target_url)
            except Exception:
                pass

    # If open failed or no URL provided, check if user has shared any spreadsheet with this account
    if not sh:
        try:
            files = client.list_spreadsheet_files()
            if files:
                sh = client.open_by_key(files[0]["id"])
        except Exception:
            pass

    if not sh:
        raise ValueError(
            f"Could not access your Google Sheet. Please verify:\n"
            f"1. You opened your Google Sheet (e.g. sheets.new)\n"
            f"2. Clicked 'Share' (top-right)\n"
            f"3. Added '{sa_email}' as 'Editor'\n"
            f"4. Clicked 'Send' / 'Share' to grant permission."
        )

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


from datetime import datetime, timezone, timedelta


def prune_sheet_jobs(spreadsheet_id: str, max_days: int = 4) -> int:
    """Removes jobs from the 'Discovered Jobs' tab that are older than max_days."""
    client = get_gspread_client()
    if not client:
        return 0

    try:
        sh = client.open_by_key(spreadsheet_id)
        ws = sh.worksheet("Discovered Jobs")
        all_vals = ws.get_all_values()
        if len(all_vals) <= 1:
            return 0

        header = all_vals[0]
        rows = all_vals[1:]
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_days)

        kept_rows = []
        pruned_count = 0

        for r in rows:
            discovered_at_str = r[9] if len(r) > 9 else ""
            is_expired = False
            if discovered_at_str:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        clean_str = discovered_at_str.split(".")[0].replace("Z", "")
                        dt = datetime.strptime(clean_str, fmt).replace(tzinfo=timezone.utc)
                        if dt < cutoff:
                            is_expired = True
                        break
                    except Exception:
                        pass
            if is_expired:
                pruned_count += 1
            else:
                kept_rows.append(r)

        if pruned_count > 0:
            ws.clear()
            ws.append_rows([header] + kept_rows)
            log.info("Pruned %d expired rows from sheet %s", pruned_count, spreadsheet_id)

        return pruned_count
    except Exception as e:
        log.warning("Could not prune sheet %s: %s", spreadsheet_id, e)
        return 0


def sync_jobs_to_sheet(spreadsheet_id: str, jobs: list[dict]) -> int:
    client = get_gspread_client()
    if not client:
        raise ValueError("Google Service Account credentials not configured.")

    # 1. First auto-prune any jobs older than 4 days
    prune_sheet_jobs(spreadsheet_id, max_days=4)

    sh = client.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet("Discovered Jobs")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Discovered Jobs", rows=1000, cols=10)
        ws.append_row([
            "Company Name", "Role / Title", "Application Link", "Work Mode",
            "Location", "Approx Salary", "Bangalore Recruiter & Referral LinkedIn Links", "Status",
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

