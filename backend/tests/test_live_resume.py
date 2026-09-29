import pytest
from datetime import datetime, timezone, timedelta
from backend.services.job_hunter import calculate_freshness_score, is_suitable_job


def test_calculate_freshness_score():
    now = datetime.now(timezone.utc)

    # 1. Past 24h
    score_24h, label_24h = calculate_freshness_score(now - timedelta(hours=3), now)
    assert score_24h == 100
    assert "Past 24 Hours" in label_24h

    # 2. 1-7 days
    score_3d, label_3d = calculate_freshness_score(now - timedelta(days=3), now)
    assert score_3d == 75
    assert "1-7d" in label_3d

    # 3. 8-15 days
    score_10d, label_10d = calculate_freshness_score(now - timedelta(days=10), now)
    assert score_10d == 50
    assert "8-15d" in label_10d

    # 4. 16-30 days
    score_20d, label_20d = calculate_freshness_score(now - timedelta(days=20), now)
    assert score_20d == 25
    assert "16-30d" in label_20d

    # 5. 31-60 days
    score_45d, label_45d = calculate_freshness_score(now - timedelta(days=45), now)
    assert score_45d == 10
    assert "31-60d" in label_45d

    # 6. >60 days: rejected
    score_70d, label_70d = calculate_freshness_score(now - timedelta(days=70), now)
    assert score_70d == -1
    assert "Stale" in label_70d


def test_is_suitable_job_resume_matching():
    # Junior AI Engineer in Bangalore with 0-2 yrs -> Suitable
    suitable, score = is_suitable_job(
        title="Junior AI Engineer",
        description="Looking for freshers or 0-1 years experience with Python and machine learning.",
        location="Bengaluru, Karnataka, India",
        resume_skills={"python", "machine learning", "fastapi"},
    )
    assert suitable is True
    assert score >= 100

    # Senior / 5+ years experience -> Strictly rejected
    suitable_sr, _ = is_suitable_job(
        title="Senior Python Architect",
        description="Requires at least 5+ years of experience in enterprise systems.",
        location="Bengaluru, India",
    )
    assert suitable_sr is False

    # Forbidden domain (flutter/react frontend) -> Strictly rejected
    suitable_fe, _ = is_suitable_job(
        title="React Flutter Frontend Developer Intern",
        description="Build mobile and web UI using Flutter and React.",
        location="Bengaluru, India",
    )
    assert suitable_fe is False
