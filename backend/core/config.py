"""Configuration management for Job Intelligence Platform."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core Application
    PROJECT_NAME: str = Field(
        default="Personal Job Intelligence Platform",
        description="Name of the application service",
    )
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment mode: development | staging | production",
    )
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode and verbose output",
    )
    API_V1_PREFIX: str = Field(
        default="/api/v1",
        description="Prefix for API version 1 routes",
    )
    HOST: str = Field(
        default="0.0.0.0",
        description="Host interface to bind server to",
    )
    PORT: int = Field(
        default=8000,
        description="Port for application HTTP server",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="Comma-separated list of allowed CORS origins",
    )

    # Database Settings (PostgreSQL System of Record)
    POSTGRES_SERVER: str = Field(default="127.0.0.1", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5433, description="PostgreSQL port")
    POSTGRES_DB: str = Field(default="job_intelligence", description="PostgreSQL database name")
    POSTGRES_USER: str = Field(default="postgres", description="PostgreSQL user")
    POSTGRES_PASSWORD: str = Field(default="", description="PostgreSQL password")
    DATABASE_URL: str | None = Field(
        default=None,
        description="Async PostgreSQL connection string (postgresql+asyncpg://...)",
    )
    SYNC_DATABASE_URL: str | None = Field(
        default=None,
        description="Sync PostgreSQL connection string for Alembic/psycopg2",
    )
    GEMINI_API_KEY: str | None = Field(
        default=None,
        description="Google Gemini API key for matching & extraction (Planned for Phase 3)",
    )
    GOOGLE_SHEETS_SPREADSHEET_ID: str | None = Field(
        default=None,
        description="Target Google Sheets ID for operational reporting (Planned for Phase 5)",
    )

    @property
    def database_url_async(self) -> str:
        """Resolve async database connection string."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        pwd = f":{self.POSTGRES_PASSWORD}" if self.POSTGRES_PASSWORD else ""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}{pwd}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def database_url_sync(self) -> str:
        """Resolve sync database connection string for Alembic and testing."""
        if self.SYNC_DATABASE_URL:
            return self.SYNC_DATABASE_URL
        if self.DATABASE_URL:
            return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        pwd = f":{self.POSTGRES_PASSWORD}" if self.POSTGRES_PASSWORD else ""
        return f"postgresql+psycopg2://{self.POSTGRES_USER}{pwd}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def cors_origins_list(self) -> list[str]:

        """Parse comma-separated CORS origins into a list of strings."""
        if not self.CORS_ORIGINS:
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
