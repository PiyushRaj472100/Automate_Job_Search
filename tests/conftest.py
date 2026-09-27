"""Pytest fixtures for API and component testing."""

from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.db.session import sync_engine
from backend.main import create_application


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Provide isolated settings for the test session."""
    return Settings(
        ENVIRONMENT="test",
        DEBUG=True,
        LOG_LEVEL="WARNING",
    )


@pytest.fixture(scope="session")
def client(test_settings: Settings) -> Generator[TestClient, None, None]:
    """Provide synchronous TestClient instance."""
    app = create_application()
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app=app, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture
async def async_client(test_settings: Settings) -> AsyncGenerator[AsyncClient, None]:
    """Provide asynchronous HTTP client."""
    app = create_application()
    app.dependency_overrides[get_settings] = lambda: test_settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an isolated database session that rolls back changes after each test."""
    connection = sync_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()

