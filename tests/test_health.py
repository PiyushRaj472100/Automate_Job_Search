"""Tests for the health check and root endpoints."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


def test_health_endpoint_contract(client: TestClient):
    """Verify GET /health returns HTTP 200 and conforms to HealthResponse schema."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["project"] == "Personal Job Intelligence Platform"
    assert data["environment"] == "test"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data

    # Verify timestamp is valid ISO format
    parsed_time = datetime.fromisoformat(data["timestamp"])
    assert parsed_time is not None


def test_api_v1_health_endpoint(client: TestClient):
    """Verify GET /api/v1/health is also reachable and returns identical status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"


def test_root_endpoint(client: TestClient):
    """Verify GET / returns online status and pointers to docs and health."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "online"
    assert data["health_url"] == "/health"
    assert data["docs_url"] == "/docs"


@pytest.mark.asyncio
async def test_health_endpoint_async(async_client: AsyncClient):
    """Verify asynchronous HTTP client can query /health successfully."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
