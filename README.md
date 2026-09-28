# Personal Job Intelligence Platform (scaffold)

Run locally:
    cp .env.example .env
    docker compose up -d db
    pip install -r backend/requirements.txt
    uvicorn backend.main:app --reload --port 8001
    cd frontend && cp .env.example .env && npm install && npm run dev   # http://localhost:3000

Put the master prompt in docs/MASTER_PROMPT.md and give it to Antigravity to continue building.

## Status (honest)
IMPLEMENTED + smoke-tested: config fail-fast (no SQLite), /health /ready /metrics (+/api/v1 prefix),
resume upload (PDF/DOCX, SHA-256 duplicate detection, deterministic skill extraction), resume list/detail/profile,
DB-down returns 503 (never []), source adapter base + Arbeitnow public-API adapter, retry with backoff,
circuit breaker, query generation, discovery search, frontend shell (Resumes, Discovery, System pages, typed API client).
Frontend builds (tsc + vite). Not tested against a live PostgreSQL or live Arbeitnow.

NOT IMPLEMENTED: Alembic migrations (uses create_all in dev), Gemini, Google Sheets, job persistence/dedup,
URL verification, matching / Missing-Improve, recruiter discovery, application tracking, scheduler,
morning verification, backups, dashboard/jobs/recruiters/applications pages, Prometheus metrics, most tests.
