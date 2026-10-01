"""Test CORS middleware and health/metrics endpoints."""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_cors_headers_on_health_from_frontend_port_3001():
    response = client.get("/health", headers={"Origin": "http://localhost:3001"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_headers_on_metrics_from_frontend_port_3001():
    response = client.get("/metrics", headers={"Origin": "http://localhost:3001"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"
    assert "total_runs" in response.json()


def test_cors_headers_on_resumes_from_frontend_port_3001():
    response = client.get("/resumes", headers={"Origin": "http://localhost:3001"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"
    assert isinstance(response.json(), list)


def test_cors_preflight_options_request():
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"
    assert "GET" in response.headers.get("access-control-allow-methods", "")
