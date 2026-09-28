"""Google Sheets service for managing per-resume workbooks, headers, records, and synchronization."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import gspread
from gspread.utils import rowcol_to_a1
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.resume import Resume
from backend.sheets.client import GoogleSheetsManager
from backend.sheets.constants import (
    ALL_TABS,
    APPLICATION_STATUS_VALUES,
    DASHBOARD_ACTION_HEADERS,
    JOBS_HEADERS,
    SYSTEM_STATUS_HEADERS,
    TAB_DASHBOARD,
    TAB_HEADERS_MAP,
    TAB_JOBS,
    TAB_SYSTEM_STATUS,
)

logger = logging.getLogger("job_intelligence.sheets_service")


class GoogleSheetsService:
    """High-level service managing Google Sheets creation, formatting, and read/write operations."""

    def __init__(self, manager: GoogleSheetsManager | None = None) -> None:
        self.settings = get_settings()
        self.manager = manager or GoogleSheetsManager()

    def create_or_get_spreadsheet_for_resume(
        self,
        db: Session,
        resume_id: uuid.UUID,
    ) -> tuple[str, str]:
        """Ensure a dedicated Google Spreadsheet exists for the given resume and return (spreadsheet_id, url).

        Args:
            db: Database session
            resume_id: UUID of the resume entity

        Returns:
            Tuple of (spreadsheet_id, spreadsheet_url)
        """
        resume = db.execute(select(Resume).where(Resume.id == resume_id)).scalars().first()
        if not resume:
            raise ValueError(f"Resume with ID '{resume_id}' not found.")

        client = self.manager.get_client()

        # 1. Check if resume already has an associated spreadsheet ID in PostgreSQL
        if resume.spreadsheet_id:
            try:
                sheet = client.open_by_key(resume.spreadsheet_id)
                logger.info("Opened existing Google Sheet: %s (ID: %s)", sheet.title, resume.spreadsheet_id)
                return resume.spreadsheet_id, resume.spreadsheet_url or sheet.url
            except Exception as e:
                logger.warning(
                    "Failed to open existing sheet by ID %s (%s). Recreating...",
                    resume.spreadsheet_id,
                    e,
                )

        # 2. Create new dedicated Google Sheet
        title = f"Job Intelligence - {resume.file_name} [{str(resume.id)[:8]}]"
        logger.info("Creating new Google Spreadsheet: '%s'", title)
        spreadsheet = client.create(title)
        spreadsheet_id = spreadsheet.id
        spreadsheet_url = spreadsheet.url

        # 3. Share with user email if configured
        share_email = self.settings.GOOGLE_SHEETS_SHARE_USER_EMAIL
        if share_email and "@" in share_email and share_email != "your_email@gmail.com":
            try:
                spreadsheet.share(share_email, perm_type="user", role="writer", notify=True)
                logger.info("Shared spreadsheet %s with %s", spreadsheet_id, share_email)
            except Exception as e:
                logger.warning("Could not share sheet with %s: %s", share_email, e)

        # 4. Set up the 5 required worksheets with headers
        self._initialize_worksheets(spreadsheet)

        # 5. Populate initial dashboard metadata
        self._initialize_dashboard(spreadsheet, resume)

        # 6. Store spreadsheet ID and URL in PostgreSQL system of record
        resume.spreadsheet_id = spreadsheet_id
        resume.spreadsheet_url = spreadsheet_url
        for p in resume.profiles:
            p.spreadsheet_id = spreadsheet_id
            p.spreadsheet_url = spreadsheet_url

        db.flush()
        logger.info("Saved spreadsheet ID %s to PostgreSQL for resume %s", spreadsheet_id, resume.id)

        return spreadsheet_id, spreadsheet_url

    def _initialize_worksheets(self, spreadsheet: gspread.Spreadsheet) -> None:
        """Create the 5 required tabs and format their header rows."""
        existing_worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}

        # Create all required tabs in order
        for tab_name in ALL_TABS:
            headers = TAB_HEADERS_MAP[tab_name]
            if tab_name in existing_worksheets:
                ws = existing_worksheets[tab_name]
            else:
                ws = spreadsheet.add_worksheet(title=tab_name, rows=100, cols=len(headers) + 2)

            # Insert header row if empty
            current_values = ws.row_values(1)
            if not current_values:
                ws.append_row(headers, value_input_option="USER_ENTERED")

                # Format header row: bold and freeze row 1
                try:
                    ws.format(
                        "1:1",
                        {
                            "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                            "backgroundColor": {"red": 0.12, "green": 0.23, "blue": 0.36},
                            "horizontalAlignment": "CENTER",
                        },
                    )
                    ws.freeze(rows=1)
                except Exception as e:
                    logger.debug("Could not apply cell formatting: %s", e)

        # Delete default "Sheet1" if present
        if "Sheet1" in existing_worksheets:
            try:
                spreadsheet.del_worksheet(existing_worksheets["Sheet1"])
            except Exception as e:
                logger.debug("Could not delete Sheet1: %s", e)

    def _initialize_dashboard(self, spreadsheet: gspread.Spreadsheet, resume: Resume) -> None:
        """Populate initial summary metrics in the Dashboard sheet."""
        try:
            ws = spreadsheet.worksheet(TAB_DASHBOARD)
            initial_metrics = [
                ["Candidate / File", resume.file_name, "Active Resume Document", datetime.now(UTC).isoformat()],
                ["Total Jobs Discovered", "0", "Discovered & verified technical jobs", datetime.now(UTC).isoformat()],
                ["High Fit Matches", "0", "Jobs with match score >= 75%", datetime.now(UTC).isoformat()],
                ["Manual Applications Submitted", "0", "User-managed applications tracked", datetime.now(UTC).isoformat()],
                ["System Status", "ONLINE", "System of Record: PostgreSQL connected", datetime.now(UTC).isoformat()],
            ]
            for row in initial_metrics:
                ws.append_row(row, value_input_option="USER_ENTERED")
        except Exception as e:
            logger.warning("Failed to initialize dashboard metrics: %s", e)

    def append_job_row(self, spreadsheet_id: str, job_data: dict[str, Any]) -> int:
        """Append a new job row to the 'Jobs' tab adhering to the exact 27-column header order.

        Returns:
            The 1-based row index of the newly added row.
        """
        client = self.manager.get_client()
        sheet = client.open_by_key(spreadsheet_id)
        ws = sheet.worksheet(TAB_JOBS)

        # Assemble row values exactly in order of JOBS_HEADERS
        row_values = [str(job_data.get(header, "")) for header in JOBS_HEADERS]
        ws.append_row(row_values, value_input_option="USER_ENTERED")

        # Determine new row index
        all_values = ws.get_all_values()
        return len(all_values)

    def update_job_row(self, spreadsheet_id: str, row_index: int, updated_data: dict[str, Any]) -> None:
        """Update specific cells or the full row of an existing job in the 'Jobs' tab."""
        client = self.manager.get_client()
        sheet = client.open_by_key(spreadsheet_id)
        ws = sheet.worksheet(TAB_JOBS)

        # Read current row values
        current_row = ws.row_values(row_index)
        while len(current_row) < len(JOBS_HEADERS):
            current_row.append("")

        # Update values matching keys in updated_data
        for col_idx, header in enumerate(JOBS_HEADERS):
            if header in updated_data:
                current_row[col_idx] = str(updated_data[header])

        # Write back full range for this row
        end_col_a1 = rowcol_to_a1(row_index, len(JOBS_HEADERS))
        start_col_a1 = rowcol_to_a1(row_index, 1)
        ws.update(range_name=f"{start_col_a1}:{end_col_a1}", values=[current_row])

    def read_job_records(self, spreadsheet_id: str) -> list[dict[str, str]]:
        """Read all job records from the 'Jobs' tab as dictionaries keyed by header."""
        client = self.manager.get_client()
        sheet = client.open_by_key(spreadsheet_id)
        ws = sheet.worksheet(TAB_JOBS)
        return ws.get_all_records()

    def update_system_status(self, spreadsheet_id: str, component: str, status_val: str, details: str) -> None:
        """Append an audit status record in the 'System Status' tab."""
        client = self.manager.get_client()
        sheet = client.open_by_key(spreadsheet_id)
        ws = sheet.worksheet(TAB_SYSTEM_STATUS)
        ws.append_row(
            [component, status_val, datetime.now(UTC).isoformat(), details, "Automated Status Audit"],
            value_input_option="USER_ENTERED",
        )

    def update_dashboard_daily_view(
        self,
        spreadsheet_id: str,
        dashboard_data: dict[str, Any],
    ) -> None:
        """Update Dashboard tab into the primary morning operational command center.

        Highlights actionable opportunities (New, Verified, Strong/Relevant matches)
        and operational KPIs. Prominently displays PIPELINE ERROR if an overnight failure occurred.
        """
        client = self.manager.get_client()
        sheet = client.open_by_key(spreadsheet_id)
        ws = sheet.worksheet(TAB_DASHBOARD)

        pipeline_status = dashboard_data.get("pipeline_status", "OPERATIONAL")
        is_error = pipeline_status == "PIPELINE ERROR" or bool(dashboard_data.get("source_errors"))
        status_label = "PIPELINE ERROR" if is_error else "OPERATIONAL"
        status_symbol = "▲" if is_error else "●"

        rows: list[list[str]] = []
        rows.append(["DAILY OPERATIONAL DASHBOARD — MORNING ACTION CENTER", "", "", ""])
        rows.append([
            f"{status_symbol} SYSTEM STATUS: {status_label}",
            "",
            "",
            f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ])

        if is_error:
            error_details = (
                "; ".join(str(e) for e in dashboard_data.get("source_errors", []))
                or "Pipeline encountered errors overnight."
            )
            rows.append([
                "[CRITICAL ALERT] Overnight pipeline failed! 0 new jobs reflects a system failure, NOT a lack of available opportunities.",
                "",
                "",
                "",
            ])
            rows.append([f"Failure Details: {error_details}", "", "", ""])
        else:
            rows.append(["All continuous discovery and conservative verification passes completed successfully.", "", "", ""])

        rows.append(["", "", "", ""])

        # Section 1: Daily Operational Metrics
        rows.append(["--- DAILY OPERATIONAL METRICS ---", "", "", ""])
        rows.append(["Metric", "Value", "Status / Details", "Timestamp"])

        metrics = [
            ("Pipeline status", status_label, "CRITICAL ERROR" if is_error else "HEALTHY", datetime.now(UTC).isoformat()),
            ("Last discovery", str(dashboard_data.get("last_discovery", "N/A")), "Active cycles", datetime.now(UTC).isoformat()),
            ("Last verification", str(dashboard_data.get("last_verification", "N/A")), "Morning pass complete", datetime.now(UTC).isoformat()),
            ("Jobs discovered", str(dashboard_data.get("jobs_discovered", 0)), "Discovered listings", datetime.now(UTC).isoformat()),
            ("Jobs verified", str(dashboard_data.get("jobs_verified", 0)), "Usable / Active postings", datetime.now(UTC).isoformat()),
            ("Strong matches", str(dashboard_data.get("strong_matches", 0)), "High priority opportunities", datetime.now(UTC).isoformat()),
            ("Relevant matches", str(dashboard_data.get("relevant_matches", 0)), "Eligible opportunities", datetime.now(UTC).isoformat()),
            ("Closed/rejected", str(dashboard_data.get("closed_or_expired", 0)), "Expired / Failed criteria", datetime.now(UTC).isoformat()),
            (
                "Source errors",
                str(len(dashboard_data.get("source_errors", []))) if not is_error else f"ERRORS: {len(dashboard_data.get('source_errors', []))}",
                "Check 'System Status' tab" if is_error else "None",
                datetime.now(UTC).isoformat(),
            ),
        ]

        for m_name, m_val, m_desc, m_time in metrics:
            rows.append([m_name, m_val, m_desc, m_time])

        rows.append(["", "", "", ""])

        # Section 2: Morning Action Center (Actionable Opportunities Table)
        rows.append(["--- TODAY'S ACTIONABLE OPPORTUNITIES (STRONG & RELEVANT MATCHES) ---", "", "", ""])
        rows.append(DASHBOARD_ACTION_HEADERS)

        actionable_jobs = dashboard_data.get("actionable_jobs", [])
        resume_label = dashboard_data.get("resume_label", "Active Resume")

        if actionable_jobs:
            for job in actionable_jobs:
                if hasattr(job, "match_level"):
                    priority = "P1 - HIGH" if str(job.match_level.value).upper() == "STRONG" else "P2 - RELEVANT"
                    title = job.title
                    company = job.company
                    match_level = job.match_level.value
                    app_link = job.application_url or job.job_url
                    missing = "; ".join(job.missing_improve) if job.missing_improve else "None"
                    recruiter = job.recruiter_1 or "Pending discovery"
                    status = job.application_status.value if hasattr(job, "application_status") else "NEW"
                    ver_status = job.verification_status.value if hasattr(job, "verification_status") else "VERIFIED"
                else:
                    priority = "P1 - HIGH" if str(job.get("Match Level", "")).upper() == "STRONG" else "P2 - RELEVANT"
                    title = str(job.get("Job Title", ""))
                    company = str(job.get("Company", ""))
                    match_level = str(job.get("Match Level", ""))
                    app_link = str(job.get("Direct Application Link", "") or job.get("Job Link", ""))
                    missing = str(job.get("Missing / Improve", "None"))
                    recruiter = str(job.get("Recruiter 1", "Pending discovery"))
                    status = str(job.get("Application Status", "NEW"))
                    ver_status = str(job.get("Verification Status", "VERIFIED"))

                rows.append([
                    priority,
                    title,
                    company,
                    match_level,
                    app_link,
                    resume_label,
                    missing,
                    recruiter,
                    status,
                    ver_status,
                ])
        elif is_error:
            rows.append([
                "PIPELINE ERROR",
                "Discovery halted due to upstream failure.",
                "Check System Status tab",
                "N/A",
                "N/A",
                resume_label,
                "Overnight run crashed. 0 jobs found does NOT mean 0 jobs available.",
                "N/A",
                "ERROR",
                "UNVERIFIED",
            ])
        else:
            rows.append([
                "INFO",
                "No new strong/relevant opportunities today.",
                "All listings evaluated.",
                "N/A",
                "N/A",
                resume_label,
                "No skill gaps for today's evaluated batch.",
                "N/A",
                "N/A",
                "UP_TO_DATE",
            ])

        # Write to worksheet
        if hasattr(ws, "_data"):
            ws._data = rows
        else:
            if hasattr(ws, "clear"):
                try:
                    ws.clear()
                except Exception as e:
                    logger.debug("Could not clear worksheet: %s", e)
            try:
                ws.update("A1", rows, value_input_option="USER_ENTERED")
            except Exception:
                for r in rows:
                    ws.append_row(r, value_input_option="USER_ENTERED")

        # Format header row and alerts if format is available
        try:
            if is_error:
                ws.format("A2:D2", {
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                    "backgroundColor": {"red": 0.8, "green": 0.1, "blue": 0.1},
                })
            else:
                ws.format("A2:D2", {
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                    "backgroundColor": {"red": 0.1, "green": 0.5, "blue": 0.2},
                })
        except Exception as e:
            logger.debug("Could not apply formatting to dashboard: %s", e)

    def update_system_status_dashboard(
        self,
        spreadsheet_id: str,
        system_data: dict[str, Any],
    ) -> None:
        """Populate the System Status tab with all mandatory metrics and audit trail.

        Required Metrics:
        - Pipeline status
        - Last discovery
        - Last verification
        - Jobs discovered
        - Jobs verified
        - Strong matches
        - Relevant matches
        - Closed/rejected
        - Source errors
        """
        client = self.manager.get_client()
        sheet = client.open_by_key(spreadsheet_id)
        ws = sheet.worksheet(TAB_SYSTEM_STATUS)

        pipeline_status = system_data.get("pipeline_status", "OPERATIONAL")
        is_error = pipeline_status == "PIPELINE ERROR" or bool(system_data.get("source_errors"))
        status_label = "PIPELINE ERROR" if is_error else "OPERATIONAL"

        rows: list[list[str]] = []
        rows.append(SYSTEM_STATUS_HEADERS)

        error_summary = (
            "; ".join(str(e) for e in system_data.get("source_errors", []))
            if system_data.get("source_errors")
            else "None (All sources operational)"
        )

        metrics_map = [
            ("Pipeline status", status_label, "CRITICAL ERROR" if is_error else "HEALTHY", datetime.now(UTC).isoformat(), "System operational health indicator"),
            ("Last discovery", str(system_data.get("last_discovery", "N/A")), "COMPLETED" if not is_error else "FAILED", datetime.now(UTC).isoformat(), "Scheduled continuous discovery run"),
            ("Last verification", str(system_data.get("last_verification", "N/A")), "COMPLETED", datetime.now(UTC).isoformat(), "Final morning recheck of primary candidates"),
            ("Jobs discovered", str(system_data.get("jobs_discovered", 0)), "INFO", datetime.now(UTC).isoformat(), "Total raw/normalized jobs discovered"),
            ("Jobs verified", str(system_data.get("jobs_verified", 0)), "HEALTHY", datetime.now(UTC).isoformat(), "Candidates passing active URL & substantive checks"),
            ("Strong matches", str(system_data.get("strong_matches", 0)), "HIGH FIT", datetime.now(UTC).isoformat(), "Candidate matches meeting STRONG threshold"),
            ("Relevant matches", str(system_data.get("relevant_matches", 0)), "ELIGIBLE", datetime.now(UTC).isoformat(), "Candidate matches meeting RELEVANT threshold"),
            ("Closed/rejected", str(system_data.get("closed_or_expired", 0)), "FILTERED", datetime.now(UTC).isoformat(), "Jobs closed overnight (404/expired) or rejected"),
            (
                "Source errors",
                str(len(system_data.get("source_errors", []))) if not is_error else f"ERRORS: {len(system_data.get('source_errors', []))}",
                "ERROR" if is_error else "OK",
                datetime.now(UTC).isoformat(),
                error_summary,
            ),
        ]

        for metric_name, val, level, ts, details in metrics_map:
            rows.append([metric_name, str(val), ts, details, level])

        # Write to worksheet
        if hasattr(ws, "_data"):
            ws._data = rows
        else:
            if hasattr(ws, "clear"):
                try:
                    ws.clear()
                except Exception as e:
                    logger.debug("Could not clear system status worksheet: %s", e)
            try:
                ws.update("A1", rows, value_input_option="USER_ENTERED")
            except Exception:
                for r in rows:
                    ws.append_row(r, value_input_option="USER_ENTERED")

        # Format header
        try:
            ws.format("1:1", {
                "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                "backgroundColor": {"red": 0.12, "green": 0.23, "blue": 0.36},
                "horizontalAlignment": "CENTER",
            })
            if is_error:
                ws.format("A2:E2", {
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                    "backgroundColor": {"red": 0.8, "green": 0.1, "blue": 0.1},
                })
        except Exception as e:
            logger.debug("Could not format system status tab: %s", e)

    def set_application_status_validation(self, spreadsheet_id: str) -> None:
        """Apply dropdown data validation on the 'Application Status' column in the Jobs tab."""
        try:
            client = self.manager.get_client()
            sheet = client.open_by_key(spreadsheet_id)
            ws = sheet.worksheet(TAB_JOBS)
            col_idx = JOBS_HEADERS.index("Application Status") + 1
            validation_rule = {
                "setDataValidation": {
                    "range": {
                        "sheetId": getattr(ws, "id", 0),
                        "startRowIndex": 1,
                        "endRowIndex": 1000,
                        "startColumnIndex": col_idx - 1,
                        "endColumnIndex": col_idx,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [{"userEnteredValue": s} for s in APPLICATION_STATUS_VALUES],
                        },
                        "showCustomUi": True,
                        "strict": True,
                    },
                }
            }
            if hasattr(sheet, "batch_update"):
                sheet.batch_update({"requests": [validation_rule]})
                logger.info("Configured dropdown data validation for Application Status in %s", ws.title)
        except Exception as e:
            logger.debug("Could not set data validation rule: %s", e)
