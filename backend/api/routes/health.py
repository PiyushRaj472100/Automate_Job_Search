from datetime import datetime, timezone
from fastapi import APIRouter, Response
from sqlalchemy import text
from backend.core.config import get_settings
from backend.db.database import engine

router = APIRouter()
STATE = {"total_runs": 0, "failed_runs": 0, "last_successful_run": None, "last_failed_run": None}


@router.get("/health")
async def health():
    s = get_settings()
    return {"status": "ok", "project": s.PROJECT_NAME, "environment": s.ENVIRONMENT,
            "version": s.VERSION, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/ready")
async def ready(response: Response):
    details = {}
    try:
        async with engine.connect() as c:
            await c.execute(text("SELECT 1"))
        details["database"] = "ok"
    except Exception as e:
        details["database"] = f"error: {type(e).__name__}"
    try:
        from backend.services.sheets_service import get_gspread_client
        client = get_gspread_client()
        details["google_sheets"] = "ok" if client is not None else "not_configured"
    except Exception as e:
        details["google_sheets"] = f"error: {type(e).__name__}"
    ok = details["database"] == "ok"
    if not ok:
        response.status_code = 503
    return {"ready": ok, "details": details}


@router.get("/metrics")
async def metrics():
    return {**STATE, "timestamp": datetime.now(timezone.utc).isoformat()}
