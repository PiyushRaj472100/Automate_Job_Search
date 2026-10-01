"""Comprehensive tests for Google Sheets integration, tab creation, headers, and read/write operations."""

import uuid
from typing import Any

import pytest
from sqlalchemy.orm import Session

from backend.models.resume import Resume
from backend.sheets.client import GoogleSheetsAuthError, GoogleSheetsManager
from backend.sheets.constants import (
    ALL_TABS,
    APPLICATION_STATUS_VALUES,
    DASHBOARD_HEADERS,
    JOBS_HEADERS,
    SYSTEM_STATUS_REQUIRED_METRICS,
    TAB_DASHBOARD,
    TAB_JOBS,
    TAB_SYSTEM_STATUS,
    ApplicationStatus,
)
from backend.sheets.service import GoogleSheetsService


class MockWorksheet:
    """In-memory mock of a gspread Worksheet."""

    def __init__(self, title: str, rows: int = 100, cols: int = 30) -> None:
        self.title = title
        self.rows_count = rows
        self.cols_count = cols
        self._data: list[list[str]] = []
        self.frozen_rows = 0

    def clear(self) -> None:
        self._data = []

    def row_values(self, row_index: int) -> list[str]:
        if 1 <= row_index <= len(self._data):
            return list(self._data[row_index - 1])
        return []

    def append_row(self, values: list[Any], value_input_option: str = "USER_ENTERED") -> None:
        self._data.append([str(v) for v in values])

    def update(self, range_name: str | None = None, values: list[list[Any]] | None = None, **kwargs: Any) -> None:
        if not values or not range_name:
            return
        # Parse start row from range (e.g. 'A2:AA2')
        import re

        match = re.search(r"[A-Z]+(\d+)", range_name)
        if match:
            row_idx = int(match.group(1)) - 1
            if 0 <= row_idx < len(self._data):
                self._data[row_idx] = [str(v) for v in values[0]]
            else:
                self._data.append([str(v) for v in values[0]])

    def get_all_values(self) -> list[list[str]]:
        return [list(r) for r in self._data]

    def get_all_records(self) -> list[dict[str, str]]:
        if not self._data or len(self._data) < 2:
            return []
        headers = self._data[0]
        records: list[dict[str, str]] = []
        for row in self._data[1:]:
            padded = list(row) + [""] * (len(headers) - len(row))
            record = {headers[i]: padded[i] for i in range(len(headers))}
            records.append(record)
        return records

    def format(self, range_name: str, format_dict: dict[str, Any]) -> None:
        pass

    def freeze(self, rows: int = 0, cols: int = 0) -> None:
        self.frozen_rows = rows


class MockSpreadsheet:
    """In-memory mock of a gspread Spreadsheet."""

    def __init__(self, title: str, sheet_id: str | None = None) -> None:
        self.title = title
        self.id = sheet_id or f"mock_sheet_{uuid.uuid4().hex[:12]}"
        self.url = f"https://docs.google.com/spreadsheets/d/{self.id}/edit"
        self._worksheets: dict[str, MockWorksheet] = {
            "Sheet1": MockWorksheet("Sheet1"),
        }

    def worksheets(self) -> list[MockWorksheet]:
        return list(self._worksheets.values())

    def worksheet(self, title: str) -> MockWorksheet:
        if title in self._worksheets:
            return self._worksheets[title]
        raise ValueError(f"Worksheet '{title}' not found.")

    def add_worksheet(self, title: str, rows: int = 100, cols: int = 30) -> MockWorksheet:
        ws = MockWorksheet(title, rows, cols)
        self._worksheets[title] = ws
        return ws

    def del_worksheet(self, worksheet: MockWorksheet) -> None:
        if worksheet.title in self._worksheets:
            del self._worksheets[worksheet.title]

    def share(self, email: str, perm_type: str, role: str, notify: bool = True) -> None:
        pass


class MockGSpreadClient:
    """In-memory mock of gspread.Client."""

    def __init__(self) -> None:
        self.spreadsheets: dict[str, MockSpreadsheet] = {}

    def create(self, title: str, folder_id: str | None = None) -> MockSpreadsheet:
        sheet = MockSpreadsheet(title)
        self.spreadsheets[sheet.id] = sheet
        return sheet

    def open_by_key(self, key: str) -> MockSpreadsheet:
        if key in self.spreadsheets:
            return self.spreadsheets[key]
        raise ValueError(f"Spreadsheet with key '{key}' not found.")


