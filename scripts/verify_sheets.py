import os
import sys

# Ensure project root is on Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import UTC, datetime

from backend.core.config import get_settings
from backend.sheets.client import GoogleSheetsAuthError, GoogleSheetsManager

from backend.sheets.constants import (
    ALL_TABS,
    JOBS_HEADERS,
    TAB_JOBS,
)
from backend.sheets.service import GoogleSheetsService


def main() -> None:
    print("================================================================")
    print("Google Sheets Integration Verifier - Job Intelligence Platform")
    print("================================================================")

    settings = get_settings()
    manager = GoogleSheetsManager()

    print("[*] Checking configuration...")
    print(f"    - Service Account File: {settings.GOOGLE_SERVICE_ACCOUNT_FILE or '(Not set)'}")
    print(f"    - Service Account JSON: {'(Provided)' if settings.GOOGLE_SERVICE_ACCOUNT_JSON else '(Not set)'}")
    print(f"    - Share User Email:     {settings.GOOGLE_SHEETS_SHARE_USER_EMAIL or '(Not set)'}")

    try:
        client = manager.get_client()
        print("[+] Authentication SUCCESSFUL! Authenticated with Google Sheets & Drive APIs.")
    except GoogleSheetsAuthError as e:
        print(f"[-] Authentication FAILED: {e}")
        print("\nTo configure Google Sheets authentication:")
        print("1. Follow the instructions in docs/GOOGLE_SHEETS_SETUP.md")
        print("2. Save your service account JSON key to credentials/service_account.json")
        print("3. Set GOOGLE_SHEETS_SHARE_USER_EMAIL in .env to your personal Google email.")
        sys.exit(1)

    # Proceed to live verification
    service = GoogleSheetsService(manager=manager)
    test_title = f"Job Intelligence - Test Verification [{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}]"
    print(f"[*] Creating live test spreadsheet: '{test_title}'...")

    try:
        spreadsheet = client.create(test_title)
        sheet_id = spreadsheet.id
        sheet_url = spreadsheet.url
        print("[+] Spreadsheet CREATED successfully!")
        print(f"    - ID:  {sheet_id}")
        print(f"    - URL: {sheet_url}")

        # Share if configured
        if settings.GOOGLE_SHEETS_SHARE_USER_EMAIL and "@" in settings.GOOGLE_SHEETS_SHARE_USER_EMAIL:
            print(f"[*] Sharing spreadsheet with {settings.GOOGLE_SHEETS_SHARE_USER_EMAIL}...")
            spreadsheet.share(settings.GOOGLE_SHEETS_SHARE_USER_EMAIL, perm_type="user", role="writer", notify=True)
            print(f"[+] Shared with {settings.GOOGLE_SHEETS_SHARE_USER_EMAIL} (Editor permissions).")

        # Initialize worksheets
        print("[*] Initializing 5 worksheets (Dashboard, Jobs, Recruiters, Applications, System Status)...")
        service._initialize_worksheets(spreadsheet)

        tabs = [ws.title for ws in spreadsheet.worksheets()]
        print(f"[+] Worksheets created: {tabs}")
        for required_tab in ALL_TABS:
            assert required_tab in tabs, f"Missing required tab: {required_tab}"

        # Verify headers in Jobs tab
        jobs_ws = spreadsheet.worksheet(TAB_JOBS)
        headers = jobs_ws.row_values(1)
        print(f"[+] Verified {len(headers)} headers on '{TAB_JOBS}' tab.")
        assert headers == JOBS_HEADERS, "Jobs headers do not match the 27 required columns!"

        # Write test record
        print("[*] Writing one test job record...")
        test_job = {
            "Date Found": datetime.now(UTC).strftime("%Y-%m-%d"),
            "Job Title": "Associate Backend Engineer",
            "Company": "TestCorp Technologies",
            "Experience": "0-2 years",
            "Location": "Remote - India",
            "Work Mode": "Remote",
            "Job Link": "https://example.com/jobs/101",
            "Direct Application Link": "https://example.com/jobs/101/apply",
            "Source": "Verification Test",
            "Job ID": "TEST-101",
            "First Seen": datetime.now(UTC).isoformat(),
            "Last Verified": datetime.now(UTC).isoformat(),
            "Verification Status": "Active (HTTP 200)",
            "Source Quality": "High",
            "Match Level": "High",
            "Why It Matches": "Direct match for verified skills.",
            "Required Skills": "Python, FastAPI, PostgreSQL",
            "Skills You Have": "Python, FastAPI, PostgreSQL",
            "Missing / Improve": "None",
            "Resume": "test_resume.pdf",
            "Recruiter 1": "Test Recruiter",
            "Recruiter 2": "",
            "Recruiter 3": "",
            "Application Status": "To Apply",
            "Applied Date": "",
            "Follow-up Date": "",
            "Notes": "Initial test write",
        }
        row_idx = service.append_job_row(sheet_id, test_job)
        print(f"[+] Written successfully at Row {row_idx}!")

        # Update record
        print("[*] Updating test record at Row 2...")
        service.update_job_row(
            sheet_id,
            row_index=2,
            updated_data={
                "Application Status": "Applied",
                "Applied Date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "Notes": "Updated verification test record",
            },
        )
        print("[+] Record updated successfully.")

        # Read back
        print("[*] Reading back updated record...")
        records = service.read_job_records(sheet_id)
        assert len(records) >= 1, "Failed to read back records!"
        assert records[0]["Application Status"] == "Applied"
        assert records[0]["Company"] == "TestCorp Technologies"
        print("[+] Read back verified matching record successfully!")

        print("\n================================================================")
        print("GOOGLE SHEETS INTEGRATION VERIFIED SUCCESSFULLY!")
        print(f"Spreadsheet URL: {sheet_url}")
        print("================================================================")

    except Exception as e:
        print(f"[-] Error during live Google Sheets verification: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
