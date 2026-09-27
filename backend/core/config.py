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

    # Future Phase Placeholders (None by default in Phase 0)
    DATABASE_URL: str | None = Field(
        default=None,
        description="PostgreSQL async connection string (Planned for Phase 1)",
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
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list of strings."""
        if not self.CORS_ORIGINS:
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