@pytest.fixture
def mock_sheets_service() -> GoogleSheetsService:
    """Fixture providing GoogleSheetsService configured with mock client."""
    mock_client = MockGSpreadClient()
    mock_manager = GoogleSheetsManager(client=mock_client)
    return GoogleSheetsService(manager=mock_manager)


# 1. Authentication & Missing Credentials Test
def test_authentication_missing_credentials_handling():
    """Verify that attempting to get a client without credentials raises GoogleSheetsAuthError."""
    manager = GoogleSheetsManager(service_account_file="/invalid/path/none.json")
    with pytest.raises(GoogleSheetsAuthError, match="Service account file not found"):
        manager.get_client()


# 2. Spreadsheet Creation & Worksheet Architecture Test
def test_spreadsheet_creation_and_tabs(db_session: Session, mock_sheets_service: GoogleSheetsService):
    """Verify that creating a spreadsheet sets up all 5 required worksheets with Sheet1 removed."""
    resume = Resume(file_name="priya_dev.pdf", file_hash="hash_12345")
    db_session.add(resume)
    db_session.flush()

    sheet_id, sheet_url = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)

    assert sheet_id is not None
    assert "https://docs.google.com/spreadsheets/d/" in sheet_url

    # Check PostgreSQL linkage
    assert resume.spreadsheet_id == sheet_id
    assert resume.spreadsheet_url == sheet_url

    # Verify worksheets on the mock spreadsheet
    client = mock_sheets_service.manager.get_client()
    spreadsheet = client.open_by_key(sheet_id)
    titles = [ws.title for ws in spreadsheet.worksheets()]

    # Assert all 5 tabs exist and Sheet1 is deleted
    assert "Sheet1" not in titles
    for tab in ALL_TABS:
        assert tab in titles


# 3. Headers Verification Test
def test_exact_27_jobs_headers(db_session: Session, mock_sheets_service: GoogleSheetsService):
    """Verify that the Jobs sheet contains the exact 27 contract headers in proper order."""
    resume = Resume(file_name="alex_eng.pdf", file_hash="hash_67890")
    db_session.add(resume)
    db_session.flush()

    sheet_id, _ = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)
    client = mock_sheets_service.manager.get_client()
    spreadsheet = client.open_by_key(sheet_id)
    jobs_ws = spreadsheet.worksheet(TAB_JOBS)

    headers = jobs_ws.row_values(1)
    assert len(headers) == 27
    assert headers == JOBS_HEADERS

    # Also check Dashboard headers
    dashboard_ws = spreadsheet.worksheet(TAB_DASHBOARD)
    assert dashboard_ws.row_values(1) == DASHBOARD_HEADERS


