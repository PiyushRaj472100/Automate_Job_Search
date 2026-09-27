"""FastAPI Application Entrypoint for Personal Job Intelligence Platform."""

import time
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

    # Cross-Origin Resource Sharing (CORS) Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging and execution timing middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "%s %s - status=%s duration=%.2fms",
            request.method,
            request.url.path,
            response.status_code,
            process_time_ms,
        )
        return response

    # Mount direct health route at root level: GET /health
    app.include_router(health_router)

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
