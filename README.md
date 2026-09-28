# Personal Job Intelligence Platform

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Architecture: Clean](https://img.shields.io/badge/architecture-modular-orange.svg)]()

> A personal, high-precision intelligence platform that discovers, verifies, matches, and surfaces 0–2 year technical job openings and recruiter contacts.

---

## ⚠️ Important Operating Principles

1. **Strictly Manual Applications**: The system **NEVER** automatically submits job applications. The user applies manually.
2. **Accuracy Over Volume**: Deterministic verification over fabricated volume.
3. **Zero AI Hallucination for URLs**: AI is never the source of truth for URL or listing verification.
4. **PostgreSQL as System of Record**: All state, matches, and audit trails live in PostgreSQL. Google Sheets acts solely as the operational dashboard.

For the complete list of 16 engineering rules, review [docs/ENGINEERING_CONTRACT.md](docs/ENGINEERING_CONTRACT.md).

---

## Project Structure

```
Automate_Job_Finder/
├── .dockerignore                 # Docker build exclusions
├── .env.example                  # Environment configuration template
├── .gitignore                    # Git version control exclusions
├── Dockerfile                    # Production container build
├── docker-compose.yml            # Local development compose (API + PostgreSQL/pgvector)
├── pyproject.toml                # Project metadata, pytest, and ruff configs
├── requirements.txt              # Production Python dependencies
├── requirements-dev.txt          # Development, linting, and testing dependencies
├── README.md                     # Project overview and local quickstart
├── docs/
│   ├── ARCHITECTURE.md           # System blueprint, component layers, phase roadmap
│   └── ENGINEERING_CONTRACT.md   # Core engineering rules & constraints
├── scripts/
│   ├── run_dev.ps1               # PowerShell helper to start dev server
│   ├── run_dev.sh                # Bash helper to start dev server
│   ├── run_tests.ps1             # PowerShell helper to run test suite
│   └── run_tests.sh              # Bash helper to run test suite
├── backend/
│   ├── __init__.py               # Backend package indicator
│   ├── main.py                   # FastAPI app factory, lifespan, and middlewares
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py             # Type-safe pydantic-settings configuration
│   │   └── logging.py            # Centralized structured/standard logging
│   └── api/
│       ├── __init__.py
│       ├── router.py             # Top-level API router aggregator
│       └── routes/
│           ├── __init__.py
│           └── health.py         # GET /health probe and Pydantic schema
└── tests/
    ├── __init__.py
    ├── conftest.py               # TestClient and AsyncClient fixtures
    └── test_health.py            # Health probe contract tests
```

---

## Quickstart: Local Development

### 1. Prerequisites
- Python 3.12+
- Git

### 2. Setup Virtual Environment
```bash
# Clone or navigate to the workspace
cd Automate_Job_Finder

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
```

### 4. Start the Application

Using helper scripts:
```powershell
# Windows (PowerShell)
.\scripts\run_dev.ps1

# Linux / macOS
./scripts/run_dev.sh
```

Or run directly with `uvicorn`:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

The server will start at `http://localhost:8000`.

- Interactive API Docs (Swagger): `http://localhost:8000/docs`
- Alternative API Docs (ReDoc): `http://localhost:8000/redoc`
- Health Probe: `http://localhost:8000/health`

---

## Running with Docker Compose

To run the application alongside a local PostgreSQL 16 database equipped with `pgvector`:

```bash
docker compose up --build
```

---

## Health Check Endpoint

### `GET /health`

**Response Status**: `200 OK`

**Sample Response Body**:
```json
{
  "status": "ok",
  "project": "Personal Job Intelligence Platform",
  "environment": "development",
  "version": "0.1.0",
  "timestamp": "2026-09-28T05:08:42.123456Z"
}
```

---

## Database Migrations (PostgreSQL)

Run migrations to create or update the normalized schema:
```powershell
# Windows (PowerShell)
.\scripts\run_migrations.ps1

# Or via Alembic CLI
alembic upgrade head
```
```bash
# Linux / macOS
./scripts/run_migrations.sh
```

---

## Google Sheets Integration (Dashboard per Resume)

Every resume profile automatically maps to its own dedicated 5-tab Google Sheet (`Dashboard`, `Jobs`, `Recruiters`, `Applications`, `System Status`), with exact 27-column job headers.

To configure Google Sheets and verify live connectivity:
1. Review setup guide: [docs/GOOGLE_SHEETS_SETUP.md](docs/GOOGLE_SHEETS_SETUP.md)
2. Place your service account JSON in `credentials/service_account.json`
3. Run the live verification utility:
   ```bash
   python scripts/verify_sheets.py
   ```

---

## Running Tests and Linting

### Running Pytest
```bash
# Using helper script
.\scripts\run_tests.ps1   # Windows
./scripts/run_tests.sh    # Linux/macOS

# Or directly via pytest
pytest -v
```

### Running Linter & Formatter
```bash
ruff check .
```

---

## Phase Roadmap

- [x] **Phase 0: Foundation & Engineering Contract** *(Completed)*
- [x] **Phase 1: System of Record & Database Schemas** *(Completed)*
- [x] **Phase 2: Multi-Resume Profile Ingestion** *(Completed)*
- [x] **Sheets Integration: Google Sheets Dashboard per Resume** *(Completed)*
- [ ] **Phase 3: Source Discovery & Collector Framework**
- [ ] **Phase 4: Gemini Matching & Deterministic Verification**
- [ ] **Phase 5: Public Recruiter Discovery & Contact Verification**
- [ ] **Phase 6: Cloud Deployment & Daily Morning Orchestration**


