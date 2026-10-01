"""Google Sheets authentication and client management using gspread."""

import json
import logging
import os
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from backend.core.config import get_settings

logger = logging.getLogger("job_intelligence.sheets_client")
from backend.core.retry import retry

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsAuthError(Exception):
    """Raised when Google Sheets authentication or credential resolution fails."""

    pass


class GoogleSheetsManager:
    """Manages authenticated connections to Google Sheets API."""

    def __init__(
        self,
        service_account_file: str | None = None,
        service_account_json: str | None = None,
        client: gspread.Client | None = None,
    ) -> None:
        self.settings = get_settings()
        self.service_account_file = service_account_file or self.settings.GOOGLE_SERVICE_ACCOUNT_FILE
        self.service_account_json = service_account_json or self.settings.GOOGLE_SERVICE_ACCOUNT_JSON
        self._client: gspread.Client | None = client

    @retry()
    def get_client(self) -> gspread.Client:
        """Obtain an authenticated gspread Client instance."""
        if self._client:
            return self._client

        creds = self._resolve_credentials()
        self._client = gspread.authorize(creds)
        logger.info("Successfully authenticated with Google Sheets API.")
        return self._client

    def _resolve_credentials(self) -> Credentials:
        """Resolve Google Service Account credentials from JSON string or file path."""
        # 1. From raw JSON string
        if self.service_account_json:
            try:
                info: dict[str, Any] = json.loads(self.service_account_json)
                return Credentials.from_service_account_info(info, scopes=SCOPES)
            except Exception as e:
                raise GoogleSheetsAuthError(f"Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: {e}") from e

        # 2. From file path
        if self.service_account_file:
            path = self.service_account_file
            if not os.path.isabs(path):
                # Resolve relative to project root
                path = os.path.abspath(path)

            if not os.path.exists(path):
                raise GoogleSheetsAuthError(
                    f"Service account file not found at '{path}'. "
                    "Please place your Google Cloud service account JSON key in credentials/service_account.json "
                    "or set GOOGLE_SERVICE_ACCOUNT_FILE in .env."
                )

            try:
                return Credentials.from_service_account_file(path, scopes=SCOPES)
            except Exception as e:
                raise GoogleSheetsAuthError(f"Failed to load credentials from '{path}': {e}") from e

        raise GoogleSheetsAuthError(
            "No Google credentials provided. Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON in .env."
        )
