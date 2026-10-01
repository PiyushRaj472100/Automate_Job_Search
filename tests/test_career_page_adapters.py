"""Unit tests for Greenhouse and Lever direct career page ATS adapters."""

from unittest.mock import MagicMock, patch

import pytest

from backend.discovery.adapters.greenhouse import GreenhouseAdapter
from backend.discovery.adapters.lever import LeverAdapter
from backend.discovery.models import SearchQuery


class TestGreenhouseAdapter:
    """Verifies Greenhouse ATS public career board adapter."""

    def test_search_filters_senior_and_matches_role(self):
        adapter = GreenhouseAdapter(target_companies=["stripe"])

        mock_jobs_payload = {
            "jobs": [
                {
                    "id": 1001,
                    "title": "Software Engineer, Early Career",
                    "location": {"name": "San Francisco, CA / Remote"},
                    "updated_at": "2026-09-01T12:00:00Z",
                    "absolute_url": "https://boards.greenhouse.io/stripe/jobs/1001",
                    "content": "<p>Looking for a backend engineer with Python or Go skills.</p>",
                },
                {
                    "id": 1002,
                    "title": "Senior Staff Backend Architect",
                    "location": {"name": "Remote"},
                    "updated_at": "2026-09-01T12:00:00Z",
                    "absolute_url": "https://boards.greenhouse.io/stripe/jobs/1002",
                    "content": "<p>10+ years of distributed systems experience.</p>",
                },
                {
                    "id": 1003,
                    "title": "Software Engineer II - Payments",
                    "location": {"name": "Remote"},
                    "updated_at": "2026-09-01T12:00:00Z",
                    "absolute_url": "https://boards.greenhouse.io/stripe/jobs/1003",
                    "content": "<p>Mid level payment engineers.</p>",
                },
            ]
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_jobs_payload

        with patch("httpx.Client.get", return_value=mock_resp):
            query = SearchQuery(
                query_text="Software Engineer Python",
                role_title="Software Engineer",
                skills=["Python"],
                limit=10,
            )
            results = adapter.search(query)

        # Senior and Software Engineer II roles must be filtered out!
        assert len(results) == 1
        assert results[0].title == "Software Engineer, Early Career"
        assert results[0].company_name == "Stripe"
        assert results[0].source_name == "greenhouse"
        assert results[0].job_url == "https://boards.greenhouse.io/stripe/jobs/1001"
        assert results[0].work_mode == "remote"

    def test_health_check_success(self):
        adapter = GreenhouseAdapter(target_companies=["stripe"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.Client.get", return_value=mock_resp):
            hc = adapter.health_check()
            assert hc.is_healthy is True
            assert hc.status_code == 200


class TestLeverAdapter:
    """Verifies Lever ATS public career postings adapter."""

    def test_search_filters_senior_and_extracts_postings(self):
        adapter = LeverAdapter(target_companies=["spotify"])

        mock_postings = [
            {
                "id": "lev-abc-123",
                "text": "Junior Software Engineer - Music Personalization",
                "categories": {"location": "Remote", "commitment": "Full-time"},
                "createdAt": 1727784000000,
                "hostedUrl": "https://jobs.lever.co/spotify/lev-abc-123",
                "applyUrl": "https://jobs.lever.co/spotify/lev-abc-123/apply",
                "descriptionPlain": "Build recommendations using Python and event streams.",
            },
            {
                "id": "lev-def-456",
                "text": "Senior Engineering Lead",
                "categories": {"location": "New York", "commitment": "Full-time"},
                "createdAt": 1727784000000,
                "hostedUrl": "https://jobs.lever.co/spotify/lev-def-456",
                "applyUrl": "https://jobs.lever.co/spotify/lev-def-456/apply",
                "descriptionPlain": "Lead 8+ engineers.",
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_postings

        with patch("httpx.Client.get", return_value=mock_resp):
            query = SearchQuery(
                query_text="Junior Software Engineer",
                role_title="Software Engineer",
                skills=["Python"],
                limit=10,
            )
            results = adapter.search(query)

        # Senior lead role must be filtered out
        assert len(results) == 1
        assert results[0].title == "Junior Software Engineer - Music Personalization"
        assert results[0].company_name == "Spotify"
        assert results[0].source_name == "lever"
        assert results[0].job_url == "https://jobs.lever.co/spotify/lev-abc-123"
        assert results[0].application_url == "https://jobs.lever.co/spotify/lev-abc-123/apply"

    def test_health_check_success(self):
        adapter = LeverAdapter(target_companies=["spotify"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.Client.get", return_value=mock_resp):
            hc = adapter.health_check()
            assert hc.is_healthy is True
            assert hc.status_code == 200