# 4. Writing, Updating, and Reading a Test Record
def test_write_update_read_job_record(db_session: Session, mock_sheets_service: GoogleSheetsService):
    """Verify writing one test job row, updating it, and reading it back cleanly."""
    resume = Resume(file_name="rohit_swe.pdf", file_hash="hash_55555")
    db_session.add(resume)
    db_session.flush()

    sheet_id, _ = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)

    # 1. Write one test record
    test_job = {
        "Date Found": "2026-09-28",
        "Job Title": "Junior Backend Engineer",
        "Company": "Nexora Tech",
        "Experience": "0-2 years",
        "Location": "Bengaluru",
        "Work Mode": "Hybrid",
        "Job Link": "https://nexora.io/careers/101",
        "Direct Application Link": "https://nexora.io/careers/101/apply",
        "Source": "Direct Careers",
        "Job ID": "NEX-101",
        "First Seen": "2026-09-28T05:00:00Z",
        "Last Verified": "2026-09-28T05:00:00Z",
        "Verification Status": "Active (HTTP 200)",
        "Source Quality": "High",
        "Match Level": "High",
        "Why It Matches": "Matches Python, FastAPI, and PostgreSQL core skills.",
        "Required Skills": "Python, FastAPI, SQL",
        "Skills You Have": "Python, FastAPI, PostgreSQL",
        "Missing / Improve": "None",
        "Resume": "rohit_swe.pdf",
        "Recruiter 1": "Anita Roy (LinkedIn)",
        "Recruiter 2": "",
        "Recruiter 3": "",
        "Application Status": "To Apply",
        "Applied Date": "",
        "Follow-up Date": "",
        "Notes": "Priority submission",
    }

    row_idx = mock_sheets_service.append_job_row(sheet_id, test_job)
    assert row_idx == 2  # Row 1 is header, Row 2 is first data row

    # 2. Read back initially written record
    records = mock_sheets_service.read_job_records(sheet_id)
    assert len(records) == 1
    assert records[0]["Job Title"] == "Junior Backend Engineer"
    assert records[0]["Company"] == "Nexora Tech"
    assert records[0]["Application Status"] == "To Apply"

    # 3. Update the record (e.g. user applied manually and updated status)
    updates = {
        "Application Status": "Applied",
        "Applied Date": "2026-09-28",
        "Follow-up Date": "2026-10-05",
        "Notes": "Applied via company career portal. Confirmation email received.",
    }
    mock_sheets_service.update_job_row(sheet_id, row_index=2, updated_data=updates)

    # 4. Read back updated record and assert changes
    updated_records = mock_sheets_service.read_job_records(sheet_id)
    assert len(updated_records) == 1
    assert updated_records[0]["Application Status"] == "Applied"
    assert updated_records[0]["Applied Date"] == "2026-09-28"
    assert updated_records[0]["Follow-up Date"] == "2026-10-05"
    assert "Applied via company career portal" in updated_records[0]["Notes"]
    # Verify untouched columns were preserved
    assert updated_records[0]["Company"] == "Nexora Tech"
    assert updated_records[0]["Job Title"] == "Junior Backend Engineer"


# 5. Idempotent Spreadsheet Retrieval
def test_idempotent_spreadsheet_retrieval(db_session: Session, mock_sheets_service: GoogleSheetsService):
    """Verify that calling create_or_get_spreadsheet_for_resume a second time reuses existing sheet ID."""
    resume = Resume(file_name="same_resume.pdf", file_hash="hash_same")
    db_session.add(resume)
    db_session.flush()

    sheet_id1, _ = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)
    sheet_id2, _ = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)

    assert sheet_id1 == sheet_id2
    assert resume.spreadsheet_id == sheet_id1


# 6. System Status Audit Log Test
def test_system_status_audit_logging(db_session: Session, mock_sheets_service: GoogleSheetsService):
    """Verify that system audits can append records to the System Status tab."""
    resume = Resume(file_name="audit_test.pdf", file_hash="hash_audit")
    db_session.add(resume)
    db_session.flush()

    sheet_id, _ = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)
    mock_sheets_service.update_system_status(
        sheet_id,
        component="URL Verifier",
        status_val="HEALTHY",
        details="Verified 15 job postings; 14 active, 1 expired",
    )

    client = mock_sheets_service.manager.get_client()
    spreadsheet = client.open_by_key(sheet_id)
    status_ws = spreadsheet.worksheet(TAB_SYSTEM_STATUS)
    status_records = status_ws.get_all_records()

    assert len(status_records) == 1
    assert status_records[0]["Component"] == "URL Verifier"
    assert status_records[0]["Status"] == "HEALTHY"


# 7. Application Status Support Test
def test_application_status_enum_and_values():
    """Verify that all 10 required application lifecycle statuses are properly supported."""
    expected_statuses = [
        "NEW",
        "REVIEWED",
        "SAVED",
        "APPLIED",
        "ASSESSMENT",
        "INTERVIEW",
        "REJECTED",
        "WITHDRAWN",
        "OFFER",
        "CLOSED",
    ]
    for status_str in expected_statuses:
        status_enum = ApplicationStatus(status_str)
        assert status_enum.value == status_str
        assert status_str in APPLICATION_STATUS_VALUES


