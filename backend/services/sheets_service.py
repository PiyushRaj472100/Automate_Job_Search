import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import re
import gspread
from google.oauth2.service_account import Credentials
from backend.core.config import get_settings

log = logging.getLogger("sheets")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _parse_service_account_dict(raw: str) -> dict:
    """Parses a service account JSON string, supporting raw JSON or base64."""
    if not raw or not raw.strip():
        raise ValueError("Service account JSON string is empty")

    s = raw.strip()
    # Strip wrapping single/double quotes if an env var was quoted
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()

    # If it does not start with '{', it might be base64-encoded
    if not s.startswith("{"):
        try:
            decoded = base64.b64decode(s).decode("utf-8").strip()
            if decoded.startswith("{"):
                s = decoded
        except Exception:
            pass

    try:
        data = json.loads(s)
    except Exception as e:
        raise ValueError(f"Failed to parse service account JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("Service account JSON must be a JSON object")

    # In environment variables, newlines in private_key often get escaped to literal '\\n'
    if "private_key" in data and isinstance(data["private_key"], str):
        if "\\n" in data["private_key"] and "\n" not in data["private_key"]:
            data["private_key"] = data["private_key"].replace("\\n", "\n")

    missing = [k for k in ("client_email", "token_uri", "private_key") if k not in data]
    if missing:
        raise ValueError(f"Service account info missing required fields: {', '.join(missing)}")

    return data


def get_service_account_info() -> tuple[dict | None, str | None]:
    """
    Retrieves the service account info dict from:
    1. GOOGLE_SERVICE_ACCOUNT_JSON env var (raw or base64)
    2. GOOGLE_SERVICE_ACCOUNT_FILE env var (if file exists)
    3. Standard file locations:
       - /etc/secrets/service_account.json (Render Secret Files default)
       - backend/credentials/service_account.json
       - credentials/service_account.json
    Returns (info_dict, error_message).
    """
    settings = get_settings()
    last_err: str | None = None

    # 1. Check GOOGLE_SERVICE_ACCOUNT_JSON environment variable
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON and settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip():
        try:
            data = _parse_service_account_dict(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            return data, None
        except Exception as e:
            last_err = f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON: {e}"
            log.warning("%s", last_err)

    # 2. Check GOOGLE_SERVICE_ACCOUNT_FILE environment variable
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE and settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip():
        filepath = Path(settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip())
        candidate_paths = [filepath]
        if not filepath.is_absolute():
            candidate_paths.append(Path.cwd() / filepath)
            candidate_paths.append(Path(__file__).resolve().parent.parent.parent / filepath)

        found = False
        for p in candidate_paths:
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = _parse_service_account_dict(f.read())
                    return data, None
                except Exception as e:
                    last_err = f"Failed to load service account file '{p}': {e}"
                    log.warning("%s", last_err)
                found = True
                break
        if not found:
            log.warning("Service account file not found at path: %s", settings.GOOGLE_SERVICE_ACCOUNT_FILE)

    # 3. Check well-known default locations
    default_candidates = [
        Path("/etc/secrets/service_account.json"),  # Standard Render Secret File path
        Path(__file__).resolve().parent.parent / "credentials" / "service_account.json",
        Path.cwd() / "backend" / "credentials" / "service_account.json",
        Path.cwd() / "credentials" / "service_account.json",
    ]
    for p in default_candidates:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = _parse_service_account_dict(f.read())
                log.info("Loaded service account credentials from %s", p)
                return data, None
            except Exception as e:
                log.warning("Found candidate service account file at %s but failed to parse: %s", p, e)

    if not last_err:
        last_err = (
            "Google Service Account credentials are not configured. "
            "Please configure the GOOGLE_SERVICE_ACCOUNT_JSON environment variable (with raw or base64-encoded JSON) "
            "or set GOOGLE_SERVICE_ACCOUNT_FILE (e.g. /etc/secrets/service_account.json on Render)."
        )
    return None, last_err


def get_gspread_client() -> gspread.Client | None:
    info, err = get_service_account_info()
    if not info:
        if err:
            log.warning("Cannot initialize Google Sheets client: %s", err)
        return None
    try:
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        log.error("Failed to authorize Google Sheets client: %s", e)
        return None


def get_service_account_email() -> str:
    info, _ = get_service_account_info()
    if info and "client_email" in info:
        return info["client_email"]
    return ""


RESUME_HEADERS = [
    "Company Name",
    "Role / Title",
    "Apply Link",
    "Location",
    "Work Mode",
    "Source Platform",
    "Job Description (Full JD)",
    "JD Match Summary",
    "Tech My Resume Had",
    "Tech Skills Not Had",
    "Applied Status",
    "Recruiter LinkedIn Links (2-3 per Company)",
    "Discovered At",
]


def create_or_get_spreadsheet(
    resume_id: str,
    filename: str,
    sheet_url: str | None = None,
    tab_name: str = "Resume 1",
) -> dict:
    info, err = get_service_account_info()
    if not info:
        raise ValueError(err or "Google Service Account credentials not configured.")

    client = get_gspread_client()
    if not client:
        raise ValueError(
            "Failed to initialize Google Sheets client with service account credentials. "
            "Please verify credentials and ensure Google Sheets & Drive APIs are enabled."
        )

    settings = get_settings()
    sa_email = get_service_account_email()
    target_url = (sheet_url or settings.GOOGLE_SHEET_URL or "").strip()

    sh = None
    if target_url:
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", target_url)
        sheet_key = m.group(1) if m else target_url.strip()
        try:
            sh = client.open_by_key(sheet_key)
        except Exception as e:
            log.warning("Could not open sheet by key '%s': %s", sheet_key, e)
            try:
                sh = client.open_by_url(target_url)
            except Exception as e_url:
                log.warning("Could not open sheet by URL '%s': %s", target_url, e_url)

    if not sh:
        try:
            files = client.list_spreadsheet_files()
            if files:
                sh = client.open_by_key(files[0]["id"])
        except Exception as e:
            log.warning("Could not list shared spreadsheet files: %s", e)

    if not sh:
        email_hint = f"'{sa_email}'" if sa_email else "the service account email"
        raise ValueError(
            f"Could not access your Google Sheet ({target_url or 'unspecified'}). Please verify:\n"
            f"1. You opened your Google Sheet (e.g. sheets.new)\n"
            f"2. Clicked 'Share' (top-right)\n"
            f"3. Added {email_hint} as 'Editor'\n"
            f"4. Clicked 'Send' / 'Share' to grant permission."
        )

    # Ensure the requested resume tab (e.g. "Resume 1", "Resume 2") exists
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        # If default Sheet1 exists and is empty or single tab, reuse it
        existing_sheets = sh.worksheets()
        if len(existing_sheets) == 1 and existing_sheets[0].title in ["Sheet1", "Sheet 1"]:
            ws = existing_sheets[0]
            ws.update_title(tab_name)
        else:
            ws = sh.add_worksheet(title=tab_name, rows=1000, cols=15)
        ws.append_row(RESUME_HEADERS)

    # If first row doesn't have headers, write them
    row1 = ws.row_values(1)
    if not row1:
        ws.append_row(RESUME_HEADERS)

    # Clean up older boilerplate tabs if present
    for old_title in ["Summary", "Discovered Jobs", "Applications"]:
        try:
            old_ws = sh.worksheet(old_title)
            if len(sh.worksheets()) > 1:
                sh.del_worksheet(old_ws)
        except Exception:
            pass

    return {
        "spreadsheet_id": sh.id,
        "spreadsheet_url": sh.url,
    }


from datetime import datetime, timezone, timedelta


def prune_sheet_jobs(spreadsheet_id: str, tab_name: str | None = None, max_days: int = 2) -> int:
    """Removes jobs from the resume tab(s) that are older than max_days (default 2 days)."""
    client = get_gspread_client()
    if not client:
        return 0

    try:
        sh = client.open_by_key(spreadsheet_id)
        if tab_name:
            target_worksheets = [sh.worksheet(tab_name)]
        else:
            target_worksheets = [ws for ws in sh.worksheets() if ws.title.startswith("Resume ")]
            if not target_worksheets:
                target_worksheets = sh.worksheets()
    except Exception as e:
        log.warning("Could not access spreadsheet %s for pruning: %s", spreadsheet_id, e)
        return 0

    total_pruned = 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_days)

    for ws in target_worksheets:
        try:
            all_vals = ws.get_all_values()
            if len(all_vals) <= 1:
                continue

            header = all_vals[0]
            rows = all_vals[1:]

            date_col_idx = len(header) - 1  # default to last column (Discovered At)
            for idx, col_name in enumerate(header):
                if "discovered" in col_name.lower():
                    date_col_idx = idx
                    break

            kept_rows = []
            pruned_count = 0

            for r in rows:
                discovered_at_str = r[date_col_idx] if len(r) > date_col_idx else ""
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
                log.info("Pruned %d expired (>%d days) rows from tab '%s' in sheet %s", pruned_count, max_days, ws.title, spreadsheet_id)
                total_pruned += pruned_count
        except Exception as e:
            log.warning("Could not prune tab '%s' in sheet %s: %s", ws.title, spreadsheet_id, e)

    return total_pruned


def sync_jobs_to_sheet(
    spreadsheet_id: str,
    jobs: list[dict],
    tab_name: str = "Resume 1",
    max_days: int = 2,
) -> int:
    client = get_gspread_client()
    if not client:
        raise ValueError("Google Service Account credentials not configured.")

    # 1. First auto-prune jobs older than 2 days in this tab
    prune_sheet_jobs(spreadsheet_id, tab_name=tab_name, max_days=max_days)

    sh = client.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=15)
        ws.append_row(RESUME_HEADERS)

    # Deduplicate against existing URLs in column C (Apply Link)
    existing_records = ws.col_values(3)
    existing_urls = set(existing_records[1:]) if len(existing_records) > 1 else set()

    rows = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    for j in jobs:
        link = (j.get("job_url", "") or j.get("application_url", "")).strip()
        if link and link in existing_urls:
            continue
        if link:
            existing_urls.add(link)

        company = j.get("company", "").strip()
        title = j.get("title", "").strip()
        location = j.get("location", "Bengaluru, India").strip()
        work_mode = j.get("work_mode", "Work from Office").strip()

        jd = (j.get("jd", "") or j.get("description", "")).strip()
        if len(jd) > 1000:
            jd = jd[:997] + "..."
        if not jd:
            jd = f"Entry-level {title} role at {company}"

        # JD match summary (brief 1-liner)
        jd_match = j.get("jd_match_summary", "")
        if not jd_match:
            jd_match = f"Found via {j.get('source', 'job board')} — {title} at {company}"

        source_platform = j.get("source", "").replace("_", " ").title() or "Job Board"
        tech_had = j.get("tech_had", "Python")
        tech_missing = j.get("tech_missing", "None (100% Match!)")
        status = j.get("status", "NEW")
        referrals = j.get("referral_links") or "N/A"
        discovered_at = j.get("discovered_at") or now_str

        rows.append([
            company,
            title,
            link,
            location,
            work_mode,
            source_platform,
            jd,
            jd_match,
            tech_had,
            tech_missing,
            status,
            referrals,
            discovered_at,
        ])

    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")

    return len(rows)


