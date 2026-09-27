# System Architecture

## 1. System Vision

The **Personal Job Intelligence Platform** is an automated, high-precision intelligence engine designed to discover, verify, match, and present relevant technical entry-level / fresher (0–2 years) job opportunities and verified recruiter contacts.

The platform serves as an operational copilot for manual applications: **it never applies automatically**.

---

## 2. Architectural Blueprint

```
+-----------------------------------------------------------------------------------+
|                                  USER / OPERATOR                                  |
|                 (Reviews dashboard, selects jobs, applies manually)               |
+-----------------------------------------+-----------------------------------------+
                                          ^
                                          |
               +--------------------------+--------------------------+
               |                                                     |
+--------------+---------------+                     +---------------+---------------+
|       GOOGLE SHEETS           |                     |       FASTAPI REST API        |
|  (Operational UI / Sheets)    |                     |   (Monitoring, APIs, Admin)   |
+--------------^---------------+                     +---------------+---------------+
               |                                                     |
               +--------------------------+--------------------------+
                                          |
                      +-------------------+-------------------+
                      |         ORCHESTRATION ENGINE          |
                      |   (Cloud Scheduler / Periodic Jobs)   |
                      +-------------------+-------------------+
                                          |
         +--------------------------------+--------------------------------+
         |                                |                                |
+--------v---------+             +--------v---------+             +--------v---------+
|   DISCOVERY &    |             |  AI RESUME &     |             |  HTTP LIVENESS & |
| EXTRACTION ENGINE|             |  JOB MATCHING    |             |  VERIFIER ENGINE |
| (Legal Scrapers, |             | (Google Gemini,  |             |  (Deterministic  |
|  Career Pages)   |             |  Pydantic Valid) |             |   Network Probes)|
+--------+---------+             +--------+---------+             +--------+---------+
         |                                |                                |
         +--------------------------------+--------------------------------+
                                          |
                         +----------------v----------------+
                         |       POSTGRESQL SYSTEM         |
                         |           OF RECORD             |
                         |  (Jobs, Profiles, Matches,      |
                         |   Recruiters, Audit Logs)       |
                         +---------------------------------+
```

---

## 3. Core Architectural Layers

### 1. API & Core Infrastructure (`backend/core`, `backend/api`)
- Fast, asynchronous REST API powered by **FastAPI** and **Uvicorn**.
- Type-safe centralized configuration via **pydantic-settings**.
- Structured, observable logging for cloud and local environments.
- Health probes and metrics (`/health`, `/metrics`).

### 2. Multi-Profile Storage (`backend/models`, `backend/db` - Planned Phase 1)
- **PostgreSQL** is the sole system of record.
- Every resume represents an independent profile with distinct match criteria.
- Complete audit trails: source URLs, fetch timestamps, raw job data, and verification histories.

### 3. Source Discovery & Extraction (`backend/discovery` - Planned Phase 3)
- Legal, compliant discovery across legitimate career boards and company career portals.
- Strict adherence to `robots.txt`, no CAPTCHA bypassing, no credential stuffing.

### 4. Deterministic Verification (`backend/verifier` - Planned Phase 4)
- **Zero Hallucination Rule**: LLMs never verify URLs or status.
- Independent HTTP client executes network requests against job URLs and application links.
- Detection of HTTP 404, redirects to expired landing pages, closed status markers.

### 5. AI Reasoning & Extraction (`backend/matching` - Planned Phase 4)
- Powered by **Google Gemini API**.
- Strictly typed Pydantic output schemas (match score, matched skills, missing requirements, reasoning).

### 6. Downstream Projection (`backend/reporting` - Planned Phase 5)
- Automated synchronization to **Google Sheets API**.
- Dedicated tab per resume profile with actionable links and recruiter contact cards.

---

## 4. Phase Rollout Strategy

| Phase | Milestone | Scope | Status |
| :--- | :--- | :--- | :--- |
| **Phase 0** | **Foundation & Contract** | Project scaffolding, FastAPI, logging, config, Docker, tests | **COMPLETED** |
| **Phase 1** | **System of Record** | PostgreSQL schema, Alembic migrations, models, deduplication | **COMPLETED** |
| **Phase 2** | **Resume Ingestion** | Multi-profile parsing, skills extraction, criteria definition | Planned |
| **Phase 3** | **Job Discovery Engine** | Legal collectors, deduplication, URL normalization | Planned |
| **Phase 4** | **Matching & Verification** | Gemini matching, missing skills analysis, HTTP URL verifier | Planned |
| **Phase 5** | **Recruiters & Sheets** | Public recruiter discovery, Google Sheets live sync | Planned |
| **Phase 6** | **Automation & Cloud** | Cloud Run, Cloud Scheduler, daily morning report pipeline | Planned |

