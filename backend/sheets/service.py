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
    JOBS_HEADERS,
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
