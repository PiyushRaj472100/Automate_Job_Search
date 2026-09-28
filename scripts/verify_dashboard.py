"""Phase 11: Daily Operational Dashboard Verification Script.

Demonstrates:
1. When user opens the Sheet in the morning, Dashboard immediately shows actionable jobs:
   - New jobs
   - Verified jobs
   - Strong matches
   - Relevant matches
   - Direct application links
   - Recommended resume
   - Missing / Improve
   - Recruiter profiles
2. All 10 Application Statuses supported:
   NEW, REVIEWED, SAVED, APPLIED, ASSESSMENT, INTERVIEW, REJECTED, WITHDRAWN, OFFER, CLOSED.
3. System Status tab with all 9 required metrics:
   Pipeline status, Last discovery, Last verification, Jobs discovered, Jobs verified,
   Strong matches, Relevant matches, Closed/rejected, Source errors.
4. Overnight Failure Handling:
   Prominently displays PIPELINE ERROR and explicitly informs user that 0 jobs does NOT mean 0 jobs found.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from backend.sheets.constants import (
    APPLICATION_STATUS_VALUES,
    SYSTEM_STATUS_REQUIRED_METRICS,
    TAB_DASHBOARD,
    TAB_JOBS,
    TAB_SYSTEM_STATUS,
    ApplicationStatus,
)
from backend.sheets.service import GoogleSheetsService

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s")
logger = logging.getLogger("verify_dashboard")


class MockWorksheet:
    def __init__(self, title: str) -> None:
        self.title = title
        self._data: list[list[str]] = []

    def clear(self) -> None:
        self._data = []

    def row_values(self, row_index: int) -> list[str]:
        if 1 <= row_index <= len(self._data):
            return list(self._data[row_index - 1])
        return []

    def append_row(self, values: list, value_input_option: str = "USER_ENTERED") -> None:
        self._data.append([str(v) for v in values])

    def update(self, range_name: str | None = None, values: list | None = None, **kwargs) -> None:
        if not values or not range_name:
            return
        import re

        match = re.search(r"[A-Z]+(\d+)", range_name)
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(self._data):
                self._data[idx] = [str(v) for v in values[0]]
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

    def format(self, range_name: str, format_dict: dict) -> None:
        pass

    def freeze(self, rows: int = 0, cols: int = 0) -> None:
        pass


class MockSpreadsheet:
    def __init__(self, sheet_id: str = "test_sheet_dashboard") -> None:
        self.id = sheet_id
        self.url = f"https://docs.google.com/spreadsheets/d/{self.id}"
        self._worksheets = {
            TAB_DASHBOARD: MockWorksheet(TAB_DASHBOARD),
            TAB_JOBS: MockWorksheet(TAB_JOBS),
            TAB_SYSTEM_STATUS: MockWorksheet(TAB_SYSTEM_STATUS),
        }

    def worksheets(self):
        return list(self._worksheets.values())

    def worksheet(self, title: str):
        return self._worksheets[title]


def main() -> None:
    logger.info("=================================================================")
    logger.info("PHASE 11: DAILY OPERATIONAL DASHBOARD VERIFICATION")
    logger.info("=================================================================")

    mock_client = MagicMock()
    mock_sheet = MockSpreadsheet("sheet_operational_demo")
    mock_client.open_by_key.return_value = mock_sheet
    manager = MagicMock()
    manager.get_client.return_value = mock_client
    service = GoogleSheetsService(manager=manager)

    # -------------------------------------------------------------------------
    # 1. Verify Support for All 10 Application Statuses
    # -------------------------------------------------------------------------
    logger.info("\n--- 1. Testing Application Lifecycle Status Support ---")
    required_statuses = [
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
    for st in required_statuses:
        assert st in APPLICATION_STATUS_VALUES
        enum_val = ApplicationStatus(st)
        assert enum_val.value == st
    logger.info("All 10 required application lifecycle statuses are validated:")
    logger.info("  %s", ", ".join(required_statuses))

    # -------------------------------------------------------------------------
    # 2. Daily Operational Dashboard (Morning Operational View)
    # -------------------------------------------------------------------------
    logger.info("\n--- 2. Testing Morning Operational Dashboard (Actionable View) ---")
    actionable_jobs = [
        {
            "Job Title": "Junior Backend Engineer",
            "Company": "Anthropic AI Lab",
            "Match Level": "STRONG",
            "Direct Application Link": "https://anthropic.com/careers/junior-backend/apply",
            "Job Link": "https://anthropic.com/careers/junior-backend",
            "Missing / Improve": "None (Full match with Python & FastAPI)",
            "Recruiter 1": "David Miller (Technical Recruiter) - https://linkedin.com/in/dmiller-recruiter",
            "Application Status": "NEW",
            "Verification Status": "VERIFIED",
        },
        {
            "Job Title": "Software Engineer I - Core Systems",
            "Company": "Stripe Payments",
            "Match Level": "RELEVANT",
            "Direct Application Link": "https://stripe.com/jobs/core-swe-1/apply",
            "Job Link": "https://stripe.com/jobs/core-swe-1",
            "Missing / Improve": "Kubernetes orchestration; RabbitMQ",
            "Recruiter 1": "Elena Rostova (Lead Talent Partner) - https://linkedin.com/in/erostova-talent",
            "Application Status": "NEW",
            "Verification Status": "VERIFIED",
        },
    ]

    operational_data = {
        "pipeline_status": "OPERATIONAL",
        "last_discovery": "2026-09-28T05:30:00Z (Sources: arbeitnow, direct_career_pages)",
        "last_verification": "2026-09-28T06:15:00Z (Morning pass rechecked 24 jobs)",
        "jobs_discovered": 24,
        "jobs_verified": 18,
        "strong_matches": 1,
        "relevant_matches": 1,
        "closed_or_expired": 6,
        "source_errors": [],
        "actionable_jobs": actionable_jobs,
        "resume_label": "rohan_verma_backend.pdf",
    }

    service.update_dashboard_daily_view(mock_sheet.id, operational_data)
    dashboard_rows = mock_sheet.worksheet(TAB_DASHBOARD).get_all_values()
    flat_cells = [cell for row in dashboard_rows for cell in row]

    logger.info("Dashboard Header & Status: %s", dashboard_rows[1][0])
    assert "SYSTEM STATUS: OPERATIONAL" in dashboard_rows[1][0]

    # Verify Actionable Items rendered
    assert "Junior Backend Engineer" in flat_cells
    assert "Anthropic AI Lab" in flat_cells
    assert "STRONG" in flat_cells
    assert "https://anthropic.com/careers/junior-backend/apply" in flat_cells
    assert "rohan_verma_backend.pdf" in flat_cells
    assert "David Miller (Technical Recruiter)" in flat_cells[flat_cells.index("Junior Backend Engineer") + 6]
    logger.info("Actionable Jobs rendered directly in main view with direct links, resume, and recruiters.")

    # -------------------------------------------------------------------------
    # 3. System Status Tab Metrics
    # -------------------------------------------------------------------------
    logger.info("\n--- 3. Testing System Status Tab (All 9 Required Metrics) ---")
    system_data = {
        "pipeline_status": "OPERATIONAL",
        "last_discovery": operational_data["last_discovery"],
        "last_verification": operational_data["last_verification"],
        "jobs_discovered": 24,
        "jobs_verified": 18,
        "strong_matches": 1,
        "relevant_matches": 1,
        "closed_or_expired": 6,
        "source_errors": [],
    }

    service.update_system_status_dashboard(mock_sheet.id, system_data)
    sys_records = mock_sheet.worksheet(TAB_SYSTEM_STATUS).get_all_records()
    sys_metric_names = [r["Component"] for r in sys_records]

    for req_metric in SYSTEM_STATUS_REQUIRED_METRICS:
        assert req_metric in sys_metric_names, f"Missing required metric: {req_metric}"
        row = next(r for r in sys_records if r["Component"] == req_metric)
        logger.info("  Metric: %-20s | Value: %-20s | Status: %s", req_metric, row["Status"], row["Audit Log"])

    logger.info("All 9 required system status metrics validated successfully.")

    # -------------------------------------------------------------------------
    # 4. Overnight Pipeline Failure Handling
    # -------------------------------------------------------------------------
    logger.info("\n--- 4. Testing Overnight Pipeline Failure (PIPELINE ERROR Alert) ---")
    failure_data = {
        "pipeline_status": "PIPELINE ERROR",
        "last_discovery": "2026-09-28T03:00:00Z",
        "last_verification": "2026-09-28T03:00:15Z",
        "jobs_discovered": 0,
        "jobs_verified": 0,
        "strong_matches": 0,
        "relevant_matches": 0,
        "closed_or_expired": 0,
        "source_errors": ["ConnectionResetError: Upstream feed severed during discovery cycle."],
        "actionable_jobs": [],
        "resume_label": "rohan_verma_backend.pdf",
    }

    service.update_dashboard_daily_view(mock_sheet.id, failure_data)
    fail_rows = mock_sheet.worksheet(TAB_DASHBOARD).get_all_values()
    fail_flat = [c for r in fail_rows for c in r]

    logger.info("Failure Banner: %s", fail_rows[1][0])
    assert "PIPELINE ERROR" in fail_rows[1][0]

    # Explicit warning requirement: Do not make user believe 0 jobs means 0 jobs found
    warning_found = any(
        "0 new jobs reflects a system failure, NOT a lack of available opportunities" in cell for cell in fail_flat
    )
    assert warning_found, "Must alert user that 0 jobs is due to pipeline error, not lack of jobs"
    logger.info("Explicit failure warning verified: Prevents false belief that 0 jobs means 0 opportunities.")

    logger.info("=================================================================")
    logger.info("PHASE 11 DAILY OPERATIONAL DASHBOARD VERIFIED SUCCESSFULLY!")
    logger.info("=================================================================")


if __name__ == "__main__":
    main()
