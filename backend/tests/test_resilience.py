from backend.core.resilience import CircuitBreaker
from backend.services.resume_service import build_profile


def test_breaker_opens():
    b = CircuitBreaker(threshold=2, cooldown=100)
    b.failure("x"); assert not b.open
    b.failure("x"); assert b.open
    b.success(); assert not b.open


def test_profile_no_invention():
    p = build_profile("I know Python and FastAPI.")
    assert p["skills"] == ["Python", "FastAPI"]
