from fastapi import APIRouter, Depends
from pydantic import BaseModel
from backend.core.config import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdateReq(BaseModel):
    google_sheet_url: str | None = None
    gemini_api_key: str | None = None
    share_email: str | None = None


@router.get("")
async def get_current_settings():
    s = get_settings()
    from backend.services.sheets_service import get_service_account_email
    return {
        "project_name": s.PROJECT_NAME,
        "environment": s.ENVIRONMENT,
        "api_v1_prefix": s.API_V1_PREFIX,
        "database_configured": bool(s.DATABASE_URL),
        "google_sheets_configured": bool(s.GOOGLE_SERVICE_ACCOUNT_FILE or s.GOOGLE_SERVICE_ACCOUNT_JSON),
        "service_account_email": get_service_account_email(),
        "google_sheet_url": s.GOOGLE_SHEET_URL,
        "share_email": s.GOOGLE_SHEETS_SHARE_USER_EMAIL,
        "gemini_api_key_configured": bool(s.GEMINI_API_KEY),
        "gemini_model": s.GEMINI_MODEL,
        "version": s.VERSION,
    }


@router.patch("")
async def update_settings(req: SettingsUpdateReq):
    s = get_settings()
    if req.google_sheet_url is not None:
        s.GOOGLE_SHEET_URL = req.google_sheet_url.strip()
    if req.gemini_api_key is not None:
        s.GEMINI_API_KEY = req.gemini_api_key.strip()
    if req.share_email is not None:
        s.GOOGLE_SHEETS_SHARE_USER_EMAIL = req.share_email.strip()

    return {
        "status": "ok",
        "message": "Settings updated successfully",
        "google_sheet_url": s.GOOGLE_SHEET_URL,
    }