# 8. Daily Operational Dashboard (Morning Action Center) Test
def test_daily_operational_dashboard_morning_action_center(
    db_session: Session, mock_sheets_service: GoogleSheetsService
):
    """Verify that Dashboard immediately presents actionable jobs and operational KPIs on morning open."""
    resume = Resume(file_name="actionable_dev.pdf", file_hash="hash_act1")
    db_session.add(resume)
    db_session.flush()

    sheet_id, _ = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)

    # Prepare actionable jobs
    actionable_jobs = [
        {
            "Job Title": "Junior Python Engineer",
            "Company": "CloudScale AI",
            "Match Level": "STRONG",
            "Direct Application Link": "https://cloudscale.ai/jobs/101/apply",
            "Job Link": "https://cloudscale.ai/jobs/101",
            "Missing / Improve": "Docker containerization",
            "Recruiter 1": "Sarah Jenkins (Lead Recruiter)",
            "Application Status": "NEW",
            "Verification Status": "VERIFIED",
        },
        {
            "Job Title": "Backend Developer",
            "Company": "FinTech Core",
            "Match Level": "RELEVANT",
            "Direct Application Link": "https://fintechcore.io/careers/apply",
            "Job Link": "https://fintechcore.io/careers",
            "Missing / Improve": "None",
            "Recruiter 1": "Alex Mercer (Talent Acquisition)",
            "Application Status": "NEW",
            "Verification Status": "VERIFIED",
        },
    ]

    dashboard_data = {
        "pipeline_status": "OPERATIONAL",
        "last_discovery": "2026-09-28T05:00:00Z",
        "last_verification": "2026-09-28T06:00:00Z",
        "jobs_discovered": 15,
        "jobs_verified": 12,
        "strong_matches": 1,
        "relevant_matches": 1,
        "closed_or_expired": 3,
        "source_errors": [],
        "actionable_jobs": actionable_jobs,
        "resume_label": "actionable_dev.pdf",
    }

    mock_sheets_service.update_dashboard_daily_view(sheet_id, dashboard_data)

    client = mock_sheets_service.manager.get_client()
    spreadsheet = client.open_by_key(sheet_id)
    ws = spreadsheet.worksheet(TAB_DASHBOARD)
    all_rows = ws.get_all_values()

    # 1. Prominent Status Header
    assert any("SYSTEM STATUS: OPERATIONAL" in cell for row in all_rows for cell in row)

    # 2. Daily Operational Metrics Present
    metrics_text = [row[0] for row in all_rows if len(row) > 0]
    assert "Pipeline status" in metrics_text
    assert "Last discovery" in metrics_text
    assert "Last verification" in metrics_text
    assert "Jobs discovered" in metrics_text
    assert "Jobs verified" in metrics_text
    assert "Strong matches" in metrics_text
    assert "Relevant matches" in metrics_text
    assert "Closed/rejected" in metrics_text
    assert "Source errors" in metrics_text

    # 3. Actionable Opportunities Section Present
    flat_cells = [cell for row in all_rows for cell in row]
    assert "Junior Python Engineer" in flat_cells
    assert "CloudScale AI" in flat_cells
    assert "STRONG" in flat_cells
    assert "https://cloudscale.ai/jobs/101/apply" in flat_cells
    assert "actionable_dev.pdf" in flat_cells
    assert "Docker containerization" in flat_cells
    assert "Sarah Jenkins (Lead Recruiter)" in flat_cells


# 9. Overnight Pipeline Failure & Error Alert Test
def test_daily_operational_dashboard_overnight_failure_alert(
    db_session: Session, mock_sheets_service: GoogleSheetsService
):
    """Verify that if pipeline failed overnight, Dashboard prominently displays PIPELINE ERROR

    and alerts that 0 jobs found does NOT mean 0 jobs available.
    """
    resume = Resume(file_name="error_test.pdf", file_hash="hash_err1")
    db_session.add(resume)
    db_session.flush()

    sheet_id, _ = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)

    dashboard_data = {
        "pipeline_status": "PIPELINE ERROR",
        "last_discovery": "2026-09-28T03:00:00Z",
        "last_verification": "2026-09-28T03:01:00Z",
        "jobs_discovered": 0,
        "jobs_verified": 0,
        "strong_matches": 0,
        "relevant_matches": 0,
        "closed_or_expired": 0,
        "source_errors": ["ConnectionRefusedError: Arbeitnow API timeout after 3 retries."],
        "actionable_jobs": [],
        "resume_label": "error_test.pdf",
    }

    mock_sheets_service.update_dashboard_daily_view(sheet_id, dashboard_data)

    client = mock_sheets_service.manager.get_client()
    spreadsheet = client.open_by_key(sheet_id)
    ws = spreadsheet.worksheet(TAB_DASHBOARD)
    all_rows = ws.get_all_values()
    flat_cells = [cell for row in all_rows for cell in row]

    # Must prominently state PIPELINE ERROR
    assert any("PIPELINE ERROR" in cell for cell in flat_cells)

    # Must explicitly inform user that 0 jobs does NOT mean 0 jobs found
    assert any("0 new jobs reflects a system failure, NOT a lack of available opportunities" in cell for cell in flat_cells)


