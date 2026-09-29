import base64
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.config import Settings
from backend.db.database import get_session
from backend.db.models import Resume, SheetLink
from backend.services.sheets_service import (
    _parse_service_account_dict,
    get_service_account_info,
    get_service_account_email,
    get_gspread_client,
    create_or_get_spreadsheet,
)


SAMPLE_SA = {
    "type": "service_account",
    "project_id": "test-project-123",
    "private_key_id": "abc123keyid",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC40xaIQY3+aL7y\n-----END PRIVATE KEY-----\n",
    "client_email": "test-sa@test-project-123.iam.gserviceaccount.com",
    "client_id": "112233445566",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def test_parse_raw_json():
    raw = json.dumps(SAMPLE_SA)
    parsed = _parse_service_account_dict(raw)
    assert parsed["client_email"] == SAMPLE_SA["client_email"]
    assert parsed["project_id"] == "test-project-123"


def test_parse_base64_encoded_json():
    raw = json.dumps(SAMPLE_SA)
    b64 = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    parsed = _parse_service_account_dict(b64)
    assert parsed["client_email"] == SAMPLE_SA["client_email"]


def test_parse_quoted_string():
    raw = f"'{json.dumps(SAMPLE_SA)}'"
    parsed = _parse_service_account_dict(raw)
    assert parsed["client_email"] == SAMPLE_SA["client_email"]

    raw2 = f'"{json.dumps(SAMPLE_SA)}"'
    parsed2 = _parse_service_account_dict(raw2)
    assert parsed2["client_email"] == SAMPLE_SA["client_email"]


def test_parse_escaped_newlines_in_private_key():
    sa_escaped = dict(SAMPLE_SA)
    sa_escaped["private_key"] = sa_escaped["private_key"].replace("\n", "\\n")
    raw = json.dumps(sa_escaped)
    parsed = _parse_service_account_dict(raw)
    assert "\n" in parsed["private_key"]
    assert "\\n" not in parsed["private_key"]


def test_parse_missing_fields_raises_clear_error():
    incomplete = {"type": "service_account", "client_email": "test@example.com"}
    with pytest.raises(ValueError, match="missing required fields.*token_uri.*private_key"):
        _parse_service_account_dict(json.dumps(incomplete))


def test_parse_empty_string_raises():
    with pytest.raises(ValueError, match="empty"):
        _parse_service_account_dict("")


def test_get_service_account_info_from_json_env():
    fake_settings = Settings(
        DATABASE_URL="postgresql+asyncpg://pjip:pjip@localhost:5432/pjip",
        GOOGLE_SERVICE_ACCOUNT_JSON=json.dumps(SAMPLE_SA),
    )
    with patch("backend.services.sheets_service.get_settings", return_value=fake_settings):
        info, err = get_service_account_info()
        assert err is None
        assert info["client_email"] == SAMPLE_SA["client_email"]


def test_get_service_account_info_file_fallback_to_json():
    fake_settings = Settings(
        DATABASE_URL="postgresql+asyncpg://pjip:pjip@localhost:5432/pjip",
        GOOGLE_SERVICE_ACCOUNT_FILE="backend/credentials/missing_file.json",
        GOOGLE_SERVICE_ACCOUNT_JSON=json.dumps(SAMPLE_SA),
    )
    with patch("backend.services.sheets_service.get_settings", return_value=fake_settings):
        info, err = get_service_account_info()
        assert err is None
        assert info["client_email"] == SAMPLE_SA["client_email"]


def test_get_service_account_info_missing_credentials():
    fake_settings = Settings(
        DATABASE_URL="postgresql+asyncpg://pjip:pjip@localhost:5432/pjip",
        GOOGLE_SERVICE_ACCOUNT_FILE="",
        GOOGLE_SERVICE_ACCOUNT_JSON="",
    )
    with patch("backend.services.sheets_service.get_settings", return_value=fake_settings), \
         patch.object(Path, "is_file", return_value=False):
        info, err = get_service_account_info()
        assert info is None
        assert "Google Service Account credentials are not configured" in err
        assert "GOOGLE_SERVICE_ACCOUNT_JSON" in err
        assert "GOOGLE_SERVICE_ACCOUNT_FILE" in err


def test_get_service_account_email():
    with patch("backend.services.sheets_service.get_service_account_info", return_value=(SAMPLE_SA, None)):
        email = get_service_account_email()
        assert email == SAMPLE_SA["client_email"]

    with patch("backend.services.sheets_service.get_service_account_info", return_value=(None, "Not configured")):
        email = get_service_account_email()
        assert email == ""


def test_create_or_get_spreadsheet_unconfigured_error():
    with patch("backend.services.sheets_service.get_service_account_info", return_value=(None, "Credentials missing")):
        with pytest.raises(ValueError, match="Credentials missing"):
            create_or_get_spreadsheet("res-1", "resume.pdf", "https://docs.google.com/spreadsheets/d/123")


def test_create_or_get_spreadsheet_unshared_error():
    mock_client = MagicMock()
    mock_client.open_by_key.side_effect = Exception("403 Forbidden: Caller does not have permission")
    mock_client.open_by_url.side_effect = Exception("403 Forbidden")
    mock_client.list_spreadsheet_files.return_value = []

    with patch("backend.services.sheets_service.get_service_account_info", return_value=(SAMPLE_SA, None)), \
         patch("backend.services.sheets_service.get_gspread_client", return_value=mock_client):
        with pytest.raises(ValueError) as excinfo:
            create_or_get_spreadsheet("res-1", "resume.pdf", "https://docs.google.com/spreadsheets/d/test-sheet-id")
        msg = str(excinfo.value)
        assert "Could not access your Google Sheet" in msg
        assert SAMPLE_SA["client_email"] in msg
        assert "Added 'test-sa@test-project-123.iam.gserviceaccount.com' as 'Editor'" in msg


@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock()
    fake_resume = Resume(
        id="35f4c62c8266473f9eb6850b6720840a",
        filename="test_resume.pdf",
        raw_text="Test resume text",
    )
    mock_session.get.return_value = fake_resume

    fake_result = MagicMock()
    fake_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = fake_result

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    yield mock_session
    app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_connect_sheet_api_flow_invalid_url(mock_db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/resumes/35f4c62c8266473f9eb6850b6720840a/connect-sheet", json={"spreadsheet_url": "invalid_url"})
        assert resp.status_code == 400
        assert "valid Google Sheet URL starting with https://" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_connect_sheet_api_flow_missing_creds(mock_db_session):
    with patch("backend.services.sheets_service.get_service_account_info", return_value=(None, "Google Service Account credentials are not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON.")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/resumes/35f4c62c8266473f9eb6850b6720840a/connect-sheet",
                json={"spreadsheet_url": "https://docs.google.com/spreadsheets/d/123/edit"}
            )
            assert resp.status_code == 400
            assert "Google Service Account credentials are not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_connect_sheet_api_flow_success(mock_db_session):
    fake_sheet_data = {
        "spreadsheet_id": "test_sheet_id_abc",
        "spreadsheet_url": "https://docs.google.com/spreadsheets/d/test_sheet_id_abc",
    }
    with patch("backend.services.sheets_service.create_or_get_spreadsheet", return_value=fake_sheet_data), \
         patch("backend.services.job_hunter.hunt_jobs_for_resume", return_value={"status": "ok"}):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/resumes/35f4c62c8266473f9eb6850b6720840a/connect-sheet",
                json={"spreadsheet_url": "https://docs.google.com/spreadsheets/d/test_sheet_id_abc/edit"}
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["spreadsheet_id"] == "test_sheet_id_abc"
            assert body["spreadsheet_url"] == "https://docs.google.com/spreadsheets/d/test_sheet_id_abc"
            assert body["sync_status"] == "SYNCED"
            assert "Google Sheet connected successfully!" in body["message"]
