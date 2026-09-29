import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from backend.core.config import get_settings
from backend.core.logging import setup_logging
from backend.db.database import Base, engine
from backend.api.routes import (
    health, resumes, discovery, dashboard, jobs, recruiters, applications, settings as settings_route, referrals
)

s = get_settings()  # fails fast if DATABASE_URL is missing
setup_logging(s.LOG_LEVEL)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app):
    try:
        async with engine.begin() as conn:
            import backend.db.models  # noqa: F401
            await conn.run_sync(Base.metadata.create_all)
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
            await conn.execute(text("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS last_hunted_at TIMESTAMPTZ;"))
            await conn.execute(text("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS hunt_count INTEGER DEFAULT 0;"))
            log.info("Database connection verified and tables initialized successfully.")
    except Exception as e:
        log.error("database unavailable at startup: %s", type(e).__name__)

    import asyncio
    from backend.services.job_hunter import run_periodic_sweep
    sweep_task = asyncio.create_task(run_periodic_sweep())

    yield

    sweep_task.cancel()
    await engine.dispose()



app = FastAPI(title=s.PROJECT_NAME, version=s.VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": s.PROJECT_NAME,
        "version": s.VERSION,
        "docs_url": "/docs",
        "health_check": "/health",
    }


@app.exception_handler(SQLAlchemyError)
@app.exception_handler(OSError)
async def db_down(request: Request, exc: Exception):
    log.error("database failure: %s", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


for prefix in ("", s.API_V1_PREFIX):
    app.include_router(health.router, prefix=prefix)
    app.include_router(resumes.router, prefix=prefix)
    app.include_router(discovery.router, prefix=prefix)
    app.include_router(dashboard.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(recruiters.router, prefix=prefix)
    app.include_router(applications.router, prefix=prefix)
    app.include_router(settings_route.router, prefix=prefix)
    app.include_router(referrals.router, prefix=prefix)