# 10. System Status Tab Required Metrics Test
def test_system_status_tab_all_required_metrics(db_session: Session, mock_sheets_service: GoogleSheetsService):
    """Verify that System Status tab presents all 9 required metrics and status levels."""
    resume = Resume(file_name="sys_status.pdf", file_hash="hash_sys1")
    db_session.add(resume)
    db_session.flush()

    sheet_id, _ = mock_sheets_service.create_or_get_spreadsheet_for_resume(db_session, resume.id)

    system_data = {
        "pipeline_status": "OPERATIONAL",
        "last_discovery": "2026-09-28 05:00:00 UTC",
        "last_verification": "2026-09-28 06:00:00 UTC",
        "jobs_discovered": 25,
        "jobs_verified": 20,
        "strong_matches": 4,
        "relevant_matches": 6,
        "closed_or_expired": 5,
        "source_errors": [],
    }

    mock_sheets_service.update_system_status_dashboard(sheet_id, system_data)

    client = mock_sheets_service.manager.get_client()
    spreadsheet = client.open_by_key(sheet_id)
    ws = spreadsheet.worksheet(TAB_SYSTEM_STATUS)
    records = ws.get_all_records()

    # Verify all 9 required metrics are present
    recorded_metrics = [r["Component"] for r in records]
    for required_metric in SYSTEM_STATUS_REQUIRED_METRICS:
        assert required_metric in recorded_metrics, f"Missing required system metric: '{required_metric}'"

    # Verify pipeline status value is OPERATIONAL
    status_row = next(r for r in records if r["Component"] == "Pipeline status")
    assert status_row["Status"] == "OPERATIONAL"
    assert status_row["Audit Log"] == "HEALTHY"


def test_append_job_row_deduplication(mock_sheets_service: GoogleSheetsService):
    """Verify that append_job_row skips duplicate rows based on Job Link, Job ID, or Company+Title."""
    client = mock_sheets_service.manager.get_client()
    sheet = client.create("Test Deduplication Sheet")
    ws = sheet.add_worksheet(TAB_JOBS)
    ws.append_row(JOBS_HEADERS)

    job_1 = {
        "Job Title": "Junior Backend Engineer",
        "Company": "Stripe",
        "Job Link": "https://boards.greenhouse.io/stripe/jobs/101",
        "Job ID": "gh_stripe_101",
        "Experience": "0-2 years",
    }
    row_1 = mock_sheets_service.append_job_row(sheet.id, job_1)
    assert row_1 == 2

    # Appending the exact same job again should return row 2 and not add row 3
    row_dup = mock_sheets_service.append_job_row(sheet.id, job_1)
    assert row_dup == 2
    assert len(ws.get_all_values()) == 2  # Header + 1 row only!

    # Appending with same link but different title should still be detected as duplicate
    job_dup_link = {
        "Job Title": "Junior Backend Developer",
        "Company": "Stripe",
        "Job Link": "https://boards.greenhouse.io/stripe/jobs/101",
        "Job ID": "gh_stripe_999",
    }
    row_dup_link = mock_sheets_service.append_job_row(sheet.id, job_dup_link)
    assert row_dup_link == 2
    assert len(ws.get_all_values()) == 2

    # Appending a truly distinct job should succeed
    job_2 = {
        "Job Title": "Frontend Engineer I",
        "Company": "Figma",
        "Job Link": "https://boards.greenhouse.io/figma/jobs/202",
        "Job ID": "gh_figma_202",
    }
    row_2 = mock_sheets_service.append_job_row(sheet.id, job_2)
    assert row_2 == 3
    assert len(ws.get_all_values()) == 3

