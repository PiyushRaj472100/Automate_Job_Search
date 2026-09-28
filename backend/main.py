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
    health, resumes, discovery, dashboard, jobs, recruiters, applications, settings as settings_route
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
app.add_middleware(CORSMiddleware, allow_origins=s.cors_list, allow_methods=["*"], allow_headers=["*"])


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
