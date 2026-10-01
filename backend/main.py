"""FastAPI Application Entrypoint for Personal Job Intelligence Platform."""

import time
import uuid
import signal
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.router import api_router
from backend.api.routes.health import router as health_router
from backend.core.config import get_settings
from backend.core.logging import get_logger, setup_logging

settings = get_settings()

# Setup logging immediately on module load
setup_logging(
    log_level=settings.LOG_LEVEL,
    json_format=(settings.ENVIRONMENT == "production"),
)
logger = get_logger("job_intelligence.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown events."""
    logger.info(
        "Starting %s [env=%s, debug=%s]",
        settings.PROJECT_NAME,
        settings.ENVIRONMENT,
        settings.DEBUG,
    )
    yield
    logger.info("Shutting down %s", settings.PROJECT_NAME)


def create_application() -> FastAPI:
    """Application factory for FastAPI service."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description="Engineering contract and foundation for Personal Job Intelligence Platform.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Request logging and execution timing middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        # Assign a unique request ID for tracing
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            process_time_ms = (time.perf_counter() - start_time) * 1000.0
            logger.exception(
                "%s %s - id=%s status=500 duration=%.2fms error=%s",
                request.method,
                request.url.path,
                request_id,
                process_time_ms,
                exc,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal Server Error",
                    "request_id": request_id,
                    "error": str(exc) if settings.DEBUG else "An unexpected error occurred",
                },
            )

        process_time_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "%s %s - id=%s status=%s duration=%.2fms",
            request.method,
            request.url.path,
            request_id,
            response.status_code,
            process_time_ms,
        )
        return response

    # Cross-Origin Resource Sharing (CORS) Middleware
    # Added AFTER @app.middleware to ensure it wraps around all responses (including errors)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Mount direct routes at root level: GET /health, /resumes, /resumes/{id}/sheets
    app.include_router(health_router)
    from backend.api.routes.discovery import router as discovery_router
    from backend.api.routes.resumes import router as resumes_router
    from backend.api.routes.sheets import router as sheets_router

    app.include_router(resumes_router)
    app.include_router(sheets_router)
    app.include_router(discovery_router)

    # Mount versioned API routes: /api/v1/...
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)



    @app.get("/", include_in_schema=False)
    async def root():
        """Root landing endpoint with system status overview."""
        return JSONResponse(
            content={
                "project": settings.PROJECT_NAME,
                "environment": settings.ENVIRONMENT,
                "status": "online",
                "health_url": "/health",
                "docs_url": "/docs",
            }
        )

    return app


app = create_application()

# Set up signal handlers for graceful shutdown
def _handle_signal(sig_num, frame):
    logger.info("Received signal %s, initiating graceful shutdown.", sig_num)
    # If any background scheduler is running, it should be stopped here.
    # Placeholder: schedule stop logic can be added when scheduler instance is accessible.
    # Exiting the process will trigger FastAPI lifespan shutdown.
    import sys
    sys.exit(0)

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)
